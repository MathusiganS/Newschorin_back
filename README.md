# NewsChorin Backend

FastAPI backend for the NewsChorin Tamil news portal. It stores news in
PostgreSQL, serves public news APIs, powers the admin panel, runs Scrapy-based
collection, tracks article views, serves downloaded images, and supports Tamil
classification and Gemini paraphrasing.

## Tech Stack

- Python
- FastAPI
- Uvicorn
- PostgreSQL
- psycopg2
- Scrapy
- Playwright
- scikit-learn/joblib for optional classification
- Gemini API for optional paraphrasing

## Requirements

- Python 3.11 or newer recommended
- PostgreSQL 12 or newer
- Playwright Chromium browser for scraper pages that need a browser

## Quick Start

Create a virtual environment:

```bash
python -m venv venv
```

Activate it on Windows:

```powershell
venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Install Playwright browser support:

```bash
playwright install chromium
```

Copy the environment example:

```bash
copy .env.example .env
```

Start the API:

```bash
uvicorn fastapi_app:app --reload --port 4000
```

Open:

```text
http://127.0.0.1:4000/api/health
```

## Environment Variables

Main settings are documented in `.env.example`.

Important variables:

| Variable | Purpose |
| --- | --- |
| `APP_ENV` | `development` or `production` |
| `DATABASE_URL` | PostgreSQL connection string |
| `ADMIN_USER` | Admin username |
| `ADMIN_PASS` | Development admin password |
| `ADMIN_PASSWORD_HASH` | Production-safe admin password hash |
| `JWT_SECRET` | Secret for admin cookie sessions |
| `COOKIE_SECURE` | Use secure cookies in production |
| `CORS_ORIGINS` | Comma-separated frontend origins |
| `SYNC_API_KEY` | API key for scraper/scheduler sync calls |
| `ENABLE_SCRAPE_SCHEDULER` | Enables automatic scraper scheduler |
| `SCRAPE_INTERVAL_SECONDS` | Scheduler interval |
| `API_SYNC_URL` | Sync endpoint used by scraper workflow |
| `TAMILNEWS_MODEL_DIR` | Optional classifier model folder |
| `TAMILNEWS_KEYWORD_FALLBACK` | Enables keyword fallback classification |
| `GEMINI_API_KEY` | Enables Gemini paraphrasing features |

Development defaults are allowed only outside production. When
`APP_ENV=production`, startup rejects unsafe default admin/database settings.

## Database Setup

Create the database in PostgreSQL:

```sql
CREATE DATABASE news_techorin;
```

The app creates or updates the required schema during startup through:

```text
app/db/schema.py
```

The migration reference is stored at:

```text
app/db/migrations/001_existing_news_schema.sql
```

The main `news` table includes moderation fields such as:

- `status`
- `approved_at`
- `view_count`
- `category_ta`
- `source`
- `image_path`
- `full_text`

When an admin approves an article, the backend saves `approved_at` using Sri
Lanka time. Public APIs expose this value so the frontend can show the approved
time to users.

## Application Layout

```text
app/
  api/routes/         HTTP route modules
  core/               config, security, password, token, logging helpers
  db/                 database connection, schema, migrations
  integrations/       external clients such as Gemini
  models/             domain enums
  repositories/       SQL queries and row mapping
  schemas/            Pydantic request/response models
  services/           business workflows
  utils/              datetime and image helpers

spiders/              Scrapy spiders
tests/                pytest tests
image/                downloaded article images served from /images
models/               optional ML classifier model files
fastapi_app.py        Uvicorn compatibility entry point
run_all.py            scraper runner and sync workflow
requirements.txt      runtime dependencies
requirements-dev.txt  test dependencies
```

## API Endpoints

### System

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/` | Basic service response |
| `GET` | `/health` | Health check |
| `GET` | `/api/health` | Health check through frontend API path |

### Public News

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/news` | List approved news |
| `GET` | `/api/news/count` | Count approved news |
| `GET` | `/api/news/popular` | Popular news by views |
| `GET` | `/api/news/trending` | Trending alias for popular news |
| `GET` | `/api/news/{article_id}` | Public article detail |
| `POST` | `/api/news/{article_id}/view` | Increment article view count |

Common query parameters for `/api/news`:

- `source`
- `category_ta`
- `search`
- `sort`
- `limit`
- `offset`

List responses include `items` and `total` for pagination.

### Admin Auth

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/admin/login` | Create admin cookie session |
| `POST` | `/api/admin/logout` | Clear admin cookie session |

