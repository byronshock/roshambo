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

    def test_estimate_backs_off_to_shorter_depth(self):
        t = self.played([(0, 1), (0, 1), (0, 1)], pseudo_count=1.0)  # opponent: paper x3
        self.assertIsNone(t.estimate(4))  # game too short
        e0 = t.estimate(0)  # (0,3,0) smoothed toward uniform with weight 1
        self.assertEqual([round(x, 4) for x in e0], [0.0833, 0.8333, 0.0833])
        self.assertAlmostEqual(sum(e0), 1.0)
        # "rp" was followed by paper twice, smoothed toward e0
        self.assertEqual([round(x, 4) for x in t.estimate(1)], [0.0278, 0.9444, 0.0278])
        # "rprp" was followed by paper once, smoothed toward depth 1
        e2 = t.estimate(2)
        self.assertEqual([round(x, 4) for x in e2], [0.0139, 0.9722, 0.0139])
        # "rprprp" has never been followed: pure prior, so identical to depth 2
        self.assertEqual(t.estimate(3), e2)
        self.assertIsNone(GotchaTable().estimate(0))

    def test_smoothing_breaks_ties_from_context(self):
        # Overall the opponent leans paper, but after "rs" it's one rock, one scissors.
        t = self.played([(0, 1)] * 8 + [(0, 2), (0, 0), (0, 2), (0, 2)], pseudo_count=4.0)
        self.assertEqual(t.table["rs"], [1, 0, 1])
        self.assertEqual(t.table[""], [1, 8, 3])
        self.assertEqual(best_response(t.table["rs"]), 0)  # raw counts: tie, falls to rock
        self.assertEqual(best_response(t.estimate(1)), 2)  # prior lean to paper: scissors

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
        self.assertEqual(preds[3].response(), 2)   # "rprprp" unseen: inherits depth 2's belief
