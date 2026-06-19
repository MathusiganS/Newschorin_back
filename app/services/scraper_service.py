from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
from contextlib import contextmanager
from typing import Iterator

from psycopg2.extensions import connection

from tamilwin_scraper.app.core.config import get_settings
from tamilwin_scraper.app.db.connection import connect
from tamilwin_scraper.app.services.image_service import log_image_directory
from tamilwin_scraper.app.services.sync_service import sync_news_json


logger = logging.getLogger(__name__)
SCHEDULER_LOCK_ID = 912_406_031


@contextmanager
def _scheduler_lock() -> Iterator[bool]:
    conn: connection | None = None
    acquired = False
    try:
        conn = connect()
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT pg_try_advisory_lock(%s)", (SCHEDULER_LOCK_ID,)
            )
            acquired = bool(cursor.fetchone()[0])
    except Exception:
        logger.exception(
            "Unable to obtain scheduler advisory lock; continuing without it"
        )
        yield True
        return

    try:
        yield acquired
    finally:
        if conn is not None:
            if acquired:
                try:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            "SELECT pg_advisory_unlock(%s)",
                            (SCHEDULER_LOCK_ID,),
                        )
                except Exception:
                    logger.exception("Unable to release scheduler advisory lock")
            conn.close()


def run_scraper_once() -> None:
    settings = get_settings()
    if not settings.run_all_path.is_file():
        logger.warning("Scraper entry point does not exist: %s", settings.run_all_path)
        return
    with _scheduler_lock() as acquired:
        if not acquired:
            logger.info("Skipping scraper run because another worker owns the lock")
            return
        try:
            logger.info("Starting scheduled scraper")
            log_image_directory("scheduler-images-before")
            env = os.environ.copy()
            env.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")
            env["SKIP_API_SYNC"] = "1"
            if settings.playwright_install_on_start:
                subprocess.run(
                    [sys.executable, "-m", "playwright", "install", "chromium"],
                    cwd=settings.package_root,
                    env=env,
                    check=False,
                )
            result = subprocess.run(
                [sys.executable, str(settings.run_all_path)],
                cwd=settings.package_root,
                env=env,
                check=False,
            )
            if result.returncode == 0:
                sync_result = sync_news_json()
                logger.info(
                    "Scheduled scraper database sync completed result=%s",
                    sync_result,
                )
            else:
                logger.error(
                    "Skipping database sync because scraper exited with code=%s",
                    result.returncode,
                )
            log_image_directory("scheduler-images-after")
            logger.info("Scheduled scraper finished")
        except Exception:
            logger.exception("Scheduled scraper failed")


async def scrape_scheduler() -> None:
    settings = get_settings()
    while True:
        await asyncio.to_thread(run_scraper_once)
        await asyncio.sleep(settings.scrape_interval_seconds)
