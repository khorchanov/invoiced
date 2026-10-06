import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.models.document import Document, DocumentStatus
from app.models.user import User
from app.repositories.document import DocumentRepository
from app.services import processing
from app.services.processing import process_document


@pytest.fixture
def session_factory(test_engine: AsyncEngine, client: AsyncClient) -> async_sessionmaker:
    # `client` is requested only so tables are truncated after each test.
    return async_sessionmaker(test_engine, expire_on_commit=False)


async def make_document(
    session_factory: async_sessionmaker, status: DocumentStatus = DocumentStatus.PENDING
) -> uuid.UUID:
    async with session_factory() as session:
        user = User(email="alice@example.com", hashed_password="x")
        session.add(user)
        await session.flush()
        document = Document(
            owner_id=user.id,
            filename="notes.txt",
            content_type="text/plain",
            storage_path="x/y.txt",
            size_bytes=5,
            status=status,
        )
        session.add(document)
        await session.commit()
        return document.id


async def fetch(session_factory: async_sessionmaker, document_id: uuid.UUID) -> Document:
    async with session_factory() as session:
        document = await DocumentRepository(session).get(document_id)
        assert document is not None
        return document


async def test_processing_marks_document_ready(session_factory: async_sessionmaker) -> None:
    document_id = await make_document(session_factory)

    await process_document(document_id, session_factory)

    assert (await fetch(session_factory, document_id)).status == DocumentStatus.READY


async def test_processing_failure_marks_document_failed(
    session_factory: async_sessionmaker, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(document: Document) -> None:
        raise RuntimeError("cannot parse")

    monkeypatch.setattr(processing, "_extract_and_index", boom)
    document_id = await make_document(session_factory)

    await process_document(document_id, session_factory)

    document = await fetch(session_factory, document_id)
    assert document.status == DocumentStatus.FAILED
    assert document.error == "cannot parse"


async def test_processing_skips_non_pending_document(
    session_factory: async_sessionmaker, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Document] = []

    async def record(document: Document) -> None:
        calls.append(document)

    monkeypatch.setattr(processing, "_extract_and_index", record)
    document_id = await make_document(session_factory, DocumentStatus.READY)

    await process_document(document_id, session_factory)

    assert calls == []
    assert (await fetch(session_factory, document_id)).status == DocumentStatus.READY


async def test_processing_unknown_document_is_a_noop(session_factory: async_sessionmaker) -> None:
    await process_document(uuid.uuid4(), session_factory)
