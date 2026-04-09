from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import settings

ENGINE_CONNECT_ARGS = {"connect_timeout": 15}
if "render.com" in settings.database_url or "dpg-" in settings.database_url:
    ENGINE_CONNECT_ARGS["sslmode"] = "require"

engine = create_engine(
    settings.database_url,
    future=True,
    pool_pre_ping=True,
    connect_args=ENGINE_CONNECT_ARGS,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
readonly_engine = create_engine(
    settings.database_url,
    future=True,
    pool_pre_ping=True,
    pool_size=1,
    max_overflow=0,
    connect_args=ENGINE_CONNECT_ARGS,
)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def wait_for_database(max_attempts: int = 18, delay_seconds: int = 5) -> None:
    last_error: Exception | None = None
    for attempt in range(max_attempts):
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return
        except Exception as exc:  # pragma: no cover - startup resilience path
            last_error = exc
            if attempt == max_attempts - 1:
                break
            import time
            time.sleep(delay_seconds)
    if last_error:
        raise last_error


@contextmanager
def get_readonly_connection():
    connection = readonly_engine.connect()
    try:
        yield connection
    finally:
        connection.close()
