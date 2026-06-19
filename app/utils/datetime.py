from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional


SRI_LANKA_TZ = timezone(timedelta(hours=5, minutes=30))


def json_datetime(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=SRI_LANKA_TZ)
        else:
            value = value.astimezone(SRI_LANKA_TZ)
        return value.isoformat()
    if isinstance(value, date):
        return datetime.combine(
            value,
            datetime.min.time(),
            tzinfo=SRI_LANKA_TZ,
        ).isoformat()
    return str(value)


def parse_scraped_datetime(value: Any) -> Optional[str]:
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=SRI_LANKA_TZ)
        return parsed.astimezone(SRI_LANKA_TZ).replace(tzinfo=None).isoformat()
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time()).isoformat()
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=SRI_LANKA_TZ)
    return parsed.astimezone(SRI_LANKA_TZ).replace(tzinfo=None).isoformat()
