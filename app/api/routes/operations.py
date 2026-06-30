from __future__ import annotations

from fastapi import APIRouter, Depends

from tamilwin_scraper.app.core.security import require_operator
from tamilwin_scraper.app.services.admin_service import reclassify_all_news
from tamilwin_scraper.app.services.sync_service import sync_news_json


router = APIRouter(
    prefix="/api",
    tags=["operations"],
    dependencies=[Depends(require_operator)],
)


@router.post("/sync")
def api_sync():
    return sync_news_json()


@router.post("/reclassify")
def api_reclassify():
    return reclassify_all_news()
