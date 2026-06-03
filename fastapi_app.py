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
import requests
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

from tamilwin_scraper.env import load_env_file
from tamilwin_scraper.classifier import classify_article_for_pipeline, diagnose_classifier

load_env_file()
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")

DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:12345@localhost:5432/news_techorin",
)

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "admin")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL") or os.environ.get("model", "gemini-2.5-flash-lite")
GEMINI_TEMPERATURE = float(os.environ.get("GEMINI_TEMPERATURE") or os.environ.get("temperature", "0.3"))
GEMINI_TOP_P = float(os.environ.get("GEMINI_TOP_P") or os.environ.get("topP", "0.8"))
GEMINI_MAX_OUTPUT_TOKENS = int(os.environ.get("GEMINI_MAX_OUTPUT_TOKENS") or os.environ.get("maxOutputTokens", "1200"))

PACKAGE_ROOT = os.path.dirname(os.path.abspath(__file__))
IMAGE_DIR = os.path.join(PACKAGE_ROOT, "image")
NEWS_JSON = os.path.join(PACKAGE_ROOT, "news.json")
RUN_ALL_PATH = os.path.join(PACKAGE_ROOT, "run_all.py")

SCRAPE_INTERVAL_SECONDS = int(os.environ.get("SCRAPE_INTERVAL_SECONDS", "900"))
ENABLE_SCRAPE_SCHEDULER = os.environ.get("ENABLE_SCRAPE_SCHEDULER", "1") != "0"
IMAGE_LOG_SAMPLE_LIMIT = int(os.environ.get("IMAGE_LOG_SAMPLE_LIMIT", "25"))
PLAYWRIGHT_INSTALL_ON_START = os.environ.get("PLAYWRIGHT_INSTALL_ON_START", "1") != "0"


def _log_image_dir(prefix: str = "[images]") -> None:
    exists = os.path.isdir(IMAGE_DIR)
    print(f"{prefix} IMAGE_DIR={IMAGE_DIR}")
    print(f"{prefix} exists={exists}")
    if not exists:
        return
    try:
        files = sorted(
            name
            for name in os.listdir(IMAGE_DIR)
            if os.path.isfile(os.path.join(IMAGE_DIR, name))
        )
    except OSError as e:
        print(f"{prefix} list failed: {e}")
        return
    print(f"{prefix} file_count={len(files)}")
    for name in files[:IMAGE_LOG_SAMPLE_LIMIT]:
        print(f"{prefix} file={name}")
    if len(files) > IMAGE_LOG_SAMPLE_LIMIT:
        print(f"{prefix} ... {len(files) - IMAGE_LOG_SAMPLE_LIMIT} more files")


