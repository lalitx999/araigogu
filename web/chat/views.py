import base64
import json

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from ai_client import client as ai

from .languages import DIFFICULTIES, JP_LEVELS, LANGUAGE_NAMES, LANGUAGES
from .models import ChatSession, Message

MAX_MESSAGE_LEN = 2000
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB


@login_required
def index(request, pk=None):
    pk = pk or request.GET.get("session")  # old links used /chat?session=ID
    try:
        pk = int(pk) if pk else None
    except (TypeError, ValueError):
        pk = None
    current = get_object_or_404(request.user.chat_sessions, pk=pk) if pk else None
    all_sessions = list(request.user.chat_sessions.all()[:50])

    return render(request, "chat/index.html", {
        "sessions": all_sessions,
        "current": current,
        "chat_messages": current.messages.all() if current else [],
        "languages": LANGUAGES,
        "current_language": current.language if current else "ja",
        "current_language_name": current.language_name if current else "ภาษาญี่ปุ่น",
        "current_difficulty": current.difficulty if current else "n5",
    })


@login_required
def dashboard(request):
    qs = request.user.chat_sessions.annotate(message_count=Count("messages"))
    recent = list(qs.order_by("-updated_at")[:6])
    for i, chat in enumerate(recent):
        chat.formatted_time = timezone.localtime(chat.updated_at).strftime("%d/%m/%y %H:%M")
        chat.aos_delay = min(300 + i * 50, 600)
    return render(request, "dashboard.html", {
        "chat_count": request.user.chat_sessions.count(),
        "recent_chats": recent,
        "languages": LANGUAGES,
    })


@login_required
@require_POST
def create(request):
    language = request.POST.get("language", "")
    if language not in LANGUAGE_NAMES:
        language = "ja"
    difficulty = request.POST.get("difficulty", "beginner")
    if language == "ja" and request.POST.get("jp_level") in JP_LEVELS:
        difficulty = request.POST["jp_level"]
    if difficulty not in DIFFICULTIES + JP_LEVELS:
        difficulty = "beginner"
    title = request.POST.get("title", "").strip()[:255] or f"แชทกับพี่ริว - {timezone.localtime():%d/%m/%Y %H:%M}"
    session = ChatSession.objects.create(
        user=request.user, title=title, language=language, difficulty=difficulty,
        learning_goal=request.POST.get("learning_goal", "").strip()[:1000],
    )
    if request.headers.get("x-requested-with") == "XMLHttpRequest" or "application/json" in request.headers.get("accept", ""):
        return JsonResponse({
            "success": True,
            "id": session.pk,
            "url": reverse("chat:detail", kwargs={"pk": session.pk}),
            "title": session.title,
        })
    return redirect("chat:detail", pk=session.pk)


def _deliver(user, session, text, model_provider="groq", model_name="",
             image_file=None, image_data_url=""):
    """Send one user message through the AI and persist the exchange. Returns (payload, http_status)."""
    text = (text or "").strip()
    images = []

    if image_file:
        try:
            if image_file.size > MAX_IMAGE_SIZE:
                return {"error": "file_too_large"}, 400
            image_bytes = image_file.read()
            image_file.seek(0)
            mime = getattr(image_file, "content_type", "image/jpeg")
            b64 = base64.b64encode(image_bytes).decode("ascii")
            images.append(f"data:{mime};base64,{b64}")
        except Exception:
            return {"error": "invalid_image"}, 400
    elif image_data_url:
        images.append(image_data_url)

    if not text and not images:
        return {"error": "invalid_message"}, 400
    if len(text) > MAX_MESSAGE_LEN:
        return {"error": "invalid_message"}, 400

    # Policy Routing:
    # 1. Images attached -> Gemini (Vision / Multimodal)
    # 2. Text only -> Groq (ultra-fast) or DeepSeek (reasoning)
    if images:
        model_provider = "gemini"
        model_name = "gemini-2.5-flash"
    elif not model_provider or model_provider not in ("groq", "deepseek", "openai"):
        model_provider = "groq"
        model_name = "openai/gpt-oss-120b"

    limit = settings.AI_DAILY_CHAT_LIMIT
    if limit:
        today = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
        used = Message.objects.filter(session__user=user, role="user", created_at__gte=today).count()
        if used >= limit:
            return {"error": "daily_limit", "limit": limit}, 429

    history = [
        {"role": m.role, "content": m.content}
        for m in session.messages.order_by("-created_at", "-id")[: settings.AI_CHAT_HISTORY_LIMIT]
    ][::-1]

    result = ai.chat(
        text, session.language, session.difficulty, history,
        language_name=session.language_name, learning_goal=session.learning_goal,
        model_provider=model_provider, model_name=model_name, images=images,
    )
    if result.get("degraded"):
        # Persist nothing: the client can retry, so saving would create duplicates.
        return {"error": result["reply"], "degraded": True}, 503

    actual_model = result.get("model_used") or model_name or "default"
    actual_provider = result.get("provider_used") or model_provider or "default"

    user_msg = Message.objects.create(
        session=session,
        role="user",
        content=text,
        topic=result.get("topic", ""),
        model_provider=actual_provider,
        model_name=actual_model,
        image=image_file if image_file else None,
    )
    assistant_msg = Message.objects.create(
        session=session,
        role="assistant",
        content=result["reply"],
        model_provider=actual_provider,
        model_name=actual_model,
    )
    # Automatically update session title if it's the first message and still default
    if session.messages.count() <= 2 and text:
        first_line = text.split("\n")[0].strip()[:35]
        session.title = first_line
    session.save(update_fields=["updated_at", "title"])

    return {
        "reply": result["reply"],
        "user_message": user_msg.content,
        "image_url": user_msg.image_url,
        "model_used": actual_model,
        "provider_used": actual_provider,
        "degraded": False,
    }, 200


