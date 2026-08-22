from __future__ import annotations

import secrets
from collections.abc import Callable


class GameService:
    """Stateless chat games that do not retain player identifiers or results."""

    COMMANDS = frozenset({"!게임", "!주사위", "!동전", "!가위바위보"})
    RPS_CHOICES = ("가위", "바위", "보")

    def __init__(self, number_picker: Callable[[int], int] = secrets.randbelow) -> None:
        self._number_picker = number_picker

    def handle(self, message: str) -> str | None:
        parts = message.split()
        if not parts:
            return None
        command, *arguments = parts
        if command not in self.COMMANDS:
            return None

        if command == "!게임":
            return "게임 명령: !주사위 [2~100] / !동전 / !가위바위보 [가위|바위|보]"
        if command == "!동전":
            if arguments:
                return "사용법: !동전"
            return f"🪙 {('앞면', '뒷면')[self._number_picker(2)]}"
        if command == "!주사위":
            return self._roll_die(arguments)
        return self._play_rps(arguments)

    def _roll_die(self, arguments: list[str]) -> str:
        if len(arguments) > 1:
            return "사용법: !주사위 또는 !주사위 [2~100]"
        try:
            sides = int(arguments[0]) if arguments else 6
        except ValueError:
            return "사용법: !주사위 또는 !주사위 [2~100]"
        if not 2 <= sides <= 100:
            return "주사위 면 수는 2~100 사이로 입력하세요."
        return f"🎲 {self._number_picker(sides) + 1} (1~{sides})"

    def _play_rps(self, arguments: list[str]) -> str:
        if len(arguments) != 1 or arguments[0] not in self.RPS_CHOICES:
            return "사용법: !가위바위보 [가위|바위|보]"

        user_choice = arguments[0]
        bot_choice = self.RPS_CHOICES[self._number_picker(len(self.RPS_CHOICES))]
        difference = (
            self.RPS_CHOICES.index(user_choice)
            - self.RPS_CHOICES.index(bot_choice)
        ) % len(self.RPS_CHOICES)
        if difference == 0:
            result = "무승부입니다."
        elif difference == 1:
            result = "사용자가 이겼습니다!"
        else:
            result = "제가 이겼습니다!"
        return f"나: {bot_choice} / 사용자: {user_choice}\n{result}"
