import asyncio
import logging
import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.models.document import Document, DocumentStatus
from app.repositories.chunk import ChunkRepository
from app.repositories.document import DocumentRepository
from app.services.chunking import chunk_text
from app.services.extraction import extract_text

logger = logging.getLogger(__name__)


async def _extract_and_index(document: Document, session: AsyncSession) -> None:
    path = Path(get_settings().upload_dir) / document.storage_path
    data = await asyncio.to_thread(path.read_bytes)
    chunks = chunk_text(extract_text(data, document.content_type))
    await ChunkRepository(session).replace_for_document(document.id, document.owner_id, chunks)
    # Embedding arrives in the next step.


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
            await _extract_and_index(document, session)
        except Exception as exc:
            logger.exception("processing failed for document %s", document_id)
            await session.rollback()
            await documents.set_status(document, DocumentStatus.FAILED, error=str(exc)[:1000])
        else:
            await documents.set_status(document, DocumentStatus.READY)