@login_required
@require_POST
def send(request, pk):
    session = get_object_or_404(request.user.chat_sessions, pk=pk)
    image_file = request.FILES.get("image")
    image_data_url = ""
    model_provider = "gemini"
    model_name = "gemini-2.5-flash"

    if request.content_type and "application/json" in request.content_type:
        try:
            body = json.loads(request.body)
            text = str(body.get("message", "")).strip()
            model_provider = str(body.get("model_provider", "gemini")).strip()
            model_name = str(body.get("model_name", "gemini-2.5-flash")).strip()
            image_data_url = str(body.get("image", "")).strip()
        except (ValueError, AttributeError):
            return JsonResponse({"error": "bad_request"}, status=400)
    else:
        text = str(request.POST.get("message", "")).strip()
        model_provider = str(request.POST.get("model_provider", "gemini")).strip()
        model_name = str(request.POST.get("model_name", "gemini-2.5-flash")).strip()

    payload, status = _deliver(
        request.user, session, text,
        model_provider=model_provider,
        model_name=model_name,
        image_file=image_file,
        image_data_url=image_data_url,
    )
    return JsonResponse(payload, status=status)


@login_required
@require_POST
def action(request):
    """Endpoint used by the original chat page: multipart form with action=send_message."""
    if request.POST.get("action") != "send_message":
        return JsonResponse({"success": False, "error": "invalid_action"})
    try:
        session = request.user.chat_sessions.get(pk=int(request.POST.get("session_id", "")))
    except (ValueError, ChatSession.DoesNotExist):
        return JsonResponse({"success": False, "error": "session_not_found"})
    payload, _ = _deliver(
        request.user, session, request.POST.get("message", "").strip(),
        model_provider=request.POST.get("model_provider", "gemini"),
        model_name=request.POST.get("model_name", "gemini-2.5-flash"),
        image_file=request.FILES.get("image"),
    )
    if "reply" in payload:
        res = {"success": True, "ai_response": payload["reply"]}
        if payload.get("image_url"):
            res["image_url"] = payload["image_url"]
        return JsonResponse(res)
    msg = {"daily_limit": f"วันนี้ใช้ครบโควตาแล้ว ({payload.get('limit')} ข้อความ) ลองใหม่พรุ่งนี้นะครับ",
           "invalid_message": "ข้อความว่างหรือยาวเกินไป",
           "file_too_large": "ไฟล์รูปภาพมีขนาดใหญ่เกินไป (ไม่เกิน 10MB)"}.get(payload["error"], payload["error"])
    return JsonResponse({"success": False, "error": msg})


@login_required
@require_POST
def clear(request):
    try:
        session_id = int(json.loads(request.body).get("session_id"))
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({"success": False}, status=400)
    session = get_object_or_404(request.user.chat_sessions, pk=session_id)
    session.messages.all().delete()
    return JsonResponse({"success": True})


@login_required
@require_POST
def delete_session(request, pk):
    session = get_object_or_404(request.user.chat_sessions, pk=pk)
    session.delete()
    return JsonResponse({"success": True})
