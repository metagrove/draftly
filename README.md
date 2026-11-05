# Draftly — Collaborative document workspace

Draftly is a time-boxed collaborative document editor built with React, TypeScript, Tiptap, FastAPI, SQLAlchemy, and SQLite.

## Current capabilities

- Create, rename, edit, save, and reopen rich-text documents.
- Persist Tiptap JSON in SQLAlchemy models.
- Import UTF-8 `.txt` and `.md` files (1 MB maximum; empty and non-UTF-8 files rejected).
- Share documents with seeded users as `viewer` or `editor`.
- Enforce document read/write access through one permission-resolution service.
- Authenticate with bcrypt password hashes and signed HTTP-only session cookies.
- Sign out and inspect the current session through `/api/auth/me`.
- Display owned and shared documents separately; viewer access is read-only in the UI and API.

## Requirements

- Python 3.10+
- Node.js 20+
- npm

## Run locally (Windows PowerShell)

### 1. Backend

From the project root:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Backend: http://localhost:8000  
API docs: http://localhost:8000/docs

### 2. Frontend

Open a second terminal from the project root:

```powershell
cd frontend
npm install
npm run dev
```

Frontend: http://localhost:5173

Optional: create `frontend/.env` with:

```env
VITE_API_URL=http://localhost:8000
```

The frontend sends requests with `credentials: include`; do not remove this setting because authentication uses an HTTP-only cookie.

## Demo accounts

| Name | Email | Password |
|---|---|---|
| Tarun | tarun@example.com | `TarunDemo!2026` |
| Alex | alex@example.com | `AlexDemo!2026` |
| Sam | sam@example.com | `SamDemo!2026` |

These are public assessment demo credentials only. Do not reuse these passwords or expose this seeded-account setup in a real production service.

## Authentication and security configuration

The API uses a signed `draftly_session` cookie. The cookie is HTTP-only, has a 12-hour maximum age, and uses `SameSite=Lax` for local development. In production, set:

```env
ENVIRONMENT=production
SESSION_SECRET=<long-random-secret-at-least-32-characters>
COOKIE_SECURE=true
FRONTEND_ORIGINS=https://your-frontend-domain.example
DATABASE_URL=postgresql+psycopg://user:password@host:5432/draftly
```

Use HTTPS in production. Configure the exact frontend origin; do not use wildcard origins with credentialed cookies. When frontend and backend are on different sites, production cookies use `SameSite=None; Secure`, and the API checks browser mutation request origins against `FRONTEND_ORIGINS`.

For local development, the app uses `http://localhost:5173` and `http://127.0.0.1:5173` as allowed frontend origins. Set `SESSION_SECRET` to a random value even in shared development environments.

## Tests

```powershell
cd backend
python -m pytest -q
```

The HTTPX/TestClient suite covers health, successful and failed login, HTTP-only cookie behavior, unauthenticated access, header-spoofing rejection, document CRUD, viewer read-only behavior, editor access, empty/non-UTF-8 file rejection, and logout.

## Storage and deployment notes

SQLite is the local development default (`backend/draftly.db`). A SQLite database on an ephemeral serverless filesystem is not durable. For deployment, use PostgreSQL (and add the matching SQLAlchemy driver) or a host with an explicitly configured persistent volume. The app does not claim a deployment is live or verified.

## Deliberate scope cuts

- No real-time simultaneous editing or conflict resolution.
- TXT and Markdown files are imported as plain text paragraphs; Markdown syntax is not parsed into formatting.
- No DOCX conversion, comments, version history, or export yet.
- Sharing is limited to seeded demo users; no email invitations.
- Production-grade account registration, password reset, rate limiting, observability, and formal database migrations remain future work.
