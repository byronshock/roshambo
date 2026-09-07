"""Greenberg, by Andrzej Nagorko. Winner of the Second International RoShamBo
Programming Competition (2000).

Direct Python port of the original C (http://www.mathpuzzle.com/greenberg.c),
cross-checked against Travis Erdman's earlier Python translation
(https://github.com/erdman/roshambo). Names and evaluation order follow the
C so the two can be compared move for move; see tools/verify_classic.

The design: history matching over own, opponent, and joint history at
context lengths 1-4, each yielding several predictions (first occurrence,
majority after three, overall majority, and a "gear" correction), plus
frequency predictors, plus the mirror-image "worst move" versions of all
of them, each tracked under all three rotations over six score windows.

Two things the C left to undefined behaviour or convention that this port
pins down:

- `find_max_index` and `find_min_index` in the C use `>=` and `<=`, so
  ties go to the LAST index. This port does the same. (Erdman's takes the
  first.)
- The gear table `gear_freq[3]` is indexed by a nine-valued gear and so
  overruns in the C. This port sizes it at nine and takes the max over all
  nine, as Erdman's does.
"""
from __future__ import annotations

_BEST_WITHOUT = (2, 0, 1)
_WINS_WITH = (1, 2, 0)
_SCORE = ((0, -1, 1), (1, 0, -1), (-1, 1, 0))  # [mine][theirs]
_LENGTHS = (10, 20, 30, 40, 49, 0)


def _cdiv(a: int, b: int) -> int:
    """C integer division: truncates toward zero."""
    q = abs(a) // abs(b)
    return q if (a < 0) == (b < 0) else -q


def _max_index(table) -> int:
    best, best_i = -123456, -1
    for i, v in enumerate(table):
        if v >= best:
            best, best_i = v, i
    return best_i


def _min_index(table) -> int:
    best, best_i = 123456, -1
    for i, v in enumerate(table):
        if v <= best:
            best, best_i = v, i
    return best_i


def _zeros(*dims):
    if len(dims) == 1:
        return [0] * dims[0]
    return [_zeros(*dims[1:]) for _ in range(dims[0])]


