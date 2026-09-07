"""Iocaine Powder, by Dan Egnor. Winner of the First International RoShamBo
Programming Competition (1999).

Direct Python port of the original C (http://ofb.net/~egnor/iocaine.html,
retrieved via the Internet Archive). Structure, names, and evaluation order
follow the C so the two can be compared move for move; see
tools/verify_classic. Egnor's text explains the design: several predictors
(history matching over own/opponent/joint history at six horizons, plus
frequency, random, and fixed), each tracked under all three "what would
have beaten it" rotations, with a meta layer choosing among them by recent
performance.

One deliberate difference: the C sized its score arrays for a 1000-round
match and froze after that. `trials=None` (the default) removes the limit;
pass 1000 to reproduce the original exactly.
"""
from __future__ import annotations

_WILL_BEAT = (1, 2, 0)
_WILL_LOSE_TO = (2, 0, 1)
_AGES = (1000, 100, 10, 5, 2, 1)


class _Stats:
    """Cumulative per-rotation scores, one snapshot per round, so any window
    of the last `age` rounds is a difference of two snapshots."""

    __slots__ = ("sums", "age", "limit")

    def __init__(self, limit: int | None):
        self.sums = [[0, 0, 0]]
        self.age = 0
        self.limit = limit

    def add(self, i: int, delta: int) -> None:
        self.sums[self.age][i] += delta

    def next(self) -> None:
        if self.limit is None or self.age < self.limit:
            self.age += 1
            self.sums.append(self.sums[-1][:])

    def max(self, age: int, score: int) -> tuple[int, int]:
        """Best rotation over the last `age` rounds if it beats `score`; (-1, score) otherwise."""
        which = -1
        cur = self.sums[self.age]
        old = None if age > self.age else self.sums[self.age - age]
        for i in range(3):
            diff = cur[i] if old is None else cur[i] - old[i]
            if diff > score:
                score, which = diff, i
        return which, score


class _Predict:
    """A predictor's last guess plus the record of each rotation of it."""

    __slots__ = ("st", "last")

    def __init__(self, limit: int | None):
        self.st = _Stats(limit)
        self.last = -1

    def do(self, last: int, guess: int) -> None:
        """Score the previous guess against the opponent's actual `last` move, then store the new guess."""
        if last != -1:
            diff = (3 + last - self.last) % 3
            self.st.add(_WILL_BEAT[diff], 1)
            self.st.add(_WILL_LOSE_TO[diff], -1)
            self.st.next()
        self.last = guess

    def scan(self, age: int, move: int, score: int) -> tuple[int, int]:
        which, score = self.st.max(age, score)
        if which != -1:
            move = (self.last + which) % 3
        return move, score


class Iocaine:
    name = "iocaine"

    def __init__(self, trials: int | None = None):
        self.trials = trials
        self.my = [0]  # 1-based; element 0 is the number of rounds played
        self.opp = [0]
        self._reset()

    def _reset(self) -> None:
        n, lim = len(_AGES), self.trials
        self.pr_history = [[[_Predict(lim) for _ in range(2)] for _ in range(3)] for _ in range(n)]
        self.pr_freq = [[_Predict(lim) for _ in range(2)] for _ in range(n)]
        self.pr_fixed = _Predict(lim)
        self.pr_random = _Predict(lim)
        self.pr_meta = [_Predict(lim) for _ in range(n)]
        self.stats = [_Stats(lim), _Stats(lim)]

    @property
    def rounds(self) -> int:
        return self.my[0]

    def observe(self, mine: int, theirs: int) -> None:
        self.my.append(mine)
        self.opp.append(theirs)
        self.my[0] += 1
        self.opp[0] += 1

    # ---- history matching -------------------------------------------

    def _match_single(self, i: int, hist: list[int]) -> int:
        """Length of the match between the history ending at i and the one ending now."""
        num, j = hist[0], 0
        while i - j > 0 and hist[i - j] == hist[num - j]:
            j += 1
        return j

    def _match_both(self, i: int) -> int:
        my, opp = self.my, self.opp
        num, j = my[0], 0
        while j < i and opp[num - j] == opp[i - j] and my[num - j] == my[i - j]:
            j += 1
        return j

    def _do_history(self, age: int) -> list[int]:
        """For each of (my, opp, both): the index of the best match within `age` rounds, or 0."""
        num = self.my[0]
        matchers = (
            lambda i: self._match_single(i, self.my),
            lambda i: self._match_single(i, self.opp),
            self._match_both,
        )
        best, best_length = [0, 0, 0], [0, 0, 0]
        for w, match in enumerate(matchers):
            i = num - 1
            while i > num - age and i > best_length[w]:
                j = match(i)
                if j > best_length[w]:
                    best_length[w] = j
                    best[w] = i
                    if j > num // 2:
                        break
                i -= 1
        return best

    # ---- play ----------------------------------------------------------

    def move(self, guess: int) -> int:
        """The bot's play, given one uniformly random move `guess` for its own use."""
        my, opp = self.my, self.opp
        num = my[0]
        last = opp[num] if num > 0 else -1

        if num == 0:
            self._reset()
        else:
            self.stats[0].add(my[num], 1)
            self.stats[1].add(opp[num], 1)

        for a, age in enumerate(_AGES):
            best = self._do_history(age)
            for w in range(3):
                b = best[w]
                if b == 0:
                    self.pr_history[a][w][0].do(last, guess)
                    self.pr_history[a][w][1].do(last, guess)
                else:
                    self.pr_history[a][w][0].do(last, my[b + 1])
                    self.pr_history[a][w][1].do(last, opp[b + 1])
            for p in range(2):
                freq, _ = self.stats[p].max(age, -1)
                self.pr_freq[a][p].do(last, freq if freq != -1 else guess)

        self.pr_random.do(last, guess)
        self.pr_fixed.do(last, 0)

        for a, age in enumerate(_AGES):
            move, score = -1, -1
            for aa in range(len(_AGES)):
                for p in range(2):
                    for w in range(3):
                        move, score = self.pr_history[aa][w][p].scan(age, move, score)
                    move, score = self.pr_freq[aa][p].scan(age, move, score)
            move, score = self.pr_random.scan(age, move, score)
            move, score = self.pr_fixed.scan(age, move, score)
            self.pr_meta[a].do(last, move)

        move, score = -1, -1
        everything = self.trials if self.trials is not None else 1 << 30
        for a in range(len(_AGES)):
            move, score = self.pr_meta[a].scan(everything, move, score)
        return move
