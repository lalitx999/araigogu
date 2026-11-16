"""Fixed-window rate limiting on Django's cache (DatabaseCache -> shared by all workers)."""
from functools import wraps

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import render

TOO_MANY = "ทำรายการเร็วเกินไป รอสักครู่แล้วลองใหม่นะครับ"


def client_ip(request):
    if settings.TRUST_X_FORWARDED_FOR:
        xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if xff:
            return xff.split(",")[-1].strip()  # last hop = the one our proxy appended
    return request.META.get("REMOTE_ADDR", "unknown")


def _key(scope, ident):
    return f"rl:{scope}:{ident}"


def is_limited(scope, ident):
    if settings.RATE_LIMIT_DISABLED:
        return False
    limit, _ = settings.RATE_LIMITS[scope]
    return cache.get(_key(scope, ident), 0) >= limit


def record(scope, ident):
    if settings.RATE_LIMIT_DISABLED:
        return
    _, window = settings.RATE_LIMITS[scope]
    key = _key(scope, ident)
    if cache.add(key, 1, window):
        return
    try:
        cache.incr(key)
    except ValueError:  # expired between add() and incr()
        cache.set(key, 1, window)


def is_ajax(request):
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def too_many(request):
    if is_ajax(request):
        return JsonResponse({"error": TOO_MANY}, status=429)
    return render(request, "429.html", {"message": TOO_MANY}, status=429)


def rate_limited(scope, by="user"):
    """Limit POSTs of a view. by='user' (needs login) or 'ip'."""
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if request.method != "POST":
                return view(request, *args, **kwargs)
            ident = request.user.pk if by == "user" else client_ip(request)
            if is_limited(scope, ident):
                return too_many(request)
            record(scope, ident)
            return view(request, *args, **kwargs)
        return wrapper
    return decorator
