from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

# Format lisible: 22/09/2025 22:50 UTC
READABLE_FMT = "%d/%m/%Y %H:%M UTC"


def to_aware(dt: datetime) -> datetime:
    """Assure que le datetime est timezone-aware en UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def format_dt(dt: datetime) -> str:
    """Formate un datetime en chaîne lisible en UTC."""
    return to_aware(dt).strftime(READABLE_FMT)


def format_iso_str(iso_str: str) -> str:
    """Parse une chaîne ISO 8601 et renvoie un format lisible en UTC.
    Retourne la chaîne originale si parsing impossible.
    """
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return format_dt(dt)
    except Exception:
        return iso_str
