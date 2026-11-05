import os
import bcrypt
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

SESSION_COOKIE = "draftly_session"
SESSION_MAX_AGE = 60 * 60 * 12


def _serializer() -> URLSafeTimedSerializer:
    production = os.getenv("APP_ENV", "development").strip().lower() == "production"
    secret = os.getenv("SESSION_SECRET")
    if production and (not secret or len(secret) < 32):
        raise RuntimeError("Production requires SESSION_SECRET with at least 32 characters")
    return URLSafeTimedSerializer(secret or "local-only-change-this-secret-before-deploying", salt="draftly-auth-v1")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_session(user_id: int) -> str:
    return _serializer().dumps({"user_id": user_id})


def read_session(token: str) -> int | None:
    try:
        payload = _serializer().loads(token, max_age=SESSION_MAX_AGE)
        user_id = payload.get("user_id")
        return user_id if isinstance(user_id, int) else None
    except (BadSignature, SignatureExpired, AttributeError, TypeError):
        return None
