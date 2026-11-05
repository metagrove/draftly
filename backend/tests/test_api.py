from fastapi.testclient import TestClient
from app.main import app
from sqlalchemy import select
from app.database import SessionLocal
from app.models import DocumentShare
import os
from pathlib import Path

TEST_DB = Path(__file__).resolve().parent / "test_draftly.db"
TEST_DB.unlink(missing_ok=True)

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"

from fastapi.testclient import TestClient
from app.main import app

def signed_in(email="tarun@example.com", password="TarunDemo!2026"):
    client = TestClient(app)
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return client


def create_doc(client, title="Test document"):
    response = client.post("/api/documents", json={"title": title})
    assert response.status_code == 200
    return response.json()


def test_01_health():
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_02_login_sets_httponly_cookie():
    client = TestClient(app)
    response = client.post("/api/auth/login", json={"email": "tarun@example.com", "password": "TarunDemo!2026"})
    assert response.status_code == 200
    assert "draftly_session" in response.cookies
    assert "httponly" in response.headers["set-cookie"].lower()


def test_03_invalid_password_is_rejected():
    response = TestClient(app).post("/api/auth/login", json={"email": "tarun@example.com", "password": "wrong-password"})
    assert response.status_code == 401


def test_04_me_requires_authentication():
    assert TestClient(app).get("/api/auth/me").status_code == 401


def test_05_identity_header_cannot_impersonate_user():
    response = TestClient(app).get("/api/documents", headers={"X-User-Email": "alex@example.com"})
    assert response.status_code == 401


def test_06_authenticated_user_can_create_and_read_document():
    client = signed_in()
    created = create_doc(client, "Persistence check")
    fetched = client.get(f"/api/documents/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["title"] == "Persistence check"
    assert fetched.json()["access"] == "owner"


def test_07_shared_viewer_can_read_document():
    owner = signed_in()
    doc = create_doc(owner, "Viewer document")
    shared = owner.post(f"/api/documents/{doc['id']}/shares", json={"email": "alex@example.com", "permission": "viewer"})
    assert shared.status_code == 200
    viewer = signed_in("alex@example.com", "AlexDemo!2026")
    response = viewer.get(f"/api/documents/{doc['id']}")
    assert response.status_code == 200
    assert response.json()["access"] == "viewer"


def test_08_viewer_cannot_edit_document():
    owner = signed_in()
    doc = create_doc(owner, "Protected document")
    owner.post(f"/api/documents/{doc['id']}/shares", json={"email": "alex@example.com", "permission": "viewer"})
    viewer = signed_in("alex@example.com", "AlexDemo!2026")
    response = viewer.patch(f"/api/documents/{doc['id']}", json={"title": "Unauthorized change"})
    assert response.status_code == 403


def test_09_shared_editor_can_edit_document():
    owner = signed_in()
    doc = create_doc(owner, "Collaborative document")
    owner.post(f"/api/documents/{doc['id']}/shares", json={"email": "sam@example.com", "permission": "editor"})
    editor = signed_in("sam@example.com", "SamDemo!2026")
    response = editor.patch(f"/api/documents/{doc['id']}", json={"title": "Edited by Sam"})
    assert response.status_code == 200
    assert response.json()["title"] == "Edited by Sam"


def test_10_empty_file_import_is_rejected():
    client = signed_in()
    response = client.post("/api/import", files={"file": ("empty.txt", b"", "text/plain")})
    assert response.status_code == 400
    assert response.json()["detail"] == "File is empty"


def test_11_non_utf8_file_import_is_rejected():
    client = signed_in()
    response = client.post("/api/import", files={"file": ("bad.txt", b"\xff\xfe", "text/plain")})
    assert response.status_code == 400


def test_12_logout_clears_session():
    client = signed_in()
    response = client.post("/api/auth/logout")
    assert response.status_code == 200
    assert client.get("/api/auth/me").status_code == 401

def test_13_unshared_user_cannot_read_document():
    owner = signed_in()
    doc = create_doc(owner, "Private document")

    stranger = signed_in("alex@example.com", "AlexDemo!2026")

    response = stranger.get(f"/api/documents/{doc['id']}")

    assert response.status_code == 404


def test_14_editor_cannot_manage_sharing():
    owner = signed_in()
    doc = create_doc(owner, "Editor permissions")

    owner.post(
        f"/api/documents/{doc['id']}/shares",
        json={"email": "sam@example.com", "permission": "editor"}
    )

    editor = signed_in("sam@example.com", "SamDemo!2026")

    response = editor.post(
        f"/api/documents/{doc['id']}/shares",
        json={"email": "alex@example.com", "permission": "viewer"}
    )

    assert response.status_code == 403


def test_15_unsupported_file_type_is_rejected():
    client = signed_in()

    response = client.post(
        "/api/import",
        files={"file": ("document.pdf", b"PDF content", "application/pdf")}
    )

    assert response.status_code == 415


def test_16_oversized_file_is_rejected():
    client = signed_in()

    large_content = b"a" * 1_000_001

    response = client.post(
        "/api/import",
        files={"file": ("large.txt", large_content, "text/plain")}
    )

    assert response.status_code == 413


def test_17_valid_file_import_succeeds():
    client = signed_in()

    response = client.post(
        "/api/import",
        files={"file": ("notes.txt", b"Hello Draftly", "text/plain")}
    )

    assert response.status_code == 200

    data = response.json()

    assert data["title"] == "notes"
    assert data["content"]["type"] == "doc"
    assert data["content"]["content"][0]["content"][0]["text"] == "Hello Draftly"


def test_18_owner_can_remove_share():
    owner = signed_in()
    doc = create_doc(owner, "Revocation test")

    owner.post(
        f"/api/documents/{doc['id']}/shares",
        json={"email": "alex@example.com", "permission": "viewer"}
    )

    with SessionLocal() as db:
        share = db.scalar(
            select(DocumentShare).where(
                DocumentShare.document_id == doc["id"]
            )
        )
        share_id = share.id

    response = owner.delete(
        f"/api/documents/{doc['id']}/shares/{share_id}"
    )

    assert response.status_code == 200

    viewer = signed_in("alex@example.com", "AlexDemo!2026")
    assert viewer.get(f"/api/documents/{doc['id']}").status_code == 404

def test_19_editor_cannot_remove_share():
    owner = signed_in()
    doc = create_doc(owner, "Protected sharing")

    owner.post(
        f"/api/documents/{doc['id']}/shares",
        json={"email": "sam@example.com", "permission": "editor"}
    )

    with SessionLocal() as db:
        share = db.scalar(
            select(DocumentShare).where(
                DocumentShare.document_id == doc["id"]
            )
        )
        share_id = share.id

    editor = signed_in("sam@example.com", "SamDemo!2026")

    response = editor.delete(
        f"/api/documents/{doc['id']}/shares/{share_id}"
    )

    assert response.status_code == 404

def test_20_shared_document_appears_in_document_list():
    owner = signed_in()
    doc = create_doc(owner, "Shared listing test")

    owner.post(
        f"/api/documents/{doc['id']}/shares",
        json={"email": "alex@example.com", "permission": "viewer"}
    )

    viewer = signed_in("alex@example.com", "AlexDemo!2026")

    response = viewer.get("/api/documents")

    assert response.status_code == 200

    shared_documents = response.json()["shared"]

    assert any(
        item["id"] == doc["id"] and item["access"] == "viewer"
        for item in shared_documents
    )
