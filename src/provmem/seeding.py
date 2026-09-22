"""Stable, process-independent seed and hash derivation.

Python's built-in hash() is salted per process, so it is never used for anything that
affects results."""

from __future__ import annotations

import hashlib
import random


def digest_int(*parts: object) -> int:
    h = hashlib.blake2b("\x1f".join(str(p) for p in parts).encode("utf-8"), digest_size=8)
    return int.from_bytes(h.digest(), "big")


def unit_hash(*parts: object) -> float:
    """Deterministic float in [0, 1) derived from the parts."""
    return digest_int(*parts) / 2**64


def rng_for(seed: int, *labels: object) -> random.Random:
    return random.Random(digest_int(seed, *labels))
