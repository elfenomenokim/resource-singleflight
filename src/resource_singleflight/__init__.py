"""Run one worker per key and share its result.

`ResourceCoordinator` gives every caller of a key the same joinable `Future`,
caches a result for a caller-chosen TTL, and supersedes a worker by generation so
a detached read cannot publish a value its caller already replaced.
"""

from .core import FALSE_WORDS, ResourceCoordinator, env_flag

__all__ = ["FALSE_WORDS", "ResourceCoordinator", "env_flag"]

__version__ = "0.1.0"
