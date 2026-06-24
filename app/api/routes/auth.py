from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import HTTPBasicCredentials

from tamilwin_scraper.app.core.config import Settings, get_settings
from tamilwin_scraper.app.core.security import _admin_credentials_valid
from tamilwin_scraper.app.core.tokens import create_admin_token
from tamilwin_scraper.app.schemas.auth import LoginRequest


router = APIRouter(prefix="/api/admin", tags=["auth"])


@router.post("/login")
def login(
    payload: LoginRequest,
    response: Response,
    settings: Settings = Depends(get_settings),
) -> dict[str, bool]:
    credentials = HTTPBasicCredentials(
        username=payload.username,
        password=payload.password,
    )
    if not _admin_credentials_valid(credentials, settings):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
        )

    response.set_cookie(
        key=settings.cookie_name,
        value=create_admin_token(settings),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        max_age=settings.jwt_expire_minutes * 60,
        path="/",
    )
    return {"ok": True}


@router.post("/logout")
def logout(
    response: Response,
    settings: Settings = Depends(get_settings),
) -> dict[str, bool]:
    response.delete_cookie(settings.cookie_name, path="/")
    return {"ok": True}
