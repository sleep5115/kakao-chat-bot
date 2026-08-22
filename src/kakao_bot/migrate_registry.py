from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from .registry import PostgresRoomRegistry, RoomRegistry, SQLiteRoomRegistry


async def migrate_registered_rooms(
    source: RoomRegistry,
    target: RoomRegistry,
) -> int:
    await source.initialize()
    await target.initialize()
    rooms = await source.list_registered()

    for room in rooms:
        await target.register(room.chat_id, room.room_type)

    for room in rooms:
        if not await target.is_registered(room.chat_id):
            raise RuntimeError("PostgreSQL registration verification failed")

    return len(rooms)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate enabled room registrations from SQLite to PostgreSQL."
    )
    parser.add_argument(
        "--sqlite-path",
        default=os.getenv("ROOM_DATABASE_PATH", "data/kakao_bot.db"),
        help="Source SQLite database path (default: ROOM_DATABASE_PATH)",
    )
    return parser.parse_args()


async def _run() -> int:
    args = _parse_args()
    sqlite_path = Path(args.sqlite_path)
    if not sqlite_path.is_file():
        raise SystemExit(f"SQLite source does not exist: {sqlite_path}")

    database_url = os.getenv("ROOM_DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit("ROOM_DATABASE_URL is required")

    migrated = await migrate_registered_rooms(
        SQLiteRoomRegistry(str(sqlite_path)),
        PostgresRoomRegistry(database_url),
    )
    print(f"Migrated and verified {migrated} registered room(s).")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()

