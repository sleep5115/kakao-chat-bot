from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

from kakao_bot.config import Settings
from kakao_bot.registry import (
    PostgresRoomRegistry,
    SQLiteRoomRegistry,
    create_room_registry,
)


class SQLiteRoomRegistryTests(unittest.IsolatedAsyncioTestCase):
    async def test_registration_persists_and_can_be_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "registry.db"
            first = SQLiteRoomRegistry(str(path))
            await first.initialize()
            await first.register("room-1", "OM")

            second = SQLiteRoomRegistry(str(path))
            await second.initialize()
            rooms = await second.list_registered()

            self.assertTrue(await second.is_registered("room-1"))
            self.assertEqual(len(rooms), 1)
            self.assertEqual(rooms[0].room_type, "OM")
            self.assertTrue(await second.disable("room-1"))
            self.assertFalse(await second.is_registered("room-1"))


class PostgresRoomRegistryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.connection = MagicMock()
        self.connection.__enter__.return_value = self.connection
        self.connection.__exit__.return_value = False
        self.connect = MagicMock(return_value=self.connection)
        self.registry = PostgresRoomRegistry(
            "postgresql://bot:secret@db:5432/kakao_bot",
            connection_factory=self.connect,
        )

    async def test_initialize_creates_postgres_table(self) -> None:
        await self.registry.initialize()

        statement = self.connection.execute.call_args.args[0]
        self.assertIn("CREATE TABLE IF NOT EXISTS registered_rooms", statement)
        self.assertIn("TIMESTAMPTZ", statement)
        self.connect.assert_called_once()

    async def test_registration_lookup_and_disable_use_parameters(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = {"?column?": 1}
        cursor.rowcount = 1
        self.connection.execute.return_value = cursor

        await self.registry.register("room-1", "OM")
        self.assertTrue(await self.registry.is_registered("room-1"))
        self.assertTrue(await self.registry.disable("room-1"))

        calls = self.connection.execute.call_args_list
        self.assertEqual(calls[0].args[1][:2], ("room-1", "OM"))
        self.assertIsInstance(calls[0].args[1][2], datetime)
        self.assertEqual(calls[1].args[1], ("room-1",))
        self.assertEqual(calls[2].args[1], ("room-1",))

    async def test_list_registered_normalizes_timestamp(self) -> None:
        cursor = MagicMock()
        registered_at = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
        cursor.fetchall.return_value = [
            {
                "chat_id": "room-1",
                "room_type": "OM",
                "registered_at": registered_at,
            }
        ]
        self.connection.execute.return_value = cursor

        rooms = await self.registry.list_registered()

        self.assertEqual(rooms[0].registered_at, registered_at.isoformat())


class RoomRegistryFactoryTests(unittest.TestCase):
    def test_sqlite_is_the_local_default(self) -> None:
        registry = create_room_registry(Settings())
        self.assertIsInstance(registry, SQLiteRoomRegistry)

    def test_database_url_selects_postgres(self) -> None:
        registry = create_room_registry(
            Settings(
                room_database_url=(
                    "postgresql://bot:secret@pickty-postgres:5432/kakao_bot"
                )
            )
        )
        self.assertIsInstance(registry, PostgresRoomRegistry)


if __name__ == "__main__":
    unittest.main()
