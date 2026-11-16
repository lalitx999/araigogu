"""Read-only queries for the chat pages. Views and services read data through here."""
from django.shortcuts import get_object_or_404
from django.utils import timezone

from ..models import ChatSession, Message

SIDEBAR_LIMIT = 50


def sidebar_sessions(user, limit: int = SIDEBAR_LIMIT) -> list[ChatSession]:
    """Chat history for the sidebar: only the columns the list renders."""
    return list(
        user.chat_sessions.only("id", "title", "language", "updated_at").order_by("-updated_at")[:limit]
    )


def get_user_session(user, pk: int) -> ChatSession:
    """A session owned by `user`, or 404 (never leaks another user's chat)."""
    return get_object_or_404(ChatSession, pk=pk, user=user)


def session_messages(session: ChatSession):
    return session.messages.only("id", "session_id", "role", "content", "image", "created_at")


def recent_history(session: ChatSession, limit: int) -> list[dict]:
    """The last `limit` messages, oldest first, in the shape the AI service expects."""
    rows = session.messages.order_by("-created_at", "-id").values("role", "content")[:limit]
    return list(rows)[::-1]


def user_messages_today(user) -> int:
    start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    return Message.objects.filter(session__user=user, role="user", created_at__gte=start).count()
