from __future__ import annotations

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader, HTTPBasic, HTTPBasicCredentials

from tamilwin_scraper.app.core.config import Settings, get_settings
from tamilwin_scraper.app.core.passwords import verify_password


basic_security = HTTPBasic()
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


def require_admin(
    credentials: HTTPBasicCredentials = Depends(basic_security),
    settings: Settings = Depends(get_settings),
) -> None:
    if not _admin_credentials_valid(credentials, settings):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )


def require_operator(
    credentials: HTTPBasicCredentials | None = Depends(optional_basic_security),
    sync_api_key: str | None = Depends(optional_sync_key),
    settings: Settings = Depends(get_settings),
) -> None:
    key_ok = bool(
        settings.sync_api_key
        and sync_api_key
        and secrets.compare_digest(sync_api_key, settings.sync_api_key)
    )
    admin_ok = bool(
        credentials and _admin_credentials_valid(credentials, settings)
    )
    if not (key_ok or admin_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid operational credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
