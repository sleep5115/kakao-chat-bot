from __future__ import annotations

import asyncio
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Protocol

from .config import Settings


@dataclass(frozen=True, slots=True)
class TrackedMessage:
    chat_id: str
    message_id: str
    sender_id: str | None
    sender_name: str | None
    content: str
    message_type: str | None
    sent_at: datetime


@dataclass(frozen=True, slots=True)
class MemberHistory:
    chat_id: str
    sender_id: str
    first_joined_at: datetime | None
    first_nickname: str | None
    current_nickname: str | None
    join_count: int
    last_joined_at: datetime | None
    last_left_at: datetime | None
    is_present: bool
    joined_at_history: tuple[datetime, ...] = ()


class TrackingRepository(Protocol):
    async def initialize(self) -> None: ...

    async def save_message(self, message: TrackedMessage) -> None: ...

    async def find_message(
        self, chat_id: str, message_id: str
    ) -> TrackedMessage | None: ...

    async def mark_deleted(
        self,
        chat_id: str,
        message_id: str,
        deleted_at: datetime,
        deleted_by_id: str | None,
        deleted_by_name: str | None,
    ) -> None: ...

    async def record_join(
        self,
        chat_id: str,
        sender_id: str,
        nickname: str | None,
        joined_at: datetime,
    ) -> MemberHistory: ...

    async def record_leave(
        self,
        chat_id: str,
        sender_id: str,
        nickname: str | None,
        left_at: datetime,
    ) -> MemberHistory: ...

    async def find_member(
        self, chat_id: str, sender_id: str
    ) -> MemberHistory | None: ...


def _as_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value)
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _message_from_row(row: Any) -> TrackedMessage:
    sent_at = _as_datetime(row["sent_at"])
    assert sent_at is not None
    return TrackedMessage(
        chat_id=str(row["chat_id"]),
        message_id=str(row["message_id"]),
        sender_id=str(row["sender_id"]) if row["sender_id"] is not None else None,
        sender_name=row["sender_name"],
        content=row["content"],
        message_type=(
            str(row["message_type"]) if row["message_type"] is not None else None
        ),
        sent_at=sent_at,
    )


def _member_from_row(
    row: Any, joined_at_history: tuple[datetime, ...] = ()
) -> MemberHistory:
    return MemberHistory(
        chat_id=str(row["chat_id"]),
        sender_id=str(row["sender_id"]),
        first_joined_at=_as_datetime(row["first_joined_at"]),
        first_nickname=row["first_nickname"],
        current_nickname=row["current_nickname"],
        join_count=int(row["join_count"]),
        last_joined_at=_as_datetime(row["last_joined_at"]),
        last_left_at=_as_datetime(row["last_left_at"]),
        is_present=bool(row["is_present"]),
        joined_at_history=joined_at_history,
    )


