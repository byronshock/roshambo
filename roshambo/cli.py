"""Interactive play and simulation entry point: `python -m roshambo`."""
from __future__ import annotations

import argparse
import sys

from .bot import Bot
from .core import NAMES, parse
from .gotcha import Gotcha, best_response
from .core import SYMBOLS
from .simulate import run_all


def play(bot: Bot) -> None:
    print("Rock, paper, scissors. Type r/p/s (q to quit). The bot is watching.\n")
    gotcha = bot.predictor(Gotcha)
    table = gotcha.table if gotcha else None
    while True:
        try:
            raw = input(f"[{bot.rounds + 1}] you> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if raw.strip().lower() in ("q", "quit", "exit"):
            break
        theirs = parse(raw)
        if theirs is None:
            print("   ? enter r, p, s, or q")
            continue
        mine = bot.move()
        r = bot.observe(theirs)
        verdict = {1: "bot wins", 0: "tie", -1: "you win"}[r]
        why = f"  (via {bot.last_expert.name})" if bot.last_expert else "  (random)"
        print(f"   bot: {NAMES[mine]:8} -> {verdict}{why}")
        print(f"   score  bot {bot.wins}  you {bot.losses}  ties {bot.ties}")
        if table:
            entries = []
            for depth, (sfx, counts) in enumerate(table.counts()):
                br = best_response(table.estimate(depth))
                entries.append(f"{sfx}({','.join(map(str, counts))})>{SYMBOLS[br] if br is not None else '-'}")
            print(f"   gotcha {table.history}: {' '.join(entries)}")
    if bot.rounds:
        n = bot.rounds
        print(f"\n{n} rounds: bot {bot.wins} ({bot.wins/n:.0%})  you {bot.losses} ({bot.losses/n:.0%})  ties {bot.ties}")
        print("\nExperts that read you best:")
        for e in bot.leaderboard(8):
            print(f"  {e.score:6.2f}  {e.wins:3}W {e.losses:3}L {e.ties:3}T  {e.name}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="roshambo", description=__doc__)
    ap.add_argument("--sim", action="store_true", help="run against scripted opponents instead of playing")
    ap.add_argument("--rounds", type=int, default=1000, help="rounds per simulated match")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--epsilon", type=float, default=0.0, help="random-move rate")
    ap.add_argument("--score-decays", type=float, nargs="+", default=(0.9, 0.99),
                    help="expert score memory horizons (0-1)")
    ap.add_argument("opponents", nargs="*", help="which scripted opponents to run with --sim")
    args = ap.parse_args(argv)
    if args.sim:
        run_all(args.rounds, seed=args.seed or 0, names=args.opponents or None)
        return 0
    play(Bot(seed=args.seed, epsilon=args.epsilon, score_decays=args.score_decays))
    return 0


if __name__ == "__main__":
    sys.exit(main())
