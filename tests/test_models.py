from __future__ import annotations

import unittest
from datetime import UTC, datetime

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
                    "type": 0,
                    "created_at": 1_777_000_000,
                },
            }
        )

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.chat_id, "200")
        self.assertEqual(event.sender_id, "300")
        self.assertEqual(event.message_id, "100")
        self.assertEqual(event.origin, "NEWMEM")
        self.assertEqual(event.message_type, "0")
        self.assertEqual(event.created_at, datetime.fromtimestamp(1_777_000_000, UTC))

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

    def test_parses_members_from_join_feed_message(self) -> None:
        event = IrisEvent.from_payload(
            {
                "msg": (
                    '{"feedType":4,"members":['
                    '{"userId":"member-1","nickName":"인사하는 프렌즈"}]}'
                ),
                "json": {"chat_id": 200, "v": {"origin": "NEWMEM"}},
            }
        )

        assert event is not None
        self.assertEqual(len(event.members), 1)
        self.assertEqual(event.members[0].user_id, "member-1")
        self.assertEqual(event.members[0].nickname, "인사하는 프렌즈")

    def test_rejects_payload_without_string_message(self) -> None:
        self.assertIsNone(IrisEvent.from_payload({"json": {"chat_id": 1}}))


if __name__ == "__main__":
    unittest.main()
