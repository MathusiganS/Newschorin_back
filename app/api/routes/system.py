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


@router.get("/api/health")
def api_health_details():
    """Health probe reachable through the frontend's /api proxy.

    ``features`` lets the admin UI verify the running backend supports a
    capability before blaming a failed save on stale data. Backends without
    this route respond 404, which the frontend treats as an outdated deploy.
    """
    return {
        "ok": True,
        "service": "Tamil News API",
        "features": {"admin_image_upload": True},
    }
