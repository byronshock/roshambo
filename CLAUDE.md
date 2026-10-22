# roshambo

An opponent-modelling rock-paper-scissors bot. Pure Python 3.12 standard
library, no dependencies. `python3 -m roshambo` plays it interactively.

## Ground rules

- **Gotcha is the owner's design.** `roshambo/gotcha.py` recreates a bot
  the owner wrote years ago, rebuilt step by step from memory. Its logic
  (bot-first history string, whole-round suffix keys including the empty
  key, ten-round key cap, add-one counts, probability matching, one
  expert per depth, no rotations) is deliberate. Don't change any of it
  without asking, even when a greedier variant scores better.
- **Gotcha alone is the default bot.** The n-gram ensemble, the rotation
  layer, and the `full` combination stay available as named lineups in
  `roshambo/experts.py` for comparison, not as the default.
- **The classic ports are frozen.** `roshambo/classic/` holds Python
  ports of Iocaine Powder and Greenberg verified move for move against
  the C originals. Any behavioural change must be re-verified with
  `python3 tools/verify_classic/verify.py` (needs gcc and network).
- **Judge changes by human exploitation first, bot robustness second.**
  The tournament measures bot against bot; the original was validated
  against people. Both matter, in that order.
- **Commit only when asked.** The owner asks for commits explicitly and
  wants a descriptive message each time.

## Commands

```bash
python3 -m roshambo                            # play the default bot (gotcha)
python3 -m roshambo --bot full                 # play another lineup: gotcha-rot, ngram, full
python3 -m unittest discover -s tests          # a few seconds, must stay green
python3 -m roshambo --sim --rounds 2000        # bot vs scripted opponents
python3 -m roshambo --tournament               # crosstable, ~5 s on many cores
python3 -m roshambo --tournament gotcha full iocaine greenberg --rounds 5000 --seeds 10
python3 -m roshambo.web                        # the browser game on http://127.0.0.1:8777/
deploy/deploy.sh                               # dry run of publishing HEAD to roshambo.docshock.studio
deploy/deploy.sh --go                          # publish: only when the owner says so
```

## Invariants the tests enforce

- Against a uniform random opponent every lineup wins, ties, and loses
  one third each. Any drift is a bug.
- Self-play is balanced.
- The `full` lineup beats every simple scripted pattern above 85% within
  500 rounds; the default gotcha lineup does the same except against the
  frequency exploiter, where probability matching only partly punishes
  it.
- Tournament results are identical serial and parallel.

## Layout

- `roshambo/core.py` moves as ints mod 3; `beats(m) == (m + 1) % 3`
- `roshambo/gotcha.py` the owner's design (see above)
- `roshambo/experts.py` n-gram predictors, the `Expert` wrapper with
  per-horizon would-have-won scores, and the named `LINEUPS`
- `roshambo/bot.py` the meta-selector; `make_bot(lineup, seed)`
- `roshambo/opponents.py` scripted opponents, keyed by name in `ALL`
- `roshambo/tournament.py` round-robin crosstable, parallel by default
- `roshambo/classic/` Iocaine Powder and Greenberg ports
- `roshambo/web.py` the browser game: one default-lineup bot per game,
  in memory; page in `roshambo/static/` (no inline script or style,
  the CSP forbids it)
- `deploy/` the systemd unit, Caddy site and deploy script for
  roshambo.docshock.studio, on the shared server (`ssh tff`) behind
  Cloudflare; the server's baseline lives in the purelyfreefonts repo
- `tools/verify_classic/` harness that diffs the ports against the C
