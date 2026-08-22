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
    iris_request_timeout_seconds: float = 5.0
    iris_reconnect_initial_seconds: float = 1.0
    iris_reconnect_max_seconds: float = 30.0
    dedup_cache_size: int = 1000
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

    @property
    def iris_websocket_url(self) -> str:
        parts = urlsplit(self.iris_base_url)
        scheme = "wss" if parts.scheme == "https" else "ws"
        path = f"{parts.path.rstrip('/')}/ws"
        return urlunsplit((scheme, parts.netloc, path, "", ""))
