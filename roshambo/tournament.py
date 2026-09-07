"""Round-robin crosstable: every entrant plays every other over several seeds.

Each cell reports the row entrant's mean margin against the column entrant,
in percentage points of rounds (wins minus losses over rounds), with an
approximate 95% confidence interval across seeds. Entrants are ranked by
their average margin over all opponents, the way the original RoShamBo
tournaments ranked their "open" division.
"""
from __future__ import annotations

import os
import random
import statistics
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from typing import Callable, Protocol, Sequence

from .bot import Bot, make_bot
from .classic import Greenberg, Iocaine
from .core import outcome
from .experts import LINEUPS
from .opponents import ALL as SCRIPTED


class Player(Protocol):
    def move(self, rng: random.Random) -> int: ...
    def observe(self, mine: int, theirs: int) -> None: ...


class BotPlayer:
    def __init__(self, bot: Bot):
        self.bot = bot

    def move(self, rng):
        return self.bot.move()

    def observe(self, mine, theirs):
        self.bot.observe(theirs)


class ClassicPlayer:
    def __init__(self, bot):
        self.bot = bot

    def move(self, rng):
        return self.bot.move(rng.randrange(3))

    def observe(self, mine, theirs):
        self.bot.observe(mine, theirs)


class ScriptedPlayer:
    def __init__(self, fn):
        self.fn, self.me, self.opp = fn, [], []

    def move(self, rng):
        return self.fn(self.me, self.opp, rng)

    def observe(self, mine, theirs):
        self.me.append(mine)
        self.opp.append(theirs)


ENTRANTS: dict[str, Callable[[int], Player]] = {
    "iocaine": lambda seed: ClassicPlayer(Iocaine()),
    "greenberg": lambda seed: ClassicPlayer(Greenberg()),
}
for _name in LINEUPS:
    ENTRANTS[_name] = lambda seed, n=_name: BotPlayer(make_bot(n, seed=seed))
for _name in ("uniform", "biased", "wsls", "beat_last", "freq_exploiter"):
    ENTRANTS[_name] = lambda seed, n=_name: ScriptedPlayer(SCRIPTED[n]())

DEFAULT = ("gotcha", "gotcha-rot", "ngram", "full", "iocaine", "greenberg", "uniform", "wsls")


def play(a: Player, b: Player, rounds: int, seed: int) -> float:
    """One match. Returns a's margin: (wins - losses) / rounds."""
    rng_a, rng_b = random.Random(2 * seed), random.Random(2 * seed + 1)
    wins = losses = 0
    for _ in range(rounds):
        x, y = a.move(rng_a), b.move(rng_b)
        a.observe(x, y)
        b.observe(y, x)
        r = outcome(x, y)
        wins += r > 0
        losses += r < 0
    return (wins - losses) / rounds


def _match(job: tuple[str, int, str, int, int, int]) -> tuple[str, str, int, float]:
    """One seeded match, picklable so it can run in a worker process."""
    a, i, b, j, rounds, s = job
    return a, b, s, play(ENTRANTS[a](1000 * s + i), ENTRANTS[b](1000 * s + j), rounds, seed=s)


def crosstable(
    names: Sequence[str],
    rounds: int,
    seeds: int,
    progress: Callable[[str], None] | None = None,
    jobs: int | None = None,
) -> dict[tuple[str, str], list[float]]:
    """Margins for every ordered pair, one per seed. Antisymmetric by construction.

    Matches are independent and run across `jobs` processes (default: all
    cores). Results are identical whatever the job count."""
    work = [
        (a, i, names[j], j, rounds, s)
        for i, a in enumerate(names)
        for j in range(i + 1, len(names))
        for s in range(seeds)
    ]
    jobs = jobs or os.cpu_count() or 1
    if jobs > 1 and len(work) > 1:
        with ProcessPoolExecutor(max_workers=min(jobs, len(work))) as pool:
            outcomes = list(pool.map(_match, work, chunksize=1))
    else:
        outcomes = [_match(w) for w in work]
    results: dict[tuple[str, str], list[float]] = defaultdict(list)
    for a, b, s, m in outcomes:  # seed order within a pair is preserved by map()
        results[(a, b)].append(m)
        results[(b, a)].append(-m)
    if progress:
        for i, a in enumerate(names):
            for b in names[i + 1 :]:
                progress(f"{a} vs {b}: {statistics.fmean(results[(a, b)]):+.3f}")
    return results


def summarize(margins: Sequence[float]) -> tuple[float, float]:
    """Mean and half-width of an approximate 95% interval, in percentage points."""
    mean = 100 * statistics.fmean(margins)
    if len(margins) < 2:
        return mean, float("nan")
    return mean, 100 * 1.96 * statistics.stdev(margins) / len(margins) ** 0.5


def report(names: Sequence[str], results: dict[tuple[str, str], list[float]], rounds: int, seeds: int) -> str:
    def avg(a):
        return statistics.fmean(statistics.fmean(results[(a, b)]) for b in names if b != a)

    ranked = sorted(names, key=avg, reverse=True)
    w = max(len(n) for n in names)
    cw = 11
    lines = [
        f"Margin of row vs column, percentage points, mean ±95% over {seeds} seeds × {rounds} rounds",
        "",
        " " * w + "".join(f"{n[:cw - 1]:>{cw}}" for n in ranked) + f"{'avg':>{cw}}",
    ]
    for a in ranked:
        cells = []
        for b in ranked:
            if a == b:
                cells.append(f"{'·':>{cw}}")
            else:
                mean, ci = summarize(results[(a, b)])
                cells.append(f"{mean:+.1f}±{ci:.1f}".rjust(cw))
        lines.append(f"{a:<{w}}" + "".join(cells) + f"{100 * avg(a):+{cw}.1f}")
    return "\n".join(lines)


def run(
    names: Sequence[str] = DEFAULT,
    rounds: int = 1000,
    seeds: int = 5,
    verbose: bool = True,
    jobs: int | None = None,
) -> str:
    unknown = [n for n in names if n not in ENTRANTS]
    if unknown:
        raise SystemExit(f"unknown entrants {unknown}; choose from {sorted(ENTRANTS)}")
    results = crosstable(names, rounds, seeds, progress=print if verbose else None, jobs=jobs)
    text = report(names, results, rounds, seeds)
    if verbose:
        print()
        print(text)
    return text
