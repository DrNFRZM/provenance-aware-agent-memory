"""Memory entry schema. See docs/memory_model.md for the field-by-field contract."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Iterable, Iterator

ClaimKey = tuple[str, str]


class EvidenceKind(str, Enum):
    DOCUMENT = "document"
    OBSERVATION = "observation"
    HEARSAY = "hearsay"
    NONE = "none"


class Verification(str, Enum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    REFUTED = "refuted"
    QUARANTINED = "quarantined"


@dataclass(frozen=True)
class Claim:
    """A structured (subject, attribute, value) statement. Claim extraction from free
    text is assumed to be accurate; that assumption is listed in docs/threat_model.md."""

    subject: str
    attribute: str
    value: str

    @property
    def key(self) -> ClaimKey:
        return (self.subject, self.attribute)

    def render(self) -> str:
        return f"The {self.attribute} of {self.subject} is {self.value}."


@dataclass(frozen=True)
class Evidence:
    kind: EvidenceKind
    ref: str = ""


@dataclass
class MemoryEntry:
    uid: str
    content: str
    claim: Claim
    origin: str
    origin_round: int
    evidence: Evidence
    confidence: float
    hop_count: int
    received_from: str | None = None
    received_round: int = 0
    lineage: tuple[str, ...] = ()
    verification: Verification = Verification.UNVERIFIED
    verified_round: int | None = None
    trust_score: float | None = None
    parent: str | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence out of range: {self.confidence}")
        if self.hop_count < 0:
            raise ValueError(f"negative hop_count: {self.hop_count}")
        if self.content != self.claim.render():
            raise ValueError("content does not match its structured claim")

    @property
    def active(self) -> bool:
        return self.verification is not Verification.QUARANTINED

    def relayed(self, sender: str, uid: str, round_: int) -> "MemoryEntry":
        """The copy a receiver stores when `sender` forwards this entry. Provenance
        fields travel with the claim; hop count and lineage are extended, local
        verification and trust state are not inherited."""
        return replace(
            self,
            uid=uid,
            hop_count=self.hop_count + 1,
            received_from=sender,
            received_round=round_,
            lineage=self.lineage + (sender,),
            verification=Verification.UNVERIFIED,
            verified_round=None,
            trust_score=None,
            parent=self.uid,
        )

    def to_dict(self) -> dict:
        return {
            "uid": self.uid,
            "content": self.content,
            "claim": {"subject": self.claim.subject, "attribute": self.claim.attribute,
                      "value": self.claim.value},
            "origin": self.origin,
            "origin_round": self.origin_round,
            "evidence": {"kind": self.evidence.kind.value, "ref": self.evidence.ref},
            "confidence": self.confidence,
            "hop_count": self.hop_count,
            "received_from": self.received_from,
            "received_round": self.received_round,
            "lineage": list(self.lineage),
            "verification": self.verification.value,
            "verified_round": self.verified_round,
            "trust_score": self.trust_score,
            "parent": self.parent,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MemoryEntry":
        return cls(
            uid=d["uid"],
            content=d["content"],
            claim=Claim(**d["claim"]),
            origin=d["origin"],
            origin_round=d["origin_round"],
            evidence=Evidence(EvidenceKind(d["evidence"]["kind"]), d["evidence"]["ref"]),
            confidence=d["confidence"],
            hop_count=d["hop_count"],
            received_from=d["received_from"],
            received_round=d["received_round"],
            lineage=tuple(d["lineage"]),
            verification=Verification(d["verification"]),
            verified_round=d["verified_round"],
            trust_score=d["trust_score"],
            parent=d["parent"],
        )


def dump_jsonl(entries: Iterable[MemoryEntry], path: str | Path) -> int:
    n = 0
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for e in entries:
            fh.write(json.dumps(e.to_dict(), sort_keys=True) + "\n")
            n += 1
    return n


def load_jsonl(path: str | Path) -> Iterator[MemoryEntry]:
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield MemoryEntry.from_dict(json.loads(line))
