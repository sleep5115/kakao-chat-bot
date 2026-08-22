from __future__ import annotations

import json
import logging
from collections import deque
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any, Mapping, Protocol

from .config import Settings
from .games import GameService
from .models import IrisEvent
from .registration import RegistrationCodeManager
from .registry import RoomRegistry
from .tracking import MemberHistory, TrackedMessage, TrackingRepository

logger = logging.getLogger(__name__)


class ReplySender(Protocol):
    async def reply(self, room_id: str, message: str) -> None: ...


class RoomTypeResolver(Protocol):
    async def get_room_type(self, room_id: str) -> str | None: ...

    async def query(
        self, query: str, bind: list[str] | None = None
    ) -> list[dict[str, Any]]: ...


class EventOutcome(StrEnum):
    REPLIED = "replied"
    REGISTRATION_CODE_ISSUED = "registration_code_issued"
    UNREGISTRATION_CODE_ISSUED = "unregistration_code_issued"
    ROOM_REGISTERED = "room_registered"
    ROOM_UNREGISTERED = "room_unregistered"
    MEMBER_WELCOMED = "member_welcomed"
    MEMBER_DEPARTURE_ANNOUNCED = "member_departure_announced"
    GAME_REPLIED = "game_replied"
    MESSAGE_DELETION_REPORTED = "message_deletion_reported"
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
    MEMBER_EVENT_ORIGINS = frozenset({"NEWMEM", "DELMEM"})
    MESSAGE_ORIGINS = frozenset({"MSG", "WRITE"})
    KOREA_TIMEZONE = timezone(timedelta(hours=9), name="KST")

    def __init__(
        self,
        settings: Settings,
        reply_sender: ReplySender,
        room_type_resolver: RoomTypeResolver,
        room_registry: RoomRegistry,
        tracking_repository: TrackingRepository,
        registration_codes: RegistrationCodeManager,
        unregistration_codes: RegistrationCodeManager,
        game_service: GameService | None = None,
    ) -> None:
        self._settings = settings
        self._reply_sender = reply_sender
        self._room_type_resolver = room_type_resolver
        self._room_registry = room_registry
        self._tracking_repository = tracking_repository
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

        if event.origin in self.MEMBER_EVENT_ORIGINS:
            return await self._handle_member_event(event)
        if event.origin == "SYNCDLMSG":
            return await self._handle_deleted_message(event)

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
        is_command = message == self._settings.bot_command or game_reply is not None

        if (
            self._settings.allowed_room_ids
            and event.chat_id not in self._settings.allowed_room_ids
        ):
            return EventOutcome.ROOM_NOT_ALLOWED

        registered = await self._room_registry.is_registered(event.chat_id)
        if registered and event.origin in self.MESSAGE_ORIGINS:
            await self._track_message(event)
        if not is_command:
            if registered:
                self._remember_event(event)
            return EventOutcome.NOT_COMMAND

        if (
            self._settings.allowed_sender_ids
            and event.sender_id not in self._settings.allowed_sender_ids
        ):
            return EventOutcome.SENDER_NOT_ALLOWED

        if not registered:
            room_type = await self._room_type_resolver.get_room_type(event.chat_id)
            if room_type != "MemoChat":
                return EventOutcome.NOT_REGISTERED

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
        await self._reply_sender.reply(event.chat_id, "등록이 완료되었습니다.")
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

        if event.sender_id is None:
            logger.warning("Ignoring member event because it has no sender_id")
            return EventOutcome.INVALID

        member_name = self._display_name(event.sender_name)
        if event.origin == "NEWMEM":
            history = await self._tracking_repository.record_join(
                event.chat_id,
                event.sender_id,
                member_name,
                event.created_at,
            )
            message = self._join_message(member_name, history)
            outcome = EventOutcome.MEMBER_WELCOMED
        else:
            history = await self._tracking_repository.record_leave(
                event.chat_id,
                event.sender_id,
                member_name,
                event.created_at,
            )
            message = self._leave_message(member_name, history)
            outcome = EventOutcome.MEMBER_DEPARTURE_ANNOUNCED

        await self._reply_sender.reply(event.chat_id, message)
        self._remember_event(event)
        logger.info("Replied to a member lifecycle event")
        return outcome

    async def _track_message(self, event: IrisEvent) -> None:
        assert event.chat_id is not None
        if event.message_id is None:
            return
        content = event.message[: self._settings.message_max_chars]
        if not content:
            content = f"[텍스트가 없는 메시지 · 유형 {event.message_type or '알 수 없음'}]"
        await self._tracking_repository.save_message(
            TrackedMessage(
                chat_id=event.chat_id,
                message_id=event.message_id,
                sender_id=event.sender_id,
                sender_name=self._display_name(event.sender_name),
                content=content,
                message_type=event.message_type,
                sent_at=event.created_at,
            )
        )

    async def _handle_deleted_message(self, event: IrisEvent) -> EventOutcome:
        assert event.chat_id is not None
        if (
            self._settings.allowed_room_ids
            and event.chat_id not in self._settings.allowed_room_ids
        ):
            return EventOutcome.ROOM_NOT_ALLOWED
        if not await self._room_registry.is_registered(event.chat_id):
            return EventOutcome.NOT_REGISTERED

        deleted_message_id = self._deleted_message_id(event.message)
        if deleted_message_id is None:
            logger.warning("Deletion event does not contain a source log ID")
            return EventOutcome.INVALID

        original = await self._tracking_repository.find_message(
            event.chat_id, deleted_message_id
        )
        actor = self._display_name(event.sender_name) or "알 수 없는 사용자"
        if original is None:
            original = await self._find_original_in_iris(
                event, deleted_message_id, actor
            )
        if original is None:
            reply = (
                f"🗑️ {actor}님이 메시지를 삭제했습니다.\n"
                "원문은 추적 시작 전 또는 보존 기간이 지난 메시지라 확인할 수 없습니다."
            )
        else:
            await self._tracking_repository.mark_deleted(
                event.chat_id,
                deleted_message_id,
                event.created_at,
                event.sender_id,
                actor,
            )
            author = original.sender_name or "알 수 없는 사용자"
            content_limit = min(self._settings.message_max_chars, 3400)
            content = original.content[:content_limit]
            reply = (
                "🗑️ 삭제된 메시지를 감지했습니다.\n"
                f"삭제한 사람: {actor}\n"
                f"원 작성자: {author}\n"
                f"작성 시각: {self._format_time(original.sent_at)}\n"
                f"내용: {content}"
            )

        await self._reply_sender.reply(event.chat_id, reply)
        self._remember_event(event)
        logger.info("Reported a deleted message")
        return EventOutcome.MESSAGE_DELETION_REPORTED

    async def _find_original_in_iris(
        self,
        deletion_event: IrisEvent,
        deleted_message_id: str,
        actor: str,
    ) -> TrackedMessage | None:
        assert deletion_event.chat_id is not None
        rows = await self._room_type_resolver.query(
            """
            SELECT _id, chat_id, user_id, type, message, created_at, v, enc
            FROM chat_logs
            WHERE _id = ? AND chat_id = ?
            LIMIT 1
            """,
            [deleted_message_id, deletion_event.chat_id],
        )
        if not rows:
            return None
        row = rows[0]
        source_message = row.get("message")
        if not isinstance(source_message, str):
            return None
        source_event = IrisEvent.from_payload(
            {
                "msg": source_message,
                "sender": (
                    actor
                    if str(row.get("user_id")) == deletion_event.sender_id
                    else None
                ),
                "json": row,
            }
        )
        if source_event is None or source_event.message_id is None:
            return None
        content = source_event.message[: self._settings.message_max_chars]
        if not content:
            content = (
                "[텍스트가 없는 메시지 · 유형 "
                f"{source_event.message_type or '알 수 없음'}]"
            )
        return TrackedMessage(
            chat_id=deletion_event.chat_id,
            message_id=source_event.message_id,
            sender_id=source_event.sender_id,
            sender_name=self._display_name(source_event.sender_name),
            content=content,
            message_type=source_event.message_type,
            sent_at=source_event.created_at,
        )

    @staticmethod
    def _deleted_message_id(message: str) -> str | None:
        try:
            data = json.loads(message)
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(data, Mapping):
            return None
        value = data.get("logId") or data.get("log_id")
        return str(value) if value is not None else None

    @staticmethod
    def _display_name(value: str | None) -> str | None:
        cleaned = " ".join((value or "").split())[:80]
        return cleaned or None

    @classmethod
    def _format_time(cls, value: datetime | None) -> str:
        if value is None:
            return "추적 시작 전"
        return value.astimezone(cls.KOREA_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")

    @classmethod
    def _join_message(
        cls, member_name: str | None, history: MemberHistory
    ) -> str:
        name = member_name or "알 수 없는 사용자"
        first_name = history.first_nickname or "확인 불가"
        first_join = cls._format_time(history.first_joined_at)
        if history.join_count <= 1:
            status = "첫 입장입니다."
        else:
            status = f"{history.join_count - 1}번째 재입장입니다."
        return (
            f"🟢 {name}님이 입장했습니다.\n"
            f"최초 입장: {first_join}\n"
            f"최초 닉네임: {first_name}\n"
            f"{status}"
        )

    @classmethod
    def _leave_message(
        cls, member_name: str | None, history: MemberHistory
    ) -> str:
        name = member_name or "알 수 없는 사용자"
        first_name = history.first_nickname or "확인 불가"
        first_join = cls._format_time(history.first_joined_at)
        reentries = max(0, history.join_count - 1)
        return (
            f"🔴 {name}님이 퇴장했습니다.\n"
            f"최초 입장: {first_join}\n"
            f"최초 닉네임: {first_name}\n"
            f"입장 {history.join_count}회 · 재입장 {reentries}회"
        )

    def _remember_event(self, event: IrisEvent) -> None:
        if event.message_id:
            self._remember(event.message_id)

    def _remember(self, message_id: str) -> None:
        self._seen_order.append(message_id)
        self._seen_ids.add(message_id)
        while len(self._seen_order) > self._settings.dedup_cache_size:
            expired = self._seen_order.popleft()
            self._seen_ids.discard(expired)
