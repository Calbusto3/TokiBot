from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Optional

_start: Optional[datetime] = None


def set_start(now: Optional[datetime] = None) -> None:
    global _start
    _start = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)


def get_start() -> Optional[datetime]:
    return _start


def get_uptime() -> Optional[timedelta]:
    if _start is None:
        return None
    return datetime.now(timezone.utc) - _start


def format_uptime() -> str:
    td = get_uptime()
    if td is None:
        return "N/A"
    total_seconds = int(td.total_seconds())
    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}j")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)
