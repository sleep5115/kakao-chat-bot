from __future__ import annotations

import unittest

from kakao_bot.models import IrisEvent


class IrisEventTests(unittest.TestCase):
    def test_parses_identifiers_from_raw_database_row(self) -> None:
        event = IrisEvent.from_payload(
            {
                "msg": "!핑",
                "room": "test room",
                "sender": "tester",
                "json": {"_id": 100, "chat_id": 200, "user_id": 300},
            }
        )

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.chat_id, "200")
        self.assertEqual(event.sender_id, "300")
        self.assertEqual(event.message_id, "100")

    def test_rejects_payload_without_string_message(self) -> None:
        self.assertIsNone(IrisEvent.from_payload({"json": {"chat_id": 1}}))


if __name__ == "__main__":
    unittest.main()

