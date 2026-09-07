"""Gotcha: a history-matching predictor over the full game string.

The whole game is kept as one string, two characters per round: the bot's
move then the opponent's, so a round where the bot played paper and the
opponent scissors is "ps". From that string we take every suffix that is
a whole number of rounds long, i.e. every even-length suffix ending with
the previous round. Longer suffixes are more specific contexts; shorter
ones have occurred more often.

Each suffix is a key in a table whose value is a count of what the
opponent played immediately after that suffix, every time it occurred.
"""
from __future__ import annotations

from typing import Sequence

from .core import PAPER, SYMBOLS

_CHAR = tuple(s.lower() for s in SYMBOLS)  # 0 -> "r", 1 -> "p", 2 -> "s"


class Gotcha:
    """max_rounds caps suffix length. None keeps every suffix, faithful to
    the original design, but costs time and memory quadratic in game length;
    contexts longer than a couple of dozen rounds never recur in practice."""

    def __init__(self, max_rounds: int | None = 10) -> None:
        self.max_rounds = max_rounds
        self.history = ""
        self.table: dict[str, list[int]] = {}  # suffix -> [rock, paper, scissors] counts

    @property
    def name(self) -> str:
        return "gotcha"

    @property
    def rounds(self) -> int:
        return len(self.history) // 2

    def observe(self, me: Sequence[int], opp: Sequence[int]) -> None:
        """Record the most recent round (already appended to me/opp).

        Every suffix of the history *before* this round now has one more
        observation of what followed it: the opponent's move this round.
        """
        for suffix in self.suffixes():
            self.table.setdefault(suffix, [0, 0, 0])[opp[-1]] += 1
        self.history += _CHAR[me[-1]] + _CHAR[opp[-1]]

    def suffixes(self) -> list[str]:
        """Every whole-round suffix of the history, shortest first.

        Starts with the empty suffix, whose table entry counts the
        opponent's moves regardless of context."""
        h = self.history
        longest = self.rounds if self.max_rounds is None else min(self.rounds, self.max_rounds)
        return [h[len(h) - 2 * k :] for k in range(0, longest + 1)]

    def counts(self) -> list[tuple[str, list[int]]]:
        """Each current suffix with its table entry, shortest first.

        Unseen suffixes get zero counts."""
        return [(sfx, self.table.get(sfx, [0, 0, 0])) for sfx in self.suffixes()]

    def predict(self, me: Sequence[int], opp: Sequence[int]) -> int | None:
        """Predicted opponent move. Placeholder: always paper."""
        return PAPER
