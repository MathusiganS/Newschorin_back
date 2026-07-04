# Tamil News Backend

The backend is a FastAPI application with PostgreSQL persistence, Scrapy and
Playwright collection, Tamil classification, Gemini paraphrasing, moderation,
view tracking, and static image serving.

## Application layout

```text
app/
  api/routes/       HTTP endpoints only
  core/             configuration, security, logging, exceptions
  db/               connection, schema setup, migration reference
  integrations/     external API clients
  models/           domain enums
  repositories/     PostgreSQL queries
  schemas/          Pydantic request/response models
  services/         business workflows
  utils/            datetime and image helpers
spiders/             Scrapy spiders
tests/               contract and unit tests
fastapi_app.py       compatibility Uvicorn entry point
```

## Run

From the repository root:

```powershell
uvicorn fastapi_app:app --reload --port 4000
```

## Configuration

Copy `.env.example` to `.env` and provide real secrets. Production mode is
enabled with `APP_ENV=production`; startup then rejects the default admin and
database credentials.

Set `CORS_ORIGINS` to comma-separated trusted frontend origins in production.
When `*` is used, credentialed CORS is disabled.

For production admin credentials, set `ADMIN_PASSWORD_HASH` to a PBKDF2 hash.
It takes precedence over `ADMIN_PASS`, while the existing Basic Auth request
format remains unchanged.

Set `SYNC_API_KEY` for scheduled and machine-to-machine calls. Operational
routes accept this value through `X-API-Key`; Basic admin credentials remain a
compatible fallback.

## Protected endpoints

Admin endpoints and the following operational endpoints use the existing HTTP
Basic credentials:

- `GET /api/classifier/diagnose`
- `POST /api/sync`
- `POST /api/reclassify`

`run_all.py` automatically sends `SYNC_API_KEY` when configured, or falls back
to `ADMIN_USER` and `ADMIN_PASS`, so the scheduled workflow remains automatic.

## Compatibility

Public news endpoints, response field names, moderation status behavior,
URL-based upserts, per-item sync commits, classification, paraphrasing, image
URLs, and scraper scheduling retain their existing behavior.

## Tests

```powershell
pip install -r requirements-dev.txt
pytest tests
```
