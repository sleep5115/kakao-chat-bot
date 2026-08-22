from __future__ import annotations

import json
import unittest

import httpx2 as httpx

from kakao_bot.config import Settings
from kakao_bot.iris import IrisApiClient


class IrisApiClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_reply_uses_official_iris_payload(self) -> None:
        captured: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json={"success": True})

        client = IrisApiClient(
            Settings(),
            transport=httpx.MockTransport(handler),
        )
        try:
            await client.reply("1234567890", "퐁")
        finally:
            await client.close()

        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0].url.path, "/reply")
        self.assertEqual(
            json.loads(captured[0].content),
            {"type": "text", "room": "1234567890", "data": "퐁"},
        )

    async def test_room_type_is_looked_up_by_chat_id(self) -> None:
        captured: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json={"data": [{"type": "OM"}]})

        client = IrisApiClient(
            Settings(),
            transport=httpx.MockTransport(handler),
        )
        try:
            room_type = await client.get_room_type("1234567890")
        finally:
            await client.close()

        self.assertEqual(room_type, "OM")
        self.assertEqual(captured[0].url.path, "/query")
        payload = json.loads(captured[0].content)
        self.assertEqual(payload["bind"], ["1234567890"])
        self.assertIn("FROM chat_rooms", payload["query"])


if __name__ == "__main__":
    unittest.main()
