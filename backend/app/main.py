from fastapi import FastAPI
from pydantic import BaseModel

from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name)


class HealthResponse(BaseModel):
    status: str
    environment: str


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", environment=settings.environment)
