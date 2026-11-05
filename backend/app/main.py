import json
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Response, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, inspect, text
from sqlalchemy.orm import Session

from .database import Base, engine, get_db, SessionLocal
from .models import User, Document, DocumentShare
from .security import SESSION_COOKIE, SESSION_MAX_AGE, create_session, read_session, hash_password, verify_password
from .permissions import resolve_document_access, require_editor

app = FastAPI(title="Draftly API", version="1.0.0")
origins = [origin.strip() for origin in os.getenv("FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def enforce_browser_origin(request: Request, call_next):
    # CORS is not a complete CSRF defense. Reject cross-origin browser mutations.
    origin = request.headers.get("origin")
    if request.method in {"POST", "PATCH", "DELETE", "PUT"} and origin and origin not in origins:
        return JSONResponse(status_code=403, content={"detail": "Untrusted request origin"})
    return await call_next(request)


Base.metadata.create_all(bind=engine)


def migrate_existing_database() -> None:
    """Add the password_hash column for users upgrading the original starter DB."""
    inspector = inspect(engine)
    if "users" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("users")}
        if "password_hash" not in columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255) NOT NULL DEFAULT ''"))


migrate_existing_database()


class LoginPayload(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=72)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("Enter a valid email address")
        return normalized


class DocumentCreate(BaseModel):
    title: str = Field(default="Untitled document", min_length=1, max_length=200)
    content: dict = Field(default_factory=lambda: {"type": "doc", "content": [{"type": "paragraph"}]})

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Title cannot be blank")
        return value.strip()


class DocumentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: dict | None = None

    @field_validator("title")
    @classmethod
    def update_title_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Title cannot be blank")
        return value.strip() if value is not None else None


class ShareCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    permission: str = "viewer"

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("Enter a valid email address")
        return normalized

    @field_validator("permission")
    @classmethod
    def valid_permission(cls, value: str) -> str:
        if value not in {"viewer", "editor"}:
            raise ValueError("Permission must be viewer or editor")
        return value


def seed_users() -> None:
    accounts = [
        ("Tarun", "tarun@example.com", "TarunDemo!2026"),
        ("Alex Morgan", "alex@example.com", "AlexDemo!2026"),
        ("Sam Lee", "sam@example.com", "SamDemo!2026"),
    ]
    with SessionLocal() as db:
        for name, email, password in accounts:
            user = db.scalar(select(User).where(User.email == email))
            if user is None:
                db.add(User(name=name, email=email, password_hash=hash_password(password)))
            elif not user.password_hash:
                user.password_hash = hash_password(password)
        db.commit()



APP_ENV = os.getenv("APP_ENV", "development").strip().lower()

if APP_ENV in {"development", "dev", "test"}:
    seed_users()

def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    user_id = read_session(token) if token else None
    if user_id is None:
        raise HTTPException(status_code=401, detail="Please sign in to continue")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Session is no longer valid")
    return user


