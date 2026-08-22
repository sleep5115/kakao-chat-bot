from __future__ import annotations

import hmac
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field


def _six_digit_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


@dataclass(slots=True)
class _ActiveCode:
    value: str
    expires_at: float
    failed_attempts_by_room: dict[str, int] = field(default_factory=dict)


class RegistrationCodeManager:
    """Maintains one short-lived, single-use room registration code."""

    def __init__(
        self,
        *,
        ttl_seconds: int = 600,
        max_attempts_per_room: int = 5,
        code_factory: Callable[[], str] = _six_digit_code,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._max_attempts_per_room = max_attempts_per_room
        self._code_factory = code_factory
        self._clock = clock
        self._active: _ActiveCode | None = None

    def issue(self) -> str:
        code = self._code_factory()
        if len(code) != 6 or not code.isdigit():
            raise ValueError("registration code factory must return six digits")
        self._active = _ActiveCode(
            value=code,
            expires_at=self._clock() + self._ttl_seconds,
        )
        return code

    def consume(self, code: str, room_id: str) -> bool:
        active = self._active
        if active is None:
            return False
        if self._clock() >= active.expires_at:
            self._active = None
            return False

        failed_attempts = active.failed_attempts_by_room.get(room_id, 0)
        if failed_attempts >= self._max_attempts_per_room:
            return False
        if not hmac.compare_digest(active.value, code):
            active.failed_attempts_by_room[room_id] = failed_attempts + 1
            return False

        self._active = None
        return True

