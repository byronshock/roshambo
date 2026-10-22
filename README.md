# roshambo

An opponent-modelling rock-paper-scissors bot. Against a truly random
opponent it wins a third of the time, as it must. Against a human it
finds the tells.

## How it works

The default bot is **gotcha**: eleven experts, one per context depth
from 0 to 10, over a shared history-matching table (see
`roshambo/gotcha.py`). Each keeps add-one smoothed counts of what the
opponent played after the last *k* rounds, draws a move from that
estimate, and plays what beats the draw. The meta-selector below chooses
which depth is reading the opponent best.

The other lineups, selectable with `--bot` and as tournament entrants,
add the machinery below: `gotcha-rot` gives gotcha the three
second-guessing rotations, `ngram` is the n-gram ensemble alone, and
`full` is both together.

- **Predictors** are n-gram tables: given the last *k* rounds (from the
  opponent's moves, the bot's own moves, or both), what came next? Depth 0
  is plain frequency. Each table exists in a never-forget and a
  fast-forget variant. Half of the tables predict the *bot's* next move
  instead, on the theory that the opponent is modelling the bot, and
  return the move the opponent would play to beat it.
- **Experts** are a predictor plus a rotation of 0, 1, or 2 steps: the
  "they know that I know" layer. Every expert keeps a decayed record of
  whether its proposal would have won, at two horizons: a fast one that
  catches a new tell in a few rounds, and a slow one that holds on to a
  steady but noisy edge through a bad streak.
- **The meta-selector** plays the proposal of whichever expert has the
  best recent record. If nothing has a positive record, the bot plays
  randomly rather than hand the opponent a pattern.

No dependencies beyond the standard library.

## Classic opponents

`roshambo/classic/` holds Python ports of the two RoShamBo tournament
winners, Dan Egnor's Iocaine Powder (1999) and Andrzej Nagorko's Greenberg
(2000), usable as opponents by name:

```bash
python3 -m roshambo --sim --rounds 1000 iocaine greenberg
```

The ports were checked move for move against the C originals; rerun that
check with `python3 tools/verify_classic/verify.py` (needs gcc and network
access to fetch the C sources, which are not redistributed here).

## Tournament

```bash
python3 -m roshambo --tournament --rounds 1000 --seeds 5
```

Round-robin crosstable between entrants: the four lineups, Iocaine
Powder, Greenberg, and scripted baselines.
Each cell is the row entrant's mean margin over the column entrant in
percentage points, with an approximate 95% interval across seeds, and
rows are ranked by average margin. Matches run in parallel across all
cores (`--jobs N` to limit). Name entrants to pick a subset:

```bash
python3 -m roshambo --tournament gotcha full iocaine greenberg --seeds 10
```

## Play it

```bash
python3 -m roshambo
```

Type `r`, `p`, or `s`. `q` quits and prints which experts read you best.

## Play it in a browser

```bash
python3 -m roshambo.web
```

Then open http://127.0.0.1:8777/ and press R, P or S, or click. The
server (`roshambo/web.py`, standard library only) keeps one gotcha bot
per game in memory, so the bot learns across rounds just as it does in
the terminal. The page keeps its game id in a JavaScript variable, not a
cookie or browser storage, so a reload starts a new game. A game ends
after 1000 rounds, and one left idle for half an hour is dropped.

It runs at https://roshambo.docshock.studio, on the server shared with
docshock.studio, behind Cloudflare and Caddy:

```bash
deploy/deploy.sh        # dry run: tests HEAD, shows every change
deploy/deploy.sh --go   # publishes HEAD
```

`deploy/roshambo-web.service` runs the game as a sandboxed systemd
service on localhost; `deploy/roshambo.caddy` is the Caddy site. Edit
both here, never on the server. A restart ends the games in progress.

## Evaluate it

```bash
python3 -m roshambo --sim --rounds 2000
```

```bash
python3 -m unittest discover -s tests
```
