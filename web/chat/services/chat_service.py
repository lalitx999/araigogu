"""Sending chat messages through the AI service, for signed-in users and for guests (free trial).

Every public function returns (payload, http_status) so the views stay a thin request -> response layer.
"""
import base64

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ai_client import client as ai

from ..languages import DIFFICULTIES, JP_LEVELS, LANGUAGE_NAMES
from ..models import ChatSession, Message
from ..selectors import chat_selector
from . import quota_service

MAX_MESSAGE_LEN = 2000
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
GUEST_SESSION_KEY = "guest_chat"
TEXT_PROVIDERS = ("groq", "deepseek", "openai")
DEFAULT_TEXT_MODEL = ("groq", "openai/gpt-oss-120b")
VISION_MODEL = ("gemini", "gemini-2.5-flash")

ERRORS = {
    "invalid_message": "ข้อความว่างหรือยาวเกินไป",
    "invalid_image": "อ่านไฟล์รูปภาพไม่ได้ ลองใหม่อีกครั้งนะครับ",
    "file_too_large": "ไฟล์รูปภาพมีขนาดใหญ่เกินไป (ไม่เกิน 10MB)",
    "daily_limit": "วันนี้ใช้ครบโควตาแล้ว ลองใหม่พรุ่งนี้นะครับ",
    "guest_limit": "ทดลองใช้ครบแล้วสำหรับวันนี้ สมัครสมาชิกฟรีเพื่อคุยกับพี่ริวต่อได้เลยครับ",
    "login_required": "เข้าสู่ระบบเพื่อแนบรูปภาพให้พี่ริวช่วยตรวจได้ครับ",
}


def _error(code: str, status: int, **extra) -> tuple[dict, int]:
    return {"error": code, "message": ERRORS.get(code, code), **extra}, status


def normalize_level(language: str, difficulty: str) -> tuple[str, str]:
    language = language if language in LANGUAGE_NAMES else "ja"
    allowed = JP_LEVELS + DIFFICULTIES if language == "ja" else DIFFICULTIES
    if difficulty not in allowed:
        difficulty = "n5" if language == "ja" else "beginner"
    return language, difficulty


def _route_model(has_images: bool, provider: str, model_name: str) -> tuple[str, str]:
    """Images always go to the vision model; text uses the chosen fast/reasoning model."""
    if has_images:
        return VISION_MODEL
    if provider not in TEXT_PROVIDERS:
        return DEFAULT_TEXT_MODEL
    return provider, model_name or ""


def _encode_image(image_file) -> tuple[str | None, str | None]:
    if image_file.size > MAX_IMAGE_SIZE:
        return None, "file_too_large"
    try:
        data = image_file.read()
        image_file.seek(0)
    except (OSError, ValueError):
        return None, "invalid_image"
    mime = getattr(image_file, "content_type", "") or "image/jpeg"
    if not mime.startswith("image/"):
        return None, "invalid_image"
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}", None


def _title_from(text: str) -> str:
    first_line = (text or "").strip().split("\n")[0].strip()
    return first_line[:60] or f"แชทกับพี่ริว - {timezone.localtime():%d/%m/%Y %H:%M}"


def create_session(user, data) -> ChatSession:
    """Empty chat from the dashboard form (language, level, optional title and learning goal)."""
    language = data.get("language", "")
    if language not in LANGUAGE_NAMES:
        language = "ja"
    difficulty = data.get("difficulty", "beginner")
    if language == "ja" and data.get("jp_level") in JP_LEVELS:
        difficulty = data["jp_level"]
    if difficulty not in DIFFICULTIES + JP_LEVELS:
        difficulty = "beginner"
    title = data.get("title", "").strip()[:255] or f"แชทกับพี่ริว - {timezone.localtime():%d/%m/%Y %H:%M}"
    return ChatSession.objects.create(
        user=user, title=title, language=language, difficulty=difficulty,
        learning_goal=data.get("learning_goal", "").strip()[:1000],
    )


