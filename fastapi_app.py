"""
FastAPI backend: news JSON + PostgreSQL API, static images, Tamil classification.

Run either:
  cd <repo_root>   && uvicorn tamilwin_scraper.fastapi_app:app --reload --port 4000
  cd tamilwin_scraper && uvicorn fastapi_app:app --reload --port 4000
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import subprocess
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Any, Optional

# So `uvicorn fastapi_app:app` works when the shell cwd is tamilwin_scraper/
_pkg_dir = os.path.dirname(os.path.abspath(__file__))
_repo_root = os.path.dirname(_pkg_dir)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

import psycopg2
import secrets
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from tamilwin_scraper.classifier import classify_article_for_pipeline, diagnose_classifier

DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:12345@localhost:5432/news_techorin",
)

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "admin")

PACKAGE_ROOT = os.path.dirname(os.path.abspath(__file__))
IMAGE_DIR = os.path.join(PACKAGE_ROOT, "image")
NEWS_JSON = os.path.join(PACKAGE_ROOT, "news.json")
RUN_ALL_PATH = os.path.join(PACKAGE_ROOT, "run_all.py")

SCRAPE_INTERVAL_SECONDS = int(os.environ.get("SCRAPE_INTERVAL_SECONDS", "900"))
ENABLE_SCRAPE_SCHEDULER = os.environ.get("ENABLE_SCRAPE_SCHEDULER", "1") != "0"


def _run_scraper_once() -> None:
    if not os.path.isfile(RUN_ALL_PATH):
        return
    try:
        print("[scheduler] Starting scraper run_all.py")
        subprocess.run(
            [sys.executable, RUN_ALL_PATH],
            cwd=PACKAGE_ROOT,
            check=False,
        )
        print("[scheduler] Finished scraper run_all.py")
    except Exception:
        print("[scheduler] Scraper run_all.py failed")
        pass


async def _scrape_scheduler() -> None:
    while True:
        await asyncio.to_thread(_run_scraper_once)
        await asyncio.sleep(max(60, SCRAPE_INTERVAL_SECONDS))


def _ensure_schema(conn) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS news (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            url TEXT UNIQUE NOT NULL,
            image_path TEXT DEFAULT '',
            full_text TEXT DEFAULT '',
            source TEXT DEFAULT '',
            category_ta TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT NOW()
        )
        """
    )
    for stmt in (
        "ALTER TABLE news ADD COLUMN IF NOT EXISTS source TEXT DEFAULT ''",
        "ALTER TABLE news ADD COLUMN IF NOT EXISTS category_ta TEXT DEFAULT ''",
        "ALTER TABLE news ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending'",
    ):
        try:
            cur.execute(stmt)
        except Exception:
            pass
    conn.commit()
    cur.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(IMAGE_DIR, exist_ok=True)
    try:
        conn = psycopg2.connect(DB_URL)
        _ensure_schema(conn)
        conn.close()
    except Exception:
        pass
    task: Optional[asyncio.Task] = None
    if ENABLE_SCRAPE_SCHEDULER:
        print(f"[scheduler] Enabled. Interval: {SCRAPE_INTERVAL_SECONDS}s")
        task = asyncio.create_task(_scrape_scheduler())
    yield
    if task:
        task.cancel()


app = FastAPI(title="Tamil News API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if os.path.isdir(IMAGE_DIR):
    app.mount("/images", StaticFiles(directory=IMAGE_DIR), name="images")

security = HTTPBasic()


def require_admin(credentials: HTTPBasicCredentials = Depends(security)) -> None:
    user_ok = secrets.compare_digest(credentials.username, ADMIN_USER)
    pass_ok = secrets.compare_digest(credentials.password, ADMIN_PASS)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=401,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )


def to_image_url(image_path: str) -> str:
    if not image_path:
        return ""
    return f"/images/{os.path.basename(image_path)}"


def db_conn():
    return psycopg2.connect(DB_URL)


