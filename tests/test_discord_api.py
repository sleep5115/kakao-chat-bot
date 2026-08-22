from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from kakao_bot.config import Settings
from kakao_bot.main import create_app


class FakeRoomRegistry:
    def __init__(self, registered: bool) -> None:
        self.registered = registered
        self.requested_room_ids: list[str] = []

    async def is_registered(self, chat_id: str) -> bool:
        self.requested_room_ids.append(chat_id)
        return self.registered


class FakeIrisApi:
    def __init__(self) -> None:
        self.replies: list[tuple[str, str]] = []

    async def reply(self, room_id: str, message: str) -> None:
        self.replies.append((room_id, message))


class DiscordBridgeEndpointTests(unittest.TestCase):
    def _settings(self, database_path: str) -> Settings:
        return Settings(
            iris_base_url="http://127.0.0.1:9",
            iris_request_timeout_seconds=0.1,
            iris_reconnect_initial_seconds=0.1,
            iris_reconnect_max_seconds=0.1,
            room_database_path=database_path,
            discord_kakao_room_id="123456",
            discord_bridge_secret="bridge-secret",
            discord_max_message_chars=100,
        )

    def test_authorized_request_forwards_formatted_message(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self._settings(str(Path(temp_dir) / "registry.db"))
            app = create_app(settings)
            registry = FakeRoomRegistry(registered=True)
            iris = FakeIrisApi()

            with TestClient(app) as client:
                app.state.room_registry = registry
                app.state.iris_api = iris
                response = client.post(
                    "/internal/discord/messages",
                    headers={"X-Discord-Bridge-Token": "bridge-secret"},
                    json={
                        "sender_name": " 디코   닉 ",
                        "message": "안녕하세요",
                    },
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "sent"})
        self.assertEqual(registry.requested_room_ids, ["123456"])
        self.assertEqual(
            iris.replies,
            [
                (
                    "123456",
                    "디코 디코 닉 :\n안녕하세요",
                )
            ],
        )

    def test_invalid_secret_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = create_app(
                self._settings(str(Path(temp_dir) / "registry.db"))
            )
            with TestClient(app) as client:
                response = client.post(
                    "/internal/discord/messages",
                    headers={"X-Discord-Bridge-Token": "wrong"},
                    json={"sender_name": "디코닉", "message": "안녕하세요"},
                )

        self.assertEqual(response.status_code, 401)

    def test_unregistered_destination_room_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = create_app(
                self._settings(str(Path(temp_dir) / "registry.db"))
            )
            registry = FakeRoomRegistry(registered=False)
            iris = FakeIrisApi()

            with TestClient(app) as client:
                app.state.room_registry = registry
                app.state.iris_api = iris
                response = client.post(
                    "/internal/discord/messages",
                    headers={"X-Discord-Bridge-Token": "bridge-secret"},
                    json={"sender_name": "디코닉", "message": "안녕하세요"},
                )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(iris.replies, [])


if __name__ == "__main__":
    unittest.main()
