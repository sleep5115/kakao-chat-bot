from __future__ import annotations

import unittest

from kakao_bot.config import Settings
from kakao_bot.games import GameService
from kakao_bot.registration import RegistrationCodeManager
from kakao_bot.registry import RegisteredRoom
from kakao_bot.service import EventOutcome, KakaoBot


class FakeReplySender:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def reply(self, room_id: str, message: str) -> None:
        self.calls.append((room_id, message))


class FakeRoomTypeResolver:
    def __init__(self, room_types: dict[str, str] | None = None) -> None:
        self.room_types = room_types or {}

    async def get_room_type(self, room_id: str) -> str | None:
        return self.room_types.get(room_id)


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


def event(
    message: str = "!핑",
    *,
    message_id: str = "1",
    chat_id: str | None = "room-1",
    sender_id: str = "sender-1",
    sender_name: str = "sender",
    origin: str | None = None,
) -> dict[str, object]:
    row: dict[str, object] = {"_id": message_id, "user_id": sender_id}
    if chat_id is not None:
        row["chat_id"] = chat_id
    if origin is not None:
        row["v"] = {"origin": origin}
    return {"msg": message, "room": "room", "sender": sender_name, "json": row}


def create_bot(
    *,
    settings: Settings | None = None,
    room_types: dict[str, str] | None = None,
) -> tuple[KakaoBot, FakeReplySender, InMemoryRoomRegistry]:
    sender = FakeReplySender()
    registry = InMemoryRoomRegistry()
    resolver = FakeRoomTypeResolver(room_types)
    codes = RegistrationCodeManager(code_factory=lambda: "123456")
    unregistration_codes = RegistrationCodeManager(code_factory=lambda: "654321")
    bot = KakaoBot(
        settings or Settings(),
        sender,
        resolver,
        registry,
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

        joined = await bot.handle_payload(
            event("joined", origin="NEWMEM", sender_name=" 새   멤버 ", message_id="1")
        )
        left = await bot.handle_payload(
            event("left", origin="DELMEM", sender_name="떠난 멤버", message_id="2")
        )

        self.assertEqual(joined, EventOutcome.MEMBER_WELCOMED)
        self.assertEqual(left, EventOutcome.MEMBER_DEPARTURE_ANNOUNCED)
        self.assertEqual(
            sender.calls,
            [
                ("room-1", "새 멤버님, 어서 오세요! 👋"),
                ("room-1", "떠난 멤버님이 퇴장했습니다."),
            ],
        )

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
        self.assertEqual(sender.calls[-2], ("target", "봇 등록이 완료되었습니다."))
        self.assertEqual(sender.calls[-1], ("target", KakaoBot.PRIVACY_NOTICE))

    async def test_registered_room_can_read_bot_info(self) -> None:
        bot, sender, registry = create_bot(room_types={"room-1": "OM"})
        await registry.register("room-1", "OM")

        outcome = await bot.handle_payload(event("!봇정보"))

        self.assertEqual(outcome, EventOutcome.BOT_INFO_REPLIED)
        self.assertEqual(sender.calls, [("room-1", KakaoBot.PRIVACY_NOTICE)])

    async def test_unregistered_room_cannot_make_bot_reply_with_info_command(self) -> None:
        bot, sender, _ = create_bot(room_types={"room-1": "OM"})

        outcome = await bot.handle_payload(event("!봇정보"))

        self.assertEqual(outcome, EventOutcome.NOT_REGISTERED)
        self.assertEqual(sender.calls, [])

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
