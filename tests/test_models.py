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
                "json": {
                    "_id": 100,
                    "chat_id": 200,
                    "user_id": 300,
                    "v": '{"origin":"NEWMEM"}',
                },
            }
        )

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.chat_id, "200")
        self.assertEqual(event.sender_id, "300")
        self.assertEqual(event.message_id, "100")
        self.assertEqual(event.origin, "NEWMEM")

    def test_accepts_mapping_version_and_id_alias(self) -> None:
        event = IrisEvent.from_payload(
            {
                "msg": "joined",
                "json": {"id": 101, "chat_id": 200, "v": {"origin": "DELMEM"}},
            }
        )

        assert event is not None
        self.assertEqual(event.message_id, "101")
        self.assertEqual(event.origin, "DELMEM")

    def test_rejects_payload_without_string_message(self) -> None:
        self.assertIsNone(IrisEvent.from_payload({"json": {"chat_id": 1}}))


if __name__ == "__main__":
    unittest.main()
