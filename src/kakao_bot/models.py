from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping


def _string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


@dataclass(frozen=True, slots=True)
class IrisEvent:
    message: str
    room_name: str | None
    sender_name: str | None
    chat_id: str | None
    sender_id: str | None
    message_id: str | None
    origin: str | None

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
        )
