from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

from kakao_bot.config import Settings
from kakao_bot.registry import SQLiteRoomRegistry
from kakao_bot.tracking import (
    PostgresTrackingRepository,
    SQLiteTrackingRepository,
    TrackedMessage,
    create_tracking_repository,
)


class SQLiteTrackingRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addAsyncCleanup(self._cleanup)
        self.path = Path(self.temp_dir.name) / "tracking.db"
        self.rooms = SQLiteRoomRegistry(str(self.path))
        await self.rooms.initialize()
        await self.rooms.register("room-1", "OM")
        self.tracking = SQLiteTrackingRepository(str(self.path), retention_days=30)
        await self.tracking.initialize()

    async def _cleanup(self) -> None:
        self.temp_dir.cleanup()

    async def test_saves_finds_and_marks_deleted_message(self) -> None:
        sent_at = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
        message = TrackedMessage(
            chat_id="room-1",
            message_id="message-1",
            sender_id="user-1",
            sender_name="첫 닉네임",
            content="삭제될 메시지",
            message_type="1",
            sent_at=sent_at,
        )

        await self.tracking.save_message(message)
        found = await self.tracking.find_message("room-1", "message-1")
        await self.tracking.mark_deleted(
            "room-1",
            "message-1",
            sent_at + timedelta(minutes=1),
            "user-1",
            "현재 닉네임",
        )

        self.assertEqual(found, message)
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute(
                "SELECT deleted_by_id, deleted_by_name FROM tracked_messages"
            ).fetchone()
        self.assertEqual(row, ("user-1", "현재 닉네임"))

    async def test_purges_messages_outside_retention_window(self) -> None:
        old = TrackedMessage(
            chat_id="room-1",
            message_id="old",
            sender_id=None,
            sender_name=None,
            content="old",
            message_type="1",
            sent_at=datetime.now(UTC) - timedelta(days=31),
        )

        await self.tracking.save_message(old)

        self.assertIsNone(await self.tracking.find_message("room-1", "old"))

    async def test_tracks_first_nickname_and_reentry_count(self) -> None:
        first_at = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
        first = await self.tracking.record_join(
            "room-1", "user-1", "첫 닉", first_at
        )
        await self.tracking.record_leave(
            "room-1", "user-1", "중간 닉", first_at + timedelta(hours=1)
        )
        rejoined = await self.tracking.record_join(
            "room-1", "user-1", "새 닉", first_at + timedelta(hours=2)
        )

        self.assertEqual(first.join_count, 1)
        self.assertEqual(rejoined.first_joined_at, first_at)
        self.assertEqual(rejoined.first_nickname, "첫 닉")
        self.assertEqual(rejoined.current_nickname, "새 닉")
        self.assertEqual(rejoined.join_count, 2)
        self.assertEqual(
            rejoined.joined_at_history,
            (first_at, first_at + timedelta(hours=2)),
        )
        self.assertTrue(rejoined.is_present)
        found = await self.tracking.find_member("room-1", "user-1")
        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(found.current_nickname, "새 닉")

    async def test_duplicate_join_event_does_not_duplicate_history(self) -> None:
        joined_at = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)

        await self.tracking.record_join("room-1", "user-1", "닉", joined_at)
        duplicate = await self.tracking.record_join(
            "room-1", "user-1", "닉", joined_at
        )

        self.assertEqual(duplicate.join_count, 1)
        self.assertEqual(duplicate.joined_at_history, (joined_at,))

    async def test_room_deletion_cascades_tracking_records(self) -> None:
        await self.tracking.save_message(
            TrackedMessage(
                chat_id="room-1",
                message_id="message-1",
                sender_id="user-1",
                sender_name="name",
                content="message",
                message_type="1",
                sent_at=datetime.now(UTC),
            )
        )
        await self.tracking.record_join(
            "room-1", "user-1", "name", datetime.now(UTC)
        )

        await self.rooms.unregister("room-1")

        self.assertIsNone(
            await self.tracking.find_message("room-1", "message-1")
        )
        with closing(sqlite3.connect(self.path)) as connection:
            member_count = connection.execute(
                "SELECT COUNT(*) FROM room_members"
            ).fetchone()[0]
            join_count = connection.execute(
                "SELECT COUNT(*) FROM room_member_joins"
            ).fetchone()[0]
        self.assertEqual(member_count, 0)
        self.assertEqual(join_count, 0)


class TrackingRepositoryFactoryTests(unittest.TestCase):
    def test_sqlite_is_local_default(self) -> None:
        repository = create_tracking_repository(Settings())
        self.assertIsInstance(repository, SQLiteTrackingRepository)

    def test_database_url_selects_postgres(self) -> None:
        repository = create_tracking_repository(
            Settings(
                room_database_url="postgresql://bot:secret@db:5432/kakao_bot"
            )
        )
        self.assertIsInstance(repository, PostgresTrackingRepository)


if __name__ == "__main__":
    unittest.main()
