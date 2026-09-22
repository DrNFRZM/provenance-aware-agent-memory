import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from provmem.embedding import HashingEmbedder
from provmem.ledger import Ledger
from provmem.schema import Claim, Evidence, EvidenceKind, MemoryEntry
from provmem.world import build_world


@pytest.fixture(scope="session")
def world():
    return build_world(seed=7, n_entities=6)


@pytest.fixture
def embedder():
    return HashingEmbedder()


@pytest.fixture
def ledger(embedder):
    return Ledger("A0", embedder)


def make_entry(world, key, value=None, *, uid="e1", origin="A1", hop=0, conf=0.8,
               kind=EvidenceKind.DOCUMENT, ref=None, round_=0):
    value = world.truth[key] if value is None else value
    claim = Claim(key[0], key[1], value)
    if ref is None:
        ref = world.doc_ref(key) if kind is EvidenceKind.DOCUMENT else ""
    return MemoryEntry(uid=uid, content=claim.render(), claim=claim, origin=origin,
                       origin_round=round_, evidence=Evidence(kind, ref), confidence=conf,
                       hop_count=hop)


def false_value_for(world, key, seed=0):
    import random
    return world.false_value(key, random.Random(seed))
