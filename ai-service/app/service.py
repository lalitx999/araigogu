import json
import random

from .llm import LLM
from .prompts import (
    BANNED_COMMENT_WORDS, CHAT_FALLBACK, CHAT_TOPIC_KEYWORDS, COMMENT_SYSTEM,
    FALLBACK_COMMENTS, LANGUAGE_NAMES, MODERATION_SYSTEM, TOPICS, chat_system_prompt,
)
from .schemas import (
    ChatRequest, ChatResponse, CommentRequest, CommentResponse,
    ModerateRequest, ModerateResponse,
)


def detect_chat_topic(message: str) -> str:
    text = message.lower()
    for topic, words in CHAT_TOPIC_KEYWORDS.items():
        if any(w in text for w in words):
            return topic
    return "general"


async def chat(llm: LLM, req: ChatRequest) -> ChatResponse:
    topic = detect_chat_topic(req.message)
    language = req.language_name or LANGUAGE_NAMES.get(req.language, "ภาษาต่างประเทศ")
    messages = [{"role": "system", "content": chat_system_prompt(language, req.difficulty, req.learning_goal)}]
    messages += [{"role": m.role, "content": m.content} for m in req.history]

    has_images = bool(req.images)
    if has_images:
        user_content: list[dict] = []
        prompt_text = req.message.strip() or "ช่วยดูภาพนี้ ถอดความและช่วยอธิบาย/สอนเนื้อหาให้หน่อยครับ"
        user_content.append({"type": "text", "text": prompt_text})
        for img in req.images:
            user_content.append({"type": "image_url", "image_url": {"url": img}})
        messages.append({"role": "user", "content": user_content})
    else:
        messages.append({"role": "user", "content": req.message})

    if hasattr(llm, "complete_chat"):
        reply, provider_used, model_used = await llm.complete_chat(
            messages,
            provider=req.model_provider,
            custom_model=req.model_name,
            has_images=has_images,
            temperature=0.7,
            max_tokens=1500,
        )
    else:
        reply = await llm.complete(
            messages,
            provider=req.model_provider,
            custom_model=req.model_name,
            has_images=has_images,
            temperature=0.7,
            max_tokens=1500,
        )
        provider_used = "gemini" if has_images else (req.model_provider or "groq")
        model_used = req.model_name

    if not reply:
        return ChatResponse(
            reply=CHAT_FALLBACK,
            topic=topic,
            degraded=True,
            model_used=model_used or "",
            provider_used=provider_used or "",
        )

    return ChatResponse(
        reply=reply.strip(),
        topic=topic,
        degraded=False,
        model_used=model_used or "",
        provider_used=provider_used or "",
    )


async def moderate(llm: LLM, req: ModerateRequest) -> ModerateResponse:
    degraded = ModerateResponse(
        moderated=False, new_content=req.content, topic="general", confidence=0.0, degraded=True,
        reason="ระบบตรวจสอบอัตโนมัติยังใช้งานไม่ได้ โพสต์นี้จะถูกส่งให้ผู้ดูแลตรวจภายหลัง",
    )
    raw = await llm.complete(
        [
            {"role": "system", "content": MODERATION_SYSTEM},
            {"role": "user", "content": f"<post>{req.content}</post>"},
        ],
        temperature=0.2,
        json_mode=True,
    )
    if not raw:
        return degraded
    try:
        data = json.loads(raw)
        moderated = bool(data["moderated"])
        new_content = str(data.get("new_content") or "").strip() or req.content
    except (ValueError, KeyError, TypeError):
        return degraded
    topic = data.get("topic") if data.get("topic") in TOPICS else "general"
    try:
        confidence = min(1.0, max(0.0, float(data.get("confidence", 0.8))))
    except (TypeError, ValueError):
        confidence = 0.8
    return ModerateResponse(
        moderated=moderated,
        new_content=new_content if moderated else req.content,
        reason=str(data.get("reason") or "")[:500]
        or ("เนื้อหาบางส่วนอาจไม่เหมาะสมกับชุมชน" if moderated else "เนื้อหาผ่านเกณฑ์ของชุมชน"),
        topic=topic,
        confidence=confidence,
    )


def finalize_comment(text: str) -> str:
    for word in BANNED_COMMENT_WORDS:
        text = text.replace(word, "")
    text = " ".join(text.split()).strip()
    if not text:
        return random.choice(FALLBACK_COMMENTS)
    if not text.endswith("ครับ"):
        text = text.rstrip(".!?") + " ครับ"
    return text


async def comment(llm: LLM, req: CommentRequest) -> CommentResponse:
    topic_line = f"หัวข้อโพสต์: {req.topic}\n" if req.topic else ""
    raw = await llm.complete(
        [
            {"role": "system", "content": COMMENT_SYSTEM},
            {"role": "user", "content": f"{topic_line}<post>{req.content}</post>\n\nเขียนคอมเมนต์ 1 ประโยค"},
        ],
        temperature=0.2,
        max_tokens=120,
    )
    if not raw:
        return CommentResponse(comment=random.choice(FALLBACK_COMMENTS), degraded=True)
    return CommentResponse(comment=finalize_comment(raw))
