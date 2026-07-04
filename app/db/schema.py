from __future__ import annotations

from psycopg2.extensions import connection


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS news (
        id SERIAL PRIMARY KEY,
        title TEXT NOT NULL,
        url TEXT UNIQUE NOT NULL,
        image_path TEXT DEFAULT '',
        full_text TEXT DEFAULT '',
        original_title TEXT DEFAULT '',
        original_full_text TEXT DEFAULT '',
        source TEXT DEFAULT '',
        category_ta TEXT DEFAULT '',
        status TEXT DEFAULT 'pending',
        view_count INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Colombo')
    )
    """,
    "ALTER TABLE news ADD COLUMN IF NOT EXISTS source TEXT DEFAULT ''",
    "ALTER TABLE news ADD COLUMN IF NOT EXISTS category_ta TEXT DEFAULT ''",
    "ALTER TABLE news ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending'",
    "ALTER TABLE news ADD COLUMN IF NOT EXISTS original_title TEXT DEFAULT ''",
    "ALTER TABLE news ADD COLUMN IF NOT EXISTS original_full_text TEXT DEFAULT ''",
    "ALTER TABLE news ADD COLUMN IF NOT EXISTS view_count INTEGER DEFAULT 0",
    (
        "ALTER TABLE news ADD COLUMN IF NOT EXISTS created_at TIMESTAMP "
        "DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Colombo')"
    ),
    (
        "ALTER TABLE news ALTER COLUMN created_at SET DEFAULT "
        "(CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Colombo')"
    ),
    """
    CREATE TABLE IF NOT EXISTS sync_errors (
        id SERIAL PRIMARY KEY,
        url TEXT,
        original_title TEXT,
        error_message TEXT NOT NULL,
        occurred_at TIMESTAMP DEFAULT NOW(),
        resolved BOOLEAN DEFAULT FALSE
    )
    """,
    (
        "CREATE INDEX IF NOT EXISTS idx_sync_errors_resolved "
        "ON sync_errors (resolved, occurred_at DESC)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS idx_sync_errors_url "
        "ON sync_errors (url)"
    ),
)


def ensure_schema(conn: connection) -> None:
    with conn.cursor() as cursor:
        for statement in SCHEMA_STATEMENTS:
            cursor.execute(statement)
    conn.commit()