def _run_scraper_once() -> None:
    if not os.path.isfile(RUN_ALL_PATH):
        return
    try:
        print("[scheduler] Starting scraper run_all.py")
        _log_image_dir("[scheduler images before]")
        env = os.environ.copy()
        env.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")
        if PLAYWRIGHT_INSTALL_ON_START:
            print("[scheduler] Ensuring Playwright Chromium is installed")
            subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                cwd=PACKAGE_ROOT,
                env=env,
                check=False,
            )
        subprocess.run(
            [sys.executable, RUN_ALL_PATH],
            cwd=PACKAGE_ROOT,
            env=env,
            check=False,
        )
        _log_image_dir("[scheduler images after]")
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
            original_title TEXT DEFAULT '',
            original_full_text TEXT DEFAULT '',
            source TEXT DEFAULT '',
            category_ta TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            view_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """
    )
    for stmt in (
        "ALTER TABLE news ADD COLUMN IF NOT EXISTS source TEXT DEFAULT ''",
        "ALTER TABLE news ADD COLUMN IF NOT EXISTS category_ta TEXT DEFAULT ''",
        "ALTER TABLE news ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending'",
        "ALTER TABLE news ADD COLUMN IF NOT EXISTS original_title TEXT DEFAULT ''",
        "ALTER TABLE news ADD COLUMN IF NOT EXISTS original_full_text TEXT DEFAULT ''",
        "ALTER TABLE news ADD COLUMN IF NOT EXISTS view_count INTEGER DEFAULT 0",
        "ALTER TABLE news ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW()",
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
    _log_image_dir("[startup images]")
    try:
        conn = psycopg2.connect(DB_URL)
        _ensure_schema(conn)
        _normalize_db_image_paths(conn)
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

os.makedirs(IMAGE_DIR, exist_ok=True)
app.mount("/images", StaticFiles(directory=IMAGE_DIR), name="images")

security = HTTPBasic()


@app.get("/")
def api_root():
    return {
        "ok": True,
        "service": "Tamil News API",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
def api_health():
    return {"ok": True}


def require_admin(credentials: HTTPBasicCredentials = Depends(security)) -> None:
    user_ok = secrets.compare_digest(credentials.username, ADMIN_USER)
    pass_ok = secrets.compare_digest(credentials.password, ADMIN_PASS)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=401,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )


def normalize_image_path(image_path: str) -> str:
    if not image_path:
        return ""
    if image_path.startswith(("http://", "https://")):
        return image_path
    filename = image_path.replace("\\", "/").rstrip("/").split("/")[-1]
    return f"/images/{filename}" if filename else ""


def to_image_url(image_path: str) -> str:
    normalized = normalize_image_path(image_path)
    if normalized.startswith("/images/"):
        filename = normalized.rsplit("/", 1)[-1]
        if not os.path.isfile(os.path.join(IMAGE_DIR, filename)):
            return ""
    return normalized


def _normalize_db_image_paths(conn) -> int:
    updated = 0
    cur = conn.cursor()
    cur.execute("SELECT id, image_path FROM news WHERE COALESCE(image_path, '') <> ''")
    rows = cur.fetchall()
    for row_id, image_path in rows:
        normalized = normalize_image_path(image_path)
        if normalized != image_path:
            cur.execute(
                "UPDATE news SET image_path = %s WHERE id = %s",
                (normalized, row_id),
            )
            updated += 1
    conn.commit()
    cur.close()
    return updated


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


def parse_scraped_datetime(value: Any) -> Optional[str]:
    """Return a DB-friendly timestamp string from scraper JSON, or None."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time()).isoformat()
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).isoformat()
    except ValueError:
        return None


def _paraphrase_tamil_news(title: str, full_text: str) -> tuple[str, str, bool]:
    if not GEMINI_API_KEY or (not title and not full_text):
        if not GEMINI_API_KEY:
            print("[paraphrase] skipped: GEMINI_API_KEY is not configured")
        return title, full_text, False

    prompt = f"""
Paraphrase the following Tamil news title and full text without changing the original meaning.

Rules:
1. Do not change names, dates, numbers, locations, organizations, or quotes.
2. Do not add new information.
3. Rewrite the title as a fresh Tamil news headline. Do not copy the original title word-for-word.
4. Keep the title concise, natural, professional, and suitable for a news website.
5. Keep the title meaning exactly the same as the original.
6. Keep the body text professional and suitable for a news website.
7. Return only valid JSON with exactly these keys: title, full_text.

Original title:
{title}

Original full_text:
{full_text}
""".strip()
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": GEMINI_TEMPERATURE,
            "topP": GEMINI_TOP_P,
            "maxOutputTokens": GEMINI_MAX_OUTPUT_TOKENS,
            "responseMimeType": "application/json",
        },
    }
    try:
        resp = requests.post(url, json=payload, timeout=45)
        resp.raise_for_status()
        data = resp.json()
        text = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )
        if text.strip().startswith("```"):
            text = text.strip().strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
        parsed = json.loads(text)
        new_title = str(parsed.get("title") or title).strip()
        new_full_text = str(parsed.get("full_text") or full_text).strip()
        if _titles_too_similar(title, new_title):
            new_title = _paraphrase_tamil_title(title, full_text)
        print("[paraphrase] completed")
        return new_title or title, new_full_text or full_text, True
    except Exception as e:
        print(f"[paraphrase] skipped: {e}")
        return title, full_text, False


def _titles_too_similar(original: str, rewritten: str) -> bool:
    original_norm = " ".join((original or "").split()).strip()
    rewritten_norm = " ".join((rewritten or "").split()).strip()
    if not original_norm or not rewritten_norm:
        return True
    if original_norm == rewritten_norm:
        return True
    original_words = set(original_norm.split())
    rewritten_words = set(rewritten_norm.split())
    if not original_words:
        return True
    overlap = len(original_words & rewritten_words) / max(1, len(original_words))
    return overlap >= 0.85


