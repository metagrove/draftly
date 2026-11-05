# Draftly architecture and engineering decisions

## Product slice

Draftly delivers a focused document lifecycle: authenticate → create → edit → persist → reopen → share. Owned and shared documents are visually distinct. File import is intentionally limited to UTF-8 `.txt` and `.md` files up to 1 MB.

## System design

- **Frontend:** React + TypeScript + Vite, with Tiptap for structured rich-text editing.
- **Backend:** FastAPI REST API. Authentication, document operations, sharing, and import validation are handled server-side.
- **Persistence:** SQLAlchemy models for `users`, `documents`, and `document_shares`; SQLite is the local default.
- **Content format:** Tiptap JSON is persisted as JSON text so headings, lists, and inline marks survive reopening.
- **Authentication:** bcrypt password hashes and a signed, timed session cookie (`itsdangerous`). The session cookie is HTTP-only and never exposed to frontend JavaScript.
- **Authorization:** `resolve_document_access` is the single document access-resolution service. Read and write endpoints use it; `require_editor` rejects viewer writes. Only owners may manage sharing.
- **Browser boundary:** Credentialed CORS is restricted to configured frontend origins. Browser mutation requests with an Origin header are checked against that allowlist. Local cookies use SameSite=Lax; cross-site production cookies require HTTPS and SameSite=None; Secure.
- **File import:** The server checks extension, reads at most 1 MB + 1 byte, rejects oversize/empty/blank/non-UTF-8 files, and creates a document owned by the authenticated user.

## Data model

- `users`: identity, unique email, bcrypt password hash.
- `documents`: title, Tiptap JSON payload, owner foreign key, creation/update timestamps.
- `document_shares`: document/user foreign keys, unique document-user pair, and a constrained `viewer` or `editor` permission.

## Priorities and trade-offs

1. **Security before feature breadth.** Replaced the starter's user-controlled `X-User-Email` identity header with signed HTTP-only sessions. The original header could be trivially spoofed.
2. **One permission policy.** Centralizing access resolution reduces the chance that individual endpoints implement inconsistent owner/share checks.
3. **SQLite locally, PostgreSQL in production.** SQLite minimizes setup friction and has no paid dependency. A persistent volume or managed PostgreSQL is required for durable deployment; ephemeral serverless disk is not sufficient.
4. **Tiptap instead of custom contenteditable.** The editor provides structured JSON and reliable baseline formatting.
5. **TXT/MD instead of DOCX.** Plain-text import has a clear, testable contract and avoids conversion complexity inside the timebox.
6. **No real-time collaboration.** Correct concurrent editing needs a CRDT/OT strategy and more testing; reliable persistence and access control are higher priority for this scope.

## Verification status

- Python source compilation was checked in the development environment.
- The complete pytest suite is provided, but dependency installation and execution must be verified in the candidate's local environment. Do not claim tests passed until `pytest -q` succeeds there.
- Frontend dependency installation and production build must also be run locally.
- No public deployment is claimed as verified.

## Next engineering steps

- Add debounced, serialized autosave with bounded retry and clear unsaved/error states.
- Add explicit share listing/revocation UI and audit the owner/editor/viewer flows.
- Add rate limiting, CSRF hardening appropriate to the final hosting topology, password reset, and account lifecycle.
- Add Alembic migrations and PostgreSQL integration tests.
- Add Playwright end-to-end tests, accessibility checks, and deployment smoke tests.
