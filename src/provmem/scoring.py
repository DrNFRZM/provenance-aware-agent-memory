"""Provenance trust scoring. Exact formulas are specified in docs/memory_model.md."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from .schema import ClaimKey, EvidenceKind, MemoryEntry, Verification

TRUST_FIELDS = ("evidence", "confidence", "hop", "agreement", "recency")

# Hand-set relative weights; they are normalised over the enabled fields. They were
# fixed before any benchmark was run and are not tuned (see docs/design_decisions.md).
DEFAULT_WEIGHTS = {"evidence": 5.0, "confidence": 2.0, "hop": 3.0, "agreement": 6.0, "recency": 2.0}

EVIDENCE_PRIOR = {
    EvidenceKind.OBSERVATION: 0.7,
    EvidenceKind.HEARSAY: 0.3,
    EvidenceKind.NONE: 0.2,
}
UNRESOLVED_DOCUMENT = 0.1


@dataclass(frozen=True)
class ScoringConfig:
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    hop_gamma: float = 0.85
    recency_half_life: float = 8.0
    verified_boost: float = 0.7

    def without(self, name: str) -> "ScoringConfig":
        return ScoringConfig({**self.weights, name: 0.0}, self.hop_gamma,
                             self.recency_half_life, self.verified_boost)

    def only(self, name: str) -> "ScoringConfig":
        return ScoringConfig({k: (v if k == name else 0.0) for k, v in self.weights.items()},
                             self.hop_gamma, self.recency_half_life, self.verified_boost)


def evidence_score(e: MemoryEntry, catalog: dict[str, ClaimKey]) -> float:
    if e.evidence.kind is EvidenceKind.DOCUMENT:
        return 1.0 if catalog.get(e.evidence.ref) == e.claim.key else UNRESOLVED_DOCUMENT
    return EVIDENCE_PRIOR[e.evidence.kind]


def hop_score(e: MemoryEntry, gamma: float) -> float:
    return gamma ** e.hop_count


def recency_score(e: MemoryEntry, now: int, half_life: float) -> float:
    return 0.5 ** (max(0, now - e.origin_round) / half_life)


def agreement_score(e: MemoryEntry, peers: Sequence[MemoryEntry]) -> float:
    """Share of distinct origins that back this value, discounted when few origins back it."""
    origins: dict[str, set[str]] = {}
    for p in peers:
        origins.setdefault(p.claim.value, set()).add(p.origin)
    origins.setdefault(e.claim.value, set()).add(e.origin)
    total = sum(len(s) for s in origins.values())
    support = len(origins[e.claim.value])
    return (support / total) * (1.0 - 0.5 ** support)


def components(e: MemoryEntry, peers: Sequence[MemoryEntry], now: int,
               catalog: dict[str, ClaimKey], cfg: ScoringConfig) -> dict[str, float]:
    w = cfg.weights
    out: dict[str, float] = {}
    if w["evidence"] > 0:
        out["evidence"] = evidence_score(e, catalog)
    if w["confidence"] > 0:
        out["confidence"] = e.confidence
    if w["hop"] > 0:
        out["hop"] = hop_score(e, cfg.hop_gamma)
    if w["agreement"] > 0:
        out["agreement"] = agreement_score(e, peers)
    if w["recency"] > 0:
        out["recency"] = recency_score(e, now, cfg.recency_half_life)
    return out


def provenance_trust(e: MemoryEntry, peers: Sequence[MemoryEntry], now: int,
                     catalog: dict[str, ClaimKey], cfg: ScoringConfig) -> float:
    comps = components(e, peers, now, catalog, cfg)
    if not comps:
        return 0.5
    total_w = sum(cfg.weights[k] for k in comps)
    return sum(cfg.weights[k] * v for k, v in comps.items()) / total_w


def apply_verification(trust: float, state: Verification, boost: float) -> float:
    if state is Verification.VERIFIED:
        return trust + (1.0 - trust) * boost
    if state in (Verification.REFUTED, Verification.QUARANTINED):
        return 0.0
    return trust
