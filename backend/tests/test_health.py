from collections.abc import AsyncIterator

from httpx import AsyncClient

from app.core.database import get_db
from app.main import app


async def test_health_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "environment": "dev", "database": "ok"}


class UnreachableSession:
    async def execute(self, *args: object, **kwargs: object) -> None:
        raise ConnectionRefusedError("database is down")


async def test_health_returns_503_when_database_unreachable(client: AsyncClient) -> None:
    async def broken_get_db() -> AsyncIterator[UnreachableSession]:
        yield UnreachableSession()

    app.dependency_overrides[get_db] = broken_get_db
    try:
        response = await client.get("/health")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {"detail": "database unavailable"}
