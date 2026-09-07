"""Python ports of the classic RoShamBo tournament winners, for use as opponents.

Both bots expose the same interface: `move(guess)` returns the bot's play
given one uniformly random move for its internal use, and
`observe(mine, theirs)` records a finished round. Histories are kept the
way the originals kept them, as 1-based lists whose element 0 is the count.
"""
from .greenberg import Greenberg
from .iocaine import Iocaine

__all__ = ["Iocaine", "Greenberg"]
