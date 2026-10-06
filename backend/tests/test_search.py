from collections.abc import Awaitable, Callable, Iterator

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.main import app
from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus
from app.models.user import User
from app.services.embedding import EmbeddingError, get_embedder

AuthHeaders = Callable[[str], Awaitable[dict[str, str]]]


def vector(index: int) -> list[float]:
    v = [0.0] * 768
    v[index] = 1.0
    return v


class QueryEmbedder:
    model = "fake"

    def __init__(self) -> None:
        self.fail = False

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if self.fail:
            raise EmbeddingError("down")
        return [vector(0) for _ in texts]


@pytest.fixture
def query_embedder() -> Iterator[QueryEmbedder]:
    embedder = QueryEmbedder()
    app.dependency_overrides[get_embedder] = lambda: embedder
    yield embedder
    app.dependency_overrides.pop(get_embedder, None)


async def add_chunks(
    test_engine: AsyncEngine, email: str, filename: str, chunks: list[tuple[str, list[float]]]
) -> None:
    async with async_sessionmaker(test_engine, expire_on_commit=False)() as session:
        user = (await session.execute(select(User).where(User.email == email))).scalar_one()
        document = Document(
            owner_id=user.id,
            filename=filename,
            content_type="text/plain",
            storage_path="x",
            size_bytes=1,
            status=DocumentStatus.READY,
        )
        session.add(document)
        await session.flush()
        session.add_all(
            Chunk(
                document_id=document.id,
                owner_id=user.id,
                position=i,
                content=content,
                embedding=embedding,
                embedding_model="fake",
            )
            for i, (content, embedding) in enumerate(chunks)
        )
        await session.commit()


async def test_search_returns_nearest_chunks_first(
    client: AsyncClient, test_engine: AsyncEngine, make_auth_headers: AuthHeaders, query_embedder: QueryEmbedder
) -> None:
    headers = await make_auth_headers("alice@example.com")
    diagonal = [0.7, 0.7] + [0.0] * 766
    await add_chunks(
        test_engine, "alice@example.com", "a.txt", [("far", vector(1)), ("near", vector(0)), ("mid", diagonal)]
    )

    response = await client.post("/search", headers=headers, json={"query": "q", "limit": 2})

    assert response.status_code == 200
    body = response.json()
    assert [r["content"] for r in body] == ["near", "mid"]
    assert body[0]["filename"] == "a.txt"
    assert body[0]["score"] == pytest.approx(1.0)


async def test_search_never_returns_other_users_chunks(
    client: AsyncClient, test_engine: AsyncEngine, make_auth_headers: AuthHeaders, query_embedder: QueryEmbedder
) -> None:
    alice = await make_auth_headers("alice@example.com")
    await make_auth_headers("bob@example.com")
    await add_chunks(test_engine, "alice@example.com", "a.txt", [("alice secret", vector(0))])
    await add_chunks(test_engine, "bob@example.com", "b.txt", [("bob secret", vector(0))])

    response = await client.post("/search", headers=alice, json={"query": "q"})

    assert [r["content"] for r in response.json()] == ["alice secret"]


async def test_search_requires_auth(client: AsyncClient) -> None:
    response = await client.post("/search", json={"query": "q"})
    assert response.status_code == 401


async def test_search_validates_input(
    client: AsyncClient, make_auth_headers: AuthHeaders, query_embedder: QueryEmbedder
) -> None:
    headers = await make_auth_headers("alice@example.com")
    assert (await client.post("/search", headers=headers, json={"query": ""})).status_code == 422
    assert (await client.post("/search", headers=headers, json={"query": "q", "limit": 99})).status_code == 422


async def test_search_embedding_failure_returns_503(
    client: AsyncClient, make_auth_headers: AuthHeaders, query_embedder: QueryEmbedder
) -> None:
    query_embedder.fail = True
    headers = await make_auth_headers("alice@example.com")

    response = await client.post("/search", headers=headers, json={"query": "q"})

    assert response.status_code == 503
