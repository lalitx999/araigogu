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


@login_required
def index(request, pk=None):
    pk = pk or request.GET.get("session")  # old links used /chat?session=ID
    try:
        pk = int(pk) if pk else None
    except (TypeError, ValueError):
        pk = None
    current = get_object_or_404(request.user.chat_sessions, pk=pk) if pk else None
    return render(request, "chat/index.html", {
        "sessions": request.user.chat_sessions.all()[:30],
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
    return redirect("chat:detail", pk=session.pk)


def _deliver(user, session, text):
    """Send one user message through the AI and persist the exchange. Returns (payload, http_status)."""
    if not text or len(text) > MAX_MESSAGE_LEN:
        return {"error": "invalid_message"}, 400

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
    result = ai.chat(text, session.language, session.difficulty, history,
                     language_name=session.language_name, learning_goal=session.learning_goal)
    if result.get("degraded"):
        # Persist nothing: the client can retry, so saving would create duplicates.
        return {"error": result["reply"], "degraded": True}, 503

    Message.objects.create(session=session, role="user", content=text, topic=result.get("topic", ""))
    Message.objects.create(session=session, role="assistant", content=result["reply"])
    session.save(update_fields=["updated_at"])
    return {"reply": result["reply"], "degraded": False}, 200


@login_required
@require_POST
def send(request, pk):
    session = get_object_or_404(request.user.chat_sessions, pk=pk)
    try:
        text = str(json.loads(request.body).get("message", "")).strip()
    except (ValueError, AttributeError):
        return JsonResponse({"error": "bad_request"}, status=400)
    payload, status = _deliver(request.user, session, text)
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
    payload, _ = _deliver(request.user, session, request.POST.get("message", "").strip())
    if "reply" in payload:
        return JsonResponse({"success": True, "ai_response": payload["reply"]})
    msg = {"daily_limit": f"วันนี้ใช้ครบโควตาแล้ว ({payload.get('limit')} ข้อความ) ลองใหม่พรุ่งนี้นะครับ",
           "invalid_message": "ข้อความว่างหรือยาวเกินไป"}.get(payload["error"], payload["error"])
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
