from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import HTTPException

from app.db.connection import connection_scope
from app.db.schema import ensure_schema
from app.repositories.news_repository import NewsRepository


logger = logging.getLogger(__name__)


def list_news(
    source: Optional[str] = None,
    category_ta: Optional[str] = None,
    search: Optional[str] = None,
    sort: Optional[str] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
) -> dict[str, Any]:
    with connection_scope() as conn:
        ensure_schema(conn)
        repository = NewsRepository(conn)
        rows = repository.list_public(
            source=source,
            category_ta=category_ta,
            search=search,
            sort=sort,
            limit=limit,
            offset=offset,
        )
        total = repository.count_public(
            source=source,
            category_ta=category_ta,
            search=search,
        )
    if (sort or "").lower() in {"trending", "popular", "views"}:
        logger.info(
            "Trending news requested sort=%s limit=%s rows=%s",
            sort,
            limit,
            [
                {
                    "id": row["id"],
                    "views": row["view_count"],
                    "title": (row["title"] or "")[:60],
                }
                for row in rows
            ],
        )
    return {"items": rows, "total": total}


def count_news(
    source: Optional[str] = None,
    category_ta: Optional[str] = None,
    search: Optional[str] = None,
) -> dict[str, int]:
    with connection_scope() as conn:
        ensure_schema(conn)
        total = NewsRepository(conn).count_public(
            source=source,
            category_ta=category_ta,
            search=search,
        )
    return {"total": total}


def important_news() -> Optional[dict[str, Any]]:
    with connection_scope() as conn:
        ensure_schema(conn)
        return NewsRepository(conn).get_important()


def popular_news(limit: int = 4) -> list[dict[str, Any]]:
    with connection_scope() as conn:
        ensure_schema(conn)
        rows = NewsRepository(conn).list_popular(limit)
    logger.info(
        "Popular news requested limit=%s rows=%s",
        max(1, min(limit, 20)),
        [
            {
                "id": row["id"],
                "views": row["view_count"],
                "title": (row["title"] or "")[:60],
            }
            for row in rows
        ],
    )
    return rows


def get_news_detail(article_id: int) -> dict[str, Any]:
    with connection_scope() as conn:
        ensure_schema(conn)
        row = NewsRepository(conn).get_public_detail(article_id)
    if not row:
        raise HTTPException(status_code=404, detail="Article not found")
    return row


def track_view(article_id: int, event_source: str = "detail") -> dict[str, Any]:
    with connection_scope() as conn:
        ensure_schema(conn)
        row = NewsRepository(conn).increment_view(article_id)
    if not row:
        logger.info("View tracking missing source=%s id=%s", event_source, article_id)
        raise HTTPException(status_code=404, detail="Article not found")
    logger.info(
        "View incremented id=%s count=%s status=%s title=%s",
        row["id"],
        row["view_count"],
        row["status"],
        row["title"][:80],
    )
    return {
        "id": row["id"],
        "status": row["status"],
        "view_count": row["view_count"],
    }
