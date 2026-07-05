from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends

from app.core.security import require_admin
from app.db.connection import connection_scope
from app.db.schema import ensure_schema
from app.integrations.gemini_client import GeminiClient
from app.repositories.news_repository import NewsRepository
from app.schemas.admin import AdminNewsUpdate
from app.services.admin_service import (
    get_admin_news,
    list_admin_news,
    paraphrase_all_news,
    paraphrase_all_titles,
    update_admin_news,
)
from app.services.image_service import (
    normalize_database_image_paths,
)


router = APIRouter(
    prefix="/api/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


@router.get("/paraphrase-status")
def api_admin_paraphrase_status():
    return GeminiClient().status()


@router.post("/paraphrase-news")
def api_admin_paraphrase_news():
    return paraphrase_all_news()


@router.post("/paraphrase-titles")
def api_admin_paraphrase_titles():
    return paraphrase_all_titles()


@router.post("/normalize-images")
def api_admin_normalize_images():
    return {"updated": normalize_database_image_paths()}


@router.get("/sync-errors")
def api_admin_sync_errors():
    with connection_scope() as conn:
        ensure_schema(conn)
        return NewsRepository(conn).list_sync_errors(resolved=False)


@router.post("/sync-errors/{error_id:int}/resolve")
def api_admin_resolve_sync_error(error_id: int):
    with connection_scope() as conn:
        ensure_schema(conn)
        NewsRepository(conn).mark_sync_error_resolved(error_id)
    return {"ok": True}


@router.get("/news")
def api_admin_news_list(
    status: Optional[str] = None,
    source: Optional[str] = None,
    category_ta: Optional[str] = None,
    search: Optional[str] = None,
    sort: Optional[str] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    include_meta: bool = False,
):
    result = list_admin_news(
        status=status,
        source=source,
        category_ta=category_ta,
        search=search,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    if include_meta:
        return result
    return result["items"]


@router.get("/news/{article_id:int}")
def api_admin_news_detail(article_id: int):
    return get_admin_news(article_id)


@router.put("/news/{article_id:int}")
def api_admin_news_update(article_id: int, body: AdminNewsUpdate):
    return update_admin_news(article_id, body)


@router.post("/news/{article_id:int}/approve")
def api_admin_approve(article_id: int):
    return update_admin_news(
        article_id,
        AdminNewsUpdate(status="approved"),
    )


@router.post("/news/{article_id:int}/reject")
def api_admin_reject(article_id: int):
    return update_admin_news(
        article_id,
        AdminNewsUpdate(status="rejected"),
    )
