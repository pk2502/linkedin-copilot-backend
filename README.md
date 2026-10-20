# ConnectPilot Backend

[![CI](https://github.com/pk2502/linkedin-copilot-backend/actions/workflows/ci.yml/badge.svg)](https://github.com/pk2502/linkedin-copilot-backend/actions/workflows/ci.yml) [![Warm ping](https://github.com/pk2502/linkedin-copilot-backend/actions/workflows/warm.yml/badge.svg)](https://github.com/pk2502/linkedin-copilot-backend/actions/workflows/warm.yml) [![Keep-alive](https://github.com/pk2502/linkedin-copilot-backend/actions/workflows/keepalive.yml/badge.svg)](https://github.com/pk2502/linkedin-copilot-backend/actions/workflows/keepalive.yml)

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

Health check: `GET http://localhost:8001/health/` returns `{"status": "ok"}`. `GET /health/db/` also queries the database (used by the daily keep-alive job).

## Checks and tests

```sh
export PYTHONDONTWRITEBYTECODE=1
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

CI (`.github/workflows/ci.yml`) runs the same checks on every push and pull request.

To judge prompt quality, `python scripts/eval_drafts.py [--compare]` drafts messages for five fictional recipients and flags banned phrases. It makes **real, billed Groq calls** and needs `GROQ_API_KEY`; it is never run by CI or the test suite.

Tests never call the real Groq API: generation tests replace the client with a fake and fail if a real one is constructed.

The suite runs against PostgreSQL using the `DB_*` settings from `.env`. Django creates and drops a temporary `test_<DB_NAME>` database, so the database user needs the `CREATEDB` privilege. A guard test fails if the backend is not PostgreSQL.

| Area | File |
| --- | --- |
| Settings hardening, health, routing | `config/tests.py` |
| Register, login, refresh rotation and blacklisting, `/me` | `accounts/tests.py` |
| Sync and streaming generation, prompts, tone, auth, throttling | `ai/tests.py` |
| History list, search, delete, per-user isolation | `generations/tests.py` |
| Drafts, variants, tweaks, prompt rules, profile use | `ai/test_drafts.py` |
| Resume / PDF import into profile fields | `ai/test_profile_import.py` |
| Outreach tracker | `contacts/tests.py` |
| First-run checklist, draft source | `generations/test_onboarding.py`, `ai/test_drafts.py` |


## Dependencies

`requirements.txt` lists direct dependencies; `constraints.txt` pins the full resolved set. Always install with both files. Update them together and re-run the checks above.

## API overview

| Method | Path | Auth |
| --- | --- | --- |
| POST | `/api/auth/register/` | none |
| POST | `/api/auth/login/` | none |
| POST | `/api/auth/refresh/` | none |
| POST | `/api/auth/logout/` | none (body `{"refresh": ...}`; revokes that refresh token, access tokens expire within 30 min) |
| GET | `/api/auth/me/` | Bearer |
| GET, PUT | `/api/profile/` | Bearer (the user's profile: headline, summary, skills, target roles, experience, writing sample; `completeness` 0-100) |
| POST | `/api/profile/parse/` | Bearer (`{text}` or multipart `{file}` PDF up to 2 MB -> suggested headline, summary, skills, target roles, experience; nothing saved; `PARSE_DAILY_LIMIT`, default 5/day) |
| POST | `/api/drafts/` | Bearer (`{type, tone?, ...fields, recipient_context?, job_description?}` → `{id, variants: [3 drafts]}`; counts once toward the daily limit. `recipient_context` (≤4000, any type), `job_description` (≤6000, referrals) and `conversation` (≤4000, recruiter replies and follow-ups; then only the name, and for recruiter replies the interest level, are required) are used for the prompt only and never stored. Optional `linkedin_url` links the draft to a tracker contact (created or matched by URL, else by name and company; the response includes `contact_id`). Optional `client: "extension"` marks the draft's `source`) |
| GET | `/api/onboarding/` | Bearer (first-run checklist: `{profile_completeness, has_draft, used_extension}`) |
| GET | `/api/contacts/` | Bearer (outreach tracker; `?status=drafted\|sent\|replied\|done`, `?due=1` for follow-ups due, `?search=`; max 200, newest activity first) |
| PATCH, DELETE | `/api/contacts/<id>/` | Bearer (`status`, `outcome`, `notes`, `follow_up_on`, `name`, `company`, `role`; setting `sent` starts a follow-up timer of `FOLLOW_UP_DAYS`, default 5; deleting keeps the drafts) |
| GET | `/api/contacts/lookup/?linkedin_url=` | Bearer (the contact for a LinkedIn profile, or 404) |
| POST | `/api/contacts/touch/` | Bearer (extension events: `{linkedin_url, name?, company?, role?, event: sent\|replied}`; replies from people never contacted are ignored with 204) |
| POST | `/api/drafts/<id>/tweak/` | Bearer (`{variant: 0-2, instruction: shorter\|warmer\|more_specific\|more_formal}` → `{id, text}`; separate daily limit) |
| POST | `/api/auth/social/google/` | none |
| POST | `/api/auth/extension-token/` | Bearer (issues a separate token pair for the browser extension) |
| POST | `/api/generate/{connection-request,referral-request,recruiter-reply,followup}/` | Bearer (original single-draft endpoints, kept for older clients) |
| POST | `/api/generate/stream/{same four}/` | Bearer (SSE) |

Generation requests are validated: every field is required and trimmed, short fields (names, company, role, job title) allow 150 characters, `your_background` and `context` 2000, `interest_level` is one of `very interested` / `somewhat interested` / `not interested`, and `days_since` is a whole number from 0 to 3650. Invalid requests return 400 and do not count toward the daily limit. If the AI provider fails, the endpoints return 502 `{"error": ...}`; a stream that fails part-way ends with a `data: {"error": ...}` event instead of `[DONE]`, and nothing is saved to history.
| GET | `/api/history/?search=` | Bearer |
| DELETE | `/api/history/<id>/` | Bearer |
| GET | `/health/` | none |
| GET | `/health/db/` | none (runs `SELECT 1`; 503 when the database is down) |
