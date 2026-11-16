"""Learning statistics for the Progress page: a handful of queries in total."""
from collections import Counter
from datetime import datetime, time, timedelta

from django.db.models import Count, Max, Q
from django.utils import timezone

from ..languages import LANGUAGE_NAMES
from ..models import ChatSession, Message

THAI_DAYS = ["จ.", "อ.", "พ.", "พฤ.", "ศ.", "ส.", "อา."]


def _user_messages(user):
    return Message.objects.filter(session__user=user, role="user")


def _days_with_counts(user, since) -> Counter:
    """Local-date -> message count. Bucketed in Python so MySQL needs no time-zone tables
    (CONVERT_TZ returns NULL without them); it reads one timestamp column per message."""
    start = timezone.make_aware(datetime.combine(since, time.min))
    stamps = _user_messages(user).filter(created_at__gte=start).values_list("created_at", flat=True)
    return Counter(timezone.localtime(t).date() for t in stamps.iterator())


def daily_activity(user, days: int = 7) -> list[dict]:
    """Messages the user sent per day for the last `days` days (oldest first), with a 0-100 bar height."""
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)
    counts = _days_with_counts(user, start)
    peak = max(counts.values(), default=0) or 1
    out = []
    for i in range(days):
        day = start + timedelta(days=i)
        n = counts.get(day, 0)
        out.append({"date": day, "label": THAI_DAYS[day.weekday()], "count": n,
                    "height": round(n / peak * 100), "is_today": day == today})
    return out


def streak(user, lookback: int = 120) -> int:
    """Consecutive days (ending today, or yesterday if nothing yet today) with at least one message."""
    today = timezone.localdate()
    days = set(_days_with_counts(user, today - timedelta(days=lookback)))
    cursor = today if today in days else today - timedelta(days=1)
    count = 0
    while cursor in days:
        count += 1
        cursor -= timedelta(days=1)
    return count


def totals(user) -> dict:
    sessions = ChatSession.objects.filter(user=user)
    return {
        "chats": sessions.count(),
        "messages": _user_messages(user).count(),
        "languages": sessions.values("language").distinct().count(),
    }


def language_breakdown(user, limit: int = 5) -> list[dict]:
    rows = list(
        ChatSession.objects.filter(user=user).values("language")
        .annotate(chats=Count("id", distinct=True), msg_count=Count("messages", filter=Q(messages__role="user")), last=Max("updated_at"))
        .filter(msg_count__gt=0)  # empty chats say nothing about what someone studies
        .order_by("-msg_count", "-last")[:limit]
    )
    peak = max((r["msg_count"] for r in rows), default=0) or 1
    return [{"code": r["language"], "name": LANGUAGE_NAMES.get(r["language"], r["language"]),
             "chats": r["chats"], "messages": r["msg_count"], "share": round(r["msg_count"] / peak * 100)}
            for r in rows]


def recent_chats(user, limit: int = 6) -> list[ChatSession]:
    return list(
        ChatSession.objects.filter(user=user)
        .only("id", "title", "language", "difficulty", "updated_at")
        .annotate(message_count=Count("messages"))
        .order_by("-updated_at")[:limit]
    )
