"""Chat views: read the request, call a service or selector, return the response. No business logic here."""
import json

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from config.ratelimit import client_ip
from public import seo

from .languages import LANGUAGE_NAMES, LANGUAGES
from .models import ChatSession
from .selectors import chat_selector, progress_selector
from .services import chat_service, quota_service
from .signals import IMPORTED_CHAT_KEY
from .starters import POPULAR_LANGUAGES, TOPICS

_POPULAR = [{"code": c, "name": LANGUAGE_NAMES[c]} for c in POPULAR_LANGUAGES]
_OTHERS = sorted(({"code": l["code"], "name": l["name"]} for l in LANGUAGES if l["code"] not in POPULAR_LANGUAGES),
                 key=lambda l: l["name"])


def _parse_pk(value):
    try:
        return int(value) if value else None
    except (TypeError, ValueError):
        return None


def _page_context(language, difficulty, locked, messages, quota, **extra):
    return {
        "chat_messages": messages,
        "topics": TOPICS,
        "popular_languages": _POPULAR,
        "other_languages": _OTHERS,
        "current_language": language,
        "current_language_name": LANGUAGE_NAMES.get(language, language),
        "current_difficulty": difficulty,
        "language_locked": locked,  # a chat keeps the language it started with
        "quota": quota,
        "member_limit": settings.AI_DAILY_CHAT_LIMIT,
        **extra,
    }


def index(request, pk=None):
    """The landing page of the whole site: guests get the free trial, members get their workspace."""
    pk = _parse_pk(pk or request.GET.get("session"))  # old links used /chat?session=ID
    if not request.user.is_authenticated:
        if pk:
            return redirect_to_login(request.get_full_path())
        if not request.session.session_key:
            request.session.save()
        state = chat_service.guest_state(request.session)
        quota = quota_service.guest_quota(client_ip(request), request.session.session_key)
        return render(request, "chat/index.html", _page_context(
            state["language"], state["difficulty"], bool(state["messages"]), state["messages"], quota,
            is_guest=True, current=None,
            jsonld=seo.jsonld(seo.organization(request), seo.website(request), seo.web_application(request)),
        ))

    if pk is None and (imported := request.session.pop(IMPORTED_CHAT_KEY, None)):
        return redirect("chat:detail", pk=imported)  # just signed up: continue the trial conversation
    current = chat_selector.get_user_session(request.user, pk) if pk else None
    return render(request, "chat/index.html", _page_context(
        current.language if current else "ja",
        current.difficulty if current else "n5",
        current is not None,
        chat_selector.session_messages(current) if current else [],
        quota_service.user_quota(request.user),
        is_guest=False, current=current,
    ))


def _read_message(request):
    """Message fields from a multipart form or a JSON body."""
    if request.content_type and "application/json" in request.content_type:
        try:
            body = json.loads(request.body)
            get = body.get
        except (ValueError, AttributeError):
            return None
    else:
        get = request.POST.get
    return {key: str(get(key, "") or "").strip()
            for key in ("message", "model_provider", "model_name", "language", "difficulty")}


@require_POST
def send_new(request):
    """First message of a new chat. Members get a saved chat; guests use their trial quota."""
    data = _read_message(request)
    if data is None:
        return JsonResponse({"error": "bad_request"}, status=400)
    image = request.FILES.get("image")
    if request.user.is_authenticated:
        payload, status = chat_service.send_user_message(
            request.user, None, data["message"], provider=data["model_provider"], model_name=data["model_name"],
            image_file=image, language=data["language"], difficulty=data["difficulty"],
        )
        if status == 200:
            payload["session"]["url"] = reverse("chat:detail", args=[payload["session"]["id"]])
    else:
        payload, status = chat_service.send_guest_message(
            request.session, client_ip(request), data["message"],
            language=data["language"], difficulty=data["difficulty"], has_image=image is not None,
        )
    return JsonResponse(payload, status=status)


@login_required
@require_POST
def send(request, pk):
    session = chat_selector.get_user_session(request.user, pk)
    data = _read_message(request)
    if data is None:
        return JsonResponse({"error": "bad_request"}, status=400)
    payload, status = chat_service.send_user_message(
        request.user, session, data["message"], provider=data["model_provider"], model_name=data["model_name"],
        image_file=request.FILES.get("image"),
    )
    return JsonResponse(payload, status=status)


@require_POST
def guest_reset(request):
    """'New chat' for a guest: forget the trial conversation (the quota is not reset)."""
    chat_service.reset_guest(request.session)
    return JsonResponse({"success": True})


@login_required
def dashboard(request):
    """'Progress': learning stats, recent chats, and the detailed new-chat form (title, goal, level)."""
    user = request.user
    return render(request, "dashboard.html", {
        "totals": progress_selector.totals(user),
        "streak": progress_selector.streak(user),
        "activity": progress_selector.daily_activity(user),
        "language_stats": progress_selector.language_breakdown(user),
        "recent_chats": progress_selector.recent_chats(user),
        "today_quota": quota_service.user_quota(user),
        "languages": LANGUAGES,
    })


@login_required
@require_POST
def create(request):
    session = chat_service.create_session(request.user, request.POST)
    if request.headers.get("x-requested-with") == "XMLHttpRequest" or "application/json" in request.headers.get("accept", ""):
        return JsonResponse({
            "success": True,
            "id": session.pk,
            "url": reverse("chat:detail", kwargs={"pk": session.pk}),
            "title": session.title,
        })
    return redirect("chat:detail", pk=session.pk)


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
    payload, _ = chat_service.send_user_message(
        request.user, session, request.POST.get("message", ""),
        provider=request.POST.get("model_provider", ""), model_name=request.POST.get("model_name", ""),
        image_file=request.FILES.get("image"),
    )
    if "reply" in payload:
        res = {"success": True, "ai_response": payload["reply"]}
        if payload.get("image_url"):
            res["image_url"] = payload["image_url"]
        return JsonResponse(res)
    return JsonResponse({"success": False, "error": payload["message"]})


@login_required
@require_POST
def clear(request):
    try:
        session_id = int(json.loads(request.body).get("session_id"))
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({"success": False}, status=400)
    chat_selector.get_user_session(request.user, session_id).messages.all().delete()
    return JsonResponse({"success": True})


@login_required
@require_POST
def delete_session(request, pk):
    chat_selector.get_user_session(request.user, pk).delete()
    return JsonResponse({"success": True})
