from __future__ import annotations

import logging
from pathlib import Path

from psycopg2.extensions import connection

from app.core.config import get_settings
from app.db.connection import connection_scope
from app.db.schema import ensure_schema
from app.repositories.news_repository import NewsRepository
from app.utils.images import normalize_image_path


logger = logging.getLogger(__name__)


def log_image_directory(prefix: str = "images") -> None:
    settings = get_settings()
    image_dir = settings.image_dir
    logger.info("%s directory=%s exists=%s", prefix, image_dir, image_dir.is_dir())
    if not image_dir.is_dir():
        return
    try:
        files = sorted(path.name for path in image_dir.iterdir() if path.is_file())
    except OSError:
        logger.exception("%s failed to list image directory", prefix)
        return
    logger.info("%s file_count=%s", prefix, len(files))
    for name in files[: settings.image_log_sample_limit]:
        logger.info("%s file=%s", prefix, name)


def normalize_database_image_paths(conn: connection | None = None) -> int:
    if conn is None:
        with connection_scope() as managed_conn:
            ensure_schema(managed_conn)
            return _normalize_with_connection(managed_conn)
    return _normalize_with_connection(conn)


def _normalize_with_connection(conn: connection) -> int:
    repository = NewsRepository(conn)
    updated = 0
    for article_id, image_path in repository.image_path_rows():
        normalized = normalize_image_path(image_path)
        if normalized != image_path:
            repository.update_image_path(article_id, normalized)
            updated += 1
    conn.commit()
    return updated
