"""Per-agent memory ledger: an append-mostly list of MemoryEntry objects with a
similarity index and a claim-key index."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .embedding import Embedder
from .schema import ClaimKey, MemoryEntry, Verification, dump_jsonl, load_jsonl


class Ledger:
    def __init__(self, owner: str, embedder: Embedder) -> None:
        self.owner = owner
        self.embedder = embedder
        self.entries: list[MemoryEntry] = []
        self._by_key: dict[ClaimKey, list[MemoryEntry]] = {}
        self._seen: dict[tuple[str, ClaimKey, str], MemoryEntry] = {}
        self._vecs: list[np.ndarray] = []
        self._matrix: np.ndarray | None = None
        self._active: np.ndarray | None = None
        self._counter = 0

    def __len__(self) -> int:
        return len(self.entries)

    def next_uid(self) -> str:
        self._counter += 1
        return f"{self.owner}#{self._counter}"

    def add(self, entry: MemoryEntry) -> bool:
        """Store an entry. A second copy of the same (origin, claim) is not stored again;
        if it arrived over a shorter path, the stored copy adopts the shorter path."""
        sig = (entry.origin, entry.claim.key, entry.claim.value)
        held = self._seen.get(sig)
        if held is not None:
            if entry.hop_count < held.hop_count:
                held.hop_count = entry.hop_count
                held.lineage = entry.lineage
                held.received_from = entry.received_from
                held.received_round = entry.received_round
                held.parent = entry.parent
            return False
        self._seen[sig] = entry
        self.entries.append(entry)
        self._by_key.setdefault(entry.claim.key, []).append(entry)
        self._vecs.append(self.embedder.embed(entry.content))
        self._matrix = None
        self._active = None
        return True

    def for_key(self, key: ClaimKey) -> list[MemoryEntry]:
        return [e for e in self._by_key.get(key, ()) if e.active]

    def keys(self) -> list[ClaimKey]:
        return list(self._by_key)

    def quarantine(self, entry: MemoryEntry) -> None:
        entry.verification = Verification.QUARANTINED
        self._active = None

    def _arrays(self) -> tuple[np.ndarray, np.ndarray]:
        if self._matrix is None:
            self._matrix = (np.stack(self._vecs) if self._vecs
                            else np.zeros((0, self.embedder.dim), dtype=np.float32))
        if self._active is None:
            self._active = np.fromiter((e.active for e in self.entries), dtype=bool,
                                       count=len(self.entries))
        return self._matrix, self._active

    def top_similar(self, query: str, n: int,
                    exclude=None) -> list[tuple[MemoryEntry, float]]:
        matrix, active = self._arrays()
        if not len(self.entries):
            return []
        sims = matrix @ self.embedder.embed(query)
        ok = active.copy()
        if exclude is not None:
            ok &= np.fromiter((not exclude(e) for e in self.entries), dtype=bool,
                              count=len(self.entries))
        sims = np.where(ok, sims, -np.inf)
        order = np.argsort(-sims, kind="stable")[:n]
        return [(self.entries[i], float(sims[i])) for i in order if np.isfinite(sims[i])]

    def save(self, path: str | Path) -> int:
        return dump_jsonl(self.entries, path)

    @classmethod
    def load(cls, owner: str, embedder: Embedder, path: str | Path) -> "Ledger":
        ledger = cls(owner, embedder)
        for e in load_jsonl(path):
            ledger.add(e)
        prefix = f"{owner}#"
        seen = [e.uid[len(prefix):] for e in ledger.entries if e.uid.startswith(prefix)]
        ledger._counter = max((int(n) for n in seen if n.isdigit()), default=0)
        return ledger
