"""Quarantine and repair (strategy 5). Per-agent state and the three mechanisms:
refutation -> quarantine, origin-suspicion cascade, and peer retractions with a quorum."""

from __future__ import annotations

from dataclasses import dataclass, field

from .ledger import Ledger
from .schema import ClaimKey, MemoryEntry, Verification
from .verify import Verifier


@dataclass(frozen=True)
class Retraction:
    sender: str
    key: ClaimKey
    value: str


@dataclass
class QuarantineState:
    suspicion_limit: int = 2
    retraction_quorum: int = 2
    refuted_keys_by_origin: dict[str, set[ClaimKey]] = field(default_factory=dict)
    retractors: dict[tuple[ClaimKey, str], set[str]] = field(default_factory=dict)
    outbox: list[Retraction] = field(default_factory=list)
    quarantined: int = 0

    def on_refuted(self, ledger: Ledger, e: MemoryEntry, me: str) -> None:
        if e.verification is not Verification.QUARANTINED:
            ledger.quarantine(e)
            self.quarantined += 1
        self.outbox.append(Retraction(me, e.claim.key, e.claim.value))
        keys = self.refuted_keys_by_origin.setdefault(e.origin, set())
        keys.add(e.claim.key)
        if len(keys) >= self.suspicion_limit:
            for other in list(ledger.entries):
                if (other.origin == e.origin and other.active
                        and other.verification is not Verification.VERIFIED):
                    ledger.quarantine(other)
                    self.quarantined += 1

    def on_retraction(self, ledger: Ledger, r: Retraction, me: str, verifier: Verifier,
                      now: int) -> None:
        senders = self.retractors.setdefault((r.key, r.value), set())
        senders.add(r.sender)
        for e in ledger.for_key(r.key):
            if e.claim.value != r.value:
                continue
            verdict = verifier.check(e, me, now)
            if verdict is Verification.REFUTED:
                self.on_refuted(ledger, e, me)
            elif (len(senders) >= self.retraction_quorum
                  and verdict is not Verification.VERIFIED):
                ledger.quarantine(e)
                self.quarantined += 1

    def audit(self, ledger: Ledger, me: str, verifier: Verifier, now: int, budget: int) -> None:
        """Spend up to `budget` verifier lookups on unchecked entries, conflicted claims first."""
        conflicted = {k for k in ledger.keys()
                      if len({e.claim.value for e in ledger.for_key(k)}) > 1}
        todo = [e for e in ledger.entries if e.active and e.verified_round is None]
        todo.sort(key=lambda e: (e.claim.key not in conflicted, e.uid))
        for e in todo:
            if budget <= 0:
                break
            if not verifier.covers(e.claim.key):
                continue
            budget -= 1
            if verifier.check(e, me, now) is Verification.REFUTED:
                self.on_refuted(ledger, e, me)
