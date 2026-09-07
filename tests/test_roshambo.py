import random
import unittest

from roshambo import Bot, beats, outcome, parse
from roshambo.core import rotate
from roshambo.gotcha import Gotcha, GotchaTable, best_response, gotcha_predictors
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
    @staticmethod
    def played(rounds, **kw):
        t = GotchaTable(**kw)
        me, opp = [], []
        for mine, theirs in rounds:
            me.append(mine)
            opp.append(theirs)
            t.observe(me, opp)
        return t

    def test_history_and_suffixes(self):
        t = self.played([(1, 2), (0, 1), (0, 0), (2, 2)])
        self.assertEqual(t.history, "psrprrss")
        self.assertEqual(t.rounds, 4)
        self.assertEqual(t.suffixes(), ["", "ss", "rrss", "rprrss", "psrprrss"])
        self.assertIsNone(t.suffix(5))

    def test_table_counts_what_followed_each_suffix(self):
        # rounds: rs, rp, rs, rp  -> after "rs" the opponent played p twice
        t = self.played([(0, 2), (0, 1), (0, 2), (0, 1)])
        self.assertEqual(t.table[""], [0, 2, 2])
        self.assertEqual(t.table["rs"], [0, 2, 0])
        self.assertEqual(t.table["rp"], [0, 0, 1])
        self.assertEqual(t.table["rsrp"], [0, 0, 1])
        self.assertEqual(t.table["rprs"], [0, 1, 0])
        self.assertEqual(t.table["rsrprs"], [0, 1, 0])
        self.assertNotIn("rsrprsrp", t.table)  # the full history has no follower yet
        self.assertEqual(t.counts()[0], ("", [0, 2, 2]))
        self.assertEqual(t.counts()[1], ("rp", [0, 0, 1]))
        self.assertEqual(t.counts()[-1], ("rsrprsrp", [0, 0, 0]))

    def test_observe_is_idempotent_per_round(self):
        t = GotchaTable()
        me, opp = [0, 0], [2, 1]
        t.observe(me[:1], opp[:1])
        t.observe(me, opp)
        t.observe(me, opp)  # a second depth predictor reporting the same round
        self.assertEqual(t.rounds, 2)
        self.assertEqual(t.table[""], [0, 1, 1])

    def test_max_rounds_caps_suffix_length(self):
        t = self.played([(0, 2), (0, 1), (0, 2), (0, 1)], max_rounds=2)
        self.assertEqual(t.suffixes(), ["", "rp", "rsrp"])
        self.assertEqual(t.table["rprs"], [0, 1, 0])
        self.assertNotIn("rsrprs", t.table)

    def test_empty(self):
        t = GotchaTable()
        self.assertEqual(t.suffixes(), [""])
        self.assertEqual(t.counts(), [("", [0, 0, 0])])

    def test_best_response(self):
        R, P, S = 0, 1, 2
        self.assertIsNone(best_response([0, 0, 0]))
        self.assertEqual(best_response([0, 3, 0]), S)   # they play paper: cut it
        self.assertEqual(best_response([4, 3, 0]), P)   # mostly rock, some paper: paper
        self.assertEqual(best_response([4, 0, 3]), R)   # rock beats scissors, ties rock, never loses
        self.assertEqual(best_response([1, 1, 1]), R)   # all equal: lowest index

    def test_depth_predictors_share_one_table(self):
        preds = gotcha_predictors(max_rounds=3)
        self.assertEqual([p.name for p in preds], ["gotcha0", "gotcha1", "gotcha2", "gotcha3"])
        self.assertTrue(all(p.table is preds[0].table for p in preds))
        me, opp = [], []
        for mine, theirs in [(0, 1), (0, 1), (0, 1)]:  # opponent always paper
            me.append(mine)
            opp.append(theirs)
            for p in preds:
                p.observe(me, opp)
        self.assertEqual(preds[0].table.table[""], [0, 3, 0])
        self.assertEqual(preds[0].response(), 2)   # best response is scissors
        self.assertEqual(preds[0].predict(me, opp), 1)  # expressed as "they play paper"
        self.assertEqual(preds[1].response(), 2)   # "rp" seen twice, followed by paper
        self.assertIsNone(preds[3].response())     # "rprprp" has never been followed
