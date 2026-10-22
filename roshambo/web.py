"""The web game: play the bot in a browser. `python3 -m roshambo.web`.

Standard library only. Each game is one bot, held in this process's memory
under a random id that the page keeps in a JavaScript variable, never in a
cookie or browser storage, so reloading the page starts a new game, and so
does restarting the server.

  GET  /, /play.css, /play.js   the page
  POST /api/play                {"game": id or null, "move": "r" | "p" | "s"}

A play without a game id, or with one this server no longer holds, starts a
new game, and the reply says so ("new": true). The bot chooses its move from
the history alone, before it reads yours, exactly as `python3 -m roshambo`
does. The reply reports the round from the player's side:

  {"game": id, "round": 7, "you": "rock", "bot": "paper", "result": "lose",
   "score": {"you": 2, "ties": 1, "bot": 4}, "new": false, "over": false}

Memory is bounded three ways: a game ends after MAX_ROUNDS ("over": true),
one idle for IDLE_SECONDS is dropped, and when MAX_GAMES are live the least
recently played is dropped to make room. In production this runs behind
Caddy (deploy/roshambo.caddy), which adds TLS; the security headers are set
here, so the page behaves the same locally.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import sys
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable

from .bot import Bot, make_bot
from .core import NAMES, parse
from .experts import DEFAULT_LINEUP

MAX_ROUNDS = 1000  # a bot holds about 1.2 KB per round at worst, so ~1.4 MB a game
MAX_GAMES = 500
IDLE_SECONDS = 30 * 60
MAX_BODY = 1024

STATIC = Path(__file__).with_name("static")
PAGES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/play.css": ("play.css", "text/css; charset=utf-8"),
    "/play.js": ("play.js", "text/javascript; charset=utf-8"),
}

# Nothing is loaded from anywhere but this host, the page talks only to this
# host, and no other site may frame it. no-transform keeps Cloudflare from
# adding anything on the way.
HEADERS = {
    "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self'; "
    "connect-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
    "magnetometer=(), microphone=(), payment=(), usb=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "X-Frame-Options": "DENY",
}

RESULT = {1: "lose", 0: "tie", -1: "win"}  # the bot's outcome, as the player sees it


@dataclass
class Game:
    bot: Bot
    seen: float
    lock: threading.Lock = field(default_factory=threading.Lock)


class Games:
    """The live games, least recently played first."""

    def __init__(
        self,
        lineup: str = DEFAULT_LINEUP,
        max_games: int = MAX_GAMES,
        idle_seconds: float = IDLE_SECONDS,
        max_rounds: int = MAX_ROUNDS,
        seed: int | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.lineup, self.max_games, self.idle_seconds = lineup, max_games, idle_seconds
        self.max_rounds, self.clock = max_rounds, clock
        # With a seed (tests), game n gets seed + n; without, every bot seeds itself from the OS.
        self._seed, self._made = seed, 0
        self._games: OrderedDict[str, Game] = OrderedDict()
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._games)

    def _get_or_start(self, game_id: str | None) -> tuple[str, Game, bool]:
        with self._lock:
            now = self.clock()
            while self._games:
                oldest = next(iter(self._games.values()))
                if now - oldest.seen < self.idle_seconds:
                    break
                self._games.popitem(last=False)
            game = self._games.get(game_id) if game_id else None
            if game is not None:
                self._games.move_to_end(game_id)
                game.seen = now
                return game_id, game, False
            while len(self._games) >= self.max_games:
                self._games.popitem(last=False)
            seed = None if self._seed is None else self._seed + self._made
            self._made += 1
            game_id = secrets.token_urlsafe(16)
            game = self._games[game_id] = Game(make_bot(self.lineup, seed=seed), now)
            return game_id, game, True

    def play(self, game_id: str | None, move: int) -> dict:
        game_id, game, new = self._get_or_start(game_id)
        with game.lock:
            bot = game.bot
            mine = bot.move()
            result = bot.observe(move)
            over = bot.rounds >= self.max_rounds
            reply = {
                "game": game_id,
                "round": bot.rounds,
                "you": NAMES[move],
                "bot": NAMES[mine],
                "result": RESULT[result],
                "score": {"you": bot.losses, "ties": bot.ties, "bot": bot.wins},
                "new": new,
                "over": over,
            }
        if over:
            with self._lock:
                self._games.pop(game_id, None)
        return reply


class Handler(BaseHTTPRequestHandler):
    server_version = "roshambo"
    sys_version = ""
    timeout = 15
    games: Games  # set by make_server
    pages: dict[str, tuple[bytes, str, str]]

    def log_message(self, format, *args):  # no access log: visits aren't recorded
        pass

    def do_GET(self):
        self._page(head=False)

    def do_HEAD(self):
        self._page(head=True)

    def _page(self, head: bool):
        page = self.pages.get(self.path.split("?", 1)[0])
        if page is None:
            return self._json(404, {"error": "not found"}, head=head)
        body, ctype, etag = page
        if self.headers.get("If-None-Match") == etag:
            return self._reply(304, b"", ctype, "no-cache, no-transform", {"ETag": etag})
        self._reply(200, b"" if head else body, ctype, "no-cache, no-transform", {"ETag": etag},
                    length=len(body))

    def do_POST(self):
        if self.path != "/api/play":
            return self._json(404, {"error": "not found"})
        if self.headers.get_content_type() != "application/json":
            return self._json(415, {"error": "send JSON"})
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            return self._json(411, {"error": "length required"})
        if not 0 <= length <= MAX_BODY:
            return self._json(413, {"error": "too large"})
        try:
            data = json.loads(self.rfile.read(length))
        except ValueError:
            return self._json(400, {"error": "not JSON"})
        if not isinstance(data, dict):
            return self._json(400, {"error": "send an object"})
        move, game_id = data.get("move"), data.get("game")
        move = parse(move) if isinstance(move, str) and len(move) <= 8 else None
        if move is None:
            return self._json(400, {"error": "move must be r, p or s"})
        if game_id is not None and not (isinstance(game_id, str) and len(game_id) <= 64):
            return self._json(400, {"error": "bad game id"})
        self._json(200, self.games.play(game_id, move))

    def _json(self, status: int, data: dict, head: bool = False):
        body = json.dumps(data).encode()
        self._reply(status, b"" if head else body, "application/json", "no-store, no-transform",
                    length=len(body))

    def _reply(self, status, body, ctype, cache, extra=None, length=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", cache)
        for name, value in {**HEADERS, **(extra or {})}.items():
            self.send_header(name, value)
        if status != 304:
            self.send_header("Content-Length", str(len(body) if length is None else length))
        self.end_headers()
        self.wfile.write(body)


def make_server(host: str = "127.0.0.1", port: int = 8777, games: Games | None = None) -> ThreadingHTTPServer:
    pages = {}
    for path, (name, ctype) in PAGES.items():
        body = (STATIC / name).read_bytes()
        pages[path] = (body, ctype, '"%s"' % hashlib.sha256(body).hexdigest()[:16])
    handler = type("BoundHandler", (Handler,), {"games": games or Games(), "pages": pages})
    return ThreadingHTTPServer((host, port), handler)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="roshambo.web", description="Serve the web game.")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8777)
    args = ap.parse_args(argv)
    server = make_server(args.host, args.port)
    print(f"roshambo: http://{args.host}:{args.port}/", file=sys.stderr, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
