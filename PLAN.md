# ai-native: plan and dev loop

Multi-user document Q&A app (agent + RAG) built to learn: FastAPI, Pydantic, SQLAlchemy, Alembic, Celery, Redis, Postgres/pgvector, LangChain, Langfuse, pytest, httpx, uv, React.

## Dev loop

All commands from the repo root unless noted.

```bash
# 1. Start infra (Postgres+pgvector, Redis). Docker Desktop must be running.
docker compose up -d --wait

# 2. Backend deps and DB schema
cd backend
uv sync
uv run alembic upgrade head

# 3. Run the API (http://127.0.0.1:8000, docs at /docs)
uv run uvicorn app.main:app --reload

# 3b. Run the Celery worker in a second terminal (--pool=solo is required on Windows)
uv run celery -A app.worker.celery_app worker --loglevel=info --pool=solo

# 4. Test
uv run pytest -q

# 5. After changing a model: generate, READ, then apply a migration
uv run alembic revision --autogenerate -m "describe change"
uv run alembic upgrade head

# Other
uv run alembic current            # current DB revision
uv run alembic downgrade -1       # undo last migration
uv add <pkg>  /  uv add --dev <pkg>
docker compose down               # stop (data kept)
docker compose down -v            # stop and wipe data
```

## Decisions

- Layered backend: routers -> services -> repositories.
- Auth: hand-rolled JWT (access tokens only), argon2/bcrypt hashing.
- Every retrieval query filtered by `user_id` (+ dedicated isolation test).
- Celery with Redis broker; document status stored in Postgres.
- Embedding model recorded per chunk (dimension differs between providers).
- LLM and embeddings: Ollama or hosted small model behind a config switch.
- Streaming answers via SSE (fetch + stream reader in React).
- Every new model must be imported in `app/models/__init__.py` or Alembic will not see it.

## Done

- [x] Milestone 1: skeleton (uv, FastAPI, settings, Docker Compose, `/health` with DB check, async pytest)
- [x] Alembic async setup, `User` model, first migration (`users` table)

## To do

### Milestone 2: auth and users (in progress)
- [ ] `core/security.py`: password hashing + JWT create/decode, unit tests
- [ ] Pydantic schemas (`UserCreate`, `UserRead`, `Token`)
- [ ] `repositories/user.py`, `services/auth.py`
- [ ] `POST /auth/register`, `POST /auth/login`, `GET /users/me` (`get_current_user` dependency)
- [ ] Tests: register, duplicate email, login, bad password, protected route
- [ ] Test DB isolation (separate test database or rollback per test)

### Milestone 3: documents and Celery
- [ ] Migration: `CREATE EXTENSION vector`, `documents` and `chunks` tables
- [ ] Upload endpoint + status (`pending`, `processing`, `ready`, `failed`)
- [ ] Celery worker: extract -> chunk -> embed -> store

### Milestone 4: retrieval and agent
- [ ] pgvector search filtered by user
- [ ] LangChain agent (tools: `search_documents`, `list_documents`, `get_document_summary`), non-streaming
- [ ] LLM/embedding provider switch (Ollama / hosted)

### Milestone 5: streaming and observability
- [ ] SSE endpoint (tool events + tokens)
- [ ] Langfuse tracing (add to Compose)

### Milestone 6: React frontend
- [ ] Login/register, documents list with status polling, chat with streaming + citations

### Milestone 7: polish
- [ ] Multi-tenancy isolation test, small eval set, README

## Open questions

- [ ] `app/models/__init__.py` style: keep re-export + `__all__` (A) or just `from app.models import user  # noqa: F401` (B)?
- [ ] Keep `String(255)` for email/hashed_password, or switch to `Text`? (Regenerate the migration if so, while it is the only one.)
- [ ] Alias `DbSession = Annotated[AsyncSession, Depends(get_db)]` once there are several routes.
- [ ] Commit: Steps 14-16 are not committed yet.
- [ ] Enqueue failure: if Redis is down after the document row is committed, the document stays `pending` forever. Fix later with a transactional outbox or a periodic sweeper that re-enqueues old `pending` rows.
- [ ] Production: `SECRET_KEY` must come from the environment (the default in `config.py` is dev only).

## Gotchas learned

- SQLAlchemy async needs `sqlalchemy[asyncio]` (greenlet).
- Driver errors like `ConnectionRefusedError` are plain `OSError`, not `SQLAlchemyError`: catch both for the DB health check.
- pytest-asyncio: use a session-scoped loop so pooled DB connections do not outlive their loop.
- `PYTHONDONTWRITEBYTECODE=1` is set at user level; terminals and editors started before that need a restart.
- Celery tasks are sync: async DB code runs via `asyncio.run` with a per-task `NullPool` engine (a pooled engine would be tied to a dead event loop).
- The processing task is idempotent: it only starts from `pending`, so redelivered messages do nothing.