def _paraphrase_tamil_title(title: str, full_text: str = "") -> str:
    if not GEMINI_API_KEY or not title:
        return title

    context = (full_text or "").strip()
    if len(context) > 1200:
        context = context[:1200]
    prompt = f"""
Rewrite only this Tamil news title as a fresh headline.

Rules:
1. Preserve the same facts, names, dates, numbers, places, and meaning.
2. Do not add any new information.
3. Do not copy the original wording.
4. Keep it natural, professional, and concise for a Tamil news website.
5. Return only valid JSON with exactly this key: title.

Original title:
{title}

Article context:
{context}
""".strip()
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": max(GEMINI_TEMPERATURE, 0.45),
            "topP": GEMINI_TOP_P,
            "maxOutputTokens": 220,
            "responseMimeType": "application/json",
        },
    }
    try:
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        text = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )
        if text.strip().startswith("```"):
            text = text.strip().strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
        parsed = json.loads(text)
        new_title = str(parsed.get("title") or "").strip()
        if new_title and not _titles_too_similar(title, new_title):
            print("[paraphrase:title] completed")
            return new_title
        print("[paraphrase:title] kept original: title rewrite too similar")
        return new_title or title
    except Exception as e:
        print(f"[paraphrase:title] skipped: {e}")
        return title


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


@app.get("/api/admin/paraphrase-status", dependencies=[Depends(require_admin)])
def api_admin_paraphrase_status():
    return {
        "gemini_api_key_configured": bool(GEMINI_API_KEY),
        "model": GEMINI_MODEL,
        "temperature": GEMINI_TEMPERATURE,
        "topP": GEMINI_TOP_P,
        "maxOutputTokens": GEMINI_MAX_OUTPUT_TOKENS,
    }


@app.get("/api/news")
def api_news_list(
    source: Optional[str] = None,
    category_ta: Optional[str] = None,
    sort: Optional[str] = None,
    limit: Optional[int] = None,
):
    try:
        conn = db_conn()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    try:
        _ensure_schema(conn)
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
        order_sql = "ORDER BY created_at DESC, id DESC"
        if (sort or "").lower() in {"trending", "popular", "views"}:
            order_sql = "ORDER BY view_count DESC, created_at DESC, id DESC"
        limit_sql = ""
        if limit is not None:
            limit_sql = "LIMIT %s"
            params.append(max(1, min(limit, 100)))
        cur.execute(
            f"""
            SELECT id, title, image_path, source, category_ta, created_at, view_count, full_text
            FROM news
            {where_sql}
            {order_sql}
            {limit_sql}
            """,
            params,
        )
        rows = cur.fetchall()
        cur.close()
        if (sort or "").lower() in {"trending", "popular", "views"}:
            print(
                "[trending] /api/news sort=%s limit=%s -> %s"
                % (
                    sort,
                    limit,
                    [
                        {
                            "id": row[0],
                            "views": row[6] or 0,
                            "title": (row[1] or "")[:60],
                        }
                        for row in rows
                    ],
                ),
                flush=True,
            )
        return [
            {
                "id": r[0],
                "title": r[1],
                "image": to_image_url(r[2] or ""),
                "source": r[3] or "unknown",
                "category_ta": r[4] or "",
                "created_at": json_datetime(r[5]) or "",
                "view_count": r[6] or 0,
                "excerpt": ((r[7] or "").strip()[:140] + ("..." if len((r[7] or "").strip()) > 140 else "")),
            }
            for r in rows
        ]
    finally:
        conn.close()


def _popular_news(limit: int = 4) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 20))
    try:
        conn = db_conn()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    try:
        _ensure_schema(conn)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, title, image_path, source, category_ta, created_at, view_count
            FROM news
            WHERE status = 'approved'
            ORDER BY view_count DESC, created_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
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
                "view_count": r[6] or 0,
            }
            for r in rows
        ]
    finally:
        conn.close()


