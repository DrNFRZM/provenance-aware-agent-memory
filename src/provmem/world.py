"""A synthetic world of invented facts: fictional stations, planets and guilds.

Everything here is made up on the spot from syllables; nothing corresponds to a real
place, organisation or person. False claims are just other plausible values from the
same attribute pool."""

from __future__ import annotations

from dataclasses import dataclass, field

from .schema import Claim, ClaimKey
from .seeding import rng_for

KIND_ATTRS: dict[str, tuple[str, str, str]] = {
    "Station": ("lead researcher", "primary instrument", "founding cycle"),
    "Planet": ("discoverer", "dominant mineral", "orbital period"),
    "Guild": ("guildmaster", "founding cycle", "archive language"),
}
_KINDS = tuple(KIND_ATTRS)

_ONSET = ["k", "v", "th", "or", "el", "ar", "s", "m", "n", "z", "qu", "br", "dr", "l", "h", "t"]
_VOWEL = ["a", "e", "i", "o", "u", "ae", "ia", "ou"]
_CODA = ["r", "n", "x", "l", "th", "s", "m", "d", ""]
_INSTRUMENT_TYPES = ["interferometer", "spectrograph", "resonator", "drift sensor",
                     "lattice array", "phase counter", "tide gauge", "echo lens"]


def _syllables(rng, n: int) -> str:
    return "".join(rng.choice(_ONSET) + rng.choice(_VOWEL) + rng.choice(_CODA) for _ in range(n))


def _unique(rng, make, size: int) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    while len(out) < size:
        v = make()
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _build_pools(seed: int, size: int = 40) -> dict[str, list[str]]:
    rng = rng_for(seed, "pools")
    person = lambda: f"{_syllables(rng, 2).capitalize()} {_syllables(rng, 2).capitalize()}"
    pools = {
        "person": _unique(rng, person, size),
        "instrument": _unique(
            rng, lambda: f"{_syllables(rng, 2).capitalize()} {rng.choice(_INSTRUMENT_TYPES)}", size),
        "cycle": _unique(rng, lambda: f"cycle {rng.randint(3000, 3999)}", size),
        "mineral": _unique(rng, lambda: f"{_syllables(rng, 2)}ite", size),
        "period": _unique(rng, lambda: f"{rng.randint(100, 900)} standard days", size),
        "language": _unique(rng, lambda: f"{_syllables(rng, 2).capitalize()}ic", size),
    }
    return pools


ATTR_POOL = {
    "lead researcher": "person", "discoverer": "person", "guildmaster": "person",
    "primary instrument": "instrument", "founding cycle": "cycle",
    "dominant mineral": "mineral", "orbital period": "period", "archive language": "language",
}


@dataclass
class World:
    seed: int
    subjects: list[str]
    facts: list[ClaimKey]
    truth: dict[ClaimKey, str]
    pools: dict[str, list[str]]
    catalog: dict[str, ClaimKey] = field(default_factory=dict)
    _ref_of: dict[ClaimKey, str] = field(default_factory=dict)

    def doc_ref(self, key: ClaimKey) -> str:
        return self._ref_of[key]

    def true_claim(self, key: ClaimKey) -> Claim:
        return Claim(key[0], key[1], self.truth[key])

    def false_value(self, key: ClaimKey, rng, exclude: tuple[str, ...] = ()) -> str:
        pool = self.pools[ATTR_POOL[key[1]]]
        banned = {self.truth[key], *exclude}
        return rng.choice([v for v in pool if v not in banned])


def build_world(seed: int, n_entities: int = 15) -> World:
    rng = rng_for(seed, "world")
    pools = _build_pools(seed)
    names = _unique(rng, lambda: _syllables(rng, 3).capitalize(), n_entities)
    subjects: list[str] = []
    facts: list[ClaimKey] = []
    truth: dict[ClaimKey, str] = {}
    for i, name in enumerate(names):
        kind = _KINDS[i % len(_KINDS)]
        subject = f"{name} {kind}"
        subjects.append(subject)
        for attr in KIND_ATTRS[kind]:
            key = (subject, attr)
            facts.append(key)
            truth[key] = rng.choice(pools[ATTR_POOL[attr]])
    world = World(seed, subjects, facts, truth, pools)
    for i, key in enumerate(facts):
        ref = f"doc-{i:03d}"
        world.catalog[ref] = key
        world._ref_of[key] = ref
    return world
