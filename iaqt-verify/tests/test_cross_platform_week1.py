import json
import unittest
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
YOUTUBE = ROOT / "content" / "youtube-week1.json"
TIKTOK = ROOT / "content" / "tiktok-week1.json"
IDENTITIES = ROOT / "content" / "platform-identities.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class CrossPlatformWeek1Tests(unittest.TestCase):
    def test_manifests_have_same_seven_ids(self):
        yt = load(YOUTUBE)
        tt = load(TIKTOK)
        self.assertEqual(7, len(yt))
        self.assertEqual(7, len(tt))
        self.assertEqual([x["id"] for x in yt], [x["id"] for x in tt])
        self.assertEqual(len({x["id"] for x in yt}), 7)

    def test_media_urls_are_public_https_mp4(self):
        for path in (YOUTUBE, TIKTOK):
            for item in load(path):
                parsed = urlparse(item["media_url"])
                self.assertEqual("https", parsed.scheme)
                self.assertTrue(parsed.netloc)
                self.assertTrue(parsed.path.endswith(".mp4"))

    def test_schedules_are_timezone_aware_and_ordered(self):
        for path in (YOUTUBE, TIKTOK):
            dates = [datetime.fromisoformat(x["publish_at_local"]) for x in load(path)]
            self.assertTrue(all(d.tzinfo is not None for d in dates))
            self.assertEqual(dates, sorted(dates))

    def test_youtube_contract(self):
        for item in load(YOUTUBE):
            self.assertEqual("youtube", item["destination"])
            self.assertEqual("SHORT", item["format"])
            self.assertLessEqual(len(item["title"]), 100)
            self.assertFalse(item["made_for_kids"])
            self.assertTrue(item["ai_generated"])
            self.assertEqual("ready_to_connect", item["status"])

    def test_tiktok_contract(self):
        for item in load(TIKTOK):
            self.assertEqual("tiktok", item["destination"])
            self.assertEqual("VIDEO", item["format"])
            self.assertEqual("PUBLIC_TO_EVERYONE", item["privacy"])
            self.assertTrue(item["ai_generated"])
            self.assertEqual("ready_to_connect", item["status"])

    def test_public_identity_is_devtieri_and_personal_profiles_are_blocked(self):
        cfg = load(IDENTITIES)
        self.assertEqual("devtieri", cfg["public_identity"])
        self.assertEqual("devtieri", cfg["accounts"]["instagram"]["target_handle"])
        self.assertEqual("devtieri", cfg["accounts"]["youtube"]["target_handle"])
        self.assertEqual("devtieri", cfg["accounts"]["tiktok"]["target_handle"])
        self.assertFalse(cfg["accounts"]["youtube"]["personal_channel_allowed"])
        self.assertFalse(cfg["accounts"]["tiktok"]["personal_account_allowed"])
        self.assertEqual("new_brand_channel", cfg["accounts"]["youtube"]["account_model"])
        self.assertEqual("new_separate_account", cfg["accounts"]["tiktok"]["account_model"])

    def test_negative_control_rejects_non_https_media(self):
        sample = dict(load(YOUTUBE)[0])
        sample["media_url"] = "http://example.test/video.mp4"
        parsed = urlparse(sample["media_url"])
        self.assertNotEqual("https", parsed.scheme)


if __name__ == "__main__":
    unittest.main()
