from __future__ import annotations

import unittest
from datetime import UTC, datetime

from kakao_bot.config import Settings
from kakao_bot.games import GameService
from kakao_bot.registration import RegistrationCodeManager
from kakao_bot.registry import RegisteredRoom
from kakao_bot.service import EventOutcome, KakaoBot
from kakao_bot.tracking import MemberHistory, TrackedMessage


class FakeReplySender:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def reply(self, room_id: str, message: str) -> None:
        self.calls.append((room_id, message))


class FakeRoomTypeResolver:
    def __init__(
        self,
        room_types: dict[str, str] | None = None,
        query_rows: list[dict[str, object]] | None = None,
    ) -> None:
        self.room_types = room_types or {}
        self.query_rows = query_rows or []

    async def get_room_type(self, room_id: str) -> str | None:
        return self.room_types.get(room_id)

    async def query(
        self, query: str, bind: list[str] | None = None
    ) -> list[dict[str, object]]:
        return self.query_rows


class InMemoryRoomRegistry:
    def __init__(self) -> None:
        self.rooms: dict[str, RegisteredRoom] = {}

    async def initialize(self) -> None:
        return None

    async def is_registered(self, chat_id: str) -> bool:
        return chat_id in self.rooms

    async def register(self, chat_id: str, room_type: str) -> None:
        self.rooms[chat_id] = RegisteredRoom(chat_id, room_type, "now")

    async def unregister(self, chat_id: str) -> bool:
        return self.rooms.pop(chat_id, None) is not None

    async def list_registered(self) -> list[RegisteredRoom]:
        return list(self.rooms.values())


class InMemoryTrackingRepository:
    def __init__(self) -> None:
        self.messages: dict[tuple[str, str], TrackedMessage] = {}
        self.members: dict[tuple[str, str], MemberHistory] = {}
        self.deleted: set[tuple[str, str]] = set()

    async def initialize(self) -> None:
        return None

    async def save_message(self, message: TrackedMessage) -> None:
        self.messages.setdefault((message.chat_id, message.message_id), message)

    async def find_message(
        self, chat_id: str, message_id: str
    ) -> TrackedMessage | None:
        return self.messages.get((chat_id, message_id))

    async def mark_deleted(
        self,
        chat_id: str,
        message_id: str,
        deleted_at: datetime,
        deleted_by_id: str | None,
        deleted_by_name: str | None,
    ) -> None:
        self.deleted.add((chat_id, message_id))

    async def record_join(
        self,
        chat_id: str,
        sender_id: str,
        nickname: str | None,
        joined_at: datetime,
    ) -> MemberHistory:
        key = (chat_id, sender_id)
        previous = self.members.get(key)
        history = MemberHistory(
            chat_id=chat_id,
            sender_id=sender_id,
            first_joined_at=(previous.first_joined_at if previous else joined_at),
            first_nickname=(previous.first_nickname if previous else nickname),
            current_nickname=nickname,
            join_count=(previous.join_count if previous else 0) + 1,
            last_joined_at=joined_at,
            last_left_at=previous.last_left_at if previous else None,
            is_present=True,
            joined_at_history=(
                (previous.joined_at_history if previous else ()) + (joined_at,)
            ),
        )
        self.members[key] = history
        return history

    async def record_leave(
        self,
        chat_id: str,
        sender_id: str,
        nickname: str | None,
        left_at: datetime,
    ) -> MemberHistory:
        key = (chat_id, sender_id)
        previous = self.members.get(key)
        history = MemberHistory(
            chat_id=chat_id,
            sender_id=sender_id,
            first_joined_at=previous.first_joined_at if previous else None,
            first_nickname=previous.first_nickname if previous else None,
            current_nickname=nickname,
            join_count=previous.join_count if previous else 0,
            last_joined_at=previous.last_joined_at if previous else None,
            last_left_at=left_at,
            is_present=False,
            joined_at_history=previous.joined_at_history if previous else (),
        )
        self.members[key] = history
        return history


