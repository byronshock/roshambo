"""Moves, outcomes, and the one algebraic fact the whole bot rests on."""

ROCK, PAPER, SCISSORS = 0, 1, 2
NAMES = ("rock", "paper", "scissors")
SYMBOLS = ("R", "P", "S")

# Moves are ints mod 3, ordered so that (m + 1) % 3 beats m.
_BEATS = (PAPER, SCISSORS, ROCK)


def beats(move: int) -> int:
    """The move that beats `move`."""
    return _BEATS[move]


def rotate(move: int, k: int) -> int:
    """Rotate a move forward k steps: k=0 identity, k=1 beats(move), k=2 beats(beats(move))."""
    return (move + k) % 3


def outcome(mine: int, theirs: int) -> int:
    """+1 if `mine` beats `theirs`, 0 on a tie, -1 if it loses."""
    if mine == theirs:
        return 0
    return 1 if beats(theirs) == mine else -1


def parse(text: str) -> int | None:
    """Parse 'r', 'rock', 'P', etc. into a move; None if unrecognised."""
    t = text.strip().lower()
    if not t:
        return None
    for move, name in enumerate(NAMES):
        if name.startswith(t):
            return move
    return None
