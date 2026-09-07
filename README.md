# roshambo

An opponent-modelling rock-paper-scissors bot. Against a truly random
opponent it wins a third of the time, as it must. Against a human it
finds the tells.

## How it works

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

## Play it

```bash
python3 -m roshambo
```

Type `r`, `p`, or `s`. `q` quits and prints which experts read you best.

## Evaluate it

```bash
python3 -m roshambo --sim --rounds 2000
```

```bash
python3 -m unittest discover -s tests
```
