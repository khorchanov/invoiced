import asyncio
import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.services.processing import process_document as process_document_async
from app.worker.celery_app import celery_app


async def _run(document_id: uuid.UUID) -> None:
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    try:
        await process_document_async(document_id, async_sessionmaker(engine, expire_on_commit=False))
    finally:
        await engine.dispose()


@celery_app.task(name="process_document")
def process_document(document_id: str) -> None:
    asyncio.run(_run(uuid.UUID(document_id)))


def enqueue_processing(document_id: uuid.UUID) -> None:
    process_document.delay(str(document_id))
