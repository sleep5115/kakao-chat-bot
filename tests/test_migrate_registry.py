from __future__ import annotations

import unittest

from kakao_bot.migrate_registry import migrate_registered_rooms
from kakao_bot.registry import RegisteredRoom


class InMemoryRegistry:
    def __init__(self, rooms: list[RegisteredRoom] | None = None) -> None:
        self.rooms = {room.chat_id: room for room in rooms or []}
        self.initialized = False

    async def initialize(self) -> None:
        self.initialized = True

    async def is_registered(self, chat_id: str) -> bool:
        return chat_id in self.rooms

    async def register(self, chat_id: str, room_type: str) -> None:
        self.rooms[chat_id] = RegisteredRoom(chat_id, room_type, "migrated")

    async def disable(self, chat_id: str) -> bool:
        return self.rooms.pop(chat_id, None) is not None

    async def list_registered(self) -> list[RegisteredRoom]:
        return list(self.rooms.values())


class RegistryMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_migrates_enabled_rooms_and_verifies_them(self) -> None:
        source = InMemoryRegistry(
            [
                RegisteredRoom("room-1", "OM", "2026-08-22T00:00:00+00:00"),
                RegisteredRoom("room-2", "DirectChat", "2026-08-22T00:00:01+00:00"),
            ]
        )
        target = InMemoryRegistry()

        migrated = await migrate_registered_rooms(source, target)

        self.assertEqual(migrated, 2)
        self.assertTrue(source.initialized)
        self.assertTrue(target.initialized)
        self.assertEqual(set(target.rooms), {"room-1", "room-2"})


if __name__ == "__main__":
    unittest.main()

