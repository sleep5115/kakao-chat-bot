from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .config import Settings
from .iris import IrisApiClient, IrisWebSocketWorker
from .registration import RegistrationCodeManager
from .registry import create_room_registry
from .service import KakaoBot
from .tracking import create_tracking_repository


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or Settings.from_env()
    logging.basicConfig(
        level=getattr(logging, active_settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        iris_api = IrisApiClient(active_settings)
        room_registry = create_room_registry(active_settings)
        await room_registry.initialize()
        tracking_repository = create_tracking_repository(active_settings)
        await tracking_repository.initialize()
        registration_codes = RegistrationCodeManager(
            ttl_seconds=active_settings.registration_code_ttl_seconds,
            max_attempts_per_room=(
                active_settings.registration_code_max_attempts_per_room
            ),
        )
        unregistration_codes = RegistrationCodeManager(
            ttl_seconds=active_settings.registration_code_ttl_seconds,
            max_attempts_per_room=(
                active_settings.registration_code_max_attempts_per_room
            ),
        )
        bot = KakaoBot(
            active_settings,
            iris_api,
            iris_api,
            room_registry,
            tracking_repository,
            registration_codes,
            unregistration_codes,
        )
        worker = IrisWebSocketWorker(active_settings, bot.handle_payload)
        worker_task = asyncio.create_task(worker.run(), name="iris-websocket-worker")
        app.state.iris_api = iris_api
        app.state.iris_worker = worker
        app.state.room_registry = room_registry
        app.state.tracking_repository = tracking_repository

        try:
            yield
        finally:
            await worker.stop()
            worker_task.cancel()
            with suppress(asyncio.CancelledError):
                await worker_task
            await iris_api.close()

    app = FastAPI(
        title="KakaoTalk Playground Bot",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    async def ready() -> JSONResponse:
        worker = getattr(app.state, "iris_worker", None)
        connected = bool(worker and worker.connected)
        body = {
            "status": "ready" if connected else "degraded",
            "iris_connected": connected,
            "last_error": worker.last_error if worker else "worker_not_started",
        }
        return JSONResponse(body, status_code=200 if connected else 503)

    return app


app = create_app()
