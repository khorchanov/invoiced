from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "ai-native"
    environment: str = "dev"
    database_url: str = "postgresql+asyncpg://ainative:ainative@localhost:5432/ainative"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "dev-only-secret-change-me-in-production-0123456789"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    upload_dir: str = "uploads"
    max_upload_bytes: int = 10 * 1024 * 1024
    ollama_base_url: str = "http://localhost:11434"
    embedding_model: str = "nomic-embed-text"
    embedding_dimensions: int = 768


@lru_cache
def get_settings() -> Settings:
    return Settings()
