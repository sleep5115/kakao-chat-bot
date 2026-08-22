from __future__ import annotations

import logging
from collections import deque
from enum import StrEnum
from typing import Any, Mapping, Protocol

from .config import Settings
from .games import GameService
from .models import IrisEvent
from .registration import RegistrationCodeManager
from .registry import RoomRegistry

logger = logging.getLogger(__name__)


class ReplySender(Protocol):
    async def reply(self, room_id: str, message: str) -> None: ...


class RoomTypeResolver(Protocol):
    async def get_room_type(self, room_id: str) -> str | None: ...


class EventOutcome(StrEnum):
    REPLIED = "replied"
    BOT_INFO_REPLIED = "bot_info_replied"
    REGISTRATION_CODE_ISSUED = "registration_code_issued"
    UNREGISTRATION_CODE_ISSUED = "unregistration_code_issued"
    ROOM_REGISTERED = "room_registered"
    ROOM_UNREGISTERED = "room_unregistered"
    MEMBER_WELCOMED = "member_welcomed"
    MEMBER_DEPARTURE_ANNOUNCED = "member_departure_announced"
    GAME_REPLIED = "game_replied"
    ALREADY_REGISTERED = "already_registered"
    NOT_REGISTERED = "not_registered"
    INVALID_REGISTRATION_CODE = "invalid_registration_code"
    INVALID_UNREGISTRATION_CODE = "invalid_unregistration_code"
    ADMIN_ONLY = "admin_only"
    UNSUPPORTED_ROOM_TYPE = "unsupported_room_type"
    INVALID = "invalid"
    NOT_COMMAND = "not_command"
    ROOM_NOT_ALLOWED = "room_not_allowed"
    SENDER_NOT_ALLOWED = "sender_not_allowed"
    MISSING_CHAT_ID = "missing_chat_id"
    DUPLICATE = "duplicate"


