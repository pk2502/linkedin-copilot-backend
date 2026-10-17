# Render Beta Deployment

This repository is prepared for a Render Python web service using Supabase PostgreSQL. No hosting resources or credentials are created by this guide.

## Render service

Create a **Web Service** from this repository with the repository root as the root directory and Python as the runtime. The root-level `runtime.txt` selects Python 3.11.9.

Build command:

```sh
pip install -r requirements.txt -c constraints.txt && python manage.py collectstatic --no-input
```

Start command:

```sh
gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --worker-class gthread --threads 4 --timeout 120
```

Set Render's health-check path to `/health/`. It returns only `{"status":"ok"}` and does not query the database or reveal settings. Run database migrations from the Render Shell after the service environment is configured and before inviting testers:

```sh
python manage.py migrate --noinput
```

Do not run migrations from every web worker's start command; use the one-time pre-release procedure above for each release that includes migrations.

## Environment variables

Set these in the Render service's Environment page. Do not commit their values or put them in `.env.example`.

| Variable | Requirement | Value |
| --- | --- | --- |
| `DJANGO_ENV` | Required | `production` |
| `DEBUG` | Required | `False` |
| `SECRET_KEY` | Required | A newly generated random value of at least 50 characters. Store it as a Render secret; do not reuse a development key. |
| `ALLOWED_HOSTS` | Required | The exact Render hostname, for example `your-service.onrender.com`, without scheme or path. |
| `DATABASE_URL` | Required, recommended | Supabase PostgreSQL connection URI. The password must be URI-encoded if it contains reserved characters. TLS is required; `sslmode=require` is applied by default. |
| `GROQ_API_KEY` | Required | The production Groq API key stored as a Render secret. Startup rejects missing or obvious placeholder values. |
| `GROQ_MODEL` | Optional | Groq model ID. Defaults to `openai/gpt-oss-120b`. Set it to switch models without a code change when Groq retires one (see console.groq.com/docs/deprecations). |
| `CORS_ALLOWED_ORIGINS` | Required when enabling extension CORS | Exact comma-separated browser origins. Set `https://li-copilot.vercel.app` and, after obtaining the published extension ID, `chrome-extension://<extension-id>`. Do not include a trailing slash. |
| `CSRF_TRUSTED_ORIGINS` | Required if overriding the default | Exact web origins that submit Django session/CSRF-protected requests. Start with `https://li-copilot.vercel.app`; the JWT-only extension does not need to be added here. |
| `GOOGLE_CLIENT_ID` | Optional | Required only if Google sign-in is enabled. |
| `GOOGLE_CLIENT_SECRET` | Optional | Required only if Google sign-in is enabled. |

Instead of `DATABASE_URL`, production can use all of `DB_NAME`, `DB_USER`, `DB_PASSWORD`, and `DB_HOST`, with optional `DB_PORT` (default `5432`). Those connections also require TLS. Do not set `DATABASE_URL` and individual database variables expecting them to merge; `DATABASE_URL` takes precedence.

For Supabase, choose a direct or session-pooler connection appropriate to the project's network setup. If using the transaction pooler on port `6543`, the backend disables Django server-side cursors. Do not expose the connection URI in logs, screenshots, support tickets, or source control.

`PORT` is supplied by Render. Do not set it manually. `runtime.txt` pins Python; no database credentials or API keys are committed.

`requirements.txt` pins direct dependencies; `constraints.txt` pins the complete tested resolution, including transitive dependencies. Keep both in the build command so Render installs the same versions. Update them together only after resolving and testing the set in an isolated Python 3.11 environment. The resolution was exercised on macOS ARM; Linux x86_64 wheels were confirmed for the native PostgreSQL and cryptography dependencies, but the Render build remains the final platform-specific check.

The Ollama provider module is dormant: the active generation service imports the Groq provider, not `ai/providers/ollama_provider.py`. The Ollama package is intentionally not installed by this deployment set; enabling that provider requires a separately reviewed dependency and runtime test.

## Origins and client compatibility

The backend's production CORS and CSRF defaults include the frontend origin `https://li-copilot.vercel.app`. The API uses `Authorization: Bearer ...` JWTs, not cookies, so CSRF settings do not affect the frontend or the extension.

