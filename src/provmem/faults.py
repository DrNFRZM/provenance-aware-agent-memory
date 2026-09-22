"""Synthetic fault injection: coordinated false claims about invented facts.

Three provenance-forgery levels are modelled. All false values are other plausible values
from the same fictional attribute pool; nothing here touches real-world content."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .schema import Claim, ClaimKey, Evidence, EvidenceKind, MemoryEntry
from .world import World


class FaultMode(str, Enum):
    NONE = "none"                # control: the extra peers exist but stay silent
    PLAIN = "plain"              # honest-looking metadata, but the cited document does not exist
    FORGED_META = "forged_meta"  # valid document reference, top confidence, hop 0, impersonated origin
    SYBIL = "sybil"              # as forged_meta, but with several fabricated origin identities


@dataclass(frozen=True)
class FaultSpec:
    mode: FaultMode = FaultMode.PLAIN
    n_faulty: int = 1
    inject_round: int = 3
    push_fanout: int = 2
    push_rounds: int = 1
    sybil_ids: int = 3
    plain_confidence: float = 0.90
    forged_confidence: float = 0.99
    evasive: bool = False  # attacker targets only facts the verifier cannot check


def plan_false_values(world: World, targets: list[ClaimKey], rng) -> dict[ClaimKey, str]:
    """One coordinated false value per target, shared by all colluding faulty agents."""
    return {key: world.false_value(key, rng) for key in targets}


def forge_entries(spec: FaultSpec, world: World, faulty_id: str, faulty_index: int,
                  honest_ids: list[str], false_values: dict[ClaimKey, str],
                  round_: int) -> list[MemoryEntry]:
    out: list[MemoryEntry] = []
    if spec.mode is FaultMode.PLAIN:
        origins = [faulty_id]
    elif spec.mode is FaultMode.FORGED_META:
        origins = [honest_ids[faulty_index % len(honest_ids)]]
    else:
        origins = [f"sybil-{faulty_index}-{i}" for i in range(spec.sybil_ids)]
    conf = spec.plain_confidence if spec.mode is FaultMode.PLAIN else spec.forged_confidence
    n = 0
    for origin in origins:
        for key, value in false_values.items():
            n += 1
            claim = Claim(key[0], key[1], value)
            ref = (f"doc-zz-{faulty_index}-{n}" if spec.mode is FaultMode.PLAIN
                   else world.doc_ref(key))
            out.append(MemoryEntry(
                uid=f"{faulty_id}#f{n}", content=claim.render(), claim=claim, origin=origin,
                origin_round=round_, evidence=Evidence(EvidenceKind.DOCUMENT, ref),
                confidence=conf, hop_count=0))
    return out
