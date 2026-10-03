from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "ai-native"
    environment: str = "dev"
    database_url: str = "postgresql+asyncpg://ainative:ainative@localhost:5432/ainative"


@lru_cache
def get_settings() -> Settings:
    return Settings()
