"""Gotcha: history matching over the full game string, one expert per depth.

The whole game is kept as one string, two characters per round: the bot's
move then the opponent's, so a round where the bot played paper and the
opponent scissors is "ps". Every whole-round suffix of that string (the
empty suffix included) is a key in a table whose value counts what the
opponent played immediately after that suffix, every time it occurred.

Each depth is its own predictor. It reads the counts for the suffix of
that many rounds, treats them as an empirical distribution over the
opponent's next move, and plays the best response to that distribution.
"""
from __future__ import annotations

from typing import Sequence

from .core import SYMBOLS, beats

_CHAR = tuple(s.lower() for s in SYMBOLS)  # 0 -> "r", 1 -> "p", 2 -> "s"


def best_response(counts: Sequence[float]) -> int | None:
    """The move with the highest expected score against these opponent-move counts.

    Playing m scores +1 when the opponent plays the move m beats and -1 when
    they play the move that beats m. Ties between moves go to the lowest
    index. None when there are no observations."""
    if not any(counts):
        return None
    ev = [counts[beats(beats(m))] - counts[beats(m)] for m in range(3)]
    return max(range(3), key=ev.__getitem__)


class GotchaTable:
    """The shared history string and suffix count table.

    max_rounds caps suffix length. None keeps every suffix, faithful to the
    original design, but costs time and memory quadratic in game length;
    contexts longer than a dozen rounds never recur in practice."""

    def __init__(self, max_rounds: int | None = 10) -> None:
        self.max_rounds = max_rounds
        self.history = ""
        self.table: dict[str, list[int]] = {}  # suffix -> [rock, paper, scissors] counts

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
            self.table.setdefault(suffix, [0, 0, 0])[opp[-1]] += 1
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

    def counts(self) -> list[tuple[str, list[int]]]:
        """Each current suffix with its table entry, shortest first. Unseen ones get zeros."""
        return [(sfx, self.table.get(sfx, [0, 0, 0])) for sfx in self.suffixes()]


class Gotcha:
    """The depth-k gotcha predictor over a shared table."""

    def __init__(self, table: GotchaTable, depth: int) -> None:
        self.table, self.depth = table, depth

    @property
    def name(self) -> str:
        return f"gotcha{self.depth}"

    def observe(self, me: Sequence[int], opp: Sequence[int]) -> None:
        self.table.observe(me, opp)

    def response(self) -> int | None:
        """Best response to the empirical distribution at this depth, or None."""
        sfx = self.table.suffix(self.depth)
        if sfx is None or sfx not in self.table.table:
            return None
        return best_response(self.table.table[sfx])

    def predict(self, me: Sequence[int], opp: Sequence[int]) -> int | None:
        """Expressed as a predicted opponent move: the one our best response beats,
        so the rotation-0 expert plays the best response itself."""
        r = self.response()
        return None if r is None else beats(beats(r))


def gotcha_predictors(max_rounds: int = 10) -> list[Gotcha]:
    """One predictor per depth, all sharing one table."""
    table = GotchaTable(max_rounds)
    return [Gotcha(table, k) for k in range(max_rounds + 1)]
