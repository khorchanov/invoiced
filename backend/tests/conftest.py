import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from pathlib import Path
from typing import Annotated

import pytest
import pytest_asyncio
from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app import models  # noqa: F401  (registers tables on Base.metadata)
from app.core.config import get_settings
from app.core.database import Base, get_db
from app.dependencies import get_document_repository, get_document_service
from app.main import app
from app.repositories.document import DocumentRepository
from app.services.document import DocumentService

TEST_DB_NAME = "ainative_test"


@pytest_asyncio.fixture(scope="session")
async def test_engine() -> AsyncIterator[AsyncEngine]:
    base_url = make_url(get_settings().database_url)

    admin = create_async_engine(base_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        exists = await conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": TEST_DB_NAME}
        )
        if not exists:
            await conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    await admin.dispose()

    engine = create_async_engine(base_url.set(database=TEST_DB_NAME))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def client(test_engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)

    async def override_get_db() -> AsyncIterator:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()

    table_names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    async with test_engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE"))


@pytest.fixture
def enqueued() -> list[uuid.UUID]:
    return []


@pytest.fixture
def upload_dir(tmp_path: Path, enqueued: list[uuid.UUID]) -> Iterator[Path]:
    def override(
        documents: Annotated[DocumentRepository, Depends(get_document_repository)],
    ) -> DocumentService:
        return DocumentService(documents, tmp_path, max_bytes=1024, enqueue=enqueued.append)

    app.dependency_overrides[get_document_service] = override
    yield tmp_path
    app.dependency_overrides.pop(get_document_service, None)


@pytest_asyncio.fixture
async def make_auth_headers(client: AsyncClient) -> Callable[[str], Awaitable[dict[str, str]]]:
    async def _make(email: str) -> dict[str, str]:
        credentials = {"email": email, "password": "correct-horse-battery"}
        await client.post("/auth/register", json=credentials)
        response = await client.post(
            "/auth/login", data={"username": email, "password": credentials["password"]}
        )
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return _make
