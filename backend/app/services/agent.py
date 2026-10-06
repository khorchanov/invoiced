import asyncio
import logging
import uuid
from dataclasses import dataclass

from langchain.agents import create_agent
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import LLMResult
from langchain_core.tools import BaseTool, tool
from langchain_ollama import ChatOllama

from app.core.config import get_settings
from app.repositories.chunk import ChunkRepository
from app.repositories.document import DocumentRepository
from app.services.search import SearchService

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You answer questions about the user's own uploaded documents. "
    "Use search_documents to find relevant passages before answering, and list_documents or "
    "get_document_summary when the user asks what documents exist or what one is about. "
    "Answer only from tool results and cite the filename of each source. "
    "If the documents do not contain the answer, say so."
)

MAX_TOOL_RESULT_CHARS = 1500
SUMMARY_CHUNKS = 5
MAX_STEPS = 12


def _short(value: object, limit: int = 300) -> str:
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[:limit] + "..."


class AgentLogger(AsyncCallbackHandler):
    """Logs each model call and tool call of one agent run."""

    def __init__(self, owner_id: uuid.UUID) -> None:
        self.prefix = f"agent[{str(owner_id)[:8]}]"
        self.model_calls = 0

    async def on_chat_model_start(self, serialized: dict, messages: list, **kwargs: object) -> None:
        self.model_calls += 1
        logger.info("%s model call #%d (%d messages)", self.prefix, self.model_calls, len(messages[0]))

    async def on_llm_end(self, response: LLMResult, **kwargs: object) -> None:
        message = response.generations[0][0].message  # type: ignore[attr-defined]
        calls = [f"{c['name']}({_short(c['args'], 120)})" for c in getattr(message, "tool_calls", [])]
        if calls:
            logger.info("%s model wants tools: %s", self.prefix, ", ".join(calls))
        else:
            logger.info("%s model answered: %s", self.prefix, _short(message.content))

    async def on_tool_start(self, serialized: dict, input_str: str, **kwargs: object) -> None:
        logger.info("%s tool start: %s(%s)", self.prefix, serialized.get("name"), _short(input_str, 120))

    async def on_tool_end(self, output: object, **kwargs: object) -> None:
        content = getattr(output, "content", output)
        logger.info("%s tool result: %s", self.prefix, _short(content))

    async def on_tool_error(self, error: BaseException, **kwargs: object) -> None:
        logger.warning("%s tool error: %s", self.prefix, error)

    async def on_llm_error(self, error: BaseException, **kwargs: object) -> None:
        logger.warning("%s model error: %s", self.prefix, error)


class AgentError(Exception):
    pass


@dataclass
class AgentAnswer:
    answer: str
    tools_used: list[str]


def get_chat_model() -> BaseChatModel:
    settings = get_settings()
    return ChatOllama(model=settings.chat_model, base_url=settings.ollama_base_url, temperature=0)


def build_tools(
    owner_id: uuid.UUID,
    search: SearchService,
    documents: DocumentRepository,
    chunks: ChunkRepository,
) -> list[BaseTool]:
    """Tools are bound to one user: the model never chooses whose data it reads."""
    # The tools share one DB session, which cannot run queries concurrently.
    lock = asyncio.Lock()

    @tool
    async def search_documents(query: str) -> str:
        """Search the user's documents for passages relevant to the query."""
        async with lock:
            hits = await search.search(owner_id, query, 5)
        if not hits:
            return "No relevant passages found."
        return "\n\n".join(f"[{h.filename}] {h.content[:MAX_TOOL_RESULT_CHARS]}" for h in hits)

    @tool
    async def list_documents() -> str:
        """List the user's documents with their IDs and processing status."""
        async with lock:
            docs = await documents.list_for_owner(owner_id)
        if not docs:
            return "The user has no documents."
        return "\n".join(f"{d.id} | {d.filename} | {d.status.value}" for d in docs)

    @tool
    async def get_document_summary(document_id: str) -> str:
        """Get the opening passages of one document (by ID from list_documents) to summarize it."""
        try:
            doc_id = uuid.UUID(document_id)
        except ValueError:
            return "Invalid document id."
        async with lock:
            document = await documents.get_for_owner(doc_id, owner_id)
            if document is None:
                return "Document not found."
            first = await chunks.first_for_document(doc_id, owner_id, SUMMARY_CHUNKS)
        if not first:
            return f"{document.filename} has no indexed content (status: {document.status.value})."
        text = "\n\n".join(c.content for c in first)
        return f"[{document.filename}] {text[: MAX_TOOL_RESULT_CHARS * 2]}"

    return [search_documents, list_documents, get_document_summary]


class AgentService:
    def __init__(
        self,
        model: BaseChatModel,
        search: SearchService,
        documents: DocumentRepository,
        chunks: ChunkRepository,
    ) -> None:
        self.model = model
        self.search = search
        self.documents = documents
        self.chunks = chunks

    async def ask(self, owner_id: uuid.UUID, message: str) -> AgentAnswer:
        tools = build_tools(owner_id, self.search, self.documents, self.chunks)
        agent = create_agent(self.model, tools, system_prompt=SYSTEM_PROMPT)
        logger.info("agent[%s] question: %s", str(owner_id)[:8], _short(message))
        try:
            result = await agent.ainvoke(
                {"messages": [("user", message)]},
                {"recursion_limit": MAX_STEPS, "callbacks": [AgentLogger(owner_id)]},
            )
        except Exception as exc:
            logger.exception("agent run failed")
            raise AgentError(str(exc)) from exc

        messages = result["messages"]
        tools_used = [
            call["name"] for m in messages if isinstance(m, AIMessage) for call in m.tool_calls
        ]
        final = messages[-1]
        return AgentAnswer(answer=str(final.content), tools_used=tools_used)
