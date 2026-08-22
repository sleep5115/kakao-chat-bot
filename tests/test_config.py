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

    def test_discord_bridge_settings_are_loaded(self) -> None:
        with patch.dict(
            os.environ,
            {
                "DISCORD_BOT_TOKEN": "token",
                "DISCORD_GUILD_ID": "100",
                "DISCORD_CHANNEL_ID": "200",
                "DISCORD_ALLOWED_USER_IDS": "300,301",
                "DISCORD_ALLOWED_ROLE_IDS": "400",
                "DISCORD_KAKAO_ROOM_ID": "500",
                "DISCORD_BRIDGE_SECRET": "secret",
                "DISCORD_MAX_MESSAGE_CHARS": "700",
            },
            clear=True,
        ):
            settings = Settings.from_env()
            settings.validate_discord_bot()

        self.assertEqual(settings.discord_guild_id, "100")
        self.assertEqual(settings.discord_channel_id, "200")
        self.assertEqual(
            settings.discord_allowed_user_ids, frozenset({"300", "301"})
        )
        self.assertEqual(settings.discord_allowed_role_ids, frozenset({"400"}))
        self.assertEqual(settings.discord_kakao_room_id, "500")
        self.assertEqual(settings.discord_max_message_chars, 700)

    def test_discord_bot_requires_core_settings(self) -> None:
        with self.assertRaises(ConfigError):
            Settings().validate_discord_bot()

    def test_discord_ids_must_be_numeric(self) -> None:
        settings = Settings(
            discord_bot_token="token",
            discord_guild_id="not-an-id",
            discord_kakao_room_id="500",
            discord_bridge_secret="secret",
        )

        with self.assertRaises(ConfigError):
            settings.validate_discord_bot()


if __name__ == "__main__":
    unittest.main()
