"""Independent verification against a reference archive that is separate from the agents."""

from __future__ import annotations

from .schema import ClaimKey, MemoryEntry, Verification
from .seeding import unit_hash
from .world import World


def is_covered(seed: int, coverage: float, key: ClaimKey) -> bool:
    return unit_hash(seed, "coverage", *key) < coverage


class Verifier:
    """Answers "does the archive support this claim?" for the fraction `coverage` of
    facts that the archive holds. Uncovered facts stay UNVERIFIED. With probability
    `noise` a covered check returns the wrong verdict (deterministically, per entry).

    The archive is modelled as an oracle. What it stands for in a real system (a curated
    knowledge base, a signed source, a tool call) is discussed in docs/threat_model.md."""

    def __init__(self, world: World, coverage: float = 0.5, noise: float = 0.0,
                 seed: int = 0) -> None:
        if not 0.0 <= coverage <= 1.0 or not 0.0 <= noise <= 1.0:
            raise ValueError("coverage and noise must be in [0, 1]")
        self.world = world
        self.coverage = coverage
        self.noise = noise
        self.seed = seed
        self.calls = 0

    def covers(self, key: ClaimKey) -> bool:
        return is_covered(self.seed, self.coverage, key)

    def peek(self, entry: MemoryEntry, agent: str) -> Verification:
        """The verdict, with no side effects and no cost accounting."""
        if not self.covers(entry.claim.key):
            return Verification.UNVERIFIED
        supported = self.world.truth[entry.claim.key] == entry.claim.value
        if self.noise and unit_hash(self.seed, "noise", agent, entry.uid) < self.noise:
            supported = not supported
        return Verification.VERIFIED if supported else Verification.REFUTED

    def check(self, entry: MemoryEntry, agent: str, now: int) -> Verification:
        """Verify once; the verdict is cached on the entry. Only checks that reach the
        archive (covered facts) count as a lookup; the coverage index itself is free."""
        if entry.verified_round is not None:
            return entry.verification
        if self.covers(entry.claim.key):
            self.calls += 1
        verdict = self.peek(entry, agent)
        entry.verified_round = now
        if entry.verification is not Verification.QUARANTINED:
            entry.verification = verdict
        return verdict