class Greenberg:
    name = "greenberg"

    def __init__(self):
        self.my = [0]  # 1-based; element 0 is the number of rounds played (the C's T)
        self.opp = [0]
        self.my_hash = [[0] for _ in range(4)]
        self.opp_hash = [[0] for _ in range(4)]
        self.gear = [[] for _ in range(24)]
        self.freq = _zeros(2, 3)
        self.p_full = _zeros(24, 4)
        self.p_freq = _zeros(2, 2)
        self.p_random = 0
        self.r_full = _zeros(24, 2)
        self.r_freq = _zeros(2, 2)
        self.p_len = _zeros(6)
        self._init()

    def _init(self) -> None:
        self.p_random_score = 0
        self.p_full_score = _zeros(50, 24, 4, 3)
        self.p_freq_score = _zeros(50, 2, 2, 3)
        self.r_full_score = _zeros(50, 24, 2, 3)
        self.r_freq_score = _zeros(50, 2, 2, 3)
        self.s_len = _zeros(6)

    @property
    def rounds(self) -> int:
        return self.opp[0]

    def observe(self, mine: int, theirs: int) -> None:
        self.my.append(mine)
        self.opp.append(theirs)
        self.my[0] += 1
        self.opp[0] += 1

    # ---- the C's functions, in order ---------------------------------

    def _find_best_prediction(self, length: int) -> int:
        T = self.opp[0]
        cur, old = T % 50, (50 + T - length) % 50
        bs, bp = -(1 << 30), 0
        if self.p_random_score > bs:
            bs, bp = self.p_random_score, self.p_random
        pfs, rfs, pqs, rqs = self.p_full_score, self.r_full_score, self.p_freq_score, self.r_freq_score
        for i in range(3):
            for j in range(24):
                for k in range(4):
                    v = pfs[cur][j][k][i] - (pfs[old][j][k][i] if length else 0)
                    if v > bs:
                        bs, bp = v, (self.p_full[j][k] + i) % 3
                for k in range(2):
                    v = rfs[cur][j][k][i] - (rfs[old][j][k][i] if length else 0)
                    if v > bs:
                        bs, bp = v, (self.r_full[j][k] + i) % 3
            for j in range(2):
                for k in range(2):
                    v = pqs[cur][j][k][i] - (pqs[old][j][k][i] if length else 0)
                    if v > bs:
                        bs, bp = v, (self.p_freq[j][k] + i) % 3
                    v = rqs[cur][j][k][i] - (rqs[old][j][k][i] if length else 0)
                    if v > bs:
                        bs, bp = v, (self.r_freq[j][k] + i) % 3
        return bp

    def _update_scores(self) -> None:
        T = self.opp[0]
        theirs = self.opp[T]
        cur, prev = T % 50, (T + 49) % 50
        self.p_random_score += _SCORE[self.p_random][theirs]
        for i in range(3):
            for j in range(24):
                for k in range(4):
                    self.p_full_score[cur][j][k][i] = (
                        self.p_full_score[prev][j][k][i] + _SCORE[(self.p_full[j][k] + i) % 3][theirs]
                    )
                for k in range(2):
                    self.r_full_score[cur][j][k][i] = (
                        self.r_full_score[prev][j][k][i] + _SCORE[(self.r_full[j][k] + i) % 3][theirs]
                    )
            for j in range(2):
                for k in range(2):
                    self.p_freq_score[cur][j][k][i] = (
                        self.p_freq_score[prev][j][k][i] + _SCORE[(self.p_freq[j][k] + i) % 3][theirs]
                    )
                    self.r_freq_score[cur][j][k][i] = (
                        self.r_freq_score[prev][j][k][i] + _SCORE[(self.r_freq[j][k] + i) % 3][theirs]
                    )
        for i in range(6):
            self.s_len[i] += _SCORE[self.p_len[i]][theirs]

    def _update_history_hash(self) -> None:
        T = self.opp[0]
        if T == 0:
            return
        my, opp = self.my, self.opp
        self.my_hash[0].append(my[T])
        self.opp_hash[0].append(opp[T])
        for i in range(1, 4):
            self.my_hash[i].append(self.my_hash[i - 1][T - 1] * 3 + my[T])
            self.opp_hash[i].append(self.opp_hash[i - 1][T - 1] * 3 + opp[T])

    def _make_predictions(self, p_random: int) -> None:
        T = self.opp[0]
        my, opp = self.my, self.opp
        self.p_random = p_random

        for i in range(24):
            g = (3 + opp[T] - self.p_full[i][2]) % 3
            if T > 1:
                g += 3 * self.gear[i][T - 1]
            self.gear[i].append(g % 9)

        value = _zeros(2, 3)
        if T == 0:
            self.freq = _zeros(2, 3)
        else:
            self.freq[0][my[T]] += 1
            self.freq[1][opp[T]] += 1
            for i in range(2):
                f = self.freq[i]
                value[i][0] = _cdiv(1000 * (f[2] - f[1]), T)
                value[i][1] = _cdiv(1000 * (f[0] - f[2]), T)
                value[i][2] = _cdiv(1000 * (f[1] - f[0]), T)

        for i in range(2):
            self.p_freq[i][0] = _WINS_WITH[_max_index(self.freq[i])]
            self.p_freq[i][1] = _WINS_WITH[_max_index(value[i])]
            self.r_freq[i][0] = _BEST_WITHOUT[_min_index(self.freq[i])]
            self.r_freq[i][1] = _BEST_WITHOUT[_min_index(value[i])]

        f = _zeros(3, 2, 4, 3)
        t = _zeros(3, 2, 4)
        m_len = _zeros(3, T + 1)
        mh, oh = self.my_hash, self.opp_hash
        for i in range(T - 1, 0, -1):
            m_len[0][i] = 4
            for j in range(4):
                if mh[j][i] != mh[j][T]:
                    m_len[0][i] = j
                    break
            m_len[1][i] = 4
            for j in range(4):
                if oh[j][i] != oh[j][T]:
                    m_len[1][i] = j
                    break
            m_len[2][i] = 4
            for j in range(4):
                if mh[j][i] != mh[j][T] or oh[j][i] != oh[j][T]:
                    m_len[2][i] = j
                    break

        p_full, r_full = self.p_full, self.r_full
        for i in range(T - 1, 0, -1):
            nxt_my, nxt_opp = my[i + 1], opp[i + 1]
            for j in range(3):
                for k in range(m_len[j][i]):
                    f[j][0][k][nxt_my] += 1
                    t[j][0][k] += 1
                    f[j][1][k][nxt_opp] += 1
                    t[j][1][k] += 1
                    if t[j][0][k] == 1:
                        p_full[j * 8 + k][0] = _WINS_WITH[nxt_my]
                    if t[j][1][k] == 1:
                        p_full[j * 8 + 4 + k][0] = _WINS_WITH[nxt_opp]
                    if t[j][0][k] == 3:
                        p_full[j * 8 + k][1] = _WINS_WITH[_max_index(f[j][0][k])]
                        r_full[j * 8 + k][0] = _BEST_WITHOUT[_min_index(f[j][0][k])]
                    if t[j][1][k] == 3:
                        p_full[j * 8 + 4 + k][1] = _WINS_WITH[_max_index(f[j][1][k])]
                        r_full[j * 8 + 4 + k][0] = _BEST_WITHOUT[_min_index(f[j][1][k])]

        for j in range(3):
            for k in range(4):
                p_full[j * 8 + k][2] = _WINS_WITH[_max_index(f[j][0][k])]
                r_full[j * 8 + k][1] = _BEST_WITHOUT[_min_index(f[j][0][k])]
                p_full[j * 8 + 4 + k][2] = _WINS_WITH[_max_index(f[j][1][k])]
                r_full[j * 8 + 4 + k][1] = _BEST_WITHOUT[_min_index(f[j][1][k])]

        for j in range(24):
            gear_freq = _zeros(9)
            gj = self.gear[j]
            for i in range(T - 1, 0, -1):
                if gj[i] == gj[T]:
                    gear_freq[gj[i + 1]] += 1
            p_full[j][3] = (p_full[j][1] + _max_index(gear_freq)) % 3

    # ---- play ----------------------------------------------------------

    def move(self, guess: int) -> int:
        """The bot's play, given one uniformly random move `guess` for its own use."""
        if self.opp[0] == 0:
            self._init()
        else:
            self._update_scores()
        self._update_history_hash()
        self._make_predictions(guess)
        self.p_len = [self._find_best_prediction(length) for length in _LENGTHS]
        return self.p_len[_max_index(self.s_len)]
