from __future__ import annotations

from typing import Optional

from fastapi import APIRouter

from app.services.news_service import (
    count_news,
    get_news_detail,
    important_news,
    list_news,
    popular_news,
    track_view,
)


router = APIRouter(prefix="/api/news", tags=["news"])


@router.get("")
def api_news_list(
    source: Optional[str] = None,
    category_ta: Optional[str] = None,
    search: Optional[str] = None,
    sort: Optional[str] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
):
    return list_news(
        source=source,
        category_ta=category_ta,
        search=search,
        sort=sort,
        limit=limit,
        offset=offset,
    )


@router.get("/count")
def api_news_count(
    source: Optional[str] = None,
    category_ta: Optional[str] = None,
    search: Optional[str] = None,
):
    return count_news(
        source=source,
        category_ta=category_ta,
        search=search,
    )


@router.get("/popular")
def api_news_popular(limit: int = 4):
    return popular_news(limit)


@router.get("/important")
def api_news_important():
    return important_news()


@router.get("/trending")
def api_news_trending(limit: int = 4):
    return popular_news(limit)


@router.post("/{article_id:int}/view")
def api_news_track_view(article_id: int):
    return track_view(article_id, "detail")


@router.get("/{article_id:int}")
def api_news_detail(article_id: int):
    return get_news_detail(article_id)
