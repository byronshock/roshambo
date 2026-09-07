"""Play the bot against scripted opponents and report win rates."""
from __future__ import annotations

import random

from .bot import Bot
from .opponents import ALL, Opponent


def play_match(opponent: Opponent, rounds: int, seed: int = 0, **bot_kwargs) -> Bot:
    bot = Bot(seed=seed, **bot_kwargs)
    rng = random.Random(seed + 1)
    for _ in range(rounds):
        mine = bot.move()
        theirs = opponent(bot.opp, bot.me, rng)
        bot.observe(theirs)
    return bot


def summarize(bot: Bot) -> tuple[float, float, float]:
    n = max(bot.rounds, 1)
    return bot.wins / n, bot.ties / n, bot.losses / n


def run_all(rounds: int = 1000, seed: int = 0, names: list[str] | None = None) -> None:
    names = names or list(ALL)
    print(f"{'opponent':16} {'win':>6} {'tie':>6} {'loss':>6}   ({rounds} rounds)")
    for name in names:
        bot = play_match(ALL[name](), rounds, seed=seed)
        w, t, l = summarize(bot)
        print(f"{name:16} {w:6.1%} {t:6.1%} {l:6.1%}")