@app.get("/api/news/popular")
def api_news_popular(limit: int = 4):
    rows = _popular_news(limit)
    print(
        "[popular] /api/news/popular limit=%s -> %s"
        % (
            max(1, min(limit, 20)),
            [
                {
                    "id": row["id"],
                    "views": row["view_count"],
                    "title": (row["title"] or "")[:60],
                }
                for row in rows
            ],
        ),
        flush=True,
    )
    return rows


@app.get("/api/news/trending")
def api_news_trending(limit: int = 4):
    return api_news_popular(limit)


def _increment_article_view(article_id: int, event_source: str) -> dict[str, Any]:
    try:
        conn = db_conn()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    try:
        _ensure_schema(conn)
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE news
            SET view_count = COALESCE(view_count, 0) + 1
            WHERE id = %s AND status = 'approved'
            RETURNING id, title, status, view_count
            """,
            (article_id,),
        )
        row = cur.fetchone()
        if not row:
            conn.rollback()
            cur.close()
            print(
                "[view_count] %s missing id=%s"
                % (event_source, article_id),
                flush=True,
            )
            raise HTTPException(status_code=404, detail="Article not found")
        conn.commit()
        cur.close()
        print(
            "[view_count] POST /api/news/%s/view incremented view_count=%s status=%s title=%s"
            % (row[0], row[3] or 0, row[2] or "", (row[1] or "")[:80]),
            flush=True,
        )
        return {"id": row[0], "status": row[2] or "", "view_count": row[3] or 0}
    finally:
        conn.close()


@app.post("/api/news/{article_id:int}/view")
def api_news_track_view(article_id: int):
    return _increment_article_view(article_id, "detail")


@app.get("/api/news/{article_id:int}")
def api_news_detail(article_id: int):
    try:
        conn = db_conn()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    try:
        _ensure_schema(conn)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, title, url, image_path, full_text, source, category_ta, created_at, view_count
            FROM news
            WHERE id = %s AND status = 'approved'
            """,
            (article_id,),
        )
        row = cur.fetchone()
        if not row:
            cur.close()
            raise HTTPException(status_code=404, detail="Article not found")
        cur.close()
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

    inserted = updated = failed = paraphrased = paraphrase_reused = paraphrase_skipped = 0

    try:
        conn = db_conn()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    try:
        _ensure_schema(conn)
        cur = conn.cursor()
        for item in items:
            try:
                original_title = item.get("original_title") or item.get("title") or ""
                url = item.get("url") or ""
                image_path = normalize_image_path(item.get("image_path") or "")
                original_full_text = item.get("original_full_text") or item.get("full_text") or ""
                scraped_created_at = parse_scraped_datetime(item.get("created_at"))
                cur.execute(
                    """
                    SELECT title, full_text, original_title, original_full_text
                    FROM news WHERE url = %s
                    """,
                    (url,),
                )
                existing = cur.fetchone()
                if (
                    existing
                    and (existing[2] or "") == original_title
                    and (existing[3] or "") == original_full_text
                    and (
                        (existing[0] or "") != original_title
                        or (existing[1] or "") != original_full_text
                    )
                ):
                    title = existing[0] or original_title
                    full_text = existing[1] or original_full_text
                    if _titles_too_similar(original_title, title):
                        title = _paraphrase_tamil_title(original_title, full_text)
                    paraphrase_reused += 1
                else:
                    title, full_text, did_paraphrase = _paraphrase_tamil_news(
                        original_title,
                        original_full_text,
                    )
                    if did_paraphrase:
                        paraphrased += 1
                    else:
                        paraphrase_skipped += 1
                src = item.get("source") or "unknown"
                category_ta = classify_article_for_pipeline(original_full_text, original_title)
                cur.execute(
                    """
                    INSERT INTO news (
                        title, url, image_path, full_text, original_title,
                        original_full_text, source, category_ta, status, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, COALESCE(%s::timestamp, NOW()))
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
                        src,
                        category_ta,
                        "pending",
                        scraped_created_at,
                        scraped_created_at,
                    ),
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

    print(
        "[sync] total=%s inserted=%s updated=%s failed=%s paraphrased=%s reused=%s skipped=%s"
        % (
            len(items),
            inserted,
            updated,
            failed,
            paraphrased,
            paraphrase_reused,
            paraphrase_skipped,
        )
    )
    return {
        "total": len(items),
        "inserted": inserted,
        "updated": updated,
        "failed": failed,
        "paraphrased": paraphrased,
        "paraphrase_reused": paraphrase_reused,
        "paraphrase_skipped": paraphrase_skipped,
    }


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


@app.post("/api/admin/paraphrase-news", dependencies=[Depends(require_admin)])
def api_admin_paraphrase_news():
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=400, detail="GEMINI_API_KEY is not configured")
    try:
        conn = db_conn()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    updated = 0
    skipped = 0
    errors = 0
    rows: list[Any] = []
    try:
        _ensure_schema(conn)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, title, full_text, original_title, original_full_text
            FROM news
            ORDER BY id
            """
        )
        rows = list(cur.fetchall())
        for row_id, title, full_text, original_title, original_full_text in rows:
            src_title = original_title or title or ""
            src_full_text = original_full_text or full_text or ""
            if not src_title and not src_full_text:
                skipped += 1
                continue
            try:
                new_title, new_full_text, did_paraphrase = _paraphrase_tamil_news(src_title, src_full_text)
                if not did_paraphrase:
                    skipped += 1
                    continue
                cur.execute(
                    """
                    UPDATE news
                    SET title = %s,
                        full_text = %s,
                        original_title = %s,
                        original_full_text = %s
                    WHERE id = %s
                    """,
                    (new_title, new_full_text, src_title, src_full_text, row_id),
                )
                updated += 1
            except Exception as e:
                print(f"[paraphrase] row {row_id} failed: {e}")
                errors += 1
        conn.commit()
        cur.close()
    finally:
        conn.close()
    return {"rows_seen": len(rows), "updated": updated, "skipped": skipped, "errors": errors}


