# ConnectPilot Backend

Django REST API for ConnectPilot (formerly Li Copilot): JWT and Google sign-in, AI-generated LinkedIn messages via Groq (sync and SSE streaming), and per-user generation history.

For production deployment (Render + Supabase), see [DEPLOYMENT.md](DEPLOYMENT.md).

## Requirements

- Python 3.11.9 (see `.python-version` / `runtime.txt`)
- PostgreSQL 14+ running locally

## Local setup

```sh
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt -c constraints.txt

cp .env.example .env   # then fill in values; never commit .env
```

`.env` must contain `DJANGO_ENV=development`. The server refuses to start when `DJANGO_ENV` is unset, so a deployed server can never fall back to development settings by accident.

`GROQ_API_KEY` is only needed to generate messages. Without it the server, health check and tests still run; generation requests fail.

Create the database and apply migrations:

```sh
createdb linkedin_copilot          # or the DB_NAME set in .env
python manage.py migrate
```

Run the server on port 8001 (the frontend and extension default to it):

```sh
python manage.py runserver 8001
```

Health check: `GET http://localhost:8001/health/` returns `{"status": "ok"}`.

## Checks and tests

```sh
export PYTHONDONTWRITEBYTECODE=1
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

Tests never call the real Groq API: generation tests replace the client with a fake and fail if a real one is constructed.

The suite runs against PostgreSQL using the `DB_*` settings from `.env`. Django creates and drops a temporary `test_<DB_NAME>` database, so the database user needs the `CREATEDB` privilege. A guard test fails if the backend is not PostgreSQL.

| Area | File |
| --- | --- |
| Settings hardening, health, routing | `config/tests.py` |
| Register, login, refresh rotation and blacklisting, `/me` | `accounts/tests.py` |
| Sync and streaming generation, prompts, tone, auth, throttling | `ai/tests.py` |
| History list, search, delete, per-user isolation | `generations/tests.py` |

`test_missing_required_fields_are_rejected` is marked as an expected failure: the generation endpoints do not validate input yet.

## Dependencies

`requirements.txt` lists direct dependencies; `constraints.txt` pins the full resolved set. Always install with both files. Update them together and re-run the checks above.

## API overview

| Method | Path | Auth |
| --- | --- | --- |
| POST | `/api/auth/register/` | none |
| POST | `/api/auth/login/` | none |
| POST | `/api/auth/refresh/` | none |
| GET | `/api/auth/me/` | Bearer |
| POST | `/api/auth/social/google/` | none |
| POST | `/api/auth/extension-token/` | Bearer (issues a separate token pair for the browser extension) |
| POST | `/api/generate/{connection-request,referral-request,recruiter-reply,followup}/` | Bearer |
| POST | `/api/generate/stream/{same four}/` | Bearer (SSE) |
| GET | `/api/history/?search=` | Bearer |
| DELETE | `/api/history/<id>/` | Bearer |
| GET | `/health/` | none |
