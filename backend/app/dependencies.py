import uuid
from pathlib import Path
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.user import User
from app.repositories.chunk import ChunkRepository
from app.repositories.document import DocumentRepository
from app.repositories.user import UserRepository
from app.services.auth import AuthService
from app.services.document import DocumentService
from app.services.embedding import Embedder, get_embedder
from app.services.search import SearchService
from app.worker.tasks import enqueue_processing

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

DbSession = Annotated[AsyncSession, Depends(get_db)]


def get_user_repository(db: DbSession) -> UserRepository:
    return UserRepository(db)


UserRepo = Annotated[UserRepository, Depends(get_user_repository)]


def get_auth_service(users: UserRepo) -> AuthService:
    return AuthService(users)


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], users: UserRepo) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        user_id = uuid.UUID(decode_access_token(token))
    except (jwt.InvalidTokenError, ValueError, KeyError):
        raise credentials_error
    user = await users.get_by_id(user_id)
    if user is None:
        raise credentials_error
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_document_repository(db: DbSession) -> DocumentRepository:
    return DocumentRepository(db)


def get_document_service(
    documents: Annotated[DocumentRepository, Depends(get_document_repository)],
) -> DocumentService:
    settings = get_settings()
    return DocumentService(
        documents, Path(settings.upload_dir), settings.max_upload_bytes, enqueue_processing
    )


def get_search_service(
    db: DbSession, embedder: Annotated[Embedder, Depends(get_embedder)]
) -> SearchService:
    return SearchService(ChunkRepository(db), embedder)
