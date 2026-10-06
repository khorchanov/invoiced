import uuid

from pydantic import BaseModel, ConfigDict, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=5, ge=1, le=20)


class SearchResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: uuid.UUID
    filename: str
    position: int
    content: str
    score: float
