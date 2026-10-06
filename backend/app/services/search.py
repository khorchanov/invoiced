import uuid

from app.repositories.chunk import ChunkRepository, SearchHit
from app.services.embedding import Embedder


class SearchService:
    def __init__(self, chunks: ChunkRepository, embedder: Embedder) -> None:
        self.chunks = chunks
        self.embedder = embedder

    async def search(self, owner_id: uuid.UUID, query: str, limit: int) -> list[SearchHit]:
        [embedding] = await self.embedder.embed([query])
        return await self.chunks.search(owner_id, embedding, limit)
