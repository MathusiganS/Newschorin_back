from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import psycopg2
from psycopg2.extensions import connection

from tamilwin_scraper.app.core.config import get_settings
from tamilwin_scraper.app.core.exceptions import DatabaseUnavailableError


def connect() -> connection:
    try:
        return psycopg2.connect(get_settings().database_url)
    except Exception as exc:
        raise DatabaseUnavailableError("Database connection failed") from exc


@contextmanager
def connection_scope() -> Iterator[connection]:
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()