def event(
    message: str = "!핑",
    *,
    message_id: str = "1",
    chat_id: str | None = "room-1",
    sender_id: str = "sender-1",
    sender_name: str = "sender",
    origin: str | None = None,
    created_at: int = 1_777_000_000,
    message_type: int = 1,
) -> dict[str, object]:
    row: dict[str, object] = {
        "_id": message_id,
        "user_id": sender_id,
        "created_at": created_at,
        "type": message_type,
    }
    if chat_id is not None:
        row["chat_id"] = chat_id
    if origin is not None:
        row["v"] = {"origin": origin}
    return {"msg": message, "room": "room", "sender": sender_name, "json": row}


def create_bot(
    *,
    settings: Settings | None = None,
    room_types: dict[str, str] | None = None,
    tracking: InMemoryTrackingRepository | None = None,
    query_rows: list[dict[str, object]] | None = None,
) -> tuple[KakaoBot, FakeReplySender, InMemoryRoomRegistry]:
    sender = FakeReplySender()
    registry = InMemoryRoomRegistry()
    resolver = FakeRoomTypeResolver(room_types, query_rows)
    tracking_repository = tracking or InMemoryTrackingRepository()
    codes = RegistrationCodeManager(code_factory=lambda: "123456")
    unregistration_codes = RegistrationCodeManager(code_factory=lambda: "654321")
    bot = KakaoBot(
        settings or Settings(),
        sender,
        resolver,
        registry,
        tracking_repository,
        codes,
        unregistration_codes,
        GameService(number_picker=lambda upper_bound: 0),
    )
    return bot, sender, registry


