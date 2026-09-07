"""Check the Python ports of Iocaine Powder and Greenberg against the C originals.

Fetches the two C sources (they are not redistributed here), applies the one
fix Greenberg needs to be well-defined (its gear_freq array is indexed by a
nine-valued gear but declared with three slots), builds harness.c, then
plays both C bots and both ports through the same scripted guesses and
opponents and diffs the moves.

    python3 tools/verify_classic/verify.py
"""
from __future__ import annotations

import random
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from roshambo.classic import Greenberg, Iocaine  # noqa: E402

SOURCES = {
    "iocaine.c": (
        "http://web.archive.org/web/2010id_/http://ofb.net/~egnor/iocaine.c",
        "http://web.archive.org/web/2010/http://ofb.net/~egnor/iocaine.c",
    ),
    "greenberg.c": ("http://www.mathpuzzle.com/greenberg.c",),
}
ROUNDS = 1000


def fetch(build: Path) -> None:
    for name, urls in SOURCES.items():
        path = build / name
        if path.exists():
            continue
        for url in urls:
            print(f"fetching {url}")
            try:
                urllib.request.urlretrieve(url, path)
                break
            except urllib.error.HTTPError as e:
                print(f"  {e}")
        else:
            sys.exit(f"could not fetch {name}; place a copy in {build}")
    fixed = build / "greenberg_fixed.c"
    src = (build / "greenberg.c").read_text()
    assert "int gear_freq[3];" in src and "find_max_index(gear_freq,3)" in src
    fixed.write_text(
        src.replace("int gear_freq[3];", "int gear_freq[9];")
        .replace("for (i = 0; i < 3; i++) gear_freq[i] = 0;", "for (i = 0; i < 9; i++) gear_freq[i] = 0;")
        .replace("find_max_index(gear_freq,3)", "find_max_index(gear_freq,9)")
    )


def opponents(seed: int) -> dict[str, list[int]]:
    rng = random.Random(seed)
    return {
        "uniform": [rng.randrange(3) for _ in range(ROUNDS)],
        "cycle": [t % 3 for t in range(ROUNDS)],
        "biased": rng.choices(range(3), weights=(5, 3, 2), k=ROUNDS),
        "blocks": [(t // 37 + t // 5) % 3 for t in range(ROUNDS)],
        "constant": [1] * ROUNDS,
        "pattern": [(t * t + t // 7) % 3 for t in range(ROUNDS)],
    }


def run_c(exe: Path, bot: str, guesses: Path, opp: Path) -> list[int]:
    out = subprocess.run([str(exe), bot, str(guesses), str(opp)], check=True, capture_output=True, text=True)
    return [int(x) for x in out.stdout.split()]


def run_py(cls, guesses: list[int], opp: list[int]) -> list[int]:
    bot, moves = cls(), []
    for g, o in zip(guesses, opp):
        m = bot.move(g)
        bot.observe(m, o)
        moves.append(m)
    return moves


def main() -> int:
    build = HERE / "build"
    build.mkdir(exist_ok=True)
    fetch(build)
    exe = build / "harness"
    subprocess.run(["gcc", "-O1", "-w", "-o", str(exe), str(HERE / "harness.c"), "-I", str(build)], check=True)

    failures = 0
    for seed in (1, 2, 3):
        guesses = [random.Random(1000 + seed).randrange(3) for _ in range(ROUNDS)]
        gpath = build / f"guesses{seed}.txt"
        gpath.write_text("\n".join(map(str, guesses)))
        for oname, opp in opponents(seed).items():
            opath = build / f"opp_{oname}{seed}.txt"
            opath.write_text("\n".join(map(str, opp)))
            for bot, cls in (("iocaine", Iocaine), ("greenberg", Greenberg)):
                c_moves = run_c(exe, bot, gpath, opath)
                py_moves = run_py(cls, guesses, opp)
                first = next((i for i, (a, b) in enumerate(zip(c_moves, py_moves)) if a != b), None)
                ok = first is None and len(c_moves) == len(py_moves) == ROUNDS
                wins = sum((m - o) % 3 == 1 for m, o in zip(py_moves, opp))
                status = "ok " if ok else f"DIFF at round {first}"
                print(f"seed {seed} {bot:9} vs {oname:8} {status}  port wins {wins}/{ROUNDS}")
                failures += not ok
    print("all ports match the C originals" if not failures else f"{failures} mismatching runs")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
