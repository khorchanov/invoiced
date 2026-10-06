from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import CurrentUser, get_agent_service
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.agent import AgentError, AgentService

router = APIRouter(prefix="/chat", tags=["chat"])

Service = Annotated[AgentService, Depends(get_agent_service)]


@router.post("", response_model=ChatResponse)
async def chat(body: ChatRequest, current_user: CurrentUser, service: Service):
    try:
        return await service.ask(current_user.id, body.message)
    except AgentError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "The assistant is unavailable")
