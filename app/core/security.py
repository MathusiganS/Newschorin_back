from __future__ import annotations

import base64
import binascii
import secrets

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader, HTTPBasic, HTTPBasicCredentials

from app.core.config import Settings, get_settings
from app.core.passwords import verify_password
from app.core.tokens import decode_admin_token


optional_basic_security = HTTPBasic(auto_error=False)
optional_sync_key = APIKeyHeader(name="X-API-Key", auto_error=False)


def _admin_credentials_valid(
    credentials: HTTPBasicCredentials,
    settings: Settings,
) -> bool:
    user_ok = secrets.compare_digest(credentials.username, settings.admin_user)
    if settings.admin_password_hash:
        password_ok = verify_password(
            credentials.password,
            settings.admin_password_hash,
        )
    else:
        password_ok = secrets.compare_digest(
            credentials.password,
            settings.admin_password,
        )
    return user_ok and password_ok


def _basic_credentials_from_header(request: Request) -> HTTPBasicCredentials | None:
    authorization = request.headers.get("Authorization", "")
    if not authorization.lower().startswith("basic "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    try:
        decoded = base64.b64decode(token).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return None
    username, separator, password = decoded.partition(":")
    if not separator:
        return None
    return HTTPBasicCredentials(username=username, password=password)


def require_admin(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> None:
    token = request.cookies.get(settings.cookie_name)
    if token:
        try:
            decode_admin_token(token, settings)
            return
        except jwt.PyJWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired session",
            )

    # Temporary migration fallback: legacy Basic-auth clients can still call
    # admin APIs until all deployed frontends use the httpOnly cookie session.
    credentials = _basic_credentials_from_header(request)
    if credentials and _admin_credentials_valid(credentials, settings):
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
    )


def require_operator(
    request: Request,
    credentials: HTTPBasicCredentials | None = Depends(optional_basic_security),
    sync_api_key: str | None = Depends(optional_sync_key),
    settings: Settings = Depends(get_settings),
) -> None:
    key_ok = bool(
        settings.sync_api_key
        and sync_api_key
        and secrets.compare_digest(sync_api_key, settings.sync_api_key)
    )

    admin_ok = False
    token = request.cookies.get(settings.cookie_name)
    if token:
        try:
            decode_admin_token(token, settings)
            admin_ok = True
        except jwt.PyJWTError:
            admin_ok = False

    # Temporary migration fallback for any existing manual sync calls.
    if not admin_ok:
        admin_ok = bool(
            credentials and _admin_credentials_valid(credentials, settings)
        )

    if not (key_ok or admin_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid operational credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
