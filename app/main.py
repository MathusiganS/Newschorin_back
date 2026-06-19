from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress

import psycopg2
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from tamilwin_scraper.app.api.routes import (
    admin,
    classification,
    news,
    operations,
    system,
)
from tamilwin_scraper.app.core.config import get_settings
from tamilwin_scraper.app.core.exceptions import DatabaseUnavailableError
from tamilwin_scraper.app.core.logging import configure_logging
from tamilwin_scraper.app.db.connection import connection_scope
from tamilwin_scraper.app.db.schema import ensure_schema
from tamilwin_scraper.app.services.image_service import (
    log_image_directory,
    normalize_database_image_paths,
)
from tamilwin_scraper.app.services.scraper_service import scrape_scheduler


configure_logging()
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_security()
    settings.image_dir.mkdir(parents=True, exist_ok=True)
    log_image_directory("startup-images")
    try:
        with connection_scope() as conn:
            ensure_schema(conn)
            normalize_database_image_paths(conn)
    except Exception:
        logger.exception("Database initialization failed during startup")

    scheduler_task: asyncio.Task[None] | None = None
    if settings.enable_scrape_scheduler:
        logger.info(
            "Scraper scheduler enabled interval_seconds=%s",
            settings.scrape_interval_seconds,
        )
        scheduler_task = asyncio.create_task(scrape_scheduler())

    yield

    if scheduler_task:
        scheduler_task.cancel()
        with suppress(asyncio.CancelledError):
            await scheduler_task


def create_app() -> FastAPI:
    application = FastAPI(title=settings.app_name, lifespan=lifespan)
    wildcard_cors = "*" in settings.cors_origins
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=not wildcard_cors,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    settings.image_dir.mkdir(parents=True, exist_ok=True)
    application.mount(
        "/images",
        StaticFiles(directory=str(settings.image_dir)),
        name="images",
    )

    application.include_router(system.router)
    application.include_router(classification.router)
    application.include_router(news.router)
    application.include_router(operations.router)
    application.include_router(admin.router)

    @application.exception_handler(DatabaseUnavailableError)
    async def database_unavailable_handler(
        request: Request, exc: DatabaseUnavailableError
    ) -> JSONResponse:
        logger.error("Database unavailable path=%s", request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Database connection failed"},
        )

    @application.exception_handler(psycopg2.Error)
    async def database_error_handler(
        request: Request, exc: psycopg2.Error
    ) -> JSONResponse:
        logger.exception("Database operation failed path=%s", request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Database operation failed"},
        )

    return application


app = create_app()
