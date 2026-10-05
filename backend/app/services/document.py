import asyncio
import uuid
from pathlib import Path, PurePosixPath

from app.models.document import Document
from app.repositories.document import DocumentRepository

CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
}


class UnsupportedFileTypeError(Exception):
    pass


class FileTooLargeError(Exception):
    pass


class InvalidFileError(Exception):
    pass


class DocumentService:
    def __init__(self, documents: DocumentRepository, upload_dir: Path, max_bytes: int) -> None:
        self.documents = documents
        self.upload_dir = upload_dir
        self.max_bytes = max_bytes

    async def upload(self, owner_id: uuid.UUID, filename: str | None, data: bytes) -> Document:
        name = PurePosixPath((filename or "").replace("\\", "/")).name
        extension = PurePosixPath(name).suffix.lower()
        if extension not in CONTENT_TYPES:
            raise UnsupportedFileTypeError(extension)
        if len(data) > self.max_bytes:
            raise FileTooLargeError
        if not data:
            raise InvalidFileError("file is empty")
        if extension == ".pdf" and not data.startswith(b"%PDF-"):
            raise InvalidFileError("file is not a valid PDF")

        document_id = uuid.uuid4()
        relative_path = f"{owner_id}/{document_id}{extension}"
        path = self.upload_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)

        document = Document(
            id=document_id,
            owner_id=owner_id,
            filename=name[:255],
            content_type=CONTENT_TYPES[extension],
            storage_path=relative_path,
            size_bytes=len(data),
        )
        try:
            return await self.documents.create(document)
        except Exception:
            path.unlink(missing_ok=True)
            raise

    async def list_for_owner(self, owner_id: uuid.UUID) -> list[Document]:
        return await self.documents.list_for_owner(owner_id)

    async def get_for_owner(self, document_id: uuid.UUID, owner_id: uuid.UUID) -> Document | None:
        return await self.documents.get_for_owner(document_id, owner_id)