The frontend reads `NEXT_PUBLIC_API_URL` (Vercel Config variable, no trailing slash). Its fallback is `http://localhost:8001`, so every Vercel environment that should reach the API needs the variable set.

The Chrome extension (1.1+) calls `https://connectpilot-api.onrender.com` from its popup. Chrome exempts extension pages from CORS for hosts listed in `host_permissions`, so no `chrome-extension://` origin needs to be added. It refreshes tokens itself and can be signed in from the web app's `/connect-extension` page, which mints a separate token pair via `POST /api/auth/extension-token/`.

### Vercel preview deployments

Preview URLs look like `https://linkedin-copilot-frontend-<hash>-pk2502s-projects.vercel.app`. To let them call the API:

1. In Render, set `CORS_ALLOWED_ORIGIN_REGEXES` to

   ```
   ^https://linkedin-copilot-frontend-[a-z0-9-]+-pk2502s-projects\.vercel\.app$
   ```

   The value is whitespace-separated. Startup rejects any pattern that is not anchored with `^https://` and `$`, has an unescaped dot, or uses `|`.
2. In Vercel, add `NEXT_PUBLIC_API_URL` to the **Preview** environment as well.

Previews then use the production API and database (real accounts and the real daily limit). Google sign-in does not work on previews because Google only accepts pre-registered exact origins; use username and password there.

## Database and migration notes

The repository's database backend is already PostgreSQL-configured, and the application migration uses standard Django fields, a foreign key to Django's user model, and `JSONField`; these have PostgreSQL equivalents. The app migration history is small (one `generations` migration; `accounts` has no custom model migration). This is a schema-level compatibility review only: no Supabase connection or production migration was run.

For a fresh beta database, create the Supabase database, configure its connection string, take a backup/snapshot, and run `migrate` once. Do not copy `db.sqlite3` to Supabase or run SQLite-specific file import commands against PostgreSQL. If local accounts/history must be preserved, rehearse a separate logical export/import on a disposable PostgreSQL database, verify user IDs, password hashes, JSON values, foreign keys, and row counts, and keep the original SQLite file unchanged. No data transfer is included here.

Before a release with schema changes, take a database backup and confirm the migration plan in staging. Rolling Render code back does not reverse database migrations. Prefer forward-compatible migrations; restore a backup only as an explicit recovery operation after assessing writes since the backup.

## Manual dashboard steps

1. Create a Supabase project and a Render Web Service connected to the backend repository; select the repository root.
2. Add the listed production environment variables in Render, using Render's secret input for `SECRET_KEY`, `DATABASE_URL`, and `GROQ_API_KEY`.
3. Restrict Supabase network access to the Render service as supported by the selected Supabase plan, and keep TLS enabled.
4. Set Render health check to `/health/`; deploy only after reviewing the build output and running `migrate` from Render Shell.
5. Set Vercel `NEXT_PUBLIC_API_URL` to the Render HTTPS base URL and redeploy the frontend in its own approved phase.
6. Before extension beta use, update its API URL and host permission in the extension repository, publish/load the resulting build, then add that exact extension ID to backend CORS. No extension edits are part of this phase.
7. Verify HTTPS, health, login, refresh rotation, authenticated generation, and history using a non-production tester account before inviting the initial 3–5 testers.

## Operations

### CI

Every push and pull request runs `.github/workflows/ci.yml`: Django `check`, `makemigrations --check` and the full test suite against a PostgreSQL 16 service container. No secrets are used; Groq is faked in tests.

### Keep-alive and uptime check

Supabase pauses free projects after 7 days without database activity. `.github/workflows/keepalive.yml` calls `GET /health/db/` once a day (03:17 UTC). The endpoint runs `SELECT 1` and returns `{"status": "ok"}`, or 503 `{"status": "unavailable"}` when the database cannot be reached; it never exposes error details. A failed run shows in the Actions tab and GitHub emails the repository owner. Run it on demand with **Actions → Keep-alive → Run workflow**.

GitHub disables scheduled workflows after 60 days without commits to the repository. If that happens, re-enable it from the same page.

`/health/` (Render's health check) stays database-free, so a database outage does not make Render restart the service.

Render's free plan sleeps after 15 minutes without traffic; the first request afterwards takes about a minute. The keep-alive job retries to allow for this.
