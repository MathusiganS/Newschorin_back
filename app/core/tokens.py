from __future__ import annotations

import time
from typing import Any

import jwt

from tamilwin_scraper.app.core.config import Settings


def _jwt_secret(settings: Settings) -> str:
    if settings.jwt_secret:
        return settings.jwt_secret
    if settings.is_production:
        raise RuntimeError("JWT_SECRET is required when APP_ENV=production")
    return f"dev-only-{settings.admin_user}-{settings.admin_password}"


def create_admin_token(settings: Settings) -> str:
    now = int(time.time())
    payload = {
        "sub": settings.admin_user,
        "iat": now,
        "exp": now + settings.jwt_expire_minutes * 60,
        "role": "admin",
    }
    return jwt.encode(
        payload,
        _jwt_secret(settings),
        algorithm=settings.jwt_algorithm,
    )


def decode_admin_token(token: str, settings: Settings) -> dict[str, Any]:
    payload = jwt.decode(
        token,
        _jwt_secret(settings),
        algorithms=[settings.jwt_algorithm],
    )
    if payload.get("sub") != settings.admin_user or payload.get("role") != "admin":
        raise jwt.InvalidTokenError("Invalid admin token")
    return payload
