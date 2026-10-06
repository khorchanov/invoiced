from typing import Protocol

import httpx

from app.core.config import get_settings


class EmbeddingError(Exception):
    pass


class Embedder(Protocol):
    model: str

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class OllamaEmbedder:
    def __init__(self, base_url: str, model: str, dimensions: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.dimensions = dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(
                    f"{self.base_url}/api/embed", json={"model": self.model, "input": texts}
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise EmbeddingError(f"Ollama embedding request failed: {exc}") from exc

        embeddings = response.json()["embeddings"]
        if len(embeddings) != len(texts) or any(len(e) != self.dimensions for e in embeddings):
            raise EmbeddingError(f"unexpected embedding shape from model {self.model}")
        return embeddings


def get_embedder() -> Embedder:
    settings = get_settings()
    return OllamaEmbedder(settings.ollama_base_url, settings.embedding_model, settings.embedding_dimensions)
