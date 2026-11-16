"""HTTP client for the FastAPI ai-service. Every call degrades instead of raising."""
import logging
from dataclasses import dataclass

import httpx
from django.conf import settings

log = logging.getLogger(__name__)


@dataclass
class ModerationResult:
    moderated: bool
    new_content: str
    reason: str
    topic: str = "general"
    degraded: bool = False


def _post(path: str, payload: dict, timeout: float) -> dict | None:
    try:
        resp = httpx.post(
            f"{settings.AI_SERVICE_URL}{path}",
            json=payload,
            headers={"X-Internal-Token": settings.AI_INTERNAL_TOKEN},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()
    except (httpx.HTTPError, ValueError):
        log.exception("ai-service call %s failed", path)
        return None


def chat(message: str, language: str, difficulty: str, history: list[dict],
         language_name: str = "", learning_goal: str = "",
         model_provider: str = "gemini", model_name: str = "",
         images: list[str] | None = None) -> dict:
    data = _post(
        "/v1/chat",
        {
            "message": message,
            "language": language,
            "difficulty": difficulty,
            "history": history,
            "language_name": language_name,
            "learning_goal": learning_goal,
            "model_provider": model_provider,
            "model_name": model_name,
            "images": images or [],
        },
        settings.AI_TIMEOUT_CHAT,
    )
    if data is None or not isinstance(data.get("reply"), str):
        return {"reply": "ขออภัยครับ ระบบ AI ยังไม่พร้อมใช้งาน ลองใหม่อีกครั้งนะครับ", "topic": "general", "degraded": True}
    return data


def moderate(content: str) -> ModerationResult:
    data = _post("/v1/moderate", {"content": content}, settings.AI_TIMEOUT_SHORT)
    if data is None:
        return ModerationResult(False, content, "ระบบตรวจสอบอัตโนมัติยังใช้งานไม่ได้", degraded=True)
    try:
        return ModerationResult(
            moderated=bool(data["moderated"]), new_content=str(data["new_content"]), reason=str(data["reason"]),
            topic=str(data.get("topic", "general")), degraded=bool(data.get("degraded", False)),
        )
    except (KeyError, TypeError):
        log.error("ai-service /v1/moderate returned an unexpected payload: %r", data)
        return ModerationResult(False, content, "ระบบตรวจสอบอัตโนมัติยังใช้งานไม่ได้", degraded=True)


def ryu_comment(content: str, topic: str | None) -> str | None:
    """Returns None when the AI is unavailable (no canned comments from a dead service)."""
    data = _post("/v1/comment", {"content": content, "topic": topic}, settings.AI_TIMEOUT_SHORT)
    if not data or data.get("degraded") or not isinstance(data.get("comment"), str):
        return None
    return data["comment"]
