from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from kakao_bot.config import ConfigError, Settings


class SettingsTests(unittest.TestCase):
    def test_defaults_point_to_adb_forward(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings.from_env()

        self.assertEqual(settings.iris_base_url, "http://127.0.0.1:3000")
        self.assertEqual(settings.iris_websocket_url, "ws://127.0.0.1:3000/ws")
        self.assertEqual(settings.bot_command, "!핑")
        self.assertEqual(settings.message_retention_days, 30)

    def test_https_base_url_becomes_secure_websocket(self) -> None:
        settings = Settings(iris_base_url="https://example.test/iris")
        settings.validate()
        self.assertEqual(settings.iris_websocket_url, "wss://example.test/iris/ws")

    def test_csv_allow_lists_are_normalized(self) -> None:
        with patch.dict(
            os.environ,
            {
                "BOT_ALLOWED_ROOM_IDS": " 10,20,10 ",
                "BOT_ALLOWED_SENDER_IDS": "30",
            },
            clear=True,
        ):
            settings = Settings.from_env()

        self.assertEqual(settings.allowed_room_ids, frozenset({"10", "20"}))
        self.assertEqual(settings.allowed_sender_ids, frozenset({"30"}))

    def test_invalid_iris_url_is_rejected(self) -> None:
        with patch.dict(os.environ, {"IRIS_BASE_URL": "127.0.0.1:3000"}, clear=True):
            with self.assertRaises(ConfigError):
                Settings.from_env()

    def test_postgres_url_is_optional_and_normalized(self) -> None:
        with patch.dict(
            os.environ,
            {"ROOM_DATABASE_URL": " postgresql://bot:secret@db:5432/kakao_bot "},
            clear=True,
        ):
            settings = Settings.from_env()

        self.assertEqual(
            settings.room_database_url,
            "postgresql://bot:secret@db:5432/kakao_bot",
        )

    def test_invalid_postgres_url_is_rejected(self) -> None:
        with patch.dict(
            os.environ,
            {"ROOM_DATABASE_URL": "sqlite:///data/bot.db"},
            clear=True,
        ):
            with self.assertRaises(ConfigError):
                Settings.from_env()

    def test_tracking_limits_are_configurable(self) -> None:
        with patch.dict(
            os.environ,
            {"MESSAGE_RETENTION_DAYS": "14", "MESSAGE_MAX_CHARS": "2000"},
            clear=True,
        ):
            settings = Settings.from_env()

        self.assertEqual(settings.message_retention_days, 14)
        self.assertEqual(settings.message_max_chars, 2000)


if __name__ == "__main__":
    unittest.main()
