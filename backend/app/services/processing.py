import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.document import Document, DocumentStatus
from app.repositories.document import DocumentRepository

logger = logging.getLogger(__name__)


async def _extract_and_index(document: Document) -> None:
    """Real work (extract text, chunk, embed) arrives in the next steps."""


async def process_document(
    document_id: uuid.UUID, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as session:
        documents = DocumentRepository(session)
        document = await documents.get(document_id)
        if document is None or document.status != DocumentStatus.PENDING:
            return

        await documents.set_status(document, DocumentStatus.PROCESSING)
        try:
            await _extract_and_index(document)
        except Exception as exc:
            logger.exception("processing failed for document %s", document_id)
            await session.rollback()
            await documents.set_status(document, DocumentStatus.FAILED, error=str(exc)[:1000])
        else:
            await documents.set_status(document, DocumentStatus.READY)
