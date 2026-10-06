import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk


class ChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def replace_for_document(
        self, document_id: uuid.UUID, owner_id: uuid.UUID, contents: list[str]
    ) -> None:
        """Insert chunks without committing; the caller owns the transaction."""
        existing = await self.session.execute(select(Chunk).where(Chunk.document_id == document_id))
        for chunk in existing.scalars():
            await self.session.delete(chunk)
        await self.session.flush()
        self.session.add_all(
            Chunk(document_id=document_id, owner_id=owner_id, position=i, content=content)
            for i, content in enumerate(contents)
        )
        await self.session.flush()

    async def list_for_document(self, document_id: uuid.UUID) -> list[Chunk]:
        result = await self.session.execute(
            select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.position)
        )
        return list(result.scalars())
