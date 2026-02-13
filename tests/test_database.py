import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from sqlalchemy.dialects import postgresql

from src.domain.models import RepositoryEntity
from src.infrastructure.database import PostgresRepository


class _DummyConn:
    def __init__(self) -> None:
        self.executed = None

    async def execute(self, stmt) -> None:
        self.executed = stmt


class _DummyBegin:
    def __init__(self, conn: _DummyConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _DummyConn:
        return self._conn

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class _DummyEngine:
    def __init__(self, conn: _DummyConn) -> None:
        self._conn = conn

    def begin(self) -> _DummyBegin:
        return _DummyBegin(self._conn)


class TestPostgresRepository(unittest.IsolatedAsyncioTestCase):
    async def test_bulk_upsert_uses_excluded_updated_at(self) -> None:
        conn = _DummyConn()
        engine = _DummyEngine(conn)

        with patch("src.infrastructure.database.create_async_engine", return_value=engine):
            repo = PostgresRepository("postgresql+asyncpg://user:pass@localhost/db")

        entity = RepositoryEntity(
            id="repo-1",
            name="example",
            owner="octocat",
            stars=10,
            updated_at=datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        )

        await repo.bulk_upsert([entity])

        self.assertIsNotNone(conn.executed)
        sql = str(conn.executed.compile(dialect=postgresql.dialect())).lower()
        self.assertIn("excluded.updated_at", sql)

    async def test_bulk_upsert_sets_crawled_at_to_now(self) -> None:
        conn = _DummyConn()
        engine = _DummyEngine(conn)

        with patch("src.infrastructure.database.create_async_engine", return_value=engine):
            repo = PostgresRepository("postgresql+asyncpg://user:pass@localhost/db")

        entity = RepositoryEntity(
            id="repo-1",
            name="example",
            owner="octocat",
            stars=10,
            updated_at=datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        )

        await repo.bulk_upsert([entity])

        self.assertIsNotNone(conn.executed)
        sql = str(conn.executed.compile(dialect=postgresql.dialect())).lower()
        self.assertIn("now()", sql)
