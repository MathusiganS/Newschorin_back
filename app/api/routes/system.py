from __future__ import annotations

from fastapi import APIRouter


router = APIRouter(tags=["system"])


@router.get("/")
def api_root():
    return {
        "ok": True,
        "service": "Tamil News API",
        "docs": "/docs",
        "health": "/health",
    }


@router.get("/health")
def api_health():
    return {"ok": True}
