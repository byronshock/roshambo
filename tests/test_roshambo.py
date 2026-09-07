import random
import statistics
import unittest

from roshambo import Bot, beats, outcome, parse
from roshambo.classic import Greenberg, Iocaine
from roshambo.core import rotate
from roshambo.gotcha import GotchaTable, gotcha_predictors
from roshambo.opponents import ALL
from roshambo.simulate import play_match, summarize
from roshambo import tournament


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

    def test_table_counts_start_at_one_and_count_what_followed(self):
        # rounds: rs, rp, rs, rp  -> after "rs" the opponent played p twice
        t = self.played([(0, 2), (0, 1), (0, 2), (0, 1)])
        self.assertEqual(t.table[""], [1, 3, 3])
        self.assertEqual(t.table["rs"], [1, 3, 1])
        self.assertEqual(t.table["rp"], [1, 1, 2])
        self.assertEqual(t.table["rsrp"], [1, 1, 2])
        self.assertEqual(t.table["rprs"], [1, 2, 1])
        self.assertEqual(t.table["rsrprs"], [1, 2, 1])
        self.assertNotIn("rsrprsrp", t.table)  # the full history has no follower yet

    def test_observe_is_idempotent_per_round(self):
        t = GotchaTable()
        me, opp = [0, 0], [2, 1]
        t.observe(me[:1], opp[:1])
        t.observe(me, opp)
        t.observe(me, opp)  # a second depth predictor reporting the same round
        self.assertEqual(t.rounds, 2)
        self.assertEqual(t.table[""], [1, 2, 2])

    def test_max_rounds_caps_suffix_length(self):
        t = self.played([(0, 2), (0, 1), (0, 2), (0, 1)], max_rounds=2)
        self.assertEqual(t.suffixes(), ["", "rp", "rsrp"])
        self.assertEqual(t.table["rprs"], [1, 2, 1])
        self.assertNotIn("rsrprs", t.table)

    def test_empty(self):
        t = GotchaTable()
        self.assertEqual(t.suffixes(), [""])
        self.assertIsNone(t.estimate(0))

    def test_estimate_is_add_one_smoothed(self):
        t = self.played([(0, 1)] * 3)  # opponent: paper x3
        self.assertEqual(t.estimate(0), [1 / 6, 4 / 6, 1 / 6])
        self.assertEqual(t.estimate(1), [1 / 5, 3 / 5, 1 / 5])  # "rp" followed by paper twice
        self.assertIsNone(t.estimate(3))  # "rprprp" has never been followed
        self.assertIsNone(t.estimate(4))  # game too short

    def test_depth_predictors_probability_match(self):
        preds = gotcha_predictors(max_rounds=3, seed=1)
        self.assertEqual([p.name for p in preds], ["gotcha0", "gotcha1", "gotcha2", "gotcha3"])
        self.assertTrue(all(p.table is preds[0].table for p in preds))
        me, opp = [], []
        for mine, theirs in [(0, 1)] * 3:  # opponent always paper
            me.append(mine)
            opp.append(theirs)
            for p in preds:
                p.observe(me, opp)
        draws = [preds[0].predict(me, opp) for _ in range(6000)]
        self.assertAlmostEqual(draws.count(1) / 6000, 4 / 6, delta=0.03)  # paper_hat
        self.assertAlmostEqual(draws.count(0) / 6000, 1 / 6, delta=0.03)  # rock_hat
        self.assertIsNone(preds[3].predict(me, opp))  # "rprprp" unseen: no entry, no draw


class ClassicBotTests(unittest.TestCase):
    """The ports are verified move-for-move against the C originals by
    tools/verify_classic/verify.py; these are cheap behavioural checks."""

    @staticmethod
    def play(cls, opponent, rounds, seed=0):
        bot, rng, wins = cls(), random.Random(seed), 0
        me, opp = [], []
        for _ in range(rounds):
            mine = bot.move(rng.randrange(3))
            theirs = opponent(opp, me, rng)
            bot.observe(mine, theirs)
            me.append(mine)
            opp.append(theirs)
            wins += (mine - theirs) % 3 == 1
        return wins / rounds

    def test_ports_exploit_simple_patterns(self):
        for cls in (Iocaine, Greenberg):
            for name in ("cycle", "beat_last", "wsls"):
                with self.subTest(bot=cls.__name__, opponent=name):
                    self.assertGreater(self.play(cls, ALL[name](), 300), 0.85)

    def test_ports_are_deterministic_given_guesses(self):
        for cls in (Iocaine, Greenberg):
            a = [self.play(cls, ALL["uniform"](), 100, seed=4) for _ in range(2)]
            self.assertEqual(a[0], a[1])

    def test_ports_register_as_opponents(self):
        for name in ("iocaine", "greenberg"):
            bot = play_match(ALL[name](), 60, seed=2)
            self.assertEqual(bot.rounds, 60)


class TournamentTests(unittest.TestCase):
    def test_crosstable_is_antisymmetric_and_ranks(self):
        names = ("bot", "wsls", "uniform")
        results = tournament.crosstable(names, rounds=150, seeds=2)
        for a in names:
            for b in names:
                if a != b:
                    self.assertEqual(len(results[(a, b)]), 2)
                    self.assertEqual(results[(a, b)], [-m for m in results[(b, a)]])
        self.assertGreater(statistics.fmean(results[("bot", "wsls")]), 0.8)
        text = tournament.report(names, results, 150, 2)
        self.assertTrue(text.splitlines()[3].startswith("bot"))  # ranked first

    def test_parallel_matches_serial(self):
        names = ("bot", "iocaine", "uniform")
        serial = tournament.crosstable(names, rounds=120, seeds=2, jobs=1)
        parallel = tournament.crosstable(names, rounds=120, seeds=2, jobs=3)
        self.assertEqual(serial, parallel)

    def test_every_entrant_constructs_and_plays(self):
        for name, make in tournament.ENTRANTS.items():
            with self.subTest(name):
                m = tournament.play(make(1), tournament.ENTRANTS["uniform"](2), 20, seed=0)
                self.assertTrue(-1 <= m <= 1)
