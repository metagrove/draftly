# AI workflow note

## Tools
Disclose the actual tools used during the assessment (for example, ChatGPT for architecture, implementation planning, code review, and test design; any IDE assistant used should be named accurately).

## Where AI accelerated work
- Decomposed the broad prompt into a time-boxed MVP and explicit scope cuts.
- Proposed a relational schema and API boundaries.
- Accelerated the initial FastAPI, SQLAlchemy, React, and Tiptap scaffolding.
- Generated a first-pass test and documentation structure.

## Human judgment and changes
- Chose SQLite to avoid external service setup during the timebox, while documenting the persistent-volume requirement for deployment.
- Chose seeded demo identities only as a reviewable prototype shortcut; explicitly rejected presenting this as production authentication.
- Limited imports to UTF-8 TXT/MD rather than claiming unsupported DOCX conversion.
- Prioritized backend permission checks over UI-only access hiding.

## Verification performed / to complete
- Run backend tests with `pytest -q`.
- Exercise create, edit, save, refresh, import, and share flows manually.
- Verify viewer accounts receive 403 on document edits and cannot manage shares.
- Check browser console and API logs; test empty, oversized, and unsupported uploads.
- Record any failures honestly in SUBMISSION.md. Do not claim checks that were not run.
