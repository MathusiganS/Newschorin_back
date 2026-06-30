from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends

from tamilwin_scraper.app.core.security import require_admin
from tamilwin_scraper.app.integrations.gemini_client import GeminiClient
from tamilwin_scraper.app.schemas.admin import AdminNewsUpdate
from tamilwin_scraper.app.services.admin_service import (
    get_admin_news,
    list_admin_news,
    paraphrase_all_news,
    paraphrase_all_titles,
    update_admin_news,
)
from tamilwin_scraper.app.services.image_service import (
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


@router.get("/news")
def api_admin_news_list(status: Optional[str] = None):
    return list_admin_news(status)


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
