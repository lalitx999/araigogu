"""Daily message quotas: guests (free trial) and signed-in users."""
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from ..selectors import chat_selector


@dataclass(frozen=True)
class Quota:
    used: int
    limit: int  # 0 = unlimited

    @property
    def remaining(self) -> int | None:
        return None if not self.limit else max(0, self.limit - self.used)

    @property
    def exhausted(self) -> bool:
        return bool(self.limit) and self.used >= self.limit

    def as_dict(self) -> dict:
        return {"used": self.used, "limit": self.limit, "remaining": self.remaining}


def _seconds_until_midnight() -> int:
    now = timezone.localtime()
    midnight = timezone.make_aware(datetime.combine(now.date() + timedelta(days=1), time.min))
    return int((midnight - now).total_seconds()) + 60


def _guest_keys(ip: str, session_key: str) -> tuple[str, str]:
    day = timezone.localdate().isoformat()
    return f"guest:{day}:sid:{session_key}", f"guest:{day}:ip:{ip}"


def guest_quota(ip: str, session_key: str) -> Quota:
    """Usage shown to the guest is per browser session; the IP cap only blocks cookie-clearing."""
    sid_key, ip_key = _guest_keys(ip, session_key)
    counts = cache.get_many([sid_key, ip_key])
    limit = settings.GUEST_DAILY_CHAT_LIMIT
    used = counts.get(sid_key, 0)
    if counts.get(ip_key, 0) >= settings.GUEST_DAILY_IP_LIMIT:
        used = limit  # this network used up its share for today
    return Quota(used=min(used, limit), limit=limit)


def consume_guest(ip: str, session_key: str) -> None:
    ttl = _seconds_until_midnight()
    for key in _guest_keys(ip, session_key):
        if cache.add(key, 1, ttl):
            continue
        try:
            cache.incr(key)
        except ValueError:  # expired between add() and incr()
            cache.set(key, 1, ttl)


def user_quota(user) -> Quota:
    limit = settings.AI_DAILY_CHAT_LIMIT
    if not limit:
        return Quota(used=0, limit=0)
    return Quota(used=chat_selector.user_messages_today(user), limit=limit)
