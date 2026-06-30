from __future__ import annotations

from typing import Any, Iterable, Optional

from psycopg2.extensions import connection

from tamilwin_scraper.app.utils.datetime import json_datetime
from tamilwin_scraper.app.utils.images import to_image_url


class NewsRepository:
    def __init__(self, conn: connection) -> None:
        self.conn = conn

    def list_public(
        self,
        source: Optional[str] = None,
        category_ta: Optional[str] = None,
        sort: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        where_parts: list[str] = []
        params: list[Any] = []
        if source:
            where_parts.append("source = %s")
            params.append(source)
        if category_ta:
            where_parts.append("category_ta = %s")
            params.append(category_ta)
        where_parts.append("status = %s")
        params.append("approved")
        where_sql = " WHERE " + " AND ".join(where_parts)
        order_sql = "ORDER BY created_at DESC, id DESC"
        if (sort or "").lower() in {"trending", "popular", "views"}:
            order_sql = "ORDER BY view_count DESC, created_at DESC, id DESC"
        limit_sql = ""
        if limit is not None:
            limit_sql = "LIMIT %s"
            params.append(max(1, min(limit, 100)))

        with self.conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, title, image_path, source, category_ta, created_at,
                       view_count, full_text
                FROM news
                {where_sql}
                {order_sql}
                {limit_sql}
                """,
                params,
            )
            rows = cursor.fetchall()
        return [self._public_list_row(row) for row in rows]

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

    def list_admin(self, status: Optional[str] = None) -> list[dict[str, Any]]:
        where_sql = ""
        params: list[Any] = []
        if status:
            where_sql = " WHERE status = %s"
            params.append(status)
        with self.conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, title, url, image_path, full_text, source,
                       category_ta, status, created_at, original_title,
                       original_full_text
                FROM news
                {where_sql}
                ORDER BY created_at DESC, id DESC
                """,
                params,
            )
            rows = cursor.fetchall()
        return [self._admin_row(row) for row in rows]

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