def send_user_message(user, session: ChatSession | None, text: str, *, provider: str = "", model_name: str = "",
                      image_file=None, language: str = "ja", difficulty: str = "") -> tuple[dict, int]:
    """Signed-in user. With session=None the first message also creates the chat (only if the AI answered)."""
    text = (text or "").strip()
    images = []
    if image_file:
        data_url, err = _encode_image(image_file)
        if err:
            return _error(err, 400)
        images.append(data_url)
    if (not text and not images) or len(text) > MAX_MESSAGE_LEN:
        return _error("invalid_message", 400)

    quota = quota_service.user_quota(user)
    if quota.exhausted:
        return _error("daily_limit", 429, limit=quota.limit, quota=quota.as_dict())

    if session is None:
        language, difficulty = normalize_level(language, difficulty)
        history, language_name, learning_goal = [], LANGUAGE_NAMES[language], ""
    else:
        language, difficulty = session.language, session.difficulty
        history = chat_selector.recent_history(session, settings.AI_CHAT_HISTORY_LIMIT)
        language_name, learning_goal = session.language_name, session.learning_goal

    provider, model_name = _route_model(bool(images), provider, model_name)
    result = ai.chat(text, language, difficulty, history, language_name=language_name,
                     learning_goal=learning_goal, model_provider=provider, model_name=model_name, images=images)
    if result.get("degraded"):
        # Persist nothing: the client can retry, so saving would create duplicates.
        return {"error": "ai_unavailable", "message": result["reply"], "degraded": True}, 503

    used_model = result.get("model_used") or model_name or "default"
    used_provider = result.get("provider_used") or provider or "default"
    created = session is None
    with transaction.atomic():
        if created:
            session = ChatSession.objects.create(user=user, title=_title_from(text),
                                                 language=language, difficulty=difficulty)
        user_msg = Message.objects.create(
            session=session, role="user", content=text, topic=result.get("topic", ""),
            model_provider=used_provider, model_name=used_model, image=image_file or None,
        )
        Message.objects.create(session=session, role="assistant", content=result["reply"],
                               model_provider=used_provider, model_name=used_model)
        session.save(update_fields=["updated_at"])

    return {
        "reply": result["reply"],
        "user_message": user_msg.content,
        "image_url": user_msg.image_url,
        "model_used": used_model,
        "provider_used": used_provider,
        "degraded": False,
        "session": {"id": session.pk, "title": session.title, "created": created},
        "quota": quota_service.Quota(quota.used + 1, quota.limit).as_dict(),
    }, 200


# --- guests -----------------------------------------------------------------------------------

def guest_state(store) -> dict:
    """The guest's conversation, kept in the Django session (no database rows until they sign up)."""
    return store.get(GUEST_SESSION_KEY) or {"language": "ja", "difficulty": "n5", "messages": []}


def reset_guest(store) -> None:
    store.pop(GUEST_SESSION_KEY, None)


def send_guest_message(store, ip: str, text: str, *, language: str = "ja", difficulty: str = "",
                       has_image: bool = False) -> tuple[dict, int]:
    text = (text or "").strip()
    if has_image:
        return _error("login_required", 403)
    if not text or len(text) > MAX_MESSAGE_LEN:
        return _error("invalid_message", 400)

    if not store.session_key:
        store.save()  # the quota is keyed by session, so make sure there is one
    quota = quota_service.guest_quota(ip, store.session_key)
    if quota.exhausted:
        return _error("guest_limit", 429, quota=quota.as_dict())

    state = guest_state(store)
    if not state["messages"]:  # the language can only change before the conversation starts
        state["language"], state["difficulty"] = normalize_level(language, difficulty)
    history = state["messages"][-settings.AI_CHAT_HISTORY_LIMIT:]
    provider, model_name = DEFAULT_TEXT_MODEL  # guests always use the fast text model
    result = ai.chat(text, state["language"], state["difficulty"], history,
                     language_name=LANGUAGE_NAMES[state["language"]],
                     model_provider=provider, model_name=model_name)
    if result.get("degraded"):
        return {"error": "ai_unavailable", "message": result["reply"], "degraded": True}, 503

    quota_service.consume_guest(ip, store.session_key)
    state["messages"] = (state["messages"] + [
        {"role": "user", "content": text},
        {"role": "assistant", "content": result["reply"]},
    ])[-settings.GUEST_HISTORY_LIMIT:]
    store[GUEST_SESSION_KEY] = state  # reassign so the session backend sees the change

    return {
        "reply": result["reply"],
        "user_message": text,
        "model_used": result.get("model_used") or model_name,
        "provider_used": result.get("provider_used") or provider,
        "degraded": False,
        "quota": quota_service.Quota(quota.used + 1, quota.limit).as_dict(),
    }, 200


def import_guest_conversation(user, store) -> ChatSession | None:
    """After sign-up / login, move the trial conversation into the account as a normal chat."""
    state = store.pop(GUEST_SESSION_KEY, None)
    if not state or not state.get("messages"):
        return None
    messages = state["messages"]
    first_user = next((m["content"] for m in messages if m["role"] == "user"), "")
    with transaction.atomic():
        session = ChatSession.objects.create(
            user=user, title=_title_from(first_user),
            language=state.get("language", "ja"), difficulty=state.get("difficulty", "n5"),
        )
        Message.objects.bulk_create([
            Message(session=session, role=m["role"], content=m["content"])
            for m in messages if m.get("role") in ("user", "assistant")
        ])
    return session
