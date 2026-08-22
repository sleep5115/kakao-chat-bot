from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx2 as httpx
import websockets
from websockets.exceptions import ConnectionClosed

from .config import Settings

logger = logging.getLogger(__name__)

EventHandler = Callable[[dict[str, Any]], Awaitable[Any]]


class IrisApiClient:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.iris_base_url,
            timeout=settings.iris_request_timeout_seconds,
            transport=transport,
        )

    async def reply(self, room_id: str, message: str) -> None:
        response = await self._client.post(
            "/reply",
            json={"type": "text", "room": room_id, "data": message},
        )
        response.raise_for_status()

    async def get_config(self) -> dict[str, Any]:
        response = await self._client.get("/config")
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Iris /config response must be a JSON object")
        return data

    async def query(
        self,
        query: str,
        bind: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        response = await self._client.post(
            "/query",
            json={"query": query, "bind": bind or []},
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise ValueError("Iris /query response must contain a data list")
        return [row for row in payload["data"] if isinstance(row, dict)]

    async def get_room_type(self, room_id: str) -> str | None:
        rows = await self.query(
            "SELECT type FROM chat_rooms WHERE id = ? LIMIT 1",
            [room_id],
        )
        if not rows:
            return None
        room_type = rows[0].get("type")
        return str(room_type) if room_type is not None else None

    async def close(self) -> None:
        await self._client.aclose()


class IrisWebSocketWorker:
    def __init__(self, settings: Settings, handler: EventHandler) -> None:
        self._settings = settings
        self._handler = handler
        self._stop_event = asyncio.Event()
        self.connected = False
        self.last_error: str | None = None

    async def run(self) -> None:
        delay = self._settings.iris_reconnect_initial_seconds
        while not self._stop_event.is_set():
            try:
                logger.info("Connecting to Iris WebSocket at %s", self._settings.iris_websocket_url)
                async with websockets.connect(
                    self._settings.iris_websocket_url,
                    open_timeout=self._settings.iris_request_timeout_seconds,
                    close_timeout=self._settings.iris_request_timeout_seconds,
                    ping_interval=20,
                    ping_timeout=20,
                    max_size=2**20,
                ) as websocket:
                    self.connected = True
                    self.last_error = None
                    delay = self._settings.iris_reconnect_initial_seconds
                    logger.info("Connected to Iris WebSocket")
                    await self._consume(websocket)
            except asyncio.CancelledError:
                raise
            except (ConnectionClosed, OSError, TimeoutError) as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
                logger.warning("Iris WebSocket disconnected; retrying in %.1fs", delay)
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
                logger.exception("Unexpected Iris WebSocket error; retrying in %.1fs", delay)
            finally:
                self.connected = False

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
            except TimeoutError:
                pass
            delay = min(delay * 2, self._settings.iris_reconnect_max_seconds)

    async def stop(self) -> None:
        self._stop_event.set()

    async def _consume(self, websocket: Any) -> None:
        async for raw_message in websocket:
            if self._stop_event.is_set():
                return
            try:
                if isinstance(raw_message, bytes):
                    raw_message = raw_message.decode("utf-8")
                payload = json.loads(raw_message)
                if not isinstance(payload, dict):
                    raise ValueError("event is not a JSON object")
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                logger.warning("Ignoring malformed Iris WebSocket event")
                continue

            try:
                await self._handler(payload)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Failed to handle Iris event")
