from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    app_env: str
    secret_key: str
    allowed_origins: list[str]

    # Database
    database_url: str

    # Redis
    redis_url: str

    # Qdrant
    qdrant_url: str
    qdrant_api_key: str
    qdrant_collection: str

    # Neo4j
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str

    # GitHub OAuth
    github_client_id: str
    github_client_secret: str
    github_redirect_uri: str

    # OpenRouter / LLM
    openrouter_api_key: str
    openrouter_base_url: str
    chat_model: str
    chat_model_fallback: str

    # Embeddings (OpenAI)
    openai_api_key: str
    embed_model: str

    # Celery
    celery_broker_url: str
    celery_result_backend: str

    # Storage
    repo_clone_dir: str

    @property
    def is_dev(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
