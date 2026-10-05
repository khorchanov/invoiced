import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, document: Document) -> Document:
        self.session.add(document)
        await self.session.commit()
        await self.session.refresh(document)
        return document

    async def list_for_owner(self, owner_id: uuid.UUID) -> list[Document]:
        result = await self.session.execute(
            select(Document).where(Document.owner_id == owner_id).order_by(Document.created_at.desc())
        )
        return list(result.scalars())

    async def get_for_owner(self, document_id: uuid.UUID, owner_id: uuid.UUID) -> Document | None:
        result = await self.session.execute(
            select(Document).where(Document.id == document_id, Document.owner_id == owner_id)
        )
        return result.scalar_one_or_none()
