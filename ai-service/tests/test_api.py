import json
import os

os.environ["AI_INTERNAL_TOKEN"] = "test-token"  # force: tests must not depend on the caller's env

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app, get_llm  # noqa: E402
from app.service import finalize_comment  # noqa: E402

H = {"X-Internal-Token": "test-token"}


class FakeLLM:
    available = True

    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    async def complete(self, messages, **kw):
        self.calls.append((messages, kw))
        return self.reply


def client(reply):
    fake = FakeLLM(reply)
    app.dependency_overrides[get_llm] = lambda: fake
    return TestClient(app), fake


def teardown_function():
    app.dependency_overrides.clear()


def test_requires_token():
    c, _ = client("x")
    assert c.post("/v1/chat", json={"message": "hi"}).status_code == 401
    assert c.post("/v1/chat", json={"message": "hi"}, headers={"X-Internal-Token": "bad"}).status_code == 401


def test_chat_includes_history_and_detects_topic():
    c, fake = client("สวัสดีครับ")
    r = c.post("/v1/chat", headers=H, json={
        "message": "ร้านอาหารญี่ปุ่นพูดว่าอะไร", "language": "ja",
        "history": [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}],
    })
    assert r.status_code == 200
    res = r.json()
    assert res["reply"] == "สวัสดีครับ" and res["topic"] == "food" and res["degraded"] is False
    roles = [m["role"] for m in fake.calls[0][0]]
    assert roles == ["system", "user", "assistant", "user"]


def test_chat_with_images_and_provider():
    c, fake = client("วิเคราะห์รูปภาพแล้วครับ")
    r = c.post("/v1/chat", headers=H, json={
        "message": "แปลรูปนี้ให้หน่อย",
        "language": "ja",
        "model_provider": "gemini",
        "model_name": "gemini-2.5-flash",
        "images": ["data:image/jpeg;base64,abc123xyz"],
    })
    assert r.status_code == 200
    assert r.json()["reply"] == "วิเคราะห์รูปภาพแล้วครับ"
    user_msg = fake.calls[0][0][-1]
    assert user_msg["role"] == "user"
    assert isinstance(user_msg["content"], list)
    assert user_msg["content"][0]["text"] == "แปลรูปนี้ให้หน่อย"
    assert user_msg["content"][1]["image_url"]["url"] == "data:image/jpeg;base64,abc123xyz"


def test_chat_degrades_without_llm():
    c, _ = client(None)
    body = c.post("/v1/chat", headers=H, json={"message": "hi"}).json()
    assert body["degraded"] is True and body["reply"]


def test_moderate_flagged_returns_suggestion():
    c, _ = client(json.dumps({"moderated": True, "new_content": "สะอาด", "reason": "หยาบ",
                              "topic": "food", "confidence": 0.9}))
    body = c.post("/v1/moderate", headers=H, json={"content": "แย่"}).json()
    assert body["moderated"] is True and body["new_content"] == "สะอาด" and body["topic"] == "food"


def test_moderate_pass_keeps_original_and_bad_topic_normalised():
    c, _ = client(json.dumps({"moderated": False, "new_content": "IGNORED", "topic": "nonsense"}))
    body = c.post("/v1/moderate", headers=H, json={"content": "สวัสดี"}).json()
    assert body["moderated"] is False and body["new_content"] == "สวัสดี" and body["topic"] == "general"


def test_moderate_degraded_on_garbage_or_no_llm():
    for reply in (None, "not json", json.dumps({"foo": 1})):
        c, _ = client(reply)
        body = c.post("/v1/moderate", headers=H, json={"content": "x"}).json()
        assert body["degraded"] is True and body["moderated"] is False


def test_comment_is_cleaned_and_ends_with_krub():
    assert finalize_comment("วุ้ย น่าสนใจจ้า") == "น่าสนใจ ครับ"
    assert finalize_comment("ขอบคุณครับ") == "ขอบคุณครับ"
    assert finalize_comment("วุ้ย").endswith("ครับ")
    c, _ = client("เยี่ยมมาก")
    assert c.post("/v1/comment", headers=H, json={"content": "x"}).json()["comment"] == "เยี่ยมมาก ครับ"


# ---- LLM wrapper ----
import asyncio  # noqa: E402

from app.config import Settings  # noqa: E402
from app.llm import LLM  # noqa: E402


class _Boom:
    class chat:
        class completions:
            @staticmethod
            async def create(**kw):
                raise RuntimeError("openai down")


def test_llm_returns_none_without_key_and_on_errors():
    # _env_file=None and empty keys: a real .env / exported key on the dev machine must not leak in
    no_keys = Settings(_env_file=None, ai_internal_token="t", openai_api_key="", gemini_api_key="",
                       groq_api_key="", deepseek_api_key="")
    assert asyncio.run(LLM(no_keys).complete([{"role": "user", "content": "x"}])) is None
    llm = LLM(Settings(ai_internal_token="t", openai_api_key="sk-test"))
    llm._client = _Boom()
    assert asyncio.run(llm.complete([{"role": "user", "content": "x"}])) is None


def test_llm_concurrency_is_capped():
    active = peak = 0

    class Slow:
        class chat:
            class completions:
                @staticmethod
                async def create(**kw):
                    nonlocal active, peak
                    active += 1
                    peak = max(peak, active)
                    await asyncio.sleep(0.02)
                    active -= 1
                    msg = type("M", (), {"content": "ok"})()
                    return type("R", (), {"choices": [type("C", (), {"message": msg})()]})()

    llm = LLM(Settings(ai_internal_token="t", openai_api_key="sk-test", max_concurrency=2))
    llm._client = Slow()

    async def run():
        await asyncio.gather(*[llm.complete([{"role": "user", "content": "x"}]) for _ in range(6)])

    asyncio.run(run())
    assert peak == 2


def test_chat_prompt_uses_language_name_goal_and_level_from_the_web_app():
    c, fake = client("ok")
    c.post("/v1/chat", headers=H, json={"message": "hi", "language": "zu", "language_name": "ภาษาซูลู",
                                        "learning_goal": "สั่งอาหารเป็น", "difficulty": "n3"})
    system = fake.calls[0][0][0]["content"]
    assert "ภาษาซูลู" in system and "สั่งอาหารเป็น" in system and "n3" in system


def test_chat_falls_back_to_builtin_names_and_omits_empty_goal():
    c, fake = client("ok")
    c.post("/v1/chat", headers=H, json={"message": "hi", "language": "ja"})
    system = fake.calls[0][0][0]["content"]
    assert "ภาษาญี่ปุ่น" in system and "เป้าหมายของผู้เรียน" not in system


def test_replies_never_contain_emoji():
    from app.service import strip_emoji
    assert strip_emoji("สวัสดีครับ 🐾\n**こんにちは** ✨ 你好 🇯🇵 ok 👍🏽") == "สวัสดีครับ\n**こんにちは**  你好  ok"
    assert strip_emoji("```\n    indented code\n```") == "```\n    indented code\n```"
