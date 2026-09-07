"""Roshambo: an ensemble opponent-modeling rock-paper-scissors bot."""
from .core import ROCK, PAPER, SCISSORS, NAMES, beats, outcome, parse
from .bot import Bot

__all__ = ["ROCK", "PAPER", "SCISSORS", "NAMES", "beats", "outcome", "parse", "Bot"]
