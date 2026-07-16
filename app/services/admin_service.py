from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from app.db.connection import connection_scope
from app.db.schema import ensure_schema
from app.integrations.gemini_client import GeminiClient
from app.models.enums import NewsStatus
from app.repositories.news_repository import NewsRepository
from app.schemas.admin import AdminNewsUpdate
from app.services.classification_service import classify_article
from app.utils.datetime import parse_scraped_datetime
from app.utils.images import normalize_image_path, save_admin_image_data


logger = logging.getLogger(__name__)
SRI_LANKA_TZ = ZoneInfo("Asia/Colombo")


def normalize_status(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    value = raw.strip().lower()
    if value in {status.value for status in NewsStatus}:
        return value
    raise HTTPException(status_code=400, detail="Invalid status value")


def list_admin_news(
    status: Optional[str] = None,
    source: Optional[str] = None,
    category_ta: Optional[str] = None,
    search: Optional[str] = None,
    sort: Optional[str] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
) -> dict[str, Any]:
    normalized = normalize_status(status)
    normalized_source = source.strip() if source else None
    normalized_category = category_ta.strip() if category_ta else None
    normalized_search = search.strip() if search else None
    with connection_scope() as conn:
        repository = NewsRepository(conn)
        items = repository.list_admin(
            status=normalized,
            source=normalized_source,
            category_ta=normalized_category,
            search=normalized_search,
            sort=sort,
            limit=limit,
            offset=offset,
        )
        total = repository.count_admin(
            status=normalized,
            source=normalized_source,
            category_ta=normalized_category,
            search=normalized_search,
        )
        counts = {
            status_value: repository.count_admin(
                status=status_value,
                source=normalized_source,
                category_ta=normalized_category,
                search=normalized_search,
            )
            for status_value in (status.value for status in NewsStatus)
        }
    return {"items": items, "total": total, "counts": counts}


def get_admin_news(article_id: int) -> dict[str, Any]:
    with connection_scope() as conn:
        row = NewsRepository(conn).get_admin_detail(article_id)
    if not row:
        raise HTTPException(status_code=404, detail="Article not found")
    return row


def update_admin_news(article_id: int, body: AdminNewsUpdate) -> dict[str, bool]:
    logger.info("Admin article update started article_id=%s", article_id)
    status = normalize_status(body.status) if body.status is not None else None
    updates: list[tuple[str, Any]] = []
    if body.title is not None:
        updates.append(("title", body.title))
    if body.url is not None:
        updates.append(("url", body.url))
    image_data = body.image_data if body.image_data is not None else body.imageData
    if image_data:
        logger.info(
            "Admin article image upload received article_id=%s image_data_chars=%s",
            article_id,
            len(image_data),
        )
        try:
            image_path = save_admin_image_data(image_data)
        except ValueError as exc:
            logger.warning(
                "Admin article image upload failed article_id=%s error=%s",
                article_id,
                exc,
            )
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        logger.info(
            "Admin article image upload stored article_id=%s image_path=%s",
            article_id,
            image_path,
        )
    else:
        image_path = (
            body.image_path
            if body.image_path is not None
            else body.image
            if body.image is not None
            else body.image_url
            if body.image_url is not None
            else body.imageUrl
        )
        if image_path is not None:
            logger.info(
                "Admin article image path update received article_id=%s image_path=%s",
                article_id,
                normalize_image_path(image_path),
            )
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
        if status == "approved":
            with connection_scope() as conn:
                current = NewsRepository(conn).get_admin_status(article_id)
            if current and (current[0] != "approved" or current[1] is None):
                approved_at = datetime.now(SRI_LANKA_TZ).replace(tzinfo=None)
                updates.append(("approved_at", approved_at))
    if not updates:
        logger.warning("Admin article update rejected article_id=%s reason=no_fields", article_id)
        raise HTTPException(status_code=400, detail="No fields to update")

    logger.info(
        "Admin article update writing database article_id=%s fields=%s",
        article_id,
        ",".join(field for field, _ in updates),
    )
    with connection_scope() as conn:
        found = NewsRepository(conn).update_admin(article_id, updates)
    if not found:
        logger.warning("Admin article update failed article_id=%s reason=not_found", article_id)
        raise HTTPException(status_code=404, detail="Article not found")
    updated = get_admin_news(article_id)
    logger.info(
        "Admin article update completed article_id=%s image_path=%s status=%s",
        article_id,
        updated.get("image_path"),
        updated.get("status"),
    )
    return updated | {"ok": True}


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
