from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Iterable


LOCAL_TZ = timezone(timedelta(hours=5, minutes=30))


def _walk_json(value: Any) -> Iterable[Any]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _parse_datetime(value: str) -> str:
    raw = _clean_text(value)
    if not raw:
        return ""

    raw = raw.replace("Published:", "").replace("Updated:", "").strip()
    raw = raw.replace("IST", "+05:30").replace("SLST", "+05:30")

    iso_candidate = raw
    if iso_candidate.endswith("Z"):
        iso_candidate = iso_candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(iso_candidate)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=LOCAL_TZ)
        return parsed.astimezone(timezone.utc).isoformat()
    except ValueError:
        pass

    for fmt in (
        "%d %b, %Y | %I:%M %p",
        "%d %b %Y | %I:%M %p",
        "%d %B, %Y | %I:%M %p",
        "%d %B %Y | %I:%M %p",
        "%d %b, %Y %I:%M %p",
        "%d %b %Y %I:%M %p",
        "%d %B, %Y %I:%M %p",
        "%d %B %Y %I:%M %p",
        "%d %b, %Y",
        "%d %b %Y",
        "%d %B, %Y",
        "%d %B %Y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
    ):
        try:
            parsed = datetime.strptime(raw, fmt).replace(tzinfo=LOCAL_TZ)
            return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            continue

    try:
        parsed = parsedate_to_datetime(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=LOCAL_TZ)
        return parsed.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, IndexError, OverflowError):
        return ""


def extract_published_at(response) -> str:
    """Return article publish/update datetime as an ISO UTC string when available."""
    candidates: list[str] = []

    for block in response.css('script[type="application/ld+json"]::text').getall():
        try:
            data = json.loads(block)
        except (json.JSONDecodeError, TypeError):
            continue
        for node in _walk_json(data):
            if not isinstance(node, dict):
                continue
            for key in ("datePublished", "dateCreated", "dateModified", "uploadDate"):
                value = node.get(key)
                if isinstance(value, str):
                    candidates.append(value)

    selectors = [
        'meta[property="article:published_time"]::attr(content)',
        'meta[property="article:modified_time"]::attr(content)',
        'meta[name="article:published_time"]::attr(content)',
        'meta[name="pubdate"]::attr(content)',
        'meta[name="publish-date"]::attr(content)',
        'meta[name="date"]::attr(content)',
        'meta[itemprop="datePublished"]::attr(content)',
        'meta[itemprop="dateModified"]::attr(content)',
        'time::attr(datetime)',
        "time::text",
        ".date::text",
        ".news-date::text",
        ".article-date::text",
        ".post-date::text",
        ".published-date::text",
        ".nav-date::text",
    ]
    for selector in selectors:
        candidates.extend(response.css(selector).getall())

    body_text = " ".join(response.css("body ::text").getall())
    candidates.extend(
        re.findall(
            r"\d{1,2}\s+[A-Za-z]{3,9},?\s+\d{4}\s*\|?\s*\d{1,2}:\d{2}\s*(?:AM|PM)?",
            body_text,
            flags=re.IGNORECASE,
        )
    )

    for candidate in candidates:
        parsed = _parse_datetime(candidate)
        if parsed:
            return parsed
    return ""
