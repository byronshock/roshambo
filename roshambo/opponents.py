"""Scripted opponents for evaluation. Each is a callable (me, opp, rng) -> move,
where `me` is the opponent's own history and `opp` is the bot's."""
from __future__ import annotations

import random
from collections import Counter
from typing import Callable, Sequence

from .core import beats

Opponent = Callable[[Sequence[int], Sequence[int], random.Random], int]


def uniform(me, opp, rng):
    return rng.randrange(3)


def constant(move: int) -> Opponent:
    return lambda me, opp, rng: move


def cycle(me, opp, rng):
    return len(me) % 3


def beat_last(me, opp, rng):
    """Play what would have beaten the bot's last move. A very human tell."""
    return beats(opp[-1]) if opp else rng.randrange(3)


def copy_last(me, opp, rng):
    return opp[-1] if opp else rng.randrange(3)


def win_stay_lose_shift(me, opp, rng):
    """Repeat after a win or tie; after a loss switch to what would have won."""
    if not me:
        return rng.randrange(3)
    last, theirs = me[-1], opp[-1]
    if last == beats(theirs) or last == theirs:
        return last
    return beats(theirs)


def frequency_exploiter(me, opp, rng):
    """Beat the bot's most common move so far."""
    if not opp:
        return rng.randrange(3)
    common = Counter(opp).most_common(1)[0][0]
    return beats(common)


def biased(weights: Sequence[float]) -> Opponent:
    return lambda me, opp, rng: rng.choices(range(3), weights=weights)[0]


def bot_opponent(**kwargs) -> Opponent:
    """Another Bot instance, for self-play. Stateful, so build one per match."""
    from .bot import Bot

    other = Bot(**kwargs)

    def play(me, opp, rng):
        if other.rounds < len(me):  # settle the previous round first
            other.observe(opp[-1])
        return other.move()

    return play


ALL: dict[str, Callable[[], Opponent]] = {
    "uniform": lambda: uniform,
    "constant": lambda: constant(0),
    "cycle": lambda: cycle,
    "beat_last": lambda: beat_last,
    "copy_last": lambda: copy_last,
    "wsls": lambda: win_stay_lose_shift,
    "freq_exploiter": lambda: frequency_exploiter,
    "biased": lambda: biased((0.5, 0.3, 0.2)),
    "self": lambda: bot_opponent(seed=12345),
}
