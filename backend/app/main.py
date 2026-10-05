from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.routers import auth, documents, users

settings = get_settings()

app = FastAPI(title=settings.app_name)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(documents.router)


class HealthResponse(BaseModel):
    status: str
    environment: str
    database: str


@app.get("/health", response_model=HealthResponse)
async def health(db: Annotated[AsyncSession, Depends(get_db)]) -> HealthResponse:
    try:
        await db.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError):
        raise HTTPException(status_code=503, detail="database unavailable")
    return HealthResponse(status="ok", environment=settings.environment, database="ok")
