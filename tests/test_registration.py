from __future__ import annotations

import unittest

from kakao_bot.registration import RegistrationCodeManager


class RegistrationCodeManagerTests(unittest.TestCase):
    def test_code_expires(self) -> None:
        now = [100.0]
        manager = RegistrationCodeManager(
            ttl_seconds=10,
            code_factory=lambda: "123456",
            clock=lambda: now[0],
        )
        manager.issue()
        now[0] = 110.0

        self.assertFalse(manager.consume("123456", "room-1"))

    def test_code_is_single_use(self) -> None:
        manager = RegistrationCodeManager(code_factory=lambda: "123456")
        manager.issue()

        self.assertTrue(manager.consume("123456", "room-1"))
        self.assertFalse(manager.consume("123456", "room-2"))

    def test_failed_attempt_limit_is_scoped_to_room(self) -> None:
        manager = RegistrationCodeManager(
            max_attempts_per_room=2,
            code_factory=lambda: "123456",
        )
        manager.issue()

        self.assertFalse(manager.consume("000000", "attacker-room"))
        self.assertFalse(manager.consume("000001", "attacker-room"))
        self.assertFalse(manager.consume("123456", "attacker-room"))
        self.assertTrue(manager.consume("123456", "target-room"))


if __name__ == "__main__":
    unittest.main()

