# Draftly API

Run from this directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API uses bcrypt password hashes and signed HTTP-only session cookies. Seeded local demo accounts are documented in the root README. Set `SESSION_SECRET`, `FRONTEND_ORIGINS`, `ENVIRONMENT`, and `DATABASE_URL` appropriately before deployment. Production requires a 32+ character session secret and HTTPS-secure cookies.

Run tests with `python -m pytest -q`.