def serialize(doc: Document, access: str) -> dict:
    return {
        "id": doc.id,
        "title": doc.title,
        "content": json.loads(doc.content),
        "owner_id": doc.owner_id,
        "owner_name": doc.owner.name if doc.owner else "",
        "access": access,
        "created_at": doc.created_at.isoformat(),
        "updated_at": doc.updated_at.isoformat(),
    }


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/auth/login")
def login(payload: LoginPayload, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    response.set_cookie(
        key=SESSION_COOKIE,
        value=create_session(user.id),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=os.getenv("COOKIE_SECURE", "true" if os.getenv("ENVIRONMENT") == "production" else "false").lower() == "true",
        samesite="none" if os.getenv("ENVIRONMENT") == "production" else "lax",
        path="/",
    )
    return {"id": user.id, "name": user.name, "email": user.email}


@app.get("/api/auth/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "name": user.name, "email": user.email}


@app.post("/api/auth/logout")
def logout(response: Response):
    production = os.getenv("ENVIRONMENT") == "production"
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, secure=production, samesite="none" if production else "lax")
    return {"message": "Signed out"}


@app.get("/api/users")
def users(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return [{"id": u.id, "name": u.name, "email": u.email} for u in db.scalars(select(User).where(User.id != user.id).order_by(User.name)).all()]


@app.get("/api/documents")
def list_documents(db: Session = Depends(get_db), user: User = Depends(current_user)):
    owned = db.scalars(select(Document).where(Document.owner_id == user.id).order_by(Document.updated_at.desc())).all()
    shared_rows = db.execute(
        select(Document, DocumentShare.permission)
        .join(DocumentShare, DocumentShare.document_id == Document.id)
        .where(DocumentShare.user_id == user.id)
        .order_by(Document.updated_at.desc())
    ).all()
    return {"owned": [serialize(doc, "owner") for doc in owned], "shared": [serialize(doc, permission) for doc, permission in shared_rows]}


@app.post("/api/documents")
def create_document(payload: DocumentCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    doc = Document(title=payload.title, content=json.dumps(payload.content), owner_id=user.id)
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return serialize(doc, "owner")


@app.get("/api/documents/{document_id}")
def get_document(document_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    doc, access = resolve_document_access(document_id, user, db)
    return serialize(doc, access)


@app.patch("/api/documents/{document_id}")
def update_document(document_id: int, payload: DocumentUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    doc, access = resolve_document_access(document_id, user, db)
    require_editor(access)
    if payload.title is not None:
        doc.title = payload.title
    if payload.content is not None:
        doc.content = json.dumps(payload.content)
    doc.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(doc)
    return serialize(doc, access)


@app.post("/api/documents/{document_id}/shares")
def share_document(document_id: int, payload: ShareCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Only the owner can manage sharing")
    recipient = db.scalar(select(User).where(User.email == payload.email.lower()))
    if recipient is None:
        raise HTTPException(status_code=404, detail="User not found")
    if recipient.id == user.id:
        raise HTTPException(status_code=400, detail="You already own this document")
    share = db.scalar(select(DocumentShare).where(DocumentShare.document_id == document_id, DocumentShare.user_id == recipient.id))
    if share:
        share.permission = payload.permission
    else:
        db.add(DocumentShare(document_id=document_id, user_id=recipient.id, permission=payload.permission))
    db.commit()
    return {"message": f"Shared with {recipient.email}", "email": recipient.email, "permission": payload.permission}


@app.delete("/api/documents/{document_id}/shares/{share_id}")
def remove_share(document_id: int, share_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    doc = db.get(Document, document_id)
    if doc is None or doc.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Document not found")
    share = db.get(DocumentShare, share_id)
    if share is None or share.document_id != document_id:
        raise HTTPException(status_code=404, detail="Share not found")
    db.delete(share)
    db.commit()
    return {"message": "Access removed"}


@app.post("/api/import")
async def import_file(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(current_user)):
    filename = Path(file.filename or "upload.txt").name
    extension = Path(filename).suffix.lower()
    if extension not in {".txt", ".md"}:
        raise HTTPException(status_code=415, detail="Only .txt and .md files are supported")
    raw = await file.read(1_000_001)
    if len(raw) > 1_000_000:
        raise HTTPException(status_code=413, detail="File must be smaller than 1 MB")
    if not raw:
        raise HTTPException(status_code=400, detail="File is empty")
    try:
        text_content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded")
    if not text_content.strip():
        raise HTTPException(status_code=400, detail="File contains no text")
    paragraphs = [
        {"type": "paragraph", "content": [{"type": "text", "text": line}]}
        if line else {"type": "paragraph"}
        for line in text_content.splitlines()
    ]
    content = {"type": "doc", "content": paragraphs or [{"type": "paragraph"}]}
    doc = Document(title=Path(filename).stem[:200] or "Imported document", content=json.dumps(content), owner_id=user.id)
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return serialize(doc, "owner")

@app.get("/api/documents/{document_id}")
def get_document(document_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    doc, access = resolve_document_access(document_id, user, db)
    return serialize(doc, access)

@app.delete("/api/documents/{document_id}")
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user)
):
    doc = db.get(Document, document_id)

    if doc is None or doc.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Document not found")

    # Remove sharing records before deleting the document.
    shares = db.scalars(
        select(DocumentShare).where(
            DocumentShare.document_id == document_id
        )
    ).all()

    for share in shares:
        db.delete(share)

    db.delete(doc)
    db.commit()

    return {"message": "Document deleted successfully"}