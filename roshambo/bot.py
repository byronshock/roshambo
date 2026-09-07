"""The bot: an ensemble of experts and a meta-selector over their recent form."""
from __future__ import annotations

import random
from typing import Sequence

from .core import outcome
from .experts import Expert, default_predictors


class Bot:
    """Call `move()` to get the bot's play, then `observe(opp_move)` with the reply.

    score_decays: horizons over which an expert's would-have-won record is
                  kept (0.9 ≈ ten rounds, 0.99 ≈ a hundred). Experts are
                  ranked by the sum across horizons.
    epsilon     : probability of a uniformly random move, as insurance
                  against opponents that model *this* bot.
    """

    def __init__(
        self,
        predictors: Sequence | None = None,
        score_decays: Sequence[float] = (0.9, 0.99),
        epsilon: float = 0.0,
        seed: int | None = None,
    ):
        self.rng = random.Random(seed)
        self.epsilon = epsilon
        preds = list(predictors) if predictors is not None else default_predictors()
        self.experts = [Expert(p, k, score_decays) for p in preds for k in range(3)]
        self.me: list[int] = []
        self.opp: list[int] = []
        self.wins = self.losses = self.ties = 0
        self.last_expert: Expert | None = None
        self._pending: int | None = None

    # ---- play ---------------------------------------------------------

    def move(self) -> int:
        """Choose this round's move. Must be followed by observe()."""
        assert self._pending is None, "observe() the previous round first"
        proposals = [(e, e.propose(self.me, self.opp)) for e in self.experts]
        live = [(e, m) for e, m in proposals if m is not None]
        self.last_expert = None
        if self.rng.random() < self.epsilon or not live:
            choice = self.rng.randrange(3)
        else:
            best, m = max(live, key=lambda em: em[0].score)
            if best.score > 0.0:
                self.last_expert, choice = best, m
            else:
                # Nothing is reading the opponent; don't hand them a pattern.
                choice = self.rng.randrange(3)
        self._pending = choice
        return choice

    def observe(self, opp_move: int) -> int:
        """Record the opponent's reply. Returns the round outcome from the bot's view."""
        assert self._pending is not None, "call move() first"
        mine, self._pending = self._pending, None
        self.me.append(mine)
        self.opp.append(opp_move)
        for e in self.experts:
            e.settle(opp_move)
        seen: set[int] = set()
        for e in self.experts:
            if id(e.predictor) not in seen:  # each predictor is shared by 3 experts
                seen.add(id(e.predictor))
                e.predictor.observe(self.me, self.opp)
        r = outcome(mine, opp_move)
        if r > 0:
            self.wins += 1
        elif r < 0:
            self.losses += 1
        else:
            self.ties += 1
        return r

    # ---- introspection -------------------------------------------------

    @property
    def rounds(self) -> int:
        return len(self.opp)

    def predictor(self, cls):
        """The bot's instance of a given predictor class, or None."""
        for e in self.experts:
            if isinstance(e.predictor, cls):
                return e.predictor
        return None

    def leaderboard(self, n: int = 10) -> list[Expert]:
        """Experts ranked by current (decayed) score."""
        return sorted(self.experts, key=lambda e: e.score, reverse=True)[:n]
