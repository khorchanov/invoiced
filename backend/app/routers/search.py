from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import CurrentUser, get_search_service
from app.schemas.search import SearchRequest, SearchResult
from app.services.embedding import EmbeddingError
from app.services.search import SearchService

router = APIRouter(prefix="/search", tags=["search"])

Service = Annotated[SearchService, Depends(get_search_service)]


@router.post("", response_model=list[SearchResult])
async def search(body: SearchRequest, current_user: CurrentUser, service: Service):
    try:
        return await service.search(current_user.id, body.query, body.limit)
    except EmbeddingError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Embedding service unavailable")
