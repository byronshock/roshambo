"""Predictors and experts.

A *predictor* looks at the round history and guesses one move. An *expert*
wraps a predictor with a rotation (0, 1, or 2 steps), which is the
"second-guessing" layer: if the raw prediction says the opponent plays X,
rotation 1 assumes they know that and play beats(X), rotation 2 assumes
they know *that* too. Every expert keeps its own decayed would-have-won
score so a meta-selector can pick whichever is reading the opponent best
right now and age out ones whose tell has gone stale.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Sequence

from .core import beats, outcome, rotate

Seq = Sequence[int]


class Ngram:
    """Context-conditioned move counts.

    depth   : how many past rounds form the context (0 = plain frequency).
    source  : which sequence forms the context: "opp", "me", or "both".
    target  : whose next move the table predicts. "opp" predicts the
              opponent directly. "me" predicts *my* next move, on the theory
              that the opponent is modelling me, and returns the move they
              would play to beat it.
    decay   : per-observation multiplier on old counts (1.0 = never forget).
    """

    def __init__(self, depth: int, source: str, target: str, decay: float):
        assert source in ("opp", "me", "both") and target in ("opp", "me")
        self.depth, self.source, self.target, self.decay = depth, source, target, decay
        self.table: dict[tuple, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])

    @property
    def name(self) -> str:
        if self.depth == 0:
            return f"freq[{self.target}]d{self.decay:g}"
        return f"{self.source}{self.depth}->{self.target} d{self.decay:g}"

    def _context(self, me: Seq, opp: Seq, end: int) -> tuple | None:
        if end < self.depth:
            return None
        start = end - self.depth
        if self.source == "opp":
            return tuple(opp[start:end])
        if self.source == "me":
            return tuple(me[start:end])
        return tuple(zip(me[start:end], opp[start:end]))

    def observe(self, me: Seq, opp: Seq) -> None:
        """Update with the most recent round (already appended to me/opp)."""
        n = len(opp)
        ctx = self._context(me, opp, n - 1)
        if ctx is None:
            return
        nxt = (opp if self.target == "opp" else me)[n - 1]
        counts = self.table[ctx]
        if self.decay < 1.0:
            for i in range(3):
                counts[i] *= self.decay
        counts[nxt] += 1.0

    def predict(self, me: Seq, opp: Seq) -> int | None:
        """Predicted opponent move, or None when this context is unseen."""
        ctx = self._context(me, opp, len(opp))
        if ctx is None or ctx not in self.table:
            return None
        counts = self.table[ctx]
        best = max(range(3), key=counts.__getitem__)
        if counts[best] == 0.0:
            return None
        return best if self.target == "opp" else beats(best)


class Expert:
    """A predictor plus a rotation, with its own would-have-won record."""

    def __init__(self, predictor, rotation: int, score_decays: Sequence[float]):
        self.predictor, self.rotation = predictor, rotation
        self.score_decays = tuple(score_decays)
        # One decayed would-have-won tally per horizon: a fast one to catch a
        # tell the moment it appears, a slow one so a steady but noisy edge
        # (a mild frequency bias, say) isn't abandoned after a bad streak.
        self.scores = [0.0] * len(self.score_decays)
        self.wins = self.losses = self.ties = 0
        self.pending: int | None = None  # the move this expert wanted to play this round

    @property
    def score(self) -> float:
        return sum(self.scores)

    @property
    def name(self) -> str:
        return f"{self.predictor.name} rot{self.rotation}"

    def propose(self, me: Seq, opp: Seq) -> int | None:
        p = self.predictor.predict(me, opp)
        self.pending = None if p is None else beats(rotate(p, self.rotation))
        return self.pending

    def settle(self, opp_move: int) -> None:
        """Score the round's proposal against what the opponent actually played."""
        self.scores = [s * d for s, d in zip(self.scores, self.score_decays)]
        if self.pending is None:
            return
        r = outcome(self.pending, opp_move)
        self.scores = [s + r for s in self.scores]
        if r > 0:
            self.wins += 1
        elif r < 0:
            self.losses += 1
        else:
            self.ties += 1
        self.pending = None


Predictor = Ngram  # anything with .name, .observe(me, opp), .predict(me, opp)


def default_predictors(max_depth: int = 5, decays: Sequence[float] = (1.0, 0.8)) -> list:
    """The standard ensemble: gotcha, frequency, and n-grams over every source/target/decay."""
    from .gotcha import Gotcha

    preds: list = [Gotcha()]
    for decay in decays:
        for target in ("opp", "me"):
            preds.append(Ngram(0, "opp", target, decay))
            for depth in range(1, max_depth + 1):
                for source in ("opp", "me", "both"):
                    preds.append(Ngram(depth, source, target, decay))
    return preds
