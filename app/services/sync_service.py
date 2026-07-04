from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import HTTPException

from app.core.config import get_settings
from app.db.connection import connection_scope
from app.db.schema import ensure_schema
from app.integrations.gemini_client import (
    GeminiClient,
    body_rewrite_acceptable,
    titles_too_similar,
)
from app.repositories.news_repository import NewsRepository
from app.services.classification_service import classify_article
from app.utils.datetime import parse_scraped_datetime
from app.utils.images import normalize_image_path


logger = logging.getLogger(__name__)


def sync_news_json() -> dict[str, int]:
    news_json = get_settings().news_json
    if not news_json.exists():
        raise HTTPException(status_code=404, detail="news.json not found")
    try:
        items = json.loads(news_json.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise HTTPException(
            status_code=500, detail=f"Invalid news.json: {exc}"
        ) from exc
    if not isinstance(items, list):
        raise HTTPException(status_code=500, detail="Invalid news.json: expected a list")

    inserted = 0
    updated = 0
    failed = 0
    paraphrased = 0
    paraphrase_reused = 0
    paraphrase_skipped = 0
    gemini = GeminiClient()

    with connection_scope() as conn:
        ensure_schema(conn)
        repository = NewsRepository(conn)
        for item in items:
            original_title = ""
            url = ""
            try:
                if not isinstance(item, dict):
                    raise ValueError("News item must be an object")
                original_title = (
                    item.get("original_title") or item.get("title") or ""
                )
                url = item.get("url") or ""
                image_path = normalize_image_path(item.get("image_path") or "")
                original_full_text = (
                    item.get("original_full_text")
                    or item.get("full_text")
                    or ""
                )
                scraped_created_at = parse_scraped_datetime(
                    item.get("created_at")
                )
                existing = repository.get_existing_source(url)
                source_is_unchanged = bool(
                    existing
                    and (existing[2] or "") == original_title
                    and (existing[3] or "") == original_full_text
                )
                existing_title = (existing[0] or "") if existing else ""
                existing_text = (existing[1] or "") if existing else ""
                existing_body_is_valid = (
                    body_rewrite_acceptable(
                        original_full_text,
                        existing_text,
                    )
                    if original_full_text.strip()
                    else True
                )
                existing_rewrite_is_valid = bool(
                    source_is_unchanged
                    and not titles_too_similar(original_title, existing_title)
                    and existing_body_is_valid
                )

                if existing_rewrite_is_valid:
                    title = existing_title
                    full_text = existing_text
                    paraphrase_reused += 1
                else:
                    result = gemini.paraphrase_news(
                        original_title, original_full_text
                    )
                    title = result.title
                    full_text = result.full_text
                    if result.changed:
                        paraphrased += 1
                    else:
                        paraphrase_skipped += 1

                category_ta = classify_article(
                    original_full_text, original_title
                )
                was_inserted = repository.upsert_scraped(
                    title=title,
                    url=url,
                    image_path=image_path,
                    full_text=full_text,
                    original_title=original_title,
                    original_full_text=original_full_text,
                    source=item.get("source") or "unknown",
                    category_ta=category_ta,
                    created_at=scraped_created_at,
                )
                if was_inserted:
                    inserted += 1
                else:
                    updated += 1
            except Exception as exc:
                conn.rollback()
                failed += 1
                error_message = f"{type(exc).__name__}: {exc}"
                try:
                    repository.record_sync_error(
                        url=url,
                        original_title=original_title,
                        error_message=error_message,
                    )
                except Exception:
                    conn.rollback()
                    logger.exception(
                        "Failed to persist sync error url=%s title=%s",
                        url,
                        original_title,
                    )
                logger.exception(
                    "Failed to synchronize a scraped news item url=%s title=%s",
                    url,
                    original_title,
                )

    result = {
        "total": len(items),
        "inserted": inserted,
        "updated": updated,
        "failed": failed,
        "paraphrased": paraphrased,
        "paraphrase_reused": paraphrase_reused,
        "paraphrase_skipped": paraphrase_skipped,
    }
    logger.info("News synchronization completed result=%s", result)
    return result
