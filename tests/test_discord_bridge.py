from __future__ import annotations

import asyncio
import json
import unittest

import httpx2 as httpx

from kakao_bot.config import Settings
from kakao_bot.discord_bridge import (
    DiscordAccessPolicy,
    DiscordKakaoClient,
    KakaoBridgeClient,
)


class DiscordAccessPolicyTests(unittest.TestCase):
    def test_guild_only_policy_allows_any_member_in_that_guild(self) -> None:
        policy = DiscordAccessPolicy(
            guild_id="100",
            channel_id=None,
            allowed_user_ids=frozenset(),
            allowed_role_ids=frozenset(),
        )

        self.assertTrue(
            policy.allows(
                guild_id="100",
                channel_id="200",
                user_id="300",
                role_ids=frozenset(),
            )
        )
        self.assertFalse(
            policy.allows(
                guild_id="999",
                channel_id="200",
                user_id="300",
                role_ids=frozenset(),
            )
        )

    def test_client_uses_guilds_intent_without_privileged_intents(self) -> None:
        settings = Settings(
            discord_bot_token="token",
            discord_guild_id="100",
            discord_kakao_room_id="500",
            discord_bridge_secret="secret",
        )
        client = DiscordKakaoClient(settings)
        try:
            self.assertTrue(client.intents.guilds)
            self.assertFalse(client.intents.members)
            self.assertFalse(client.intents.presences)
            self.assertFalse(client.intents.message_content)
        finally:
            asyncio.run(client.close())

    def test_channel_and_user_or_role_filters_are_enforced(self) -> None:
        policy = DiscordAccessPolicy(
            guild_id="100",
            channel_id="200",
            allowed_user_ids=frozenset({"301"}),
            allowed_role_ids=frozenset({"401"}),
        )

        self.assertTrue(
            policy.allows(
                guild_id="100",
                channel_id="200",
                user_id="301",
                role_ids=frozenset(),
            )
        )
        self.assertTrue(
            policy.allows(
                guild_id="100",
                channel_id="200",
                user_id="302",
                role_ids=frozenset({"401"}),
            )
        )
        self.assertFalse(
            policy.allows(
                guild_id="100",
                channel_id="999",
                user_id="301",
                role_ids=frozenset(),
            )
        )
        self.assertFalse(
            policy.allows(
                guild_id="100",
                channel_id="200",
                user_id="302",
                role_ids=frozenset({"402"}),
            )
        )


class KakaoBridgeClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_send_uses_internal_api_and_secret_header(self) -> None:
        captured: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json={"status": "sent"})

        settings = Settings(
            discord_bridge_secret="bridge-secret",
            discord_bridge_api_url="http://kakao-bot:8000",
        )
        client = KakaoBridgeClient(
            settings,
            transport=httpx.MockTransport(handler),
        )
        try:
            await client.send("디코닉", "안녕하세요")
        finally:
            await client.close()

        self.assertEqual(len(captured), 1)
        request = captured[0]
        self.assertEqual(request.url.path, "/internal/discord/messages")
        self.assertEqual(
            request.headers["X-Discord-Bridge-Token"], "bridge-secret"
        )
        self.assertEqual(
            json.loads(request.content),
            {"sender_name": "디코닉", "message": "안녕하세요"},
        )


if __name__ == "__main__":
    unittest.main()