class KakaoBot:
    REGISTERABLE_ROOM_TYPES = frozenset({"DirectChat", "MultiChat", "OD", "OM"})
    PRIVACY_NOTICE = (
        "대화 내용, 방 이름, 닉네임, 사용자 ID는 저장하지 않습니다. "
        "방 ID·방 종류·등록 시각만 등록 해제 전까지 보관하며, "
        "나와의 채팅에서 !해제코드를 발급해 등록을 해제하면 즉시 삭제됩니다."
    )

    def __init__(
        self,
        settings: Settings,
        reply_sender: ReplySender,
        room_type_resolver: RoomTypeResolver,
        room_registry: RoomRegistry,
        registration_codes: RegistrationCodeManager,
        unregistration_codes: RegistrationCodeManager,
        game_service: GameService | None = None,
    ) -> None:
        self._settings = settings
        self._reply_sender = reply_sender
        self._room_type_resolver = room_type_resolver
        self._room_registry = room_registry
        self._registration_codes = registration_codes
        self._unregistration_codes = unregistration_codes
        self._games = game_service or GameService()
        self._seen_order: deque[str] = deque()
        self._seen_ids: set[str] = set()

    async def handle_payload(self, payload: Mapping[str, Any]) -> EventOutcome:
        event = IrisEvent.from_payload(payload)
        if event is None:
            return EventOutcome.INVALID
        if event.message_id and event.message_id in self._seen_ids:
            return EventOutcome.DUPLICATE
        if event.chat_id is None:
            logger.warning("Ignoring command because the Iris event has no chat_id")
            return EventOutcome.MISSING_CHAT_ID

        if event.origin in {"NEWMEM", "DELMEM"}:
            return await self._handle_member_event(event)

        message = event.message.strip()
        if message == "!등록코드":
            return await self._issue_registration_code(event)
        if message == "!해제코드":
            return await self._issue_unregistration_code(event)
        if message == "!봇등록" or message.startswith("!봇등록 "):
            return await self._register_room(event, message)
        if message == "!봇해제" or message.startswith("!봇해제 "):
            return await self._unregister_room(event, message)
        game_reply = self._games.handle(message)
        if (
            message not in {self._settings.bot_command, "!봇정보"}
            and game_reply is None
        ):
            return EventOutcome.NOT_COMMAND

        if (
            self._settings.allowed_room_ids
            and event.chat_id not in self._settings.allowed_room_ids
        ):
            return EventOutcome.ROOM_NOT_ALLOWED
        if (
            self._settings.allowed_sender_ids
            and event.sender_id not in self._settings.allowed_sender_ids
        ):
            return EventOutcome.SENDER_NOT_ALLOWED

        registered = await self._room_registry.is_registered(event.chat_id)
        if not registered:
            room_type = await self._room_type_resolver.get_room_type(event.chat_id)
            if room_type != "MemoChat":
                return EventOutcome.NOT_REGISTERED

        if message == "!봇정보":
            await self._reply_sender.reply(event.chat_id, self.PRIVACY_NOTICE)
            self._remember_event(event)
            return EventOutcome.BOT_INFO_REPLIED

        if game_reply is not None:
            await self._reply_sender.reply(event.chat_id, game_reply)
            self._remember_event(event)
            logger.info("Replied to a stateless game command")
            return EventOutcome.GAME_REPLIED

        await self._reply_sender.reply(event.chat_id, self._settings.bot_reply)
        self._remember_event(event)
        logger.info("Replied to ping command")
        return EventOutcome.REPLIED

    async def _issue_registration_code(self, event: IrisEvent) -> EventOutcome:
        assert event.chat_id is not None
        room_type = await self._room_type_resolver.get_room_type(event.chat_id)
        if room_type != "MemoChat":
            return EventOutcome.ADMIN_ONLY

        code = self._registration_codes.issue()
        minutes = max(1, self._settings.registration_code_ttl_seconds // 60)
        await self._reply_sender.reply(
            event.chat_id,
            f"!봇등록 {code}",
        )
        await self._reply_sender.reply(
            event.chat_id,
            f"{minutes}분 안에 위 명령을 등록할 채팅방에 입력하세요.",
        )
        self._remember_event(event)
        logger.info("Issued a one-time room registration code")
        return EventOutcome.REGISTRATION_CODE_ISSUED

    async def _issue_unregistration_code(self, event: IrisEvent) -> EventOutcome:
        assert event.chat_id is not None
        room_type = await self._room_type_resolver.get_room_type(event.chat_id)
        if room_type != "MemoChat":
            return EventOutcome.ADMIN_ONLY

        code = self._unregistration_codes.issue()
        minutes = max(1, self._settings.registration_code_ttl_seconds // 60)
        await self._reply_sender.reply(event.chat_id, f"!봇해제 {code}")
        await self._reply_sender.reply(
            event.chat_id,
            f"{minutes}분 안에 위 명령을 해제할 채팅방에 입력하세요.",
        )
        self._remember_event(event)
        logger.info("Issued a one-time room unregistration code")
        return EventOutcome.UNREGISTRATION_CODE_ISSUED

    async def _register_room(
        self,
        event: IrisEvent,
        message: str,
    ) -> EventOutcome:
        assert event.chat_id is not None
        parts = message.split()
        if len(parts) != 2 or len(parts[1]) != 6 or not parts[1].isdigit():
            return EventOutcome.INVALID_REGISTRATION_CODE
        if (
            self._settings.allowed_room_ids
            and event.chat_id not in self._settings.allowed_room_ids
        ):
            return EventOutcome.ROOM_NOT_ALLOWED
        if await self._room_registry.is_registered(event.chat_id):
            await self._reply_sender.reply(event.chat_id, "이미 등록된 방입니다.")
            self._remember_event(event)
            return EventOutcome.ALREADY_REGISTERED

        room_type = await self._room_type_resolver.get_room_type(event.chat_id)
        if room_type not in self.REGISTERABLE_ROOM_TYPES:
            return EventOutcome.UNSUPPORTED_ROOM_TYPE
        if not self._registration_codes.consume(parts[1], event.chat_id):
            return EventOutcome.INVALID_REGISTRATION_CODE

        await self._room_registry.register(event.chat_id, room_type)
        await self._reply_sender.reply(event.chat_id, "봇 등록이 완료되었습니다.")
        await self._reply_sender.reply(event.chat_id, self.PRIVACY_NOTICE)
        self._remember_event(event)
        logger.info("Registered a chat room for bot commands")
        return EventOutcome.ROOM_REGISTERED

    async def _unregister_room(
        self,
        event: IrisEvent,
        message: str,
    ) -> EventOutcome:
        assert event.chat_id is not None
        parts = message.split()
        if len(parts) != 2 or len(parts[1]) != 6 or not parts[1].isdigit():
            return EventOutcome.INVALID_UNREGISTRATION_CODE
        if (
            self._settings.allowed_room_ids
            and event.chat_id not in self._settings.allowed_room_ids
        ):
            return EventOutcome.ROOM_NOT_ALLOWED
        if not await self._room_registry.is_registered(event.chat_id):
            return EventOutcome.NOT_REGISTERED
        if not self._unregistration_codes.consume(parts[1], event.chat_id):
            return EventOutcome.INVALID_UNREGISTRATION_CODE

        await self._room_registry.unregister(event.chat_id)
        await self._reply_sender.reply(
            event.chat_id,
            "봇 등록과 저장된 방 정보가 삭제되었습니다.",
        )
        self._remember_event(event)
        logger.info("Unregistered a chat room and deleted its registration data")
        return EventOutcome.ROOM_UNREGISTERED

    async def _handle_member_event(self, event: IrisEvent) -> EventOutcome:
        assert event.chat_id is not None
        if (
            self._settings.allowed_room_ids
            and event.chat_id not in self._settings.allowed_room_ids
        ):
            return EventOutcome.ROOM_NOT_ALLOWED
        if not await self._room_registry.is_registered(event.chat_id):
            return EventOutcome.NOT_REGISTERED

        member_name = " ".join((event.sender_name or "").split())[:40]
        if event.origin == "NEWMEM":
            message = (
                f"{member_name}님, 어서 오세요! 👋"
                if member_name
                else "새 멤버가 입장했습니다. 어서 오세요! 👋"
            )
            outcome = EventOutcome.MEMBER_WELCOMED
        else:
            message = (
                f"{member_name}님이 퇴장했습니다."
                if member_name
                else "멤버가 퇴장했습니다."
            )
            outcome = EventOutcome.MEMBER_DEPARTURE_ANNOUNCED

        await self._reply_sender.reply(event.chat_id, message)
        self._remember_event(event)
        logger.info("Replied to a member lifecycle event")
        return outcome

    def _remember_event(self, event: IrisEvent) -> None:
        if event.message_id:
            self._remember(event.message_id)

    def _remember(self, message_id: str) -> None:
        self._seen_order.append(message_id)
        self._seen_ids.add(message_id)
        while len(self._seen_order) > self._settings.dedup_cache_size:
            expired = self._seen_order.popleft()
            self._seen_ids.discard(expired)