def json_datetime(value: Any) -> Optional[str]:
    """PostgreSQL timestamps → ISO strings for reliable JSON in the browser."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


class ClassifyRequest(BaseModel):
    text: Optional[str] = None
    full_text: Optional[str] = None

    def snippet_source(self) -> str:
        t = self.text or self.full_text or ""
        return t


class ClassifyResponse(BaseModel):
    category_ta: str = Field(default="")


class AdminNewsUpdate(BaseModel):
    title: Optional[str] = None
    url: Optional[str] = None
    image_path: Optional[str] = None
    image: Optional[str] = None
    full_text: Optional[str] = None
    source: Optional[str] = None
    category_ta: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[str] = None


def _normalize_status(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    val = raw.strip().lower()
    if val in ("pending", "approved", "rejected"):
        return val
    raise HTTPException(status_code=400, detail="Invalid status value")


@app.get("/api/classifier/diagnose")
def api_classifier_diagnose():
    """Why categories may be empty: paths tried, load errors, keyword fallback env."""
    return diagnose_classifier()


@app.post("/api/classify", response_model=ClassifyResponse)
def api_classify(body: ClassifyRequest) -> ClassifyResponse:
    raw = body.snippet_source()
    if not raw.strip():
        return ClassifyResponse(category_ta="")
    return ClassifyResponse(category_ta=classify_article_for_pipeline(raw))


@app.get("/api/news")
def api_news_list(
    source: Optional[str] = None,
    category_ta: Optional[str] = None,
):
    try:
        conn = db_conn()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    try:
        cur = conn.cursor()
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
        where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
        cur.execute(
            f"""
            SELECT id, title, image_path, source, category_ta, created_at
            FROM news
            {where_sql}
            ORDER BY created_at DESC, id DESC
            """,
            params,
        )
        rows = cur.fetchall()
        cur.close()
        return [
            {
                "id": r[0],
                "title": r[1],
                "image": to_image_url(r[2] or ""),
                "source": r[3] or "unknown",
                "category_ta": r[4] or "",
                "created_at": json_datetime(r[5]) or "",
            }
            for r in rows
        ]
    finally:
        conn.close()


@app.get("/api/news/{article_id:int}")
def api_news_detail(article_id: int):
    try:
        conn = db_conn()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, title, url, image_path, full_text, source, category_ta, created_at
            FROM news WHERE id = %s AND status = 'approved'
            """,
            (article_id,),
        )
        row = cur.fetchone()
        cur.close()
        if not row:
            raise HTTPException(status_code=404, detail="Article not found")
        return {
            "id": row[0],
            "title": row[1],
            "url": row[2],
            "image": to_image_url(row[3] or ""),
            "full_text": row[4] or "",
            "source": row[5] or "unknown",
            "category_ta": row[6] or "",
            "created_at": json_datetime(row[7]) or "",
        }
    finally:
        conn.close()


@app.post("/api/sync")
def api_sync():
    if not os.path.exists(NEWS_JSON):
        raise HTTPException(status_code=404, detail="news.json not found")
    try:
        with open(NEWS_JSON, "r", encoding="utf-8") as f:
            items = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise HTTPException(status_code=500, detail=f"Invalid news.json: {e}")

    inserted = updated = failed = 0

    try:
        conn = db_conn()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    try:
        _ensure_schema(conn)
        cur = conn.cursor()
        for item in items:
            try:
                title = item.get("title") or ""
                url = item.get("url") or ""
                image_path = item.get("image_path") or ""
                full_text = item.get("full_text") or ""
                src = item.get("source") or "unknown"
                category_ta = classify_article_for_pipeline(full_text, title)
                cur.execute(
                    """
                    INSERT INTO news (title, url, image_path, full_text, source, category_ta, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (url) DO UPDATE SET
                        title = EXCLUDED.title,
                        image_path = EXCLUDED.image_path,
                        full_text = EXCLUDED.full_text,
                        source = EXCLUDED.source,
                        category_ta = EXCLUDED.category_ta,
                        status = news.status
                    RETURNING (xmax = 0) AS is_insert
                    """,
                    (title, url, image_path, full_text, src, category_ta, "pending"),
                )
                if cur.fetchone()[0]:
                    inserted += 1
                else:
                    updated += 1
                conn.commit()
            except Exception:
                conn.rollback()
                failed += 1
        cur.close()
    finally:
        conn.close()

    return {"total": len(items), "inserted": inserted, "updated": updated, "failed": failed}


