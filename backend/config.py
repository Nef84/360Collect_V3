from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "360CollectPlus API"
    database_url: str = "postgresql+psycopg2://postgres:postgres@db:5432/collectplus"

    # JWT — access token
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 15

    # JWT — refresh token
    jwt_refresh_secret_key: str = "change-me-refresh-in-production"
    jwt_refresh_expire_days: int = 7

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

# ── Business constants ──────────────────────────────────────────────────────
COLLECTOR_DAILY_WORKLIST_LIMIT = 420
PLACEMENT_SEQUENCE = ["V11", "V12", "V13", "V16", "V18"]
PLACEMENT_EXTERNAL_SUFFIX = {"V11": "0", "V12": "1", "V13": "2", "V16": "5", "V18": "4"}
EXTERNAL_AGENCY_SLOTS = list(range(1, 11))
INTERNAL_WORKLIST_SLOTS = list(range(1, 16))