@app.post("/api/admin/paraphrase-titles", dependencies=[Depends(require_admin)])
def api_admin_paraphrase_titles():
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=400, detail="GEMINI_API_KEY is not configured")
    try:
        conn = db_conn()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    updated = 0
    skipped = 0
    errors = 0
    rows: list[Any] = []
    try:
        _ensure_schema(conn)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, title, full_text, original_title, original_full_text
            FROM news
            ORDER BY id
            """
        )
        rows = list(cur.fetchall())
        for row_id, title, full_text, original_title, original_full_text in rows:
            src_title = original_title or title or ""
            context = original_full_text or full_text or ""
            if not src_title:
                skipped += 1
                continue
            try:
                new_title = _paraphrase_tamil_title(src_title, context)
                if not new_title or new_title == title:
                    skipped += 1
                    continue
                cur.execute(
                    """
                    UPDATE news
                    SET title = %s,
                        original_title = %s
                    WHERE id = %s
                    """,
                    (new_title, src_title, row_id),
                )
                updated += 1
            except Exception as e:
                print(f"[paraphrase:title] row {row_id} failed: {e}")
                errors += 1
        conn.commit()
        cur.close()
    finally:
        conn.close()
    return {"rows_seen": len(rows), "updated": updated, "skipped": skipped, "errors": errors}


@app.post("/api/admin/normalize-images", dependencies=[Depends(require_admin)])
def api_admin_normalize_images():
    try:
        conn = db_conn()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    updated = 0
    try:
        updated = _normalize_db_image_paths(conn)
    finally:
        conn.close()
    return {"updated": updated}


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
            SELECT id, title, url, image_path, full_text, source, category_ta, status,
                   created_at, original_title, original_full_text
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
                "image_path": to_image_url(r[3] or ""),
                "full_text": r[4] or "",
                "source": r[5] or "unknown",
                "category_ta": r[6] or "",
                "status": r[7] or "pending",
                "created_at": json_datetime(r[8]) or "",
                "original_title": r[9] or r[1] or "",
                "original_full_text": r[10] or r[4] or "",
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
            SELECT id, title, url, image_path, full_text, source, category_ta, status,
                   created_at, original_title, original_full_text
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
            "image_path": to_image_url(row[3] or ""),
            "full_text": row[4] or "",
            "source": row[5] or "unknown",
            "category_ta": row[6] or "",
            "status": row[7] or "pending",
            "created_at": json_datetime(row[8]) or "",
            "original_title": row[9] or row[1] or "",
            "original_full_text": row[10] or row[4] or "",
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
        add("image_path", normalize_image_path(image_path))
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
