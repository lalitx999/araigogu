from urllib.parse import urlencode, urlparse

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Exists, OuterRef, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from accounts.archetypes import ARCHETYPE_DATA
from ai_client import client as ai
from config.ratelimit import is_ajax, rate_limited

from .models import Bookmark, Comment, Like, Post, Repost

User = get_user_model()
MAX_POST_LEN = 1000
MAX_COMMENT_LEN = 500
PENDING_KEY = "pending_post"
TOGGLES = {"like": Like, "bookmark": Bookmark, "repost": Repost}


# ---------- helpers ----------
def _posts_qs(user):
    return (
        Post.objects.select_related("author")
        .annotate(
            like_count=Count("likes", distinct=True),
            comment_count=Count("comments", distinct=True),
            repost_count=Count("reposts", distinct=True),
            liked=Exists(Like.objects.filter(post=OuterRef("pk"), user=user)),
            bookmarked=Exists(Bookmark.objects.filter(post=OuterRef("pk"), user=user)),
            reposted=Exists(Repost.objects.filter(post=OuterRef("pk"), user=user)),
        )
        .order_by("-created_at")
    )


def _posted_today(user):
    """The original allowed one post per person per day."""
    start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    return Post.objects.filter(author=user, created_at__gte=start).exists()


def _next_url(request, page):
    if not page.has_next():
        return ""
    params = {k: v for k, v in request.GET.items() if k != "page"}
    params["page"] = page.next_page_number()
    return f"{request.path}?{urlencode(params)}"


def _with_error(url, code):
    return f"{url}{'&' if '?' in url else '?'}error={code}"


def _safe_referer(request):
    target = request.POST.get("next") or request.META.get("HTTP_REFERER") or ""
    if target and url_has_allowed_host_and_scheme(target, {request.get_host()}, request.is_secure()):
        return urlparse(target).path  # same-host only; keep just the path
    return ""


def _back(request, fallback="community:feed"):
    return redirect(_safe_referer(request) or reverse(fallback))


def _publish(user, content, *, original="", moderated=False, topic="general", needs_review=False):
    return Post.objects.create(
        author=user, content=content, original_content=original,
        ai_moderated=moderated, topic=topic, needs_review=needs_review,
    )


def _ensure_ryu(post):
    """P'Ryu's comment, at most one per post. None when the AI is unavailable."""
    if post.comments.filter(is_ai=True).exists():
        return None
    text = ai.ryu_comment(post.content, post.topic)
    return Comment.objects.create(post=post, body=text, is_ai=True) if text else None


# ---------- pages ----------
@login_required
def feed(request):
    page = Paginator(_posts_qs(request.user), 20).get_page(request.GET.get("page"))
    nxt = _next_url(request, page)
    if is_ajax(request):  # "load more"
        return JsonResponse({"html": render_to_string("community/_feed_posts.html", {"page": page}, request), "next": nxt})
    ryu_url = ""
    try:
        ryu_id = int(request.GET.get("ryu", ""))
        if Post.objects.filter(pk=ryu_id, author=request.user).exists():
            ryu_url = reverse("community:ryu", args=[ryu_id])
    except ValueError:
        pass
    return render(request, "community/feed.html", {
        "page": page,
        "next_url": nxt,
        "can_post": not _posted_today(request.user),
        "pending": request.session.get(PENDING_KEY),
        "error": request.GET.get("error"),
        "ryu_url": ryu_url,
        "ryu_post_id": request.GET.get("ryu", ""),
    })


@login_required
def search(request):
    q = request.GET.get("q", "").strip()[:100]
    users = []
    if q:
        users = list(User.objects.filter(is_active=True).filter(
            Q(full_name__icontains=q) | Q(email__icontains=q))[:20])
    trends = [{"key": k, "name": v["name"], "count": Post.objects.filter(author__archetype=k).count()}
              for k, v in list(ARCHETYPE_DATA.items())[:5]]
    suggestions = User.objects.filter(is_active=True).exclude(pk=request.user.pk).order_by("?")[:3]
    return render(request, "community/search.html", {
        "query": q, "users": users, "trends": trends, "suggestions": suggestions})


