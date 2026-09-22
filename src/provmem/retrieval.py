"""The five retrieval strategies compared in this project."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .ledger import Ledger
from .schema import ClaimKey, MemoryEntry, Verification
from .scoring import ScoringConfig, apply_verification, provenance_trust
from .verify import Verifier


class Strategy(str, Enum):
    NAIVE = "naive"
    CONFIDENCE = "confidence"
    PROVENANCE = "provenance"
    VERIFIED = "verified"
    QUARANTINE = "quarantine"

    @property
    def uses_verifier(self) -> bool:
        return self in (Strategy.VERIFIED, Strategy.QUARANTINE)


@dataclass(frozen=True)
class RetrievalConfig:
    strategy: Strategy = Strategy.NAIVE
    k: int = 3
    threshold: float = 0.5
    pool_factor: int = 4
    max_hops: int | None = None
    rank: str = "similarity"  # "similarity": trust gates and weights; "product": rank by sim * trust
    scoring: ScoringConfig = field(default_factory=ScoringConfig)


@dataclass
class Retrieved:
    entries: list[MemoryEntry] = field(default_factory=list)
    trusts: list[float] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    scored: int = 0
    newly_refuted: list[MemoryEntry] = field(default_factory=list)


class Retriever:
    def __init__(self, cfg: RetrievalConfig, catalog: dict[str, ClaimKey],
                 verifier: Verifier | None = None) -> None:
        if cfg.strategy.uses_verifier and verifier is None:
            raise ValueError(f"strategy {cfg.strategy.value} needs a verifier")
        self.cfg = cfg
        self.catalog = catalog
        self.verifier = verifier

    def _verdict(self, e: MemoryEntry, agent: str, now: int, charge: bool) -> Verification:
        if e.verified_round is not None or e.verification is Verification.QUARANTINED:
            return e.verification
        if charge:
            return self.verifier.check(e, agent, now)
        return self.verifier.peek(e, agent)

    def _trust(self, e: MemoryEntry, ledger: Ledger, now: int, agent: str, charge: bool,
               peers: dict[ClaimKey, list[MemoryEntry]]) -> tuple[float, bool]:
        """Returns (trust, hard_reject)."""
        s = self.cfg.strategy
        if s is Strategy.CONFIDENCE:
            return e.confidence, False
        if self.cfg.max_hops is not None and e.hop_count > self.cfg.max_hops:
            return 0.0, True
        key = e.claim.key
        if key not in peers:
            peers[key] = ledger.for_key(key)
        t = provenance_trust(e, peers[key], now, self.catalog, self.cfg.scoring)
        if s.uses_verifier:
            state = self._verdict(e, agent, now, charge)
            if state in (Verification.REFUTED, Verification.QUARANTINED):
                return 0.0, True
            t = apply_verification(t, state, self.cfg.scoring.verified_boost)
        return t, False

    def judge(self, ledger: Ledger, e: MemoryEntry, now: int, agent: str,
              charge: bool = False) -> tuple[bool, bool]:
        """Would this entry be accepted (used for relaying and for false-positive /
        false-negative accounting)? Returns (accepted, newly_refuted)."""
        s = self.cfg.strategy
        if s is Strategy.NAIVE:
            return e.active, False
        was_unchecked = e.verified_round is None
        t, hard = self._trust(e, ledger, now, agent, charge, {})
        newly = (charge and s.uses_verifier and was_unchecked
                 and e.verification is Verification.REFUTED)
        return (e.active and not hard and t >= self.cfg.threshold), newly

    def retrieve(self, ledger: Ledger, query: str, now: int, agent: str,
                 dry: bool = False, exclude=None) -> Retrieved:
        cfg, s = self.cfg, self.cfg.strategy
        out = Retrieved()
        if s is Strategy.NAIVE:
            for e, _ in ledger.top_similar(query, cfg.k, exclude):
                out.entries.append(e)
                out.trusts.append(1.0)
                out.lines.append(f"- {e.content}")
            out.scored = len(out.entries)
            return out

        pool = ledger.top_similar(query, cfg.pool_factor * cfg.k, exclude)
        peers: dict[ClaimKey, list[MemoryEntry]] = {}
        ranked: list[tuple[float, float, MemoryEntry]] = []
        for e, sim in pool:
            was_unchecked = e.verified_round is None
            t, hard = self._trust(e, ledger, now, agent, not dry, peers)
            out.scored += 1
            if not dry:
                e.trust_score = t
                if s.uses_verifier and was_unchecked and e.verification is Verification.REFUTED:
                    out.newly_refuted.append(e)
            if hard or t < cfg.threshold:
                continue
            ranked.append((sim * t if cfg.rank == "product" else sim, t, e))
        ranked.sort(key=lambda r: -r[0])
        for _, t, e in ranked[:cfg.k]:
            out.entries.append(e)
            out.trusts.append(t)
            out.lines.append(self._render(e, t, agent))
        return out

    def _render(self, e: MemoryEntry, t: float, agent: str) -> str:
        s = self.cfg.strategy
        if s is Strategy.CONFIDENCE:
            return f"- [w={t:.2f}] {e.content}"
        meta = (f"w={t:.2f} origin={e.origin} hop={e.hop_count} "
                f"ev={e.evidence.kind.value} conf={e.confidence:.2f}")
        if s.uses_verifier:
            state = e.verification if e.verified_round is not None else self.verifier.peek(e, agent)
            meta += f" ver={state.value}"
        return f"- [{meta}] {e.content}"
