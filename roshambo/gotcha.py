"""Gotcha: history matching over the full game string, one expert per depth.

The whole game is kept as one string, two characters per round: the bot's
move then the opponent's, so a round where the bot played paper and the
opponent scissors is "ps". Every whole-round suffix of that string (the
empty suffix included) is a key in a table whose value counts what the
opponent played immediately after that suffix, every time it occurred.

Entries start at (1, 1, 1), so the normalised counts are an add-one
smoothed estimate (rock_hat, paper_hat, scissors_hat) of the opponent's
next move. Each depth is its own predictor, and rather than always playing
the single best response it probability-matches: it plays ROCK with
probability scissors_hat, PAPER with probability rock_hat, and SCISSORS
with probability paper_hat. In predictor terms, it draws an opponent move
from the estimate and the rotation-0 expert plays what beats the draw.
"""
from __future__ import annotations

import random
from typing import Sequence

from .core import SYMBOLS

_CHAR = tuple(s.lower() for s in SYMBOLS)  # 0 -> "r", 1 -> "p", 2 -> "s"


class GotchaTable:
    """The shared history string and suffix count table.

    max_rounds caps suffix length. None keeps every suffix, faithful to the
    original design, but costs time and memory quadratic in game length;
    contexts longer than a dozen rounds never recur in practice."""

    def __init__(self, max_rounds: int | None = 10, rng: random.Random | None = None) -> None:
        self.max_rounds = max_rounds
        self.rng = rng or random.Random()
        self.history = ""
        self.table: dict[str, list[int]] = {}  # suffix -> [rock, paper, scissors] counts, from (1, 1, 1)

    @property
    def rounds(self) -> int:
        return len(self.history) // 2

    def observe(self, me: Sequence[int], opp: Sequence[int]) -> None:
        """Record the most recent round (already appended to me/opp), once.

        Every suffix of the history *before* this round now has one more
        observation of what followed it: the opponent's move this round."""
        if self.rounds >= len(opp):
            return  # another depth's predictor already recorded this round
        for suffix in self.suffixes():
            self.table.setdefault(suffix, [1, 1, 1])[opp[-1]] += 1
        self.history += _CHAR[me[-1]] + _CHAR[opp[-1]]

    def suffix(self, depth: int) -> str | None:
        """The last `depth` rounds as a string, or None if the game is shorter."""
        if depth > self.rounds:
            return None
        return self.history[len(self.history) - 2 * depth :]

    def suffixes(self) -> list[str]:
        """Every whole-round suffix up to the cap, shortest first (empty first)."""
        longest = self.rounds if self.max_rounds is None else min(self.rounds, self.max_rounds)
        return [self.suffix(k) for k in range(longest + 1)]

    def estimate(self, depth: int) -> list[float] | None:
        """Add-one smoothed estimate of the opponent's next move at this depth.

        None when the game is shorter than `depth` rounds or this context
        has never been followed by anything."""
        sfx = self.suffix(depth)
        if sfx is None or sfx not in self.table:
            return None
        counts = self.table[sfx]
        total = sum(counts)
        return [c / total for c in counts]


class Gotcha:
    """The depth-k gotcha predictor over a shared table.

    `rotations` says which second-guessing experts to build on it. The
    default is rotation 0 only: play what beats the draw, nothing cleverer."""

    def __init__(self, table: GotchaTable, depth: int, rotations: Sequence[int] = (0,)) -> None:
        self.table, self.depth = table, depth
        self.rotations = tuple(rotations)

    @property
    def name(self) -> str:
        return f"gotcha{self.depth}"

    def observe(self, me: Sequence[int], opp: Sequence[int]) -> None:
        self.table.observe(me, opp)

    def predict(self, me: Sequence[int], opp: Sequence[int]) -> int | None:
        """An opponent move drawn from this depth's estimate, or None without data."""
        est = self.table.estimate(self.depth)
        if est is None:
            return None
        return self.table.rng.choices((0, 1, 2), weights=est)[0]


def gotcha_predictors(
    max_rounds: int = 10, seed: int | None = None, rotations: Sequence[int] = (0,)
) -> list[Gotcha]:
    """One predictor per depth, all sharing one table."""
    table = GotchaTable(max_rounds, random.Random(seed))
    return [Gotcha(table, k, rotations) for k in range(max_rounds + 1)]