class KakaoBotTests(unittest.IsolatedAsyncioTestCase):
    async def test_unregistered_room_cannot_use_ping(self) -> None:
        bot, sender, _ = create_bot(room_types={"room-1": "OM"})

        outcome = await bot.handle_payload(event())

        self.assertEqual(outcome, EventOutcome.NOT_REGISTERED)
        self.assertEqual(sender.calls, [])

    async def test_registered_room_can_use_ping(self) -> None:
        bot, sender, registry = create_bot(room_types={"room-1": "OM"})
        await registry.register("room-1", "OM")

        outcome = await bot.handle_payload(event())

        self.assertEqual(outcome, EventOutcome.REPLIED)
        self.assertEqual(sender.calls, [("room-1", "퐁")])

    async def test_registered_room_receives_join_and_leave_notices(self) -> None:
        bot, sender, registry = create_bot(room_types={"room-1": "OM"})
        await registry.register("room-1", "OM")

        first_join = await bot.handle_payload(
            event("joined", origin="NEWMEM", sender_name=" 첫   닉 ", message_id="1")
        )
        left = await bot.handle_payload(
            event("left", origin="DELMEM", sender_name="현재 닉", message_id="2")
        )
        rejoined = await bot.handle_payload(
            event("joined", origin="NEWMEM", sender_name="새 닉", message_id="3")
        )

        self.assertEqual(first_join, EventOutcome.MEMBER_WELCOMED)
        self.assertEqual(left, EventOutcome.MEMBER_DEPARTURE_ANNOUNCED)
        self.assertEqual(rejoined, EventOutcome.MEMBER_WELCOMED)
        self.assertIn("첫 닉님이 입장했습니다", sender.calls[0][1])
        self.assertIn("최초 닉네임: 첫 닉", sender.calls[0][1])
        self.assertIn("입장이력:", sender.calls[0][1])
        self.assertIn("현재 닉님이 퇴장했습니다", sender.calls[1][1])
        self.assertIn("입장 1회 · 재입장 0회", sender.calls[1][1])
        self.assertIn("새 닉님이 입장했습니다", sender.calls[2][1])
        self.assertIn("최초 닉네임: 첫 닉", sender.calls[2][1])
        history_block = sender.calls[2][1].split("입장이력:\n", 1)[1]
        self.assertEqual(history_block.count("2026-04-24"), 2)
        self.assertNotIn("🟢", sender.calls[0][1])
        self.assertNotIn("🔴", sender.calls[1][1])

    async def test_member_event_uses_members_from_iris_feed(self) -> None:
        bot, sender, registry = create_bot(room_types={"room-1": "OM"})
        await registry.register("room-1", "OM")

        outcome = await bot.handle_payload(
            event(
                '{"feedType":4,"members":['
                '{"userId":"member-1","nickName":"인사하는 프렌즈"}]}',
                origin="NEWMEM",
                sender_name="",
            )
        )

        self.assertEqual(outcome, EventOutcome.MEMBER_WELCOMED)
        self.assertIn("인사하는 프렌즈님이 입장했습니다", sender.calls[0][1])
        self.assertIn("최초 닉네임: 인사하는 프렌즈", sender.calls[0][1])

    async def test_same_nickname_members_are_tracked_by_distinct_user_ids(self) -> None:
        tracking = InMemoryTrackingRepository()
        bot, sender, registry = create_bot(
            room_types={"room-1": "OM"}, tracking=tracking
        )
        await registry.register("room-1", "OM")

        await bot.handle_payload(
            event(
                '{"feedType":4,"members":['
                '{"userId":"member-1","nickName":"같은 닉"},'
                '{"userId":"member-2","nickName":"같은 닉"}]}',
                origin="NEWMEM",
                sender_name="",
            )
        )

        self.assertIn(("room-1", "member-1"), tracking.members)
        self.assertIn(("room-1", "member-2"), tracking.members)
        self.assertEqual(sender.calls[0][1].count("같은 닉님이 입장했습니다"), 2)

    async def test_reports_author_and_content_when_message_is_deleted(self) -> None:
        tracking = InMemoryTrackingRepository()
        bot, sender, registry = create_bot(
            room_types={"room-1": "OM"}, tracking=tracking
        )
        await registry.register("room-1", "OM")

        stored = await bot.handle_payload(
            event(
                "삭제될 원문",
                origin="MSG",
                message_id="100",
                sender_id="author-1",
                sender_name="원작성자",
            )
        )
        deleted = await bot.handle_payload(
            event(
                '{"logId":"100"}',
                origin="SYNCDLMSG",
                message_id="101",
                sender_id="deleter-1",
                sender_name="삭제자",
            )
        )

        self.assertEqual(stored, EventOutcome.NOT_COMMAND)
        self.assertEqual(deleted, EventOutcome.MESSAGE_DELETION_REPORTED)
        self.assertIn("삭제한 사람: 삭제자", sender.calls[0][1])
        self.assertIn("원 작성자: 원작성자", sender.calls[0][1])
        self.assertIn("내용: 삭제될 원문", sender.calls[0][1])
        self.assertIn(("room-1", "100"), tracking.deleted)

    async def test_falls_back_to_iris_for_message_written_before_tracking(self) -> None:
        bot, sender, registry = create_bot(
            room_types={"room-1": "OM"},
            query_rows=[
                {
                    "_id": "90",
                    "chat_id": "room-1",
                    "user_id": "author-1",
                    "type": 1,
                    "message": "배포 전 원문",
                    "created_at": 1_777_000_000,
                    "v": '{"origin":"MSG"}',
                }
            ],
        )
        await registry.register("room-1", "OM")

        outcome = await bot.handle_payload(
            event(
                '{"logId":"90"}',
                origin="SYNCDLMSG",
                message_id="91",
                sender_id="author-1",
                sender_name="원작성자",
            )
        )

        self.assertEqual(outcome, EventOutcome.MESSAGE_DELETION_REPORTED)
        self.assertIn("원 작성자: 원작성자", sender.calls[0][1])
        self.assertIn("내용: 배포 전 원문", sender.calls[0][1])

    async def test_unregistered_room_ignores_member_events(self) -> None:
        bot, sender, _ = create_bot(room_types={"room-1": "OM"})

        outcome = await bot.handle_payload(event("joined", origin="NEWMEM"))

        self.assertEqual(outcome, EventOutcome.NOT_REGISTERED)
        self.assertEqual(sender.calls, [])

    async def test_registered_room_can_play_stateless_games(self) -> None:
        bot, sender, registry = create_bot(room_types={"room-1": "OM"})
        await registry.register("room-1", "OM")

        outcome = await bot.handle_payload(event("!주사위", message_id="game-1"))

        self.assertEqual(outcome, EventOutcome.GAME_REPLIED)
        self.assertEqual(sender.calls, [("room-1", "🎲 1 (1~6)")])

    async def test_memo_chat_can_use_ping_without_registration(self) -> None:
        bot, sender, _ = create_bot(room_types={"memo": "MemoChat"})

        outcome = await bot.handle_payload(event(chat_id="memo"))

        self.assertEqual(outcome, EventOutcome.REPLIED)
        self.assertEqual(sender.calls, [("memo", "퐁")])

    async def test_registration_code_is_issued_only_in_memo_chat(self) -> None:
        bot, sender, _ = create_bot(
            room_types={"memo": "MemoChat", "other": "DirectChat"}
        )

        denied = await bot.handle_payload(
            event("!등록코드", chat_id="other", message_id="1")
        )
        issued = await bot.handle_payload(
            event("!등록코드", chat_id="memo", message_id="2")
        )

        self.assertEqual(denied, EventOutcome.ADMIN_ONLY)
        self.assertEqual(issued, EventOutcome.REGISTRATION_CODE_ISSUED)
        self.assertEqual(
            sender.calls,
            [
                ("memo", "!봇등록 123456"),
                ("memo", "10분 안에 위 명령을 등록할 채팅방에 입력하세요."),
            ],
        )

    async def test_one_time_code_registers_target_room(self) -> None:
        bot, sender, registry = create_bot(
            room_types={"memo": "MemoChat", "target": "OM", "other": "DirectChat"}
        )
        await bot.handle_payload(event("!등록코드", chat_id="memo", message_id="1"))

        registered = await bot.handle_payload(
            event("!봇등록 123456", chat_id="target", message_id="2")
        )
        reused = await bot.handle_payload(
            event("!봇등록 123456", chat_id="other", message_id="3")
        )

        self.assertEqual(registered, EventOutcome.ROOM_REGISTERED)
        self.assertTrue(await registry.is_registered("target"))
        self.assertEqual(reused, EventOutcome.INVALID_REGISTRATION_CODE)
        self.assertFalse(await registry.is_registered("other"))
        self.assertEqual(sender.calls[-1], ("target", "등록이 완료되었습니다."))
        self.assertEqual(len(sender.calls), 3)

    async def test_unregister_deletes_room_data_and_blocks_future_commands(self) -> None:
        bot, sender, registry = create_bot(
            room_types={"memo": "MemoChat", "room-1": "OM"}
        )
        await registry.register("room-1", "OM")
        await bot.handle_payload(
            event("!해제코드", chat_id="memo", message_id="issue-1")
        )
        sender.calls.clear()

        outcome = await bot.handle_payload(event("!봇해제 654321", message_id="1"))
        ping_outcome = await bot.handle_payload(event("!핑", message_id="2"))

        self.assertEqual(outcome, EventOutcome.ROOM_UNREGISTERED)
        self.assertFalse(await registry.is_registered("room-1"))
        self.assertEqual(ping_outcome, EventOutcome.NOT_REGISTERED)
        self.assertEqual(
            sender.calls,
            [("room-1", "봇 등록과 저장된 방 정보가 삭제되었습니다.")],
        )

    async def test_plain_unregister_command_cannot_delete_room(self) -> None:
        bot, sender, registry = create_bot(room_types={"room-1": "OM"})
        await registry.register("room-1", "OM")

        outcome = await bot.handle_payload(event("!봇해제"))

        self.assertEqual(outcome, EventOutcome.INVALID_UNREGISTRATION_CODE)
        self.assertTrue(await registry.is_registered("room-1"))
        self.assertEqual(sender.calls, [])

    async def test_unregistration_code_is_issued_only_in_memo_chat(self) -> None:
        bot, sender, _ = create_bot(
            room_types={"memo": "MemoChat", "other": "OM"}
        )

        denied = await bot.handle_payload(
            event("!해제코드", chat_id="other", message_id="1")
        )
        issued = await bot.handle_payload(
            event("!해제코드", chat_id="memo", message_id="2")
        )

        self.assertEqual(denied, EventOutcome.ADMIN_ONLY)
        self.assertEqual(issued, EventOutcome.UNREGISTRATION_CODE_ISSUED)
        self.assertEqual(
            sender.calls,
            [
                ("memo", "!봇해제 654321"),
                ("memo", "10분 안에 위 명령을 해제할 채팅방에 입력하세요."),
            ],
        )

    async def test_invalid_code_does_not_reply_or_register(self) -> None:
        bot, sender, registry = create_bot(
            room_types={"memo": "MemoChat", "target": "OM"}
        )
        await bot.handle_payload(event("!등록코드", chat_id="memo", message_id="1"))
        sender.calls.clear()

        outcome = await bot.handle_payload(
            event("!봇등록 999999", chat_id="target", message_id="2")
        )

        self.assertEqual(outcome, EventOutcome.INVALID_REGISTRATION_CODE)
        self.assertFalse(await registry.is_registered("target"))
        self.assertEqual(sender.calls, [])

    async def test_cannot_register_memo_or_plus_chat(self) -> None:
        bot, sender, registry = create_bot(
            room_types={"memo": "MemoChat", "plus": "PlusChat"}
        )
        await bot.handle_payload(event("!등록코드", chat_id="memo", message_id="1"))
        sender.calls.clear()

        outcome = await bot.handle_payload(
            event("!봇등록 123456", chat_id="plus", message_id="2")
        )

        self.assertEqual(outcome, EventOutcome.UNSUPPORTED_ROOM_TYPE)
        self.assertFalse(await registry.is_registered("plus"))
        self.assertEqual(sender.calls, [])

    async def test_ignores_other_messages(self) -> None:
        bot, sender, _ = create_bot()

        outcome = await bot.handle_payload(event("안녕"))

        self.assertEqual(outcome, EventOutcome.NOT_COMMAND)
        self.assertEqual(sender.calls, [])

    async def test_enforces_emergency_room_and_sender_allow_lists(self) -> None:
        settings = Settings(
            allowed_room_ids=frozenset({"allowed-room"}),
            allowed_sender_ids=frozenset({"allowed-sender"}),
        )
        bot, sender, registry = create_bot(settings=settings)
        await registry.register("wrong-room", "OM")
        await registry.register("allowed-room", "OM")

        room_outcome = await bot.handle_payload(event(chat_id="wrong-room"))
        sender_outcome = await bot.handle_payload(
            event(
                chat_id="allowed-room",
                sender_id="wrong-sender",
                message_id="2",
            )
        )

        self.assertEqual(room_outcome, EventOutcome.ROOM_NOT_ALLOWED)
        self.assertEqual(sender_outcome, EventOutcome.SENDER_NOT_ALLOWED)
        self.assertEqual(sender.calls, [])

    async def test_requires_chat_id_for_command(self) -> None:
        bot, sender, _ = create_bot()

        outcome = await bot.handle_payload(event(chat_id=None))

        self.assertEqual(outcome, EventOutcome.MISSING_CHAT_ID)
        self.assertEqual(sender.calls, [])

    async def test_deduplicates_successfully_processed_message_id(self) -> None:
        bot, sender, registry = create_bot()
        await registry.register("room-1", "OM")

        first = await bot.handle_payload(event())
        second = await bot.handle_payload(event())

        self.assertEqual(first, EventOutcome.REPLIED)
        self.assertEqual(second, EventOutcome.DUPLICATE)
        self.assertEqual(sender.calls, [("room-1", "퐁")])


if __name__ == "__main__":
    unittest.main()
