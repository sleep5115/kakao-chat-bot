from __future__ import annotations

import unittest

from kakao_bot.games import GameService


class GameServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.games = GameService(number_picker=lambda upper_bound: 0)

    def test_lists_available_games(self) -> None:
        self.assertIn("!주사위", self.games.handle("!게임") or "")

    def test_rolls_default_and_custom_dice(self) -> None:
        self.assertEqual(self.games.handle("!주사위"), "🎲 1 (1~6)")
        self.assertEqual(self.games.handle("!주사위 20"), "🎲 1 (1~20)")

    def test_rejects_invalid_dice(self) -> None:
        self.assertEqual(
            self.games.handle("!주사위 101"),
            "주사위 면 수는 2~100 사이로 입력하세요.",
        )

    def test_flips_coin(self) -> None:
        self.assertEqual(self.games.handle("!동전"), "🪙 앞면")

    def test_plays_rock_paper_scissors(self) -> None:
        self.assertEqual(
            self.games.handle("!가위바위보 바위"),
            "나: 가위 / 사용자: 바위\n사용자가 이겼습니다!",
        )

    def test_ignores_non_game_command(self) -> None:
        self.assertIsNone(self.games.handle("!핑"))
        self.assertIsNone(self.games.handle("   "))


if __name__ == "__main__":
    unittest.main()