@app.post("/api/reclassify")
def api_reclassify():
    """
    Re-label every PostgreSQL row from full_text (ML + optional keyword fallback).
    """
    try:
        conn = db_conn()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    updated = 0
    errors = 0
    rows: list[Any] = []
    try:
        _ensure_schema(conn)
        cur = conn.cursor()
        cur.execute("SELECT id, title, full_text FROM news ORDER BY id")
        rows = list(cur.fetchall())
        for row_id, title, full_text in rows:
            try:
                cat = classify_article_for_pipeline(full_text or "", title or "")
                cur.execute(
                    "UPDATE news SET category_ta = %s WHERE id = %s",
                    (cat, row_id),
                )
                updated += 1
            except Exception:
                errors += 1
        conn.commit()
        cur.close()
    finally:
        conn.close()
    return {"rows_seen": len(rows), "updated": updated, "errors": errors}


@app.get("/api/admin/news", dependencies=[Depends(require_admin)])
def api_admin_news_list(status: Optional[str] = None):
    status_norm = _normalize_status(status)
    try:
        conn = db_conn()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    try:
        cur = conn.cursor()
        where_parts: list[str] = []
        params: list[Any] = []
        if status_norm:
            where_parts.append("status = %s")
            params.append(status_norm)
        where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
        cur.execute(
            f"""
            SELECT id, title, url, image_path, full_text, source, category_ta, status, created_at
            FROM news
            {where_sql}
            ORDER BY created_at DESC, id DESC
            """,
            params,
        )
        rows = cur.fetchall()
        cur.close()
        return [
            {
                "id": r[0],
                "title": r[1],
                "url": r[2],
                "image": to_image_url(r[3] or ""),
                "image_path": r[3] or "",
                "full_text": r[4] or "",
                "source": r[5] or "unknown",
                "category_ta": r[6] or "",
                "status": r[7] or "pending",
                "created_at": json_datetime(r[8]) or "",
            }
            for r in rows
        ]
    finally:
        conn.close()


@app.get("/api/admin/news/{article_id:int}", dependencies=[Depends(require_admin)])
def api_admin_news_detail(article_id: int):
    try:
        conn = db_conn()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, title, url, image_path, full_text, source, category_ta, status, created_at
            FROM news WHERE id = %s
            """,
            (article_id,),
        )
        row = cur.fetchone()
        cur.close()
        if not row:
            raise HTTPException(status_code=404, detail="Article not found")
        return {
            "id": row[0],
            "title": row[1],
            "url": row[2],
            "image": to_image_url(row[3] or ""),
            "image_path": row[3] or "",
            "full_text": row[4] or "",
            "source": row[5] or "unknown",
            "category_ta": row[6] or "",
            "status": row[7] or "pending",
            "created_at": json_datetime(row[8]) or "",
        }
    finally:
        conn.close()


@app.put("/api/admin/news/{article_id:int}", dependencies=[Depends(require_admin)])
def api_admin_news_update(article_id: int, body: AdminNewsUpdate):
    status_norm = _normalize_status(body.status) if body.status is not None else None
    updates: list[str] = []
    params: list[Any] = []

    def add(field: str, value: Any) -> None:
        updates.append(f"{field} = %s")
        params.append(value)

    if body.title is not None:
        add("title", body.title)
    if body.url is not None:
        add("url", body.url)
    image_path = body.image_path if body.image_path is not None else body.image
    if image_path is not None:
        add("image_path", image_path)
    if body.full_text is not None:
        add("full_text", body.full_text)
    if body.source is not None:
        add("source", body.source)
    if body.category_ta is not None:
        add("category_ta", body.category_ta)
    if body.created_at is not None:
        add("created_at", body.created_at)
    if status_norm is not None:
        add("status", status_norm)

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    try:
        conn = db_conn()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    try:
        cur = conn.cursor()
        params.append(article_id)
        cur.execute(
            f"UPDATE news SET {', '.join(updates)} WHERE id = %s",
            params,
        )
        if cur.rowcount == 0:
            conn.rollback()
            raise HTTPException(status_code=404, detail="Article not found")
        conn.commit()
        cur.close()
        return {"ok": True}
    finally:
        conn.close()


@app.post("/api/admin/news/{article_id:int}/approve", dependencies=[Depends(require_admin)])
def api_admin_approve(article_id: int):
    return api_admin_news_update(article_id, AdminNewsUpdate(status="approved"))


@app.post("/api/admin/news/{article_id:int}/reject", dependencies=[Depends(require_admin)])
def api_admin_reject(article_id: int):
    return api_admin_news_update(article_id, AdminNewsUpdate(status="rejected"))
