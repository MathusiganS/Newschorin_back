from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import HTTPException

from tamilwin_scraper.app.db.connection import connection_scope
from tamilwin_scraper.app.db.schema import ensure_schema
from tamilwin_scraper.app.integrations.gemini_client import GeminiClient
from tamilwin_scraper.app.models.enums import NewsStatus
from tamilwin_scraper.app.repositories.news_repository import NewsRepository
from tamilwin_scraper.app.schemas.admin import AdminNewsUpdate
from tamilwin_scraper.app.services.classification_service import classify_article
from tamilwin_scraper.app.utils.datetime import parse_scraped_datetime
from tamilwin_scraper.app.utils.images import normalize_image_path


logger = logging.getLogger(__name__)


def normalize_status(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    value = raw.strip().lower()
    if value in {status.value for status in NewsStatus}:
        return value
    raise HTTPException(status_code=400, detail="Invalid status value")


def list_admin_news(status: Optional[str] = None) -> list[dict[str, Any]]:
    normalized = normalize_status(status)
    with connection_scope() as conn:
        return NewsRepository(conn).list_admin(normalized)


def get_admin_news(article_id: int) -> dict[str, Any]:
    with connection_scope() as conn:
        row = NewsRepository(conn).get_admin_detail(article_id)
    if not row:
        raise HTTPException(status_code=404, detail="Article not found")
    return row


def update_admin_news(article_id: int, body: AdminNewsUpdate) -> dict[str, bool]:
    status = normalize_status(body.status) if body.status is not None else None
    updates: list[tuple[str, Any]] = []
    if body.title is not None:
        updates.append(("title", body.title))
    if body.url is not None:
        updates.append(("url", body.url))
    image_path = body.image_path if body.image_path is not None else body.image
    if image_path is not None:
        updates.append(("image_path", normalize_image_path(image_path)))
    if body.full_text is not None:
        updates.append(("full_text", body.full_text))
    if body.source is not None:
        updates.append(("source", body.source))
    if body.category_ta is not None:
        updates.append(("category_ta", body.category_ta))
    if body.created_at is not None:
        updates.append(("created_at", parse_scraped_datetime(body.created_at)))
    if status is not None:
        updates.append(("status", status))
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    with connection_scope() as conn:
        found = NewsRepository(conn).update_admin(article_id, updates)
    if not found:
        raise HTTPException(status_code=404, detail="Article not found")
    return {"ok": True}


def reclassify_all_news() -> dict[str, int]:
    updated = 0
    errors = 0
    with connection_scope() as conn:
        ensure_schema(conn)
        repository = NewsRepository(conn)
        rows = repository.list_classification_rows()
        for article_id, title, full_text in rows:
            try:
                category = classify_article(full_text or "", title or "")
                repository.update_category(article_id, category)
                updated += 1
            except Exception:
                errors += 1
                logger.exception("Failed to reclassify article id=%s", article_id)
        conn.commit()
    return {"rows_seen": len(rows), "updated": updated, "errors": errors}


def paraphrase_all_news() -> dict[str, int]:
    gemini = GeminiClient()
    if not gemini.configured:
        raise HTTPException(
            status_code=400, detail="GEMINI_API_KEY is not configured"
        )
    updated = 0
    skipped = 0
    errors = 0
    with connection_scope() as conn:
        ensure_schema(conn)
        repository = NewsRepository(conn)
        rows = repository.list_paraphrase_rows()
        for (
            article_id,
            title,
            full_text,
            original_title,
            original_full_text,
        ) in rows:
            source_title = original_title or title or ""
            source_text = original_full_text or full_text or ""
            if not source_title and not source_text:
                skipped += 1
                continue
            try:
                result = gemini.paraphrase_news(source_title, source_text)
                if not result.changed:
                    skipped += 1
                    continue
                repository.update_paraphrased_article(
                    article_id,
                    result.title,
                    result.full_text,
                    source_title,
                    source_text,
                )
                updated += 1
            except Exception:
                errors += 1
                logger.exception(
                    "Failed to paraphrase article id=%s", article_id
                )
        conn.commit()
    return {
        "rows_seen": len(rows),
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
    }


def paraphrase_all_titles() -> dict[str, int]:
    gemini = GeminiClient()
    if not gemini.configured:
        raise HTTPException(
            status_code=400, detail="GEMINI_API_KEY is not configured"
        )
    updated = 0
    skipped = 0
    errors = 0
    with connection_scope() as conn:
        ensure_schema(conn)
        repository = NewsRepository(conn)
        rows = repository.list_paraphrase_rows()
        for (
            article_id,
            title,
            full_text,
            original_title,
            original_full_text,
        ) in rows:
            source_title = original_title or title or ""
            context = original_full_text or full_text or ""
            if not source_title:
                skipped += 1
                continue
            try:
                new_title = gemini.paraphrase_title(source_title, context)
                if not new_title or new_title == title:
                    skipped += 1
                    continue
                repository.update_paraphrased_title(
                    article_id, new_title, source_title
                )
                updated += 1
            except Exception:
                errors += 1
                logger.exception(
                    "Failed to paraphrase title id=%s", article_id
                )
        conn.commit()
    return {
        "rows_seen": len(rows),
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
    }
