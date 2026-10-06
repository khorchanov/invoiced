from collections.abc import Awaitable, Callable, Iterator
from typing import Any

import pytest
from httpx import AsyncClient
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from sqlalchemy.ext.asyncio import AsyncEngine

from app.main import app
from app.services.agent import get_chat_model
from app.services.embedding import get_embedder
from tests.test_search import QueryEmbedder, add_chunks, vector

AuthHeaders = Callable[[str], Awaitable[dict[str, str]]]


class ScriptedModel(BaseChatModel):
    """Replays prepared AI messages in order and records what it was shown."""

    script: list[AIMessage]
    seen: list[list[BaseMessage]] = []
    fail: bool = False

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedModel":
        return self

    def _generate(self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **kwargs: Any) -> ChatResult:
        if self.fail:
            raise RuntimeError("model is down")
        self.seen.append(list(messages))
        reply = self.script[len(self.seen) - 1]
        return ChatResult(generations=[ChatGeneration(message=reply)])


def tool_call(name: str, **args: Any) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"call-{name}"}])


@pytest.fixture
def scripted(request: pytest.FixtureRequest) -> Iterator[ScriptedModel]:
    model = ScriptedModel(script=[], seen=[])
    app.dependency_overrides[get_chat_model] = lambda: model
    app.dependency_overrides[get_embedder] = lambda: QueryEmbedder()
    yield model
    app.dependency_overrides.pop(get_chat_model, None)
    app.dependency_overrides.pop(get_embedder, None)


def tool_outputs(model: ScriptedModel) -> list[str]:
    return [str(m.content) for m in model.seen[-1] if isinstance(m, ToolMessage)]


async def test_chat_searches_documents_and_answers(
    client: AsyncClient, test_engine: AsyncEngine, make_auth_headers: AuthHeaders, scripted: ScriptedModel
) -> None:
    alice = await make_auth_headers("alice@example.com")
    await make_auth_headers("bob@example.com")
    await add_chunks(test_engine, "alice@example.com", "a.txt", [("alice fact", vector(0))])
    await add_chunks(test_engine, "bob@example.com", "b.txt", [("bob fact", vector(0))])
    scripted.script = [tool_call("search_documents", query="facts"), AIMessage(content="Alice fact (a.txt)")]

    response = await client.post("/chat", headers=alice, json={"message": "what facts?"})

    assert response.status_code == 200
    assert response.json() == {"answer": "Alice fact (a.txt)", "tools_used": ["search_documents"]}
    [output] = tool_outputs(scripted)
    assert "alice fact" in output and "bob fact" not in output


async def test_chat_list_documents_is_scoped_to_user(
    client: AsyncClient, test_engine: AsyncEngine, make_auth_headers: AuthHeaders, scripted: ScriptedModel
) -> None:
    alice = await make_auth_headers("alice@example.com")
    await make_auth_headers("bob@example.com")
    await add_chunks(test_engine, "alice@example.com", "a.txt", [("x", vector(0))])
    await add_chunks(test_engine, "bob@example.com", "b.txt", [("y", vector(0))])
    scripted.script = [tool_call("list_documents"), AIMessage(content="one document")]

    await client.post("/chat", headers=alice, json={"message": "what do I have?"})

    [output] = tool_outputs(scripted)
    assert "a.txt" in output and "b.txt" not in output


async def test_summary_tool_cannot_read_other_users_document(
    client: AsyncClient, test_engine: AsyncEngine, make_auth_headers: AuthHeaders, scripted: ScriptedModel
) -> None:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.models.document import Document

    alice = await make_auth_headers("alice@example.com")
    await make_auth_headers("bob@example.com")
    await add_chunks(test_engine, "bob@example.com", "b.txt", [("bob secret", vector(0))])
    async with async_sessionmaker(test_engine)() as session:
        bob_doc = (await session.execute(select(Document))).scalar_one()
    scripted.script = [
        tool_call("get_document_summary", document_id=str(bob_doc.id)),
        AIMessage(content="not found"),
    ]

    await client.post("/chat", headers=alice, json={"message": "summarize it"})

    assert tool_outputs(scripted) == ["Document not found."]


async def test_chat_model_failure_returns_503(
    client: AsyncClient, make_auth_headers: AuthHeaders, scripted: ScriptedModel
) -> None:
    scripted.fail = True
    headers = await make_auth_headers("alice@example.com")

    response = await client.post("/chat", headers=headers, json={"message": "hi"})

    assert response.status_code == 503


async def test_chat_requires_auth_and_message(client: AsyncClient, make_auth_headers: AuthHeaders) -> None:
    assert (await client.post("/chat", json={"message": "hi"})).status_code == 401
    headers = await make_auth_headers("alice@example.com")
    assert (await client.post("/chat", headers=headers, json={"message": ""})).status_code == 422


async def test_agent_activity_is_logged(
    client: AsyncClient,
    test_engine: AsyncEngine,
    make_auth_headers: AuthHeaders,
    scripted: ScriptedModel,
    caplog: pytest.LogCaptureFixture,
) -> None:
    headers = await make_auth_headers("alice@example.com")
    await add_chunks(test_engine, "alice@example.com", "a.txt", [("alice fact", vector(0))])
    scripted.script = [tool_call("search_documents", query="facts"), AIMessage(content="Alice fact (a.txt)")]

    with caplog.at_level("INFO", logger="app.services.agent"):
        await client.post("/chat", headers=headers, json={"message": "what facts?"})

    log = "\n".join(r.getMessage() for r in caplog.records)
    assert "question: what facts?" in log
    assert "model wants tools: search_documents" in log
    assert "tool start: search_documents" in log
    assert "tool result: [a.txt] alice fact" in log
    assert "model answered: Alice fact (a.txt)" in log
