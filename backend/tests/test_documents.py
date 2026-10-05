import uuid
from collections.abc import Awaitable, Callable, Iterator
from pathlib import Path
from typing import Annotated

import pytest
from fastapi import Depends
from httpx import AsyncClient

from app.dependencies import get_document_repository, get_document_service
from app.main import app
from app.repositories.document import DocumentRepository
from app.services.document import DocumentService

AuthHeaders = Callable[[str], Awaitable[dict[str, str]]]

PDF_BYTES = b"%PDF-1.4\n% fake but valid-looking pdf\n"


@pytest.fixture
def upload_dir(tmp_path: Path) -> Iterator[Path]:
    def override(
        documents: Annotated[DocumentRepository, Depends(get_document_repository)],
    ) -> DocumentService:
        return DocumentService(documents, tmp_path, max_bytes=1024)

    app.dependency_overrides[get_document_service] = override
    yield tmp_path
    app.dependency_overrides.pop(get_document_service, None)


async def upload(client: AsyncClient, headers: dict[str, str], name: str, data: bytes):
    return await client.post("/documents", headers=headers, files={"file": (name, data)})


async def test_upload_text_file(client: AsyncClient, upload_dir: Path, make_auth_headers: AuthHeaders) -> None:
    headers = await make_auth_headers("alice@example.com")

    response = await upload(client, headers, "notes.txt", b"hello world")

    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "notes.txt"
    assert body["content_type"] == "text/plain"
    assert body["size_bytes"] == 11
    assert body["status"] == "pending"
    assert "storage_path" not in body
    stored = list(upload_dir.rglob("*.txt"))
    assert len(stored) == 1 and stored[0].read_bytes() == b"hello world"


async def test_upload_pdf_file(client: AsyncClient, upload_dir: Path, make_auth_headers: AuthHeaders) -> None:
    headers = await make_auth_headers("alice@example.com")

    response = await upload(client, headers, "report.pdf", PDF_BYTES)

    assert response.status_code == 201
    assert response.json()["content_type"] == "application/pdf"


async def test_upload_fake_pdf_is_rejected(client: AsyncClient, upload_dir: Path, make_auth_headers: AuthHeaders) -> None:
    headers = await make_auth_headers("alice@example.com")

    response = await upload(client, headers, "report.pdf", b"just text pretending to be a pdf")

    assert response.status_code == 422
    assert list(upload_dir.rglob("*.pdf")) == []


async def test_upload_unsupported_type_returns_415(client: AsyncClient, upload_dir: Path, make_auth_headers: AuthHeaders) -> None:
    headers = await make_auth_headers("alice@example.com")

    assert (await upload(client, headers, "virus.exe", b"MZ")).status_code == 415


async def test_upload_too_large_returns_413(client: AsyncClient, upload_dir: Path, make_auth_headers: AuthHeaders) -> None:
    headers = await make_auth_headers("alice@example.com")

    assert (await upload(client, headers, "big.txt", b"x" * 2000)).status_code == 413


async def test_upload_empty_file_returns_422(client: AsyncClient, upload_dir: Path, make_auth_headers: AuthHeaders) -> None:
    headers = await make_auth_headers("alice@example.com")

    assert (await upload(client, headers, "empty.txt", b"")).status_code == 422


async def test_upload_path_traversal_filename_is_neutralized(
    client: AsyncClient, upload_dir: Path, make_auth_headers: AuthHeaders
) -> None:
    headers = await make_auth_headers("alice@example.com")

    response = await upload(client, headers, "../../evil.txt", b"data")

    assert response.status_code == 201
    assert response.json()["filename"] == "evil.txt"
    stored = list(upload_dir.rglob("*.txt"))
    assert len(stored) == 1
    assert upload_dir in stored[0].parents


async def test_upload_requires_authentication(client: AsyncClient, upload_dir: Path) -> None:
    response = await client.post("/documents", files={"file": ("a.txt", b"hi")})

    assert response.status_code == 401


async def test_list_returns_only_own_documents(client: AsyncClient, upload_dir: Path, make_auth_headers: AuthHeaders) -> None:
    alice = await make_auth_headers("alice@example.com")
    bob = await make_auth_headers("bob@example.com")
    await upload(client, alice, "alice.txt", b"a")
    await upload(client, bob, "bob.txt", b"b")

    response = await client.get("/documents", headers=alice)

    assert [d["filename"] for d in response.json()] == ["alice.txt"]


async def test_get_document_of_another_user_returns_404(
    client: AsyncClient, upload_dir: Path, make_auth_headers: AuthHeaders
) -> None:
    alice = await make_auth_headers("alice@example.com")
    bob = await make_auth_headers("bob@example.com")
    document_id = (await upload(client, alice, "alice.txt", b"a")).json()["id"]

    assert (await client.get(f"/documents/{document_id}", headers=alice)).status_code == 200
    assert (await client.get(f"/documents/{document_id}", headers=bob)).status_code == 404


async def test_get_unknown_document_returns_404(client: AsyncClient, make_auth_headers: AuthHeaders) -> None:
    headers = await make_auth_headers("alice@example.com")

    assert (await client.get(f"/documents/{uuid.uuid4()}", headers=headers)).status_code == 404
