from unittest import mock

import httpx
from django.test import SimpleTestCase, override_settings

from . import client


def resp(status=200, payload=None):
    r = mock.Mock()
    r.json.return_value = payload
    if status >= 400:
        r.raise_for_status.side_effect = httpx.HTTPStatusError("x", request=mock.Mock(), response=mock.Mock())
    return r


@override_settings(AI_SERVICE_URL="http://ai:8001", AI_INTERNAL_TOKEN="tok")
class ClientTests(SimpleTestCase):
    @mock.patch("ai_client.client.httpx.post")
    def test_sends_token_and_url(self, post):
        post.return_value = resp(payload={"reply": "hi", "topic": "general", "degraded": False})
        self.assertEqual(client.chat("a", "ja", "beginner", [])["reply"], "hi")
        self.assertEqual(post.call_args.args[0], "http://ai:8001/v1/chat")
        self.assertEqual(post.call_args.kwargs["headers"], {"X-Internal-Token": "tok"})

    @mock.patch("ai_client.client.httpx.post", side_effect=httpx.ConnectTimeout("slow"))
    def test_timeout_degrades_everywhere(self, _):
        self.assertTrue(client.chat("a", "ja", "beginner", [])["degraded"])
        m = client.moderate("hello")
        self.assertTrue(m.degraded and not m.moderated and m.new_content == "hello")
        self.assertIsNone(client.ryu_comment("x", None))

    @mock.patch("ai_client.client.httpx.post", return_value=resp(500))
    def test_http_500_degrades(self, _):
        self.assertTrue(client.chat("a", "ja", "beginner", [])["degraded"])
        self.assertTrue(client.moderate("x").degraded)

    @mock.patch("ai_client.client.httpx.post", return_value=resp(401))
    def test_wrong_token_degrades(self, _):
        self.assertTrue(client.moderate("x").degraded)

    @mock.patch("ai_client.client.httpx.post")
    def test_malformed_payloads_degrade(self, post):
        post.return_value = resp(payload={"unexpected": 1})
        self.assertTrue(client.moderate("x").degraded)
        self.assertTrue(client.chat("a", "ja", "beginner", [])["degraded"])
        self.assertIsNone(client.ryu_comment("x", None))
        post.return_value = resp(payload=None)
        self.assertTrue(client.moderate("x").degraded)

    @mock.patch("ai_client.client.httpx.post")
    def test_ryu_comment_skips_degraded_canned_text(self, post):
        post.return_value = resp(payload={"comment": "ขอบคุณครับ", "degraded": True})
        self.assertIsNone(client.ryu_comment("x", None))
        post.return_value = resp(payload={"comment": "ขอบคุณครับ", "degraded": False})
        self.assertEqual(client.ryu_comment("x", "food"), "ขอบคุณครับ")
