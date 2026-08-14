"""
Application configuration, loaded from environment variables.

Design decision: DATABASE_URL defaults to a local SQLite file so the project
can be cloned and run with zero external services for evaluation/demo
purposes. Swapping to PostgreSQL only requires setting DATABASE_URL to a
postgres:// DSN (see docker-compose.yml) - the code makes no SQLite-specific
assumptions beyond the default.
"""
import os
from functools import lru_cache


class Settings:
    APP_NAME: str = "TraceFlow AI"
    ENV: str = os.getenv("ENV", "development")

    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "sqlite:///./data/traceflow.db"
    )

    # LLM configuration. If ANTHROPIC_API_KEY is not set, the system falls
    # back to a deterministic, template-based synthesis step instead of
    # calling an external model. This keeps the demo runnable offline and
    # keeps the honesty guarantee: we never silently pretend an LLM call
    # happened when it didn't.
    ANTHROPIC_API_KEY: str | None = os.getenv("ANTHROPIC_API_KEY")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "claude-sonnet-4-6")
    LLM_ENABLED: bool = bool(ANTHROPIC_API_KEY)

    # Security controls (see docs/security.md)
    SQL_QUERY_TIMEOUT_SECONDS: int = int(os.getenv("SQL_QUERY_TIMEOUT_SECONDS", "5"))
    SQL_MAX_ROWS: int = int(os.getenv("SQL_MAX_ROWS", "500"))

    CORS_ORIGINS: list[str] = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")


@lru_cache
def get_settings() -> Settings:
    return Settings()
