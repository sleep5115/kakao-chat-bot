from __future__ import annotations

import asyncio
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Protocol

from .config import Settings


@dataclass(frozen=True, slots=True)
class RegisteredRoom:
    chat_id: str
    room_type: str
    registered_at: str


class RoomRegistry(Protocol):
    async def initialize(self) -> None: ...

    async def is_registered(self, chat_id: str) -> bool: ...

    async def register(self, chat_id: str, room_type: str) -> None: ...

    async def unregister(self, chat_id: str) -> bool: ...

    async def list_registered(self) -> list[RegisteredRoom]: ...


class SQLiteRoomRegistry:
    """Privacy-minimal local registry for development."""

    def __init__(self, database_path: str) -> None:
        self._database_path = Path(database_path)

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize_sync)

    async def is_registered(self, chat_id: str) -> bool:
        return await asyncio.to_thread(self._is_registered_sync, chat_id)

    async def register(self, chat_id: str, room_type: str) -> None:
        await asyncio.to_thread(self._register_sync, chat_id, room_type)

    async def unregister(self, chat_id: str) -> bool:
        return await asyncio.to_thread(self._unregister_sync, chat_id)

    async def list_registered(self) -> list[RegisteredRoom]:
        return await asyncio.to_thread(self._list_registered_sync)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize_sync(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            with connection:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS registered_rooms (
                        chat_id TEXT PRIMARY KEY,
                        room_type TEXT NOT NULL,
                        registered_at TEXT NOT NULL,
                        enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1))
                    )
                    """
                )

    def _is_registered_sync(self, chat_id: str) -> bool:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT 1 FROM registered_rooms WHERE chat_id = ? AND enabled = 1",
                (chat_id,),
            ).fetchone()
        return row is not None

    def _register_sync(self, chat_id: str, room_type: str) -> None:
        registered_at = datetime.now(UTC).isoformat()
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO registered_rooms (chat_id, room_type, registered_at, enabled)
                    VALUES (?, ?, ?, 1)
                    ON CONFLICT(chat_id) DO UPDATE SET
                        room_type = excluded.room_type,
                        registered_at = excluded.registered_at,
                        enabled = 1
                    """,
                    (chat_id, room_type, registered_at),
                )

    def _unregister_sync(self, chat_id: str) -> bool:
        with closing(self._connect()) as connection:
            with connection:
                cursor = connection.execute(
                    "DELETE FROM registered_rooms WHERE chat_id = ?",
                    (chat_id,),
                )
                changed = cursor.rowcount > 0
        return changed

    def _list_registered_sync(self) -> list[RegisteredRoom]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT chat_id, room_type, registered_at
                FROM registered_rooms
                WHERE enabled = 1
                ORDER BY registered_at
                """
            ).fetchall()
        return [
            RegisteredRoom(
                chat_id=row["chat_id"],
                room_type=row["room_type"],
                registered_at=row["registered_at"],
            )
            for row in rows
        ]


class PostgresRoomRegistry:
    """Production registry using the bot's dedicated PostgreSQL database."""

    def __init__(
        self,
        database_url: str,
        connect_timeout_seconds: float = 5.0,
        connection_factory: Callable[[str, float], Any] | None = None,
    ) -> None:
        self._database_url = database_url
        self._connect_timeout_seconds = connect_timeout_seconds
        self._connection_factory = connection_factory

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize_sync)

    async def is_registered(self, chat_id: str) -> bool:
        return await asyncio.to_thread(self._is_registered_sync, chat_id)

    async def register(self, chat_id: str, room_type: str) -> None:
        await asyncio.to_thread(self._register_sync, chat_id, room_type)

    async def unregister(self, chat_id: str) -> bool:
        return await asyncio.to_thread(self._unregister_sync, chat_id)

    async def list_registered(self) -> list[RegisteredRoom]:
        return await asyncio.to_thread(self._list_registered_sync)

    def _connect(self) -> Any:
        if self._connection_factory is not None:
            return self._connection_factory(
                self._database_url,
                self._connect_timeout_seconds,
            )

        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(
            self._database_url,
            connect_timeout=self._connect_timeout_seconds,
            row_factory=dict_row,
        )

    def _initialize_sync(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS registered_rooms (
                    chat_id TEXT PRIMARY KEY,
                    room_type TEXT NOT NULL,
                    registered_at TIMESTAMPTZ NOT NULL,
                    enabled BOOLEAN NOT NULL DEFAULT TRUE
                )
                """
            )

    def _is_registered_sync(self, chat_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM registered_rooms
                WHERE chat_id = %s AND enabled = TRUE
                """,
                (chat_id,),
            ).fetchone()
        return row is not None

    def _register_sync(self, chat_id: str, room_type: str) -> None:
        registered_at = datetime.now(UTC)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO registered_rooms (chat_id, room_type, registered_at, enabled)
                VALUES (%s, %s, %s, TRUE)
                ON CONFLICT(chat_id) DO UPDATE SET
                    room_type = excluded.room_type,
                    registered_at = excluded.registered_at,
                    enabled = TRUE
                """,
                (chat_id, room_type, registered_at),
            )

    def _unregister_sync(self, chat_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM registered_rooms
                WHERE chat_id = %s
                """,
                (chat_id,),
            )
            changed = cursor.rowcount > 0
        return changed

    def _list_registered_sync(self) -> list[RegisteredRoom]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT chat_id, room_type, registered_at
                FROM registered_rooms
                WHERE enabled = TRUE
                ORDER BY registered_at
                """
            ).fetchall()
        return [
            RegisteredRoom(
                chat_id=row["chat_id"],
                room_type=row["room_type"],
                registered_at=(
                    row["registered_at"].isoformat()
                    if isinstance(row["registered_at"], datetime)
                    else str(row["registered_at"])
                ),
            )
            for row in rows
        ]


def create_room_registry(settings: Settings) -> RoomRegistry:
    if settings.room_database_url:
        return PostgresRoomRegistry(
            settings.room_database_url,
            connect_timeout_seconds=settings.iris_request_timeout_seconds,
        )
    return SQLiteRoomRegistry(settings.room_database_path)
