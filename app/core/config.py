from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from tamilwin_scraper.env import load_env_file


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _env_int(name: str, default: int, minimum: int | None = None) -> int:
    raw = os.environ.get(name)
    value = int(raw) if raw is not None else default
    return max(minimum, value) if minimum is not None else value


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw is not None else default


def _env_list(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.environ.get(name)
    if not raw:
        return default
    values = tuple(value.strip() for value in raw.split(",") if value.strip())
    return values or default


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_env: str
    database_url: str
    admin_user: str
    admin_password: str
    admin_password_hash: str
    sync_api_key: str
    jwt_secret: str
    jwt_algorithm: str
    jwt_expire_minutes: int
    cookie_name: str
    cookie_secure: bool
    cors_origins: tuple[str, ...]
    gemini_api_key: str
    gemini_model: str
    gemini_temperature: float
    gemini_top_p: float
    gemini_max_output_tokens: int
    gemini_max_attempts: int
    scrape_interval_seconds: int
    sync_request_timeout_seconds: int
    enable_scrape_scheduler: bool
    image_log_sample_limit: int
    playwright_install_on_start: bool
    package_root: Path
    image_dir: Path
    news_json: Path
    run_all_path: Path

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}

    @property
    def allow_default_credentials(self) -> bool:
        return not self.is_production

    def validate_security(self) -> None:
        if not self.is_production:
            return
        insecure_admin = (
            self.admin_user == "admin"
            or (
                not self.admin_password_hash
                and self.admin_password == "admin"
            )
        )
        if insecure_admin:
            raise RuntimeError(
                "Production requires non-default admin credentials."
            )
        if not self.jwt_secret:
            raise RuntimeError(
                "Production requires JWT_SECRET for admin cookie sessions."
            )
        if "postgres:12345@" in self.database_url:
            raise RuntimeError(
                "Production requires DATABASE_URL without the development password."
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_env_file()
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")

    package_root = Path(__file__).resolve().parents[2]
    app_env = os.environ.get("APP_ENV", "development")
    cookie_secure_default = app_env.lower() in {"production", "prod"}
    gemini_model = (
        os.environ.get("GEMINI_MODEL")
        or os.environ.get("model")
        or "gemini-2.5-flash-lite"
    )
    gemini_temperature = float(
        os.environ.get("GEMINI_TEMPERATURE")
        or os.environ.get("temperature")
        or "0.3"
    )
    gemini_top_p = float(
        os.environ.get("GEMINI_TOP_P") or os.environ.get("topP") or "0.8"
    )
    gemini_max_output_tokens = int(
        os.environ.get("GEMINI_MAX_OUTPUT_TOKENS")
        or os.environ.get("maxOutputTokens")
        or "1200"
    )

    return Settings(
        app_name=os.environ.get("APP_NAME", "Tamil News API"),
        app_env=app_env,
        database_url=os.environ.get(
            "DATABASE_URL",
            "postgresql://postgres:12345@localhost:5432/news_techorin",
        ),
        admin_user=os.environ.get("ADMIN_USER", "admin"),
        admin_password=os.environ.get("ADMIN_PASS", "admin"),
        admin_password_hash=os.environ.get("ADMIN_PASSWORD_HASH", ""),
        sync_api_key=os.environ.get("SYNC_API_KEY", ""),
        jwt_secret=os.environ.get("JWT_SECRET", ""),
        jwt_algorithm=os.environ.get("JWT_ALGORITHM", "HS256"),
        jwt_expire_minutes=_env_int("JWT_EXPIRE_MINUTES", 480, minimum=1),
        cookie_name=os.environ.get("COOKIE_NAME", "admin_session"),
        cookie_secure=_env_bool("COOKIE_SECURE", cookie_secure_default),
        cors_origins=_env_list(
            "CORS_ORIGINS",
            ("http://localhost:5173", "http://127.0.0.1:5173"),
        ),
        gemini_api_key=os.environ.get("GEMINI_API_KEY", ""),
        gemini_model=gemini_model,
        gemini_temperature=gemini_temperature,
        gemini_top_p=gemini_top_p,
        gemini_max_output_tokens=gemini_max_output_tokens,
        gemini_max_attempts=_env_int("GEMINI_MAX_ATTEMPTS", 2, minimum=1),
        scrape_interval_seconds=_env_int(
            "SCRAPE_INTERVAL_SECONDS", 900, minimum=60
        ),
        sync_request_timeout_seconds=_env_int(
            "SYNC_REQUEST_TIMEOUT_SECONDS", 600, minimum=60
        ),
        enable_scrape_scheduler=_env_bool("ENABLE_SCRAPE_SCHEDULER", True),
        image_log_sample_limit=_env_int(
            "IMAGE_LOG_SAMPLE_LIMIT", 25, minimum=0
        ),
        playwright_install_on_start=_env_bool(
            "PLAYWRIGHT_INSTALL_ON_START", True
        ),
        package_root=package_root,
        image_dir=package_root / "image",
        news_json=package_root / "news.json",
        run_all_path=package_root / "run_all.py",
    )
