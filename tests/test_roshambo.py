import random
import unittest

from roshambo import Bot, beats, outcome, parse
from roshambo.core import rotate
from roshambo.gotcha import Gotcha
from roshambo.opponents import ALL
from roshambo.simulate import play_match, summarize


class CoreTests(unittest.TestCase):
    def test_beats_cycle(self):
        for m in range(3):
            self.assertEqual(outcome(beats(m), m), 1)
            self.assertEqual(outcome(m, beats(m)), -1)
            self.assertEqual(outcome(m, m), 0)
            self.assertEqual(rotate(m, 1), beats(m))
            self.assertEqual(rotate(m, 3), m)

    def test_parse(self):
        self.assertEqual([parse(x) for x in ("r", "Paper", "sc", "", "x")], [0, 1, 2, None, None])


class BotTests(unittest.TestCase):
    def test_deterministic_with_seed(self):
        a = play_match(ALL["uniform"](), 200, seed=7)
        b = play_match(ALL["uniform"](), 200, seed=7)
        self.assertEqual(a.me, b.me)

    def test_random_opponent_is_a_coin_flip(self):
        bot = play_match(ALL["uniform"](), 6000, seed=1)
        w, t, l = summarize(bot)
        for rate in (w, t, l):
            self.assertAlmostEqual(rate, 1 / 3, delta=0.03)

    def test_exploits_simple_patterns(self):
        for name in ("constant", "cycle", "beat_last", "copy_last", "wsls", "freq_exploiter"):
            with self.subTest(name):
                bot = play_match(ALL[name](), 500, seed=3)
                w, _, _ = summarize(bot)
                self.assertGreater(w, 0.85, f"{name}: win rate {w:.2f}")

    def test_exploits_bias(self):
        bot = play_match(ALL["biased"](), 3000, seed=5)
        w, _, l = summarize(bot)
        self.assertGreater(w - l, 0.15)

    def test_self_play_is_balanced(self):
        bot = play_match(ALL["self"](), 3000, seed=9)
        w, _, l = summarize(bot)
        self.assertLess(abs(w - l), 0.06)

    def test_requires_observe_between_moves(self):
        bot = Bot(seed=0)
        bot.move()
        with self.assertRaises(AssertionError):
            bot.move()


if __name__ == "__main__":
    unittest.main()


class GotchaTests(unittest.TestCase):
    def test_history_and_suffixes(self):
        g = Gotcha()
        me, opp = [], []
        for mine, theirs in [(1, 2), (0, 1), (0, 0), (2, 2)]:
            me.append(mine)
            opp.append(theirs)
            g.observe(me, opp)
        self.assertEqual(g.history, "psrprrss")
        self.assertEqual(g.rounds, 4)
        self.assertEqual(g.suffixes(), ["", "ss", "rrss", "rprrss", "psrprrss"])

    def test_table_counts_what_followed_each_suffix(self):
        g = Gotcha()
        me, opp = [], []
        # rounds: rs, rp, rs, rp  -> after "rs" the opponent played p twice
        for mine, theirs in [(0, 2), (0, 1), (0, 2), (0, 1)]:
            me.append(mine)
            opp.append(theirs)
            g.observe(me, opp)
        self.assertEqual(g.table[""], [0, 2, 2])
        self.assertEqual(g.table["rs"], [0, 2, 0])
        self.assertEqual(g.table["rp"], [0, 0, 1])
        self.assertEqual(g.table["rsrp"], [0, 0, 1])
        self.assertEqual(g.table["rprs"], [0, 1, 0])
        self.assertEqual(g.table["rsrprs"], [0, 1, 0])
        self.assertNotIn("rsrprsrp", g.table)  # the full history has no follower yet
        self.assertEqual(g.counts()[0], ("", [0, 2, 2]))
        self.assertEqual(g.counts()[1], ("rp", [0, 0, 1]))
        self.assertEqual(g.counts()[-1], ("rsrprsrp", [0, 0, 0]))

    def test_max_rounds_caps_suffix_length(self):
        g = Gotcha(max_rounds=2)
        me, opp = [0, 0, 0, 0], [2, 1, 2, 1]
        for i in range(1, 5):
            g.observe(me[:i], opp[:i])
        self.assertEqual(g.suffixes(), ["", "rp", "rsrp"])
        self.assertEqual(g.table["rprs"], [0, 1, 0])
        self.assertNotIn("rsrprs", g.table)

    def test_empty(self):
        self.assertEqual(Gotcha().suffixes(), [""])
        self.assertEqual(Gotcha().counts(), [("", [0, 0, 0])])
