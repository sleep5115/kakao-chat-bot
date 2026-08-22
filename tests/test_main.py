from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from kakao_bot.config import Settings
from kakao_bot.main import create_app


class HealthEndpointTests(unittest.TestCase):
    def test_live_is_ok_and_ready_is_degraded_without_iris(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = Settings(
                iris_base_url="http://127.0.0.1:9",
                iris_request_timeout_seconds=0.1,
                iris_reconnect_initial_seconds=0.1,
                iris_reconnect_max_seconds=0.1,
                room_database_path=str(Path(temp_dir) / "registry.db"),
            )
            app = create_app(settings)

            with TestClient(app) as client:
                live = client.get("/health/live")
                ready = client.get("/health/ready")

        self.assertEqual(live.status_code, 200)
        self.assertEqual(live.json(), {"status": "ok"})
        self.assertEqual(ready.status_code, 503)
        self.assertEqual(ready.json()["status"], "degraded")
        self.assertFalse(ready.json()["iris_connected"])


if __name__ == "__main__":
    unittest.main()
