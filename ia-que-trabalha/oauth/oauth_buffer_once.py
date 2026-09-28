from __future__ import annotations

import base64
import hashlib
import http.server
import importlib.util
import json
import os
import re
import secrets
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ROOT = Path(__file__).resolve().parents[1]
PUBLISHER = ROOT / "src" / "publish_buffer.py"
PUBLIC_KEY = ROOT / "oauth" / "relay-public.pem"
HANDOFF = ROOT / "oauth" / "auth-url.enc.json"
TRIGGER = ROOT / "oauth" / "request.json"
BRANCH = "ops/ia-que-trabalha-buffer"

AUTH_BASE = "https://auth.buffer.com"
REGISTER_URL = AUTH_BASE + "/reg"
AUTHORIZE_URL = AUTH_BASE + "/auth"
TOKEN_URL = AUTH_BASE + "/token"
SCOPES = "account:read posts:read posts:write offline_access"


class OAuthError(RuntimeError):
    pass


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def post_json(url: str, payload: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "ia-que-trabalha-buffer-oauth/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise OAuthError(f"HTTP {exc.code} em registro OAuth: {raw[:300]}") from exc
    return json.loads(raw)


def post_form(url: str, values: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(values).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": "ia-que-trabalha-buffer-oauth/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise OAuthError(f"HTTP {exc.code} na troca OAuth: {raw[:300]}") from exc
    return json.loads(raw)


def start_callback_server(port: int):
    state_holder = {"params": None}
    event = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != "/callback":
                self.send_response(404)
                self.end_headers()
                return
            state_holder["params"] = {
                key: values[0]
                for key, values in urllib.parse.parse_qs(parsed.query).items()
                if values
            }
            body = (
                "<html><body><h2>Autorização recebida.</h2>"
                "<p>Você pode fechar esta aba e voltar ao ChatGPT.</p></body></html>"
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            event.set()

        def log_message(self, fmt, *args):
            return

    server = http.server.ThreadingHTTPServer(("0.0.0.0", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, event, state_holder


def start_tunnel(port: int) -> tuple[subprocess.Popen, str]:
    proc = subprocess.Popen(
        [
            "./cloudflared",
            "tunnel",
            "--no-autoupdate",
            "--url",
            f"http://127.0.0.1:{port}",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    deadline = time.time() + 45
    pattern = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
    captured = []
    assert proc.stdout is not None
    while time.time() < deadline:
        line = proc.stdout.readline()
        if line:
            captured.append(line.rstrip())
            match = pattern.search(line)
            if match:
                return proc, match.group(0)
        elif proc.poll() is not None:
            break
        else:
            time.sleep(0.2)
    proc.terminate()
    raise OAuthError("não foi possível criar callback HTTPS temporário do Cloudflare")


def encrypt_handoff(text: str) -> dict:
    public_key = serialization.load_pem_public_key(PUBLIC_KEY.read_bytes())
    aes_key = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)
    ciphertext = AESGCM(aes_key).encrypt(nonce, text.encode("utf-8"), None)
    encrypted_key = public_key.encrypt(
        aes_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return {
        "alg": "RSA-OAEP-SHA256+A256GCM",
        "encrypted_key": base64.b64encode(encrypted_key).decode("ascii"),
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
    }


def persist_encrypted_handoff(payload: dict, correlation_id: str) -> None:
    HANDOFF.parent.mkdir(parents=True, exist_ok=True)
    HANDOFF.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
    subprocess.run(
        ["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"],
        check=True,
    )
    subprocess.run(["git", "add", str(HANDOFF.relative_to(Path.cwd()))], check=True)
    subprocess.run(
        ["git", "commit", "-m", f"chore: publica handoff OAuth criptografado {correlation_id}"],
        check=True,
    )
    subprocess.run(["git", "push", "origin", f"HEAD:{BRANCH}"], check=True)


def load_publisher():
    spec = importlib.util.spec_from_file_location("publish_buffer", PUBLISHER)
    if not spec or not spec.loader:
        raise OAuthError("não foi possível carregar publish_buffer.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    trigger = json.loads(TRIGGER.read_text(encoding="utf-8"))
    correlation_id = str(trigger.get("correlation_id") or "").strip()
    if trigger.get("action") != "oauth-and-schedule-buffer" or not correlation_id:
        raise OAuthError("gatilho inválido")

    port = 8765
    callback_server, callback_event, callback_state = start_callback_server(port)
    tunnel_proc = None
    try:
        tunnel_proc, tunnel_base = start_tunnel(port)
        redirect_uri = tunnel_base.rstrip("/") + "/callback"

        registration = post_json(
            REGISTER_URL,
            {
                "client_name": "IA que Trabalha - sessão efêmera",
                "redirect_uris": [redirect_uri],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "none",
                "scope": SCOPES,
            },
        )
        client_id = str(registration.get("client_id") or "")
        if not client_id:
            raise OAuthError("Buffer não retornou client_id")

        verifier = b64url(secrets.token_bytes(64))
        challenge = b64url(hashlib.sha256(verifier.encode("ascii")).digest())
        state = b64url(secrets.token_bytes(32))
        auth_url = AUTHORIZE_URL + "?" + urllib.parse.urlencode(
            {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": SCOPES,
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "prompt": "consent",
            }
        )

        persist_encrypted_handoff(
            {
                **encrypt_handoff(auth_url),
                "correlation_id": correlation_id,
                "expires_in_seconds": 420,
            },
            correlation_id,
        )
        print("OAUTH_HANDOFF_READY=true")
        print(f"correlation_id={correlation_id}")
        print("authorization_url_logged=false")
        print("token_persisted=false")

        if not callback_event.wait(timeout=420):
            raise OAuthError("autorização não recebida dentro da janela limitada")

        params = callback_state["params"] or {}
        if params.get("error"):
            raise OAuthError("autorização recusada pelo provedor")
        if params.get("state") != state:
            raise OAuthError("state OAuth divergente")
        code = str(params.get("code") or "")
        if not code:
            raise OAuthError("callback sem authorization code")

        token_data = post_form(
            TOKEN_URL,
            {
                "client_id": client_id,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": verifier,
            },
        )
        access_token = str(token_data.get("access_token") or "")
        if not access_token:
            raise OAuthError("Buffer não retornou access_token")

        publisher = load_publisher()
        client = publisher.BufferClient(access_token)
        result = publisher.schedule_week(
            client,
            "devtieri",
            __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        )
        print("BUFFER_OAUTH_SCHEDULE_OK")
        print(json.dumps(result, ensure_ascii=False))

        access_token = ""
        token_data.clear()
        return 0
    finally:
        callback_server.shutdown()
        callback_server.server_close()
        if tunnel_proc is not None and tunnel_proc.poll() is None:
            tunnel_proc.terminate()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"BUFFER_OAUTH_BLOCKED: {type(exc).__name__}: {exc}")
        raise SystemExit(2)
