import httpx
import pytest

from app.services import embedding
from app.services.embedding import EmbeddingError, OllamaEmbedder


def patch_transport(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    real = httpx.AsyncClient
    monkeypatch.setattr(
        embedding.httpx,
        "AsyncClient",
        lambda **kw: real(transport=httpx.MockTransport(handler), **kw),
    )


async def test_embed_returns_vectors(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": [[0.0, 1.0], [1.0, 0.0]]})

    patch_transport(monkeypatch, handler)
    result = await OllamaEmbedder("http://x", "m", 2).embed(["a", "b"])
    assert result == [[0.0, 1.0], [1.0, 0.0]]


async def test_embed_wrong_dimensions_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_transport(monkeypatch, lambda r: httpx.Response(200, json={"embeddings": [[0.0]]}))
    with pytest.raises(EmbeddingError):
        await OllamaEmbedder("http://x", "m", 2).embed(["a"])


async def test_embed_http_error_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_transport(monkeypatch, lambda r: httpx.Response(500))
    with pytest.raises(EmbeddingError):
        await OllamaEmbedder("http://x", "m", 2).embed(["a"])