@login_required
def profile(request, user_id):
    owner = get_object_or_404(User, pk=user_id, is_active=True)
    own = list(Post.objects.filter(author=owner).select_related("author")[:50])
    for p in own:
        p.type = "post"
    shared = list(Post.objects.filter(reposts__user=owner).select_related("author")[:50])
    for p in shared:
        p.type = "repost"
    timeline = sorted(own + shared, key=lambda p: p.created_at, reverse=True)[:50]
    return render(request, "community/profile.html", {
        "profile": owner, "posts": timeline, "post_count": len(timeline),
        "is_own_profile": owner.pk == request.user.pk,
    })


@login_required
def post_detail(request, pk):
    post = get_object_or_404(_posts_qs(request.user), pk=pk)
    comments = list(post.comments.select_related("author"))
    return render(request, "community/detail.html", {"post": post, "comments": comments, "profile": request.user})


# ---------- posting ----------
@login_required
@rate_limited("post")
@require_POST
def create_post(request):
    content = request.POST.get("content", "").strip()
    if not content or len(content) > MAX_POST_LEN:
        return redirect(_with_error(reverse("community:feed"), "empty_content"))
    if _posted_today(request.user):
        return redirect(_with_error(reverse("community:feed"), "already_posted"))

    result = ai.moderate(content)
    if result.moderated:  # the feed shows the "P'Ryu suggests..." modal from this session entry
        request.session[PENDING_KEY] = {"original": content, "suggestion": result.new_content,
                                        "reason": result.reason, "topic": result.topic}
        return redirect("community:feed")
    post = _publish(request.user, content, topic=result.topic, needs_review=result.degraded)
    return redirect(f"{reverse('community:feed')}?ryu={post.pk}")


@login_required
@require_POST
def review_decide(request):
    pending = request.session.pop(PENDING_KEY, None)
    if request.POST.get("choice") != "accept" or not pending:
        return redirect("community:feed")
    if _posted_today(request.user):
        return redirect(_with_error(reverse("community:feed"), "already_posted"))
    post = _publish(request.user, pending["suggestion"], original=pending["original"],
                    moderated=True, topic=pending["topic"])
    return redirect(f"{reverse('community:feed')}?ryu={post.pk}")


@login_required
@rate_limited("ryu")
@require_POST
def ryu(request, pk):
    """Called by the feed page in the background after posting, so the author never waits for the AI."""
    post = get_object_or_404(Post, pk=pk, author=request.user)
    comment = _ensure_ryu(post)
    return JsonResponse({"created": bool(comment), "count": post.comments.count()})


# ---------- reactions & comments ----------
@login_required
@require_POST
def toggle(request, pk, kind):
    model = TOGGLES.get(kind)
    if model is None:
        return JsonResponse({"error": "unknown action"}, status=404) if is_ajax(request) else redirect("community:feed")
    post = get_object_or_404(Post, pk=pk)
    obj, created = model.objects.get_or_create(user=request.user, post=post)
    if not created:
        obj.delete()
    if is_ajax(request):
        return JsonResponse({"active": created, "count": model.objects.filter(post=post).count()})
    return _back(request)


@login_required
@rate_limited("comment")
@require_POST
def add_comment(request, pk):
    post = get_object_or_404(Post, pk=pk)
    body = (request.POST.get("content") or request.POST.get("body") or "").strip()
    target = _safe_referer(request) or reverse("community:detail", args=[pk])
    if not body or len(body) > MAX_COMMENT_LEN:
        return JsonResponse({"error": "missing_data"}, status=400) if is_ajax(request) \
            else redirect(_with_error(target, "missing_data"))
    result = ai.moderate(body)
    if result.moderated:
        return JsonResponse({"error": "inappropriate", "reason": result.reason}, status=400) if is_ajax(request) \
            else redirect(_with_error(target, "inappropriate"))
    Comment.objects.create(post=post, author=request.user, body=body, needs_review=result.degraded)
    if is_ajax(request):
        return JsonResponse({"ok": True, "count": post.comments.count()})
    return redirect(target)
