"""Gotcha: a history-matching predictor over the full game string.

The whole game is kept as one string, two characters per round: the bot's
move then the opponent's, so a round where the bot played paper and the
opponent scissors is "ps". From that string we take every suffix that is
a whole number of rounds long, i.e. every even-length suffix ending with
the previous round. Longer suffixes are more specific contexts; shorter
ones have occurred more often.
"""
from __future__ import annotations

from typing import Sequence

from .core import PAPER, SYMBOLS

_CHAR = tuple(s.lower() for s in SYMBOLS)  # 0 -> "r", 1 -> "p", 2 -> "s"


class Gotcha:
    def __init__(self) -> None:
        self.history = ""

    @property
    def name(self) -> str:
        return "gotcha"

    @property
    def rounds(self) -> int:
        return len(self.history) // 2

    def observe(self, me: Sequence[int], opp: Sequence[int]) -> None:
        """Append the most recent round (already appended to me/opp)."""
        self.history += _CHAR[me[-1]] + _CHAR[opp[-1]]

    def suffixes(self) -> list[str]:
        """Every whole-round suffix of the history, shortest first."""
        h = self.history
        return [h[len(h) - 2 * k :] for k in range(1, self.rounds + 1)]

    def predict(self, me: Sequence[int], opp: Sequence[int]) -> int | None:
        """Predicted opponent move. Placeholder: always paper."""
        return PAPER
