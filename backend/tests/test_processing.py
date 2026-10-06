import uuid

import pytest
from httpx import AsyncClient
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.models.document import Document, DocumentStatus
from app.models.user import User
from app.core.config import get_settings
from app.repositories.chunk import ChunkRepository
from app.repositories.document import DocumentRepository
from app.services import processing
from app.services.processing import process_document


@pytest.fixture
def session_factory(test_engine: AsyncEngine, client: AsyncClient) -> async_sessionmaker:
    # `client` is requested only so tables are truncated after each test.
    return async_sessionmaker(test_engine, expire_on_commit=False)


class FakeEmbedder:
    model = "fake-model"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * 768 for _ in texts]


@pytest.fixture(autouse=True)
def fake_embedder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(processing, "get_embedder", FakeEmbedder)


@pytest.fixture
def upload_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


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


async def test_processing_stores_chunks_and_marks_ready(
    session_factory: async_sessionmaker, upload_dir: Path
) -> None:
    (upload_dir / "x").mkdir()
    (upload_dir / "x" / "y.txt").write_text("hello world", encoding="utf-8")
    document_id = await make_document(session_factory)

    await process_document(document_id, session_factory)

    assert (await fetch(session_factory, document_id)).status == DocumentStatus.READY
    async with session_factory() as session:
        chunks = await ChunkRepository(session).list_for_document(document_id)
    assert [c.content for c in chunks] == ["hello world"]
    assert chunks[0].embedding_model == "fake-model"
    assert len(chunks[0].embedding) == 768


async def test_processing_missing_file_marks_document_failed(
    session_factory: async_sessionmaker, upload_dir: Path
) -> None:
    document_id = await make_document(session_factory)

    await process_document(document_id, session_factory)

    assert (await fetch(session_factory, document_id)).status == DocumentStatus.FAILED


async def test_processing_failure_marks_document_failed(
    session_factory: async_sessionmaker, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(document: Document, session: AsyncSession) -> None:
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

    async def record(document: Document, session: AsyncSession) -> None:
        calls.append(document)

    monkeypatch.setattr(processing, "_extract_and_index", record)
    document_id = await make_document(session_factory, DocumentStatus.READY)

    await process_document(document_id, session_factory)

    assert calls == []
    assert (await fetch(session_factory, document_id)).status == DocumentStatus.READY


async def test_processing_unknown_document_is_a_noop(session_factory: async_sessionmaker) -> None:
    await process_document(uuid.uuid4(), session_factory)