class SQLiteTrackingRepository:
    def __init__(self, database_path: str, retention_days: int) -> None:
        self._database_path = Path(database_path)
        self._retention_days = retention_days

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize_sync)

    async def save_message(self, message: TrackedMessage) -> None:
        await asyncio.to_thread(self._save_message_sync, message)

    async def find_message(
        self, chat_id: str, message_id: str
    ) -> TrackedMessage | None:
        return await asyncio.to_thread(self._find_message_sync, chat_id, message_id)

    async def mark_deleted(
        self,
        chat_id: str,
        message_id: str,
        deleted_at: datetime,
        deleted_by_id: str | None,
        deleted_by_name: str | None,
    ) -> None:
        await asyncio.to_thread(
            self._mark_deleted_sync,
            chat_id,
            message_id,
            deleted_at,
            deleted_by_id,
            deleted_by_name,
        )

    async def record_join(
        self,
        chat_id: str,
        sender_id: str,
        nickname: str | None,
        joined_at: datetime,
    ) -> MemberHistory:
        return await asyncio.to_thread(
            self._record_join_sync, chat_id, sender_id, nickname, joined_at
        )

    async def record_leave(
        self,
        chat_id: str,
        sender_id: str,
        nickname: str | None,
        left_at: datetime,
    ) -> MemberHistory:
        return await asyncio.to_thread(
            self._record_leave_sync, chat_id, sender_id, nickname, left_at
        )

    async def find_member(
        self, chat_id: str, sender_id: str
    ) -> MemberHistory | None:
        return await asyncio.to_thread(self._find_member_sync, chat_id, sender_id)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize_sync(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            with connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS tracked_messages (
                        chat_id TEXT NOT NULL,
                        message_id TEXT NOT NULL,
                        sender_id TEXT,
                        sender_name TEXT,
                        content TEXT NOT NULL,
                        message_type TEXT,
                        sent_at TEXT NOT NULL,
                        deleted_at TEXT,
                        deleted_by_id TEXT,
                        deleted_by_name TEXT,
                        PRIMARY KEY (chat_id, message_id),
                        FOREIGN KEY (chat_id) REFERENCES registered_rooms(chat_id)
                            ON DELETE CASCADE
                    );
                    CREATE INDEX IF NOT EXISTS tracked_messages_sent_at_idx
                        ON tracked_messages(sent_at);
                    CREATE TABLE IF NOT EXISTS room_members (
                        chat_id TEXT NOT NULL,
                        sender_id TEXT NOT NULL,
                        first_joined_at TEXT,
                        first_nickname TEXT,
                        current_nickname TEXT,
                        join_count INTEGER NOT NULL DEFAULT 0,
                        last_joined_at TEXT,
                        last_left_at TEXT,
                        is_present INTEGER NOT NULL DEFAULT 0
                            CHECK (is_present IN (0, 1)),
                        PRIMARY KEY (chat_id, sender_id),
                        FOREIGN KEY (chat_id) REFERENCES registered_rooms(chat_id)
                            ON DELETE CASCADE
                    );
                    CREATE TABLE IF NOT EXISTS room_member_joins (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        chat_id TEXT NOT NULL,
                        sender_id TEXT NOT NULL,
                        nickname TEXT,
                        joined_at TEXT NOT NULL,
                        UNIQUE (chat_id, sender_id, joined_at),
                        FOREIGN KEY (chat_id) REFERENCES registered_rooms(chat_id)
                            ON DELETE CASCADE
                    );
                    CREATE INDEX IF NOT EXISTS room_member_joins_member_idx
                        ON room_member_joins(chat_id, sender_id, joined_at);
                    INSERT OR IGNORE INTO room_member_joins (
                        chat_id, sender_id, nickname, joined_at
                    )
                    SELECT chat_id, sender_id, first_nickname, first_joined_at
                    FROM room_members
                    WHERE first_joined_at IS NOT NULL;
                    INSERT OR IGNORE INTO room_member_joins (
                        chat_id, sender_id, nickname, joined_at
                    )
                    SELECT chat_id, sender_id, current_nickname, last_joined_at
                    FROM room_members
                    WHERE last_joined_at IS NOT NULL;
                    """
                )

    def _save_message_sync(self, message: TrackedMessage) -> None:
        cutoff = datetime.now(UTC) - timedelta(days=self._retention_days)
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO tracked_messages (
                        chat_id, message_id, sender_id, sender_name, content,
                        message_type, sent_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(chat_id, message_id) DO NOTHING
                    """,
                    (
                        message.chat_id,
                        message.message_id,
                        message.sender_id,
                        message.sender_name,
                        message.content,
                        message.message_type,
                        message.sent_at.isoformat(),
                    ),
                )
                connection.execute(
                    "DELETE FROM tracked_messages WHERE sent_at < ?",
                    (cutoff.isoformat(),),
                )

    def _find_message_sync(
        self, chat_id: str, message_id: str
    ) -> TrackedMessage | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT chat_id, message_id, sender_id, sender_name, content,
                       message_type, sent_at
                FROM tracked_messages
                WHERE chat_id = ? AND message_id = ?
                """,
                (chat_id, message_id),
            ).fetchone()
        return _message_from_row(row) if row else None

    def _mark_deleted_sync(
        self,
        chat_id: str,
        message_id: str,
        deleted_at: datetime,
        deleted_by_id: str | None,
        deleted_by_name: str | None,
    ) -> None:
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    UPDATE tracked_messages
                    SET deleted_at = ?, deleted_by_id = ?, deleted_by_name = ?
                    WHERE chat_id = ? AND message_id = ?
                    """,
                    (
                        deleted_at.isoformat(),
                        deleted_by_id,
                        deleted_by_name,
                        chat_id,
                        message_id,
                    ),
                )

    def _record_join_sync(
        self,
        chat_id: str,
        sender_id: str,
        nickname: str | None,
        joined_at: datetime,
    ) -> MemberHistory:
        value = joined_at.isoformat()
        with closing(self._connect()) as connection:
            with connection:
                inserted = connection.execute(
                    """
                    INSERT INTO room_member_joins (
                        chat_id, sender_id, nickname, joined_at
                    ) VALUES (?, ?, ?, ?)
                    ON CONFLICT(chat_id, sender_id, joined_at) DO NOTHING
                    """,
                    (chat_id, sender_id, nickname, value),
                ).rowcount
                if inserted:
                    connection.execute(
                        """
                        INSERT INTO room_members (
                            chat_id, sender_id, first_joined_at, first_nickname,
                            current_nickname, join_count, last_joined_at, is_present
                        ) VALUES (?, ?, ?, ?, ?, 1, ?, 1)
                        ON CONFLICT(chat_id, sender_id) DO UPDATE SET
                            first_joined_at = CASE
                                WHEN room_members.first_joined_at IS NULL
                                     AND room_members.join_count > 0
                                THEN NULL
                                ELSE COALESCE(
                                    room_members.first_joined_at,
                                    excluded.first_joined_at
                                )
                            END,
                            first_nickname = COALESCE(
                                room_members.first_nickname, excluded.first_nickname
                            ),
                            current_nickname = excluded.current_nickname,
                            join_count = room_members.join_count + 1,
                            last_joined_at = excluded.last_joined_at,
                            is_present = 1
                        """,
                        (chat_id, sender_id, value, nickname, nickname, value),
                    )
                row = connection.execute(
                    "SELECT * FROM room_members WHERE chat_id = ? AND sender_id = ?",
                    (chat_id, sender_id),
                ).fetchone()
                history_rows = connection.execute(
                    """
                    SELECT joined_at FROM room_member_joins
                    WHERE chat_id = ? AND sender_id = ?
                    ORDER BY joined_at
                    """,
                    (chat_id, sender_id),
                ).fetchall()
        assert row is not None
        joined_at_history = tuple(
            value
            for history_row in history_rows
            if (value := _as_datetime(history_row["joined_at"])) is not None
        )
        return _member_from_row(row, joined_at_history)

    def _record_leave_sync(
        self,
        chat_id: str,
        sender_id: str,
        nickname: str | None,
        left_at: datetime,
    ) -> MemberHistory:
        value = left_at.isoformat()
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO room_members (
                        chat_id, sender_id, first_nickname, current_nickname,
                        join_count, last_left_at, is_present
                    ) VALUES (?, ?, ?, ?, 1, ?, 0)
                    ON CONFLICT(chat_id, sender_id) DO UPDATE SET
                        current_nickname = excluded.current_nickname,
                        last_left_at = excluded.last_left_at,
                        is_present = 0
                    """,
                    (chat_id, sender_id, nickname, nickname, value),
                )
                row = connection.execute(
                    "SELECT * FROM room_members WHERE chat_id = ? AND sender_id = ?",
                    (chat_id, sender_id),
                ).fetchone()
        assert row is not None
        return _member_from_row(row)

    def _find_member_sync(
        self, chat_id: str, sender_id: str
    ) -> MemberHistory | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM room_members WHERE chat_id = ? AND sender_id = ?",
                (chat_id, sender_id),
            ).fetchone()
        return _member_from_row(row) if row else None


class PostgresTrackingRepository:
    def __init__(
        self,
        database_url: str,
        retention_days: int,
        connect_timeout_seconds: float = 5.0,
        connection_factory: Callable[[str, float], Any] | None = None,
    ) -> None:
        self._database_url = database_url
        self._retention_days = retention_days
        self._connect_timeout_seconds = connect_timeout_seconds
        self._connection_factory = connection_factory

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize_sync)

    async def save_message(self, message: TrackedMessage) -> None:
        await asyncio.to_thread(self._save_message_sync, message)

    async def find_message(
        self, chat_id: str, message_id: str
    ) -> TrackedMessage | None:
        return await asyncio.to_thread(self._find_message_sync, chat_id, message_id)

    async def mark_deleted(
        self,
        chat_id: str,
        message_id: str,
        deleted_at: datetime,
        deleted_by_id: str | None,
        deleted_by_name: str | None,
    ) -> None:
        await asyncio.to_thread(
            self._mark_deleted_sync,
            chat_id,
            message_id,
            deleted_at,
            deleted_by_id,
            deleted_by_name,
        )

    async def record_join(
        self,
        chat_id: str,
        sender_id: str,
        nickname: str | None,
        joined_at: datetime,
    ) -> MemberHistory:
        return await asyncio.to_thread(
            self._record_join_sync, chat_id, sender_id, nickname, joined_at
        )

    async def record_leave(
        self,
        chat_id: str,
        sender_id: str,
        nickname: str | None,
        left_at: datetime,
    ) -> MemberHistory:
        return await asyncio.to_thread(
            self._record_leave_sync, chat_id, sender_id, nickname, left_at
        )

    async def find_member(
        self, chat_id: str, sender_id: str
    ) -> MemberHistory | None:
        return await asyncio.to_thread(self._find_member_sync, chat_id, sender_id)

    def _connect(self) -> Any:
        if self._connection_factory is not None:
            return self._connection_factory(
                self._database_url, self._connect_timeout_seconds
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
                CREATE TABLE IF NOT EXISTS tracked_messages (
                    chat_id TEXT NOT NULL REFERENCES registered_rooms(chat_id)
                        ON DELETE CASCADE,
                    message_id TEXT NOT NULL,
                    sender_id TEXT,
                    sender_name TEXT,
                    content TEXT NOT NULL,
                    message_type TEXT,
                    sent_at TIMESTAMPTZ NOT NULL,
                    deleted_at TIMESTAMPTZ,
                    deleted_by_id TEXT,
                    deleted_by_name TEXT,
                    PRIMARY KEY (chat_id, message_id)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS tracked_messages_sent_at_idx
                ON tracked_messages(sent_at)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS room_members (
                    chat_id TEXT NOT NULL REFERENCES registered_rooms(chat_id)
                        ON DELETE CASCADE,
                    sender_id TEXT NOT NULL,
                    first_joined_at TIMESTAMPTZ,
                    first_nickname TEXT,
                    current_nickname TEXT,
                    join_count INTEGER NOT NULL DEFAULT 0,
                    last_joined_at TIMESTAMPTZ,
                    last_left_at TIMESTAMPTZ,
                    is_present BOOLEAN NOT NULL DEFAULT FALSE,
                    PRIMARY KEY (chat_id, sender_id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS room_member_joins (
                    id BIGSERIAL PRIMARY KEY,
                    chat_id TEXT NOT NULL REFERENCES registered_rooms(chat_id)
                        ON DELETE CASCADE,
                    sender_id TEXT NOT NULL,
                    nickname TEXT,
                    joined_at TIMESTAMPTZ NOT NULL,
                    UNIQUE (chat_id, sender_id, joined_at)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS room_member_joins_member_idx
                ON room_member_joins(chat_id, sender_id, joined_at)
                """
            )
            connection.execute(
                """
                INSERT INTO room_member_joins (
                    chat_id, sender_id, nickname, joined_at
                )
                SELECT chat_id, sender_id, first_nickname, first_joined_at
                FROM room_members
                WHERE first_joined_at IS NOT NULL
                ON CONFLICT (chat_id, sender_id, joined_at) DO NOTHING
                """
            )
            connection.execute(
                """
                INSERT INTO room_member_joins (
                    chat_id, sender_id, nickname, joined_at
                )
                SELECT chat_id, sender_id, current_nickname, last_joined_at
                FROM room_members
                WHERE last_joined_at IS NOT NULL
                ON CONFLICT (chat_id, sender_id, joined_at) DO NOTHING
                """
            )

    def _save_message_sync(self, message: TrackedMessage) -> None:
        cutoff = datetime.now(UTC) - timedelta(days=self._retention_days)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO tracked_messages (
                    chat_id, message_id, sender_id, sender_name, content,
                    message_type, sent_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(chat_id, message_id) DO NOTHING
                """,
                (
                    message.chat_id,
                    message.message_id,
                    message.sender_id,
                    message.sender_name,
                    message.content,
                    message.message_type,
                    message.sent_at,
                ),
            )
            connection.execute(
                "DELETE FROM tracked_messages WHERE sent_at < %s", (cutoff,)
            )

    def _find_message_sync(
        self, chat_id: str, message_id: str
    ) -> TrackedMessage | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT chat_id, message_id, sender_id, sender_name, content,
                       message_type, sent_at
                FROM tracked_messages
                WHERE chat_id = %s AND message_id = %s
                """,
                (chat_id, message_id),
            ).fetchone()
        return _message_from_row(row) if row else None

    def _mark_deleted_sync(
        self,
        chat_id: str,
        message_id: str,
        deleted_at: datetime,
        deleted_by_id: str | None,
        deleted_by_name: str | None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE tracked_messages
                SET deleted_at = %s, deleted_by_id = %s, deleted_by_name = %s
                WHERE chat_id = %s AND message_id = %s
                """,
                (deleted_at, deleted_by_id, deleted_by_name, chat_id, message_id),
            )

    def _record_join_sync(
        self,
        chat_id: str,
        sender_id: str,
        nickname: str | None,
        joined_at: datetime,
    ) -> MemberHistory:
        with self._connect() as connection:
            inserted = connection.execute(
                """
                INSERT INTO room_member_joins (
                    chat_id, sender_id, nickname, joined_at
                ) VALUES (%s, %s, %s, %s)
                ON CONFLICT (chat_id, sender_id, joined_at) DO NOTHING
                RETURNING id
                """,
                (chat_id, sender_id, nickname, joined_at),
            ).fetchone()
            if inserted is not None:
                row = connection.execute(
                    """
                    INSERT INTO room_members (
                        chat_id, sender_id, first_joined_at, first_nickname,
                        current_nickname, join_count, last_joined_at, is_present
                    ) VALUES (%s, %s, %s, %s, %s, 1, %s, TRUE)
                    ON CONFLICT(chat_id, sender_id) DO UPDATE SET
                        first_joined_at = CASE
                            WHEN room_members.first_joined_at IS NULL
                                 AND room_members.join_count > 0
                            THEN NULL
                            ELSE COALESCE(
                                room_members.first_joined_at,
                                excluded.first_joined_at
                            )
                        END,
                        first_nickname = COALESCE(
                            room_members.first_nickname, excluded.first_nickname
                        ),
                        current_nickname = excluded.current_nickname,
                        join_count = room_members.join_count + 1,
                        last_joined_at = excluded.last_joined_at,
                        is_present = TRUE
                    RETURNING *
                    """,
                    (chat_id, sender_id, joined_at, nickname, nickname, joined_at),
                ).fetchone()
            else:
                row = connection.execute(
                    """
                    SELECT * FROM room_members
                    WHERE chat_id = %s AND sender_id = %s
                    """,
                    (chat_id, sender_id),
                ).fetchone()
            history_rows = connection.execute(
                """
                SELECT joined_at FROM room_member_joins
                WHERE chat_id = %s AND sender_id = %s
                ORDER BY joined_at
                """,
                (chat_id, sender_id),
            ).fetchall()
        assert row is not None
        joined_at_history = tuple(
            value
            for history_row in history_rows
            if (value := _as_datetime(history_row["joined_at"])) is not None
        )
        return _member_from_row(row, joined_at_history)

    def _record_leave_sync(
        self,
        chat_id: str,
        sender_id: str,
        nickname: str | None,
        left_at: datetime,
    ) -> MemberHistory:
        with self._connect() as connection:
            row = connection.execute(
                """
                INSERT INTO room_members (
                    chat_id, sender_id, first_nickname, current_nickname,
                    join_count, last_left_at, is_present
                ) VALUES (%s, %s, %s, %s, 1, %s, FALSE)
                ON CONFLICT(chat_id, sender_id) DO UPDATE SET
                    current_nickname = excluded.current_nickname,
                    last_left_at = excluded.last_left_at,
                    is_present = FALSE
                RETURNING *
                """,
                (chat_id, sender_id, nickname, nickname, left_at),
            ).fetchone()
        assert row is not None
        return _member_from_row(row)

    def _find_member_sync(
        self, chat_id: str, sender_id: str
    ) -> MemberHistory | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM room_members
                WHERE chat_id = %s AND sender_id = %s
                """,
                (chat_id, sender_id),
            ).fetchone()
        return _member_from_row(row) if row else None


def create_tracking_repository(settings: Settings) -> TrackingRepository:
    if settings.room_database_url:
        return PostgresTrackingRepository(
            settings.room_database_url,
            settings.message_retention_days,
            connect_timeout_seconds=settings.iris_request_timeout_seconds,
        )
    return SQLiteTrackingRepository(
        settings.room_database_path, settings.message_retention_days
    )
