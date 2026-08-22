from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit


class ConfigError(ValueError):
    """Raised when an environment setting is invalid."""


def _csv_set(value: str | None) -> frozenset[str]:
    if not value:
        return frozenset()
    return frozenset(item.strip() for item in value.split(",") if item.strip())


def _optional_env(name: str) -> str | None:
    return os.getenv(name, "").strip() or None


def _positive_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number") from exc
    if value <= 0:
        raise ConfigError(f"{name} must be greater than zero")
    return value


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ConfigError(f"{name} must be greater than zero")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    iris_base_url: str = "http://127.0.0.1:3000"
    bot_command: str = "!핑"
    bot_reply: str = "퐁"
    allowed_room_ids: frozenset[str] = frozenset()
    allowed_sender_ids: frozenset[str] = frozenset()
    room_database_url: str | None = None
    room_database_path: str = "data/kakao_bot.db"
    registration_code_ttl_seconds: int = 600
    registration_code_max_attempts_per_room: int = 5
    message_retention_days: int = 30
    message_max_chars: int = 4000
    iris_request_timeout_seconds: float = 5.0
    iris_reconnect_initial_seconds: float = 1.0
    iris_reconnect_max_seconds: float = 30.0
    dedup_cache_size: int = 1000
    discord_bot_token: str | None = None
    discord_guild_id: str | None = None
    discord_channel_id: str | None = None
    discord_allowed_user_ids: frozenset[str] = frozenset()
    discord_allowed_role_ids: frozenset[str] = frozenset()
    discord_kakao_room_id: str | None = None
    discord_bridge_secret: str | None = None
    discord_bridge_api_url: str = "http://kakao-bot:8000"
    discord_max_message_chars: int = 1000
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        defaults = cls()
        settings = cls(
            iris_base_url=os.getenv("IRIS_BASE_URL", defaults.iris_base_url).rstrip("/"),
            bot_command=os.getenv("BOT_COMMAND", defaults.bot_command),
            bot_reply=os.getenv("BOT_REPLY", defaults.bot_reply),
            allowed_room_ids=_csv_set(os.getenv("BOT_ALLOWED_ROOM_IDS")),
            allowed_sender_ids=_csv_set(os.getenv("BOT_ALLOWED_SENDER_IDS")),
            room_database_url=(
                os.getenv("ROOM_DATABASE_URL", "").strip() or None
            ),
            room_database_path=os.getenv(
                "ROOM_DATABASE_PATH", defaults.room_database_path
            ),
            registration_code_ttl_seconds=_positive_int(
                "REGISTRATION_CODE_TTL_SECONDS",
                defaults.registration_code_ttl_seconds,
            ),
            registration_code_max_attempts_per_room=_positive_int(
                "REGISTRATION_CODE_MAX_ATTEMPTS_PER_ROOM",
                defaults.registration_code_max_attempts_per_room,
            ),
            message_retention_days=_positive_int(
                "MESSAGE_RETENTION_DAYS", defaults.message_retention_days
            ),
            message_max_chars=_positive_int(
                "MESSAGE_MAX_CHARS", defaults.message_max_chars
            ),
            iris_request_timeout_seconds=_positive_float(
                "IRIS_REQUEST_TIMEOUT_SECONDS", defaults.iris_request_timeout_seconds
            ),
            iris_reconnect_initial_seconds=_positive_float(
                "IRIS_RECONNECT_INITIAL_SECONDS", defaults.iris_reconnect_initial_seconds
            ),
            iris_reconnect_max_seconds=_positive_float(
                "IRIS_RECONNECT_MAX_SECONDS", defaults.iris_reconnect_max_seconds
            ),
            dedup_cache_size=_positive_int(
                "BOT_DEDUP_CACHE_SIZE", defaults.dedup_cache_size
            ),
            discord_bot_token=_optional_env("DISCORD_BOT_TOKEN"),
            discord_guild_id=_optional_env("DISCORD_GUILD_ID"),
            discord_channel_id=_optional_env("DISCORD_CHANNEL_ID"),
            discord_allowed_user_ids=_csv_set(
                os.getenv("DISCORD_ALLOWED_USER_IDS")
            ),
            discord_allowed_role_ids=_csv_set(
                os.getenv("DISCORD_ALLOWED_ROLE_IDS")
            ),
            discord_kakao_room_id=_optional_env("DISCORD_KAKAO_ROOM_ID"),
            discord_bridge_secret=_optional_env("DISCORD_BRIDGE_SECRET"),
            discord_bridge_api_url=os.getenv(
                "DISCORD_BRIDGE_API_URL", defaults.discord_bridge_api_url
            ).rstrip("/"),
            discord_max_message_chars=_positive_int(
                "DISCORD_MAX_MESSAGE_CHARS", defaults.discord_max_message_chars
            ),
            app_host=os.getenv("APP_HOST", defaults.app_host),
            app_port=_positive_int("APP_PORT", defaults.app_port),
            log_level=os.getenv("LOG_LEVEL", defaults.log_level).upper(),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        parts = urlsplit(self.iris_base_url)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ConfigError("IRIS_BASE_URL must be an absolute http(s) URL")
        if not self.bot_command:
            raise ConfigError("BOT_COMMAND must not be empty")
        if not self.room_database_url and not self.room_database_path.strip():
            raise ConfigError("ROOM_DATABASE_PATH must not be empty")
        if self.room_database_url:
            database_parts = urlsplit(self.room_database_url)
            if (
                database_parts.scheme not in {"postgres", "postgresql"}
                or not database_parts.hostname
                or not database_parts.path.strip("/")
            ):
                raise ConfigError(
                    "ROOM_DATABASE_URL must be a PostgreSQL URL with a database name"
                )
        if self.iris_reconnect_max_seconds < self.iris_reconnect_initial_seconds:
            raise ConfigError(
                "IRIS_RECONNECT_MAX_SECONDS must be greater than or equal to "
                "IRIS_RECONNECT_INITIAL_SECONDS"
            )
        if self.app_port > 65535:
            raise ConfigError("APP_PORT must be at most 65535")
        bridge_parts = urlsplit(self.discord_bridge_api_url)
        if (
            bridge_parts.scheme not in {"http", "https"}
            or not bridge_parts.netloc
        ):
            raise ConfigError(
                "DISCORD_BRIDGE_API_URL must be an absolute http(s) URL"
            )

    def validate_discord_bot(self) -> None:
        required = {
            "DISCORD_BOT_TOKEN": self.discord_bot_token,
            "DISCORD_GUILD_ID": self.discord_guild_id,
            "DISCORD_KAKAO_ROOM_ID": self.discord_kakao_room_id,
            "DISCORD_BRIDGE_SECRET": self.discord_bridge_secret,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ConfigError(
                "Discord bot settings are missing: " + ", ".join(missing)
            )
        id_values = (
            ("DISCORD_GUILD_ID", self.discord_guild_id),
            ("DISCORD_CHANNEL_ID", self.discord_channel_id),
            ("DISCORD_KAKAO_ROOM_ID", self.discord_kakao_room_id),
            *(
                ("DISCORD_ALLOWED_USER_IDS", value)
                for value in self.discord_allowed_user_ids
            ),
            *(
                ("DISCORD_ALLOWED_ROLE_IDS", value)
                for value in self.discord_allowed_role_ids
            ),
        )
        for name, value in id_values:
            if value is not None and not value.isdigit():
                raise ConfigError(f"{name} values must contain digits only")

    @property
    def iris_websocket_url(self) -> str:
        parts = urlsplit(self.iris_base_url)
        scheme = "wss" if parts.scheme == "https" else "ws"
        path = f"{parts.path.rstrip('/')}/ws"
        return urlunsplit((scheme, parts.netloc, path, "", ""))