### Admin News

These routes require admin authentication.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/admin/news` | List admin news with filters and pagination |
| `GET` | `/api/admin/news/{article_id}` | Get full admin article detail |
| `PUT` | `/api/admin/news/{article_id}` | Update editable article fields |
| `POST` | `/api/admin/news/{article_id}/approve` | Approve news and save Sri Lanka approval time |
| `POST` | `/api/admin/news/{article_id}/reject` | Reject news |

Admin list supports:

- `status`
- `source`
- `category_ta`
- `search`
- `sort`
- `limit`
- `offset`
- `include_meta=true`

Use `include_meta=true` when the frontend needs pagination totals.

### Operations

These routes require admin credentials or `X-API-Key` with `SYNC_API_KEY`.

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/sync` | Sync `news.json` into PostgreSQL |
| `POST` | `/api/reclassify` | Re-run classification |
| `GET` | `/api/classifier/diagnose` | Check classifier status |
| `POST` | `/api/classify` | Classify supplied Tamil text |

### Images

```text
GET /images/<file>
```

Images are served from the local `image/` directory.

## Scraper Workflow

Run all configured spiders and sync results:

```bash
python run_all.py
```

Run a single spider:

```bash
scrapy crawl tamilwin
```

Scraper output:

- Downloads images into `image/`
- Writes merged article data to `news.json`
- Syncs to PostgreSQL through `/api/sync` when configured
- Uses `SYNC_API_KEY` when available

## Classification

Classification is optional.

To use model-based classification, place model files in `models/` or set:

```env
TAMILNEWS_MODEL_DIR=C:\path\to\models
```

If model files are missing and `TAMILNEWS_KEYWORD_FALLBACK=1`, the backend can
still use keyword-based Tamil category detection.

## Gemini Paraphrasing

Set `GEMINI_API_KEY` to enable paraphrasing actions in the admin panel.

Related settings:

- `GEMINI_MODEL`
- `GEMINI_TEMPERATURE`
- `GEMINI_TOP_P`
- `GEMINI_MAX_OUTPUT_TOKENS`
- `GEMINI_MAX_ATTEMPTS`

Admin endpoints expose paraphrase status and bulk paraphrase actions.

## Tests

Install test dependencies:

```bash
pip install -r requirements-dev.txt
```

Run tests:

```bash
pytest tests
```

If pytest is unavailable, install `requirements-dev.txt` first.

## Development Workflow

1. Start PostgreSQL.
2. Start backend with `uvicorn fastapi_app:app --reload --port 4000`.
3. Start the frontend from `Newschorin_front`.
4. Log into `/admin`.
5. Approve or reject pending news.
6. Confirm approved stories appear on public pages.

## Troubleshooting

### Database connection failed

Check:

- PostgreSQL service is running.
- `DATABASE_URL` points to the correct database.
- The database exists.
- Username and password are correct.

### Frontend cannot call backend

Check:

- Backend is running on port `4000`.
- Frontend `.env` points to `http://127.0.0.1:4000`.
- Backend `CORS_ORIGINS` includes `http://localhost:5173` and
  `http://127.0.0.1:5173`.

### Images return 404

Check:

- The file exists inside `image/`.
- The database `image_path` points to the right `/images/...` path.
- Backend startup completed successfully.

### Admin login fails

Check:

- `ADMIN_USER`
- `ADMIN_PASS`
- `ADMIN_PASSWORD_HASH`
- `JWT_SECRET`
- Browser cookies are allowed for the frontend/backend origins.

## Production Checklist

- Set `APP_ENV=production`.
- Use a strong `DATABASE_URL`.
- Set `ADMIN_PASSWORD_HASH`.
- Set a long random `JWT_SECRET`.
- Set `COOKIE_SECURE=1` behind HTTPS.
- Set explicit `CORS_ORIGINS`.
- Set `SYNC_API_KEY` for scheduled sync.
- Confirm `/api/health` returns success.
- Confirm admin approve/reject flow works.
- Confirm public pages show approved news with `approved_at`.
