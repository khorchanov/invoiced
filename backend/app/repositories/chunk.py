import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk
from app.models.document import Document


@dataclass
class SearchHit:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    position: int
    content: str
    score: float


class ChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def replace_for_document(
        self,
        document_id: uuid.UUID,
        owner_id: uuid.UUID,
        contents: list[str],
        embeddings: list[list[float]],
        embedding_model: str,
    ) -> None:
        """Insert chunks without committing; the caller owns the transaction."""
        existing = await self.session.execute(select(Chunk).where(Chunk.document_id == document_id))
        for chunk in existing.scalars():
            await self.session.delete(chunk)
        await self.session.flush()
        self.session.add_all(
            Chunk(
                document_id=document_id,
                owner_id=owner_id,
                position=i,
                content=content,
                embedding=embedding,
                embedding_model=embedding_model,
            )
            for i, (content, embedding) in enumerate(zip(contents, embeddings, strict=True))
        )
        await self.session.flush()

    async def list_for_document(self, document_id: uuid.UUID) -> list[Chunk]:
        result = await self.session.execute(
            select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.position)
        )
        return list(result.scalars())

    async def search(
        self, owner_id: uuid.UUID, query_embedding: list[float], limit: int
    ) -> list[SearchHit]:
        """Nearest chunks by cosine similarity. Always scoped to `owner_id`."""
        distance = Chunk.embedding.cosine_distance(query_embedding)
        result = await self.session.execute(
            select(Chunk, Document.filename, distance.label("distance"))
            .join(Document, Document.id == Chunk.document_id)
            .where(Chunk.owner_id == owner_id, Chunk.embedding.is_not(None))
            .order_by(distance)
            .limit(limit)
        )
        return [
            SearchHit(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                filename=filename,
                position=chunk.position,
                content=chunk.content,
                score=1 - dist,
            )
            for chunk, filename, dist in result.all()
        ]
