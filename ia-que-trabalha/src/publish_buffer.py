from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "content" / "buffer-week1.json"
API_URL = "https://api.buffer.com"


class BufferError(RuntimeError):
    pass


def gql_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


class BufferClient:
    def __init__(self, api_key: str):
        if not api_key.strip():
            raise BufferError("BUFFER_API_KEY ausente")
        self.api_key = api_key.strip()

    def _request(self, query: str) -> dict[str, Any]:
        payload = json.dumps({"query": query}).encode("utf-8")
        req = urllib.request.Request(
            API_URL,
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": "ia-que-trabalha/1.0",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise BufferError(f"Buffer HTTP {exc.code}: {body[:300]}") from exc
        except Exception as exc:
            raise BufferError(f"Falha de rede Buffer: {type(exc).__name__}") from exc

        data = json.loads(raw)
        if data.get("errors"):
            message = str(data["errors"][0].get("message") or "GraphQL error")[:300]
            raise BufferError(f"Buffer GraphQL: {message}")
        return data.get("data") or {}

    def get_organizations(self) -> list[dict[str, Any]]:
        data = self._request(
            """
            query AccountOrganizations {
              account {
                organizations {
                  id
                  name
                }
              }
            }
            """
        )
        return list(((data.get("account") or {}).get("organizations") or []))

    def list_channels(self, organization_id: str) -> list[dict[str, Any]]:
        query = f"""
        query Channels {{
          channels(input: {{ organizationId: {gql_string(organization_id)} }}) {{
            id
            name
            displayName
            service
            externalLink
            isDisconnected
            isLocked
          }}
        }}
        """
        data = self._request(query)
        return list(data.get("channels") or [])

    def list_scheduled(self, organization_id: str, channel_id: str) -> list[dict[str, Any]]:
        query = f"""
        query Scheduled {{
          posts(
            first: 100
            input: {{
              organizationId: {gql_string(organization_id)}
              filter: {{
                status: [scheduled]
                channelIds: [{gql_string(channel_id)}]
              }}
              sort: [{{ field: dueAt, direction: asc }}]
            }}
          ) {{
            edges {{
              node {{
                id
                text
                status
                dueAt
                channelId
                assets {{
                  source
                  mimeType
                }}
                metadata {{
                  ... on InstagramPostMetadata {{
                    type
                    shouldShareToFeed
                    isAiGenerated
                  }}
                }}
              }}
            }}
          }}
        }}
        """
        data = self._request(query)
        return [edge["node"] for edge in (((data.get("posts") or {}).get("edges")) or [])]

    def create_reel(
        self,
        *,
        channel_id: str,
        due_at: str,
        text: str,
        video_url: str,
    ) -> dict[str, Any]:
        query = f"""
        mutation CreateReel {{
          createPost(
            input: {{
              text: {gql_string(text)}
              channelId: {gql_string(channel_id)}
              schedulingType: automatic
              mode: customScheduled
              dueAt: {gql_string(due_at)}
              aiAssisted: true
              assets: [
                {{
                  video: {{
                    url: {gql_string(video_url)}
                  }}
                }}
              ]
              metadata: {{
                instagram: {{
                  type: reel
                  shouldShareToFeed: true
                  isAiGenerated: true
                }}
              }}
            }}
          ) {{
            ... on PostActionSuccess {{
              post {{
                id
                text
                status
                dueAt
                channelId
                assets {{
                  source
                  mimeType
                }}
              }}
            }}
            ... on MutationError {{
              message
            }}
          }}
        }}
        """
        data = self._request(query)
        result = data.get("createPost") or {}
        if result.get("message") and not result.get("post"):
            raise BufferError(f"Buffer createPost: {str(result['message'])[:300]}")
        post = result.get("post")
        if not post:
            raise BufferError("Buffer não retornou post criado")
        return post


def load_manifest() -> list[dict[str, Any]]:
    items = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if not isinstance(items, list) or not items:
        raise BufferError("manifesto Buffer vazio ou inválido")
    return items


def normalize_handle(value: str) -> str:
    return value.strip().lstrip("@").casefold()


def resolve_instagram_channel(
    organizations: list[dict[str, Any]],
    channel_fetcher,
    expected_username: str,
) -> tuple[str, dict[str, Any]]:
    expected = normalize_handle(expected_username)
    if not expected:
        raise BufferError("BUFFER_EXPECTED_USERNAME ausente")

    matches: list[tuple[str, dict[str, Any]]] = []
    for org in organizations:
        org_id = str(org.get("id") or "")
        if not org_id:
            continue
        for channel in channel_fetcher(org_id):
            if str(channel.get("service") or "").casefold() != "instagram":
                continue
            if channel.get("isDisconnected") is True or channel.get("isLocked") is True:
                continue
            candidates = {
                normalize_handle(str(channel.get("name") or "")),
                normalize_handle(str(channel.get("displayName") or "")),
            }
            external = str(channel.get("externalLink") or "").rstrip("/")
            if external:
                candidates.add(normalize_handle(external.rsplit("/", 1)[-1]))
            if expected in candidates:
                matches.append((org_id, channel))

    if len(matches) != 1:
        raise BufferError(
            f"esperado exatamente 1 canal Instagram @{expected}; encontrados={len(matches)}"
        )
    return matches[0]


def utc_iso(value: str) -> str:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise BufferError(f"publish_at sem timezone: {value}")
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def post_matches(item: dict[str, Any], post: dict[str, Any]) -> bool:
    expected_due = utc_iso(str(item["publish_at_local"]))
    actual_due = utc_iso(str(post.get("dueAt") or ""))
    if expected_due != actual_due:
        return False
    expected_url = str(item["media_url"])
    sources = {str(asset.get("source") or "") for asset in (post.get("assets") or [])}
    return expected_url in sources


def schedule_week(client: BufferClient, expected_username: str, now: datetime) -> dict[str, Any]:
    organizations = client.get_organizations()
    if not organizations:
        raise BufferError("conta Buffer sem organização disponível")

    organization_id, channel = resolve_instagram_channel(
        organizations,
        client.list_channels,
        expected_username,
    )
    channel_id = str(channel["id"])
    scheduled = client.list_scheduled(organization_id, channel_id)
    items = load_manifest()

    eligible = [
        item for item in items
        if datetime.fromisoformat(str(item["publish_at_local"])).astimezone(timezone.utc) > now
    ]

    missing_items = [
        item
        for item in eligible
        if not any(post_matches(item, post) for post in scheduled)
    ]
    if len(scheduled) + len(missing_items) > 10:
        raise BufferError(
            "fila gratuita excederia 10 posts agendados por canal: "
            f"existentes={len(scheduled)} novos={len(missing_items)}"
        )

    created: list[dict[str, Any]] = []
    skipped: list[str] = []

    for item in eligible:
        if any(post_matches(item, post) for post in scheduled):
            skipped.append(str(item["id"]))
            continue
        post = client.create_reel(
            channel_id=channel_id,
            due_at=utc_iso(str(item["publish_at_local"])),
            text=str(item["caption"]),
            video_url=str(item["media_url"]),
        )
        created.append({"content_id": item["id"], "post_id": post["id"]})
        scheduled.append(post)

    observed = client.list_scheduled(organization_id, channel_id)
    missing = [
        str(item["id"])
        for item in eligible
        if not any(post_matches(item, post) for post in observed)
    ]
    if missing:
        raise BufferError("readback não confirmou: " + ",".join(missing))

    return {
        "ok": True,
        "organization_id": organization_id,
        "channel_id": channel_id,
        "channel_name": channel.get("displayName") or channel.get("name"),
        "created": created,
        "already_scheduled": skipped,
        "verified_count": len(eligible),
    }


def main() -> int:
    key = os.environ.get("BUFFER_API_KEY", "").strip()
    expected = os.environ.get("BUFFER_EXPECTED_USERNAME", "devtieri").strip()
    if not key:
        print(json.dumps({
            "ok": False,
            "reason": "missing_configuration",
            "missing": ["BUFFER_API_KEY"],
        }, ensure_ascii=False))
        return 2

    try:
        result = schedule_week(
            BufferClient(key),
            expected,
            datetime.now(timezone.utc),
        )
    except BufferError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
