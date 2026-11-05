from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Document, DocumentShare, User


def resolve_document_access(document_id: int, user: User, db: Session) -> tuple[Document, str]:
    """Single source of truth for document read/write authorization."""
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    if document.owner_id == user.id:
        return document, "owner"

    share = db.scalar(
        select(DocumentShare).where(
            DocumentShare.document_id == document_id,
            DocumentShare.user_id == user.id,
        )
    )
    if share is None:
        # Avoid disclosing the existence of documents to unrelated users.
        raise HTTPException(status_code=404, detail="Document not found")
    return document, share.permission


def require_editor(access: str) -> None:
    if access not in {"owner", "editor"}:
        raise HTTPException(status_code=403, detail="Viewer access cannot modify this document")
