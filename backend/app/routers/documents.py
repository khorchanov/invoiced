import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from app.dependencies import CurrentUser, get_document_service
from app.schemas.document import DocumentRead
from app.services.document import (
    DocumentService,
    FileTooLargeError,
    InvalidFileError,
    UnsupportedFileTypeError,
)

router = APIRouter(prefix="/documents", tags=["documents"])

Service = Annotated[DocumentService, Depends(get_document_service)]


@router.post("", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(file: UploadFile, current_user: CurrentUser, service: Service):
    data = await file.read(service.max_bytes + 1)
    try:
        return await service.upload(current_user.id, file.filename, data)
    except UnsupportedFileTypeError:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only .pdf, .txt and .md files are supported")
    except FileTooLargeError:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "File is too large")
    except InvalidFileError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e))


@router.get("", response_model=list[DocumentRead])
async def list_documents(current_user: CurrentUser, service: Service):
    return await service.list_for_owner(current_user.id)


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document(document_id: uuid.UUID, current_user: CurrentUser, service: Service):
    document = await service.get_for_owner(document_id, current_user.id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return document
