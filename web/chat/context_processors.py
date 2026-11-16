"""Data the shared app shell (sidebar + profile menu) needs on every page.

Everything that hits the database is lazy: auth pages and the About page never
render the sidebar, so they never run these queries.
"""
from django.conf import settings
from django.utils.functional import SimpleLazyObject

from .selectors import chat_selector
from .services import quota_service
from .starters import TOPICS

_SECTIONS = {"community": "community", "dashboard": "progress", "edit_profile": "settings"}


def _section(request) -> str:
    match = getattr(request, "resolver_match", None)
    if match is None:
        return ""
    if match.namespace == "community":
        return "community"
    return _SECTIONS.get(match.url_name, "chat" if match.namespace == "chat" or match.url_name == "home" else "")


def app_shell(request):
    user = getattr(request, "user", None)
    member = bool(user and user.is_authenticated)
    return {
        "topics": TOPICS,
        "member_limit": settings.AI_DAILY_CHAT_LIMIT,
        "nav_section": _section(request),
        "sidebar_sessions": SimpleLazyObject(lambda: chat_selector.sidebar_sessions(user)) if member else [],
        "member_quota": SimpleLazyObject(lambda: quota_service.user_quota(user)) if member else None,
    }
