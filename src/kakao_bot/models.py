from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Mapping


def _string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, (int, float)) or (
        isinstance(value, str) and value.strip().replace(".", "", 1).isdigit()
    ):
        timestamp = float(value)
        if timestamp > 100_000_000_000:
            timestamp /= 1000
        return datetime.fromtimestamp(timestamp, UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            pass
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class IrisEvent:
    message: str
    room_name: str | None
    sender_name: str | None
    chat_id: str | None
    sender_id: str | None
    message_id: str | None
    origin: str | None
    message_type: str | None
    created_at: datetime

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "IrisEvent | None":
        message = payload.get("msg")
        if not isinstance(message, str):
            return None

        row = payload.get("json")
        if not isinstance(row, Mapping):
            row = {}

        version = row.get("v")
        if isinstance(version, str):
            try:
                version = json.loads(version)
            except (json.JSONDecodeError, TypeError):
                version = {}
        if not isinstance(version, Mapping):
            version = {}

        return cls(
            message=message,
            room_name=_string(payload.get("room")),
            sender_name=_string(payload.get("sender")),
            chat_id=_string(row.get("chat_id")),
            sender_id=_string(row.get("user_id")),
            message_id=_string(row.get("_id") or row.get("id")),
            origin=_string(version.get("origin")),
            message_type=_string(row.get("type")),
            created_at=_datetime(row.get("created_at")),
        )
