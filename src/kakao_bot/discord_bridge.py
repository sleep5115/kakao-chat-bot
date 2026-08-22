from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import discord
import httpx2 as httpx
from discord import app_commands

from .config import Settings

logger = logging.getLogger(__name__)
READY_FILE = Path("/tmp/discord-kakao-ready")


@dataclass(frozen=True, slots=True)
class DiscordAccessPolicy:
    guild_id: str
    channel_id: str | None
    allowed_user_ids: frozenset[str]
    allowed_role_ids: frozenset[str]

    def allows(
        self,
        *,
        guild_id: str | None,
        channel_id: str | None,
        user_id: str,
        role_ids: frozenset[str],
    ) -> bool:
        if guild_id != self.guild_id:
            return False
        if self.channel_id and channel_id != self.channel_id:
            return False
        if not self.allowed_user_ids and not self.allowed_role_ids:
            return True
        return (
            user_id in self.allowed_user_ids
            or bool(role_ids & self.allowed_role_ids)
        )


class KakaoBridgeClient:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        assert settings.discord_bridge_secret is not None
        self._client = httpx.AsyncClient(
            base_url=settings.discord_bridge_api_url,
            timeout=settings.iris_request_timeout_seconds,
            headers={"X-Discord-Bridge-Token": settings.discord_bridge_secret},
            transport=transport,
        )

    async def send(self, sender_name: str, message: str) -> None:
        response = await self._client.post(
            "/internal/discord/messages",
            json={"sender_name": sender_name, "message": message},
        )
        response.raise_for_status()

    async def close(self) -> None:
        await self._client.aclose()


class DiscordKakaoClient(discord.Client):
    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        super().__init__(intents=intents)
        assert settings.discord_guild_id is not None
        self._settings = settings
        self._guild = discord.Object(id=int(settings.discord_guild_id))
        self._policy = DiscordAccessPolicy(
            guild_id=settings.discord_guild_id,
            channel_id=settings.discord_channel_id,
            allowed_user_ids=settings.discord_allowed_user_ids,
            allowed_role_ids=settings.discord_allowed_role_ids,
        )
        self._bridge = KakaoBridgeClient(settings)
        self.tree = app_commands.CommandTree(self)

        async def send_kakao(
            interaction: discord.Interaction,
            메시지: str,
        ) -> None:
            await self._handle_send(interaction, 메시지)

        command = app_commands.Command(
            name="카톡",
            description="카카오톡 채팅방으로 메시지를 전송합니다.",
            callback=send_kakao,
        )
        command.error(self._handle_command_error)
        self.tree.add_command(command, guild=self._guild)

    async def setup_hook(self) -> None:
        synced = await self.tree.sync(guild=self._guild)
        logger.info("Synced %d Discord guild command(s)", len(synced))

    async def on_ready(self) -> None:
        READY_FILE.write_text("ready\n", encoding="utf-8")
        logger.info("Discord bot connected as %s", self.user)

    async def on_disconnect(self) -> None:
        READY_FILE.unlink(missing_ok=True)
        logger.warning("Discord bot disconnected")

    async def close(self) -> None:
        READY_FILE.unlink(missing_ok=True)
        await self._bridge.close()
        await super().close()

    async def _handle_send(
        self,
        interaction: discord.Interaction,
        message: str,
    ) -> None:
        role_ids = frozenset(
            str(role.id)
            for role in getattr(interaction.user, "roles", ())
        )
        if not self._policy.allows(
            guild_id=str(interaction.guild_id) if interaction.guild_id else None,
            channel_id=(
                str(interaction.channel_id) if interaction.channel_id else None
            ),
            user_id=str(interaction.user.id),
            role_ids=role_ids,
        ):
            await interaction.response.send_message(
                "이 서버·채널 또는 사용자에게는 사용할 권한이 없습니다.",
                ephemeral=True,
            )
            return

        message = message.strip()
        if not message or len(message) > self._settings.discord_max_message_chars:
            await interaction.response.send_message(
                (
                    "메시지는 1자 이상 "
                    f"{self._settings.discord_max_message_chars}자 이하로 입력하세요."
                ),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        sender_name = " ".join(interaction.user.display_name.split())[:80]
        try:
            await self._bridge.send(sender_name, message)
        except httpx.HTTPError:
            logger.exception("Failed to forward a Discord message to KakaoTalk")
            await interaction.followup.send(
                "카카오톡 전송에 실패했습니다. 잠시 후 다시 시도하세요.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            "카카오톡으로 전송했습니다.",
            ephemeral=True,
        )

    async def _handle_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        logger.exception("Discord slash command failed", exc_info=error)
        message = "명령 처리 중 오류가 발생했습니다."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


def main() -> None:
    settings = Settings.from_env()
    settings.validate_discord_bot()
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    client = DiscordKakaoClient(settings)
    assert settings.discord_bot_token is not None
    client.run(settings.discord_bot_token, log_handler=None)


if __name__ == "__main__":
    main()
