import json
import re
import threading
import unittest
import urllib.error
import urllib.request

from roshambo.web import Games, make_server


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class GamesTests(unittest.TestCase):
    def test_the_bot_learns_within_a_game(self):
        games = Games(seed=0)
        game = None
        for _ in range(100):
            reply = games.play(game, 0)  # always rock
            game = reply["game"]
        self.assertEqual(reply["round"], 100)
        self.assertGreater(reply["score"]["bot"], 80)

    def test_score_is_from_the_players_side(self):
        games = Games(seed=0)
        game = None
        for _ in range(30):
            reply = games.play(game, 0)
            game = reply["game"]
            expected = {"rock": "tie", "paper": "lose", "scissors": "win"}[reply["bot"]]
            self.assertEqual(reply["you"], "rock")
            self.assertEqual(reply["result"], expected)
        self.assertEqual(sum(reply["score"].values()), 30)

    def test_games_are_independent(self):
        games = Games(seed=0)
        a = games.play(None, 0)
        b = games.play(None, 0)
        self.assertNotEqual(a["game"], b["game"])
        for _ in range(5):
            a = games.play(a["game"], 0)
        self.assertEqual(games.play(b["game"], 0)["round"], 2)
        self.assertEqual(a["round"], 6)

    def test_unknown_game_starts_a_new_one(self):
        games = Games(seed=0)
        reply = games.play("no-such-game", 1)
        self.assertTrue(reply["new"])
        self.assertEqual(reply["round"], 1)
        self.assertFalse(games.play(reply["game"], 1)["new"])

    def test_a_game_ends_at_max_rounds(self):
        games = Games(seed=0, max_rounds=5)
        game = None
        for n in range(1, 6):
            reply = games.play(game, 2)
            game = reply["game"]
            self.assertEqual(reply["over"], n == 5)
        self.assertEqual(len(games), 0)
        self.assertTrue(games.play(game, 2)["new"])

    def test_idle_games_are_dropped(self):
        clock = Clock()
        games = Games(seed=0, idle_seconds=60, clock=clock)
        old = games.play(None, 0)["game"]
        clock.now = 30
        kept = games.play(None, 0)["game"]
        clock.now = 61
        self.assertTrue(games.play(old, 0)["new"])
        self.assertFalse(games.play(kept, 0)["new"])

    def test_the_least_recently_played_game_makes_room(self):
        games = Games(seed=0, max_games=2)
        a = games.play(None, 0)["game"]
        b = games.play(None, 0)["game"]
        games.play(a, 0)  # now b is the least recent
        games.play(None, 0)
        self.assertEqual(len(games), 2)
        self.assertFalse(games.play(a, 0)["new"])
        self.assertTrue(games.play(b, 0)["new"])

    def test_concurrent_plays_on_one_game(self):
        games = Games(seed=0)
        game = games.play(None, 0)["game"]
        errors = []

        def hammer():
            try:
                for _ in range(50):
                    games.play(game, 1)
            except Exception as e:  # pragma: no cover - reported below
                errors.append(e)

        threads = [threading.Thread(target=hammer) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(games.play(game, 1)["round"], 1 + 8 * 50 + 1)


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server("127.0.0.1", 0, Games(seed=0))
        cls.base = "http://127.0.0.1:%d" % cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def request(self, path, body=None, ctype="application/json", headers=None):
        data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, headers=dict(headers or {}))
        if data is not None:
            req.add_header("Content-Type", ctype)
        try:
            with urllib.request.urlopen(req) as res:
                return res.status, res.headers, res.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    def test_page_and_assets(self):
        for path, ctype in (("/", "text/html"), ("/play.css", "text/css"), ("/play.js", "text/javascript")):
            status, headers, body = self.request(path)
            self.assertEqual(status, 200, path)
            self.assertTrue(headers["Content-Type"].startswith(ctype), path)
            self.assertIn("no-transform", headers["Cache-Control"])
            self.assertIn("default-src 'none'", headers["Content-Security-Policy"])
            self.assertTrue(body)

    def test_page_has_nothing_inline_for_the_policy_to_refuse(self):
        html = self.request("/")[2].decode()
        self.assertNotRegex(html, r"<style|style=|<script(?![^>]*\bsrc=)|\bon[a-z]+=")
        for ref in re.findall(r'(?:src|href)="([^"]+)"', html):
            self.assertTrue(ref.startswith("/") and not ref.startswith("//"), ref)
            self.assertEqual(self.request(ref)[0], 200, ref)

    def test_unchanged_assets_are_not_resent(self):
        etag = self.request("/play.js")[1]["ETag"]
        status, _, body = self.request("/play.js", headers={"If-None-Match": etag})
        self.assertEqual((status, body), (304, b""))

    def test_unknown_path(self):
        self.assertEqual(self.request("/nope")[0], 404)
        self.assertEqual(self.request("/api/nope", {"move": "r"})[0], 404)

    def test_a_game_over_http(self):
        status, headers, body = self.request("/api/play", {"game": None, "move": "r"})
        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], "no-store, no-transform")
        first = json.loads(body)
        self.assertTrue(first["new"])
        second = json.loads(self.request("/api/play", {"game": first["game"], "move": "rock"})[2])
        self.assertEqual((second["game"], second["round"], second["new"]), (first["game"], 2, False))

    def test_bad_requests(self):
        cases = [
            ({"move": "x"}, "application/json", 400),
            ({"move": 1}, "application/json", 400),
            ({"move": ""}, "application/json", 400),
            ({"move": "r", "game": 5}, "application/json", 400),
            (["r"], "application/json", 400),
            (b"{not json", "application/json", 400),
            ({"move": "r"}, "text/plain", 415),
            (json.dumps({"move": "r", "pad": "x" * 2000}).encode(), "application/json", 413),
        ]
        for body, ctype, expected in cases:
            status, _, reply = self.request("/api/play", body, ctype)
            self.assertEqual(status, expected, body)
            self.assertIn("error", json.loads(reply))


if __name__ == "__main__":
    unittest.main()
