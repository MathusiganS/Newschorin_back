from __future__ import annotations

from typing import Any, Iterable, Optional

from psycopg2.extensions import connection

from app.utils.datetime import json_datetime
from app.utils.images import to_image_url


class NewsRepository:
    def __init__(self, conn: connection) -> None:
        self.conn = conn

    def list_public(
        self,
        source: Optional[str] = None,
        category_ta: Optional[str] = None,
        search: Optional[str] = None,
        sort: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        where_sql, params = self._public_filters(source, category_ta, search)
        order_sql = "ORDER BY created_at DESC, id DESC"
        if (sort or "").lower() in {"trending", "popular", "views"}:
            order_sql = "ORDER BY view_count DESC, created_at DESC, id DESC"
        bounded_limit = max(1, min(limit or 20, 100))
        bounded_offset = max(0, offset or 0)
        params.extend([bounded_limit, bounded_offset])

        with self.conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, title, image_path, source, category_ta, created_at,
                       view_count, full_text
                FROM news
                {where_sql}
                {order_sql}
                LIMIT %s OFFSET %s
                """,
                params,
            )
            rows = cursor.fetchall()
        return [self._public_list_row(row) for row in rows]

    def count_public(
        self,
        source: Optional[str] = None,
        category_ta: Optional[str] = None,
        search: Optional[str] = None,
    ) -> int:
        where_sql, params = self._public_filters(source, category_ta, search)
        with self.conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT COUNT(*)
                FROM news
                {where_sql}
                """,
                params,
            )
            row = cursor.fetchone()
        return int(row[0] if row else 0)

    def list_popular(self, limit: int = 4) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(limit, 20))
        with self.conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, title, image_path, source, category_ta, created_at,
                       view_count
                FROM news
                WHERE status = 'approved'
                ORDER BY view_count DESC, created_at DESC, id DESC
                LIMIT %s
                """,
                (bounded_limit,),
            )
            rows = cursor.fetchall()
        return [self._popular_row(row) for row in rows]

    def get_public_detail(self, article_id: int) -> Optional[dict[str, Any]]:
        with self.conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, title, url, image_path, full_text, source,
                       category_ta, created_at, view_count
                FROM news
                WHERE id = %s AND status = 'approved'
                """,
                (article_id,),
            )
            row = cursor.fetchone()
        return self._public_detail_row(row) if row else None

    def increment_view(self, article_id: int) -> Optional[dict[str, Any]]:
        with self.conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE news
                SET view_count = COALESCE(view_count, 0) + 1
                WHERE id = %s AND status = 'approved'
                RETURNING id, title, status, view_count
                """,
                (article_id,),
            )
            row = cursor.fetchone()
        if not row:
            self.conn.rollback()
            return None
        self.conn.commit()
        return {
            "id": row[0],
            "title": row[1] or "",
            "status": row[2] or "",
            "view_count": row[3] or 0,
        }

    def get_existing_source(
        self, url: str
    ) -> Optional[tuple[str, str, str, str]]:
        with self.conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT title, full_text, original_title, original_full_text
                FROM news
                WHERE url = %s
                """,
                (url,),
            )
            return cursor.fetchone()

    def upsert_scraped(
        self,
        *,
        title: str,
        url: str,
        image_path: str,
        full_text: str,
        original_title: str,
        original_full_text: str,
        source: str,
        category_ta: str,
        created_at: Optional[str],
    ) -> bool:
        with self.conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO news (
                    title, url, image_path, full_text, original_title,
                    original_full_text, source, category_ta, status, created_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    COALESCE(%s::timestamp, NOW())
                )
                ON CONFLICT (url) DO UPDATE SET
                    title = EXCLUDED.title,
                    image_path = EXCLUDED.image_path,
                    full_text = EXCLUDED.full_text,
                    original_title = EXCLUDED.original_title,
                    original_full_text = EXCLUDED.original_full_text,
                    source = EXCLUDED.source,
                    category_ta = EXCLUDED.category_ta,
                    status = news.status,
                    created_at = COALESCE(%s::timestamp, news.created_at)
                RETURNING (xmax = 0) AS is_insert
                """,
                (
                    title,
                    url,
                    image_path,
                    full_text,
                    original_title,
                    original_full_text,
                    source,
                    category_ta,
                    "pending",
                    created_at,
                    created_at,
                ),
            )
            inserted = bool(cursor.fetchone()[0])
        self.conn.commit()
        return inserted

    def list_classification_rows(self) -> list[tuple[int, str, str]]:
        with self.conn.cursor() as cursor:
            cursor.execute("SELECT id, title, full_text FROM news ORDER BY id")
            return list(cursor.fetchall())

    def update_category(self, article_id: int, category_ta: str) -> None:
        with self.conn.cursor() as cursor:
            cursor.execute(
                "UPDATE news SET category_ta = %s WHERE id = %s",
                (category_ta, article_id),
            )

    def list_paraphrase_rows(
        self,
    ) -> list[tuple[int, str, str, str, str]]:
        with self.conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, title, full_text, original_title, original_full_text
                FROM news
                ORDER BY id
                """
            )
            return list(cursor.fetchall())

    def update_paraphrased_article(
        self,
        article_id: int,
        title: str,
        full_text: str,
        original_title: str,
        original_full_text: str,
    ) -> None:
        with self.conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE news
                SET title = %s,
                    full_text = %s,
                    original_title = %s,
                    original_full_text = %s
                WHERE id = %s
                """,
                (
                    title,
                    full_text,
                    original_title,
                    original_full_text,
                    article_id,
                ),
            )

    def update_paraphrased_title(
        self, article_id: int, title: str, original_title: str
    ) -> None:
        with self.conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE news
                SET title = %s,
                    original_title = %s
                WHERE id = %s
                """,
                (title, original_title, article_id),
            )

    def image_path_rows(self) -> list[tuple[int, str]]:
        with self.conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, image_path
                FROM news
                WHERE COALESCE(image_path, '') <> ''
                """
            )
            return list(cursor.fetchall())

    def update_image_path(self, article_id: int, image_path: str) -> None:
        with self.conn.cursor() as cursor:
            cursor.execute(
                "UPDATE news SET image_path = %s WHERE id = %s",
                (image_path, article_id),
            )

    def list_admin(
        self,
        status: Optional[str] = None,
        source: Optional[str] = None,
        category_ta: Optional[str] = None,
        search: Optional[str] = None,
        sort: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        where_sql, params = self._admin_filters(
            status=status,
            source=source,
            category_ta=category_ta,
            search=search,
        )
        order_sql = self._admin_order(sort)
        bounded_limit = max(1, min(limit or 20, 100))
        bounded_offset = max(0, offset or 0)
        params.extend([bounded_limit, bounded_offset])
        with self.conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, title, url, image_path, full_text, source,
                       category_ta, status, created_at, original_title,
                       original_full_text
                FROM news
                {where_sql}
                {order_sql}
                LIMIT %s OFFSET %s
                """,
                params,
            )
            rows = cursor.fetchall()
        return [self._admin_row(row) for row in rows]

    def count_admin(
        self,
        status: Optional[str] = None,
        source: Optional[str] = None,
        category_ta: Optional[str] = None,
        search: Optional[str] = None,
    ) -> int:
        where_sql, params = self._admin_filters(
            status=status,
            source=source,
            category_ta=category_ta,
            search=search,
        )
        with self.conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT COUNT(*)
                FROM news
                {where_sql}
                """,
                params,
            )
            row = cursor.fetchone()
        return int(row[0] if row else 0)

    def get_admin_detail(self, article_id: int) -> Optional[dict[str, Any]]:
        with self.conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, title, url, image_path, full_text, source,
                       category_ta, status, created_at, original_title,
                       original_full_text
                FROM news
                WHERE id = %s
                """,
                (article_id,),
            )
            row = cursor.fetchone()
        return self._admin_row(row) if row else None

    def update_admin(
        self,
        article_id: int,
        updates: Iterable[tuple[str, Any]],
    ) -> bool:
        update_list = list(updates)
        assignments = [f"{field} = %s" for field, _ in update_list]
        params = [value for _, value in update_list]
        params.append(article_id)
        with self.conn.cursor() as cursor:
            cursor.execute(
                f"UPDATE news SET {', '.join(assignments)} WHERE id = %s",
                params,
            )
            found = cursor.rowcount > 0
        if found:
            self.conn.commit()
        else:
            self.conn.rollback()
        return found

    def record_sync_error(
        self,
        *,
        url: str,
        original_title: str,
        error_message: str,
    ) -> None:
        with self.conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO sync_errors (url, original_title, error_message)
                VALUES (%s, %s, %s)
                """,
                (
                    url or None,
                    original_title or None,
                    error_message[:2000],
                ),
            )
        self.conn.commit()

    def list_sync_errors(self, resolved: bool = False) -> list[dict[str, Any]]:
        with self.conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, url, original_title, error_message, occurred_at
                FROM sync_errors
                WHERE resolved = %s
                ORDER BY occurred_at DESC
                """,
                (resolved,),
            )
            rows = cursor.fetchall()
        return [
            {
                "id": row[0],
                "url": row[1] or "",
                "original_title": row[2] or "",
                "error_message": row[3] or "",
                "occurred_at": json_datetime(row[4]) or "",
            }
            for row in rows
        ]

    def mark_sync_error_resolved(self, error_id: int) -> None:
        with self.conn.cursor() as cursor:
            cursor.execute(
                "UPDATE sync_errors SET resolved = TRUE WHERE id = %s",
                (error_id,),
            )
        self.conn.commit()

    @staticmethod
    def _public_filters(
        source: Optional[str] = None,
        category_ta: Optional[str] = None,
        search: Optional[str] = None,
    ) -> tuple[str, list[Any]]:
        where_parts: list[str] = []
        params: list[Any] = []
        if source:
            where_parts.append("source = %s")
            params.append(source)
        if category_ta:
            where_parts.append("category_ta = %s")
            params.append(category_ta)
        if search:
            where_parts.append("(title ILIKE %s OR full_text ILIKE %s)")
            like = f"%{search}%"
            params.extend([like, like])
        where_parts.append("status = %s")
        params.append("approved")
        return " WHERE " + " AND ".join(where_parts), params

    @staticmethod
    def _admin_filters(
        status: Optional[str] = None,
        source: Optional[str] = None,
        category_ta: Optional[str] = None,
        search: Optional[str] = None,
    ) -> tuple[str, list[Any]]:
        where_parts: list[str] = []
        params: list[Any] = []
        if status:
            where_parts.append("status = %s")
            params.append(status)
        if source:
            where_parts.append("source = %s")
            params.append(source)
        if category_ta:
            where_parts.append("category_ta = %s")
            params.append(category_ta)
        if search:
            where_parts.append(
                "(title ILIKE %s OR original_title ILIKE %s OR "
                "url ILIKE %s OR source ILIKE %s)"
            )
            like = f"%{search}%"
            params.extend([like, like, like, like])
        if not where_parts:
            return "", params
        return " WHERE " + " AND ".join(where_parts), params

    @staticmethod
    def _admin_order(sort: Optional[str] = None) -> str:
        match (sort or "newest").lower():
            case "oldest" | "created_asc":
                return "ORDER BY created_at ASC, id ASC"
            case "title" | "title_asc":
                return "ORDER BY LOWER(title) ASC, created_at DESC, id DESC"
            case "title_desc":
                return "ORDER BY LOWER(title) DESC, created_at DESC, id DESC"
            case "source" | "source_asc":
                return "ORDER BY LOWER(source) ASC, created_at DESC, id DESC"
            case "status" | "status_asc":
                return "ORDER BY status ASC, created_at DESC, id DESC"
            case _:
                return "ORDER BY created_at DESC, id DESC"

    @staticmethod
    def _public_list_row(row: tuple[Any, ...]) -> dict[str, Any]:
        full_text = (row[7] or "").strip()
        return {
            "id": row[0],
            "title": row[1],
            "image": to_image_url(row[2] or ""),
            "source": row[3] or "unknown",
            "category_ta": row[4] or "",
            "created_at": json_datetime(row[5]) or "",
            "view_count": row[6] or 0,
            "excerpt": full_text[:140] + ("..." if len(full_text) > 140 else ""),
        }

    @staticmethod
    def _popular_row(row: tuple[Any, ...]) -> dict[str, Any]:
        return {
            "id": row[0],
            "title": row[1],
            "image": to_image_url(row[2] or ""),
            "source": row[3] or "unknown",
            "category_ta": row[4] or "",
            "created_at": json_datetime(row[5]) or "",
            "view_count": row[6] or 0,
        }

    @staticmethod
    def _public_detail_row(row: tuple[Any, ...]) -> dict[str, Any]:
        return {
            "id": row[0],
            "title": row[1],
            "url": row[2],
            "image": to_image_url(row[3] or ""),
            "full_text": row[4] or "",
            "source": row[5] or "unknown",
            "category_ta": row[6] or "",
            "created_at": json_datetime(row[7]) or "",
            "view_count": row[8] or 0,
        }

    @staticmethod
    def _admin_row(row: tuple[Any, ...]) -> dict[str, Any]:
        image = to_image_url(row[3] or "")
        return {
            "id": row[0],
            "title": row[1],
            "url": row[2],
            "image": image,
            "image_path": image,
            "full_text": row[4] or "",
            "source": row[5] or "unknown",
            "category_ta": row[6] or "",
            "status": row[7] or "pending",
            "created_at": json_datetime(row[8]) or "",
            "original_title": row[9] or row[1] or "",
            "original_full_text": row[10] or row[4] or "",
        }
