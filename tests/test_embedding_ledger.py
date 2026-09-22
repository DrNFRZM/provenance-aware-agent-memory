import numpy as np

from conftest import false_value_for, make_entry
from provmem.embedding import HashingEmbedder
from provmem.ledger import Ledger
from provmem.schema import Verification


def test_embedder_is_deterministic_and_normalised():
    text = "The lead researcher of Kelvara Station is Ilsa Voren."
    a, b = HashingEmbedder(), HashingEmbedder()
    v = a.embed(text)
    assert np.array_equal(v, b.embed(text))
    assert abs(float(np.linalg.norm(v)) - 1.0) < 1e-5


def test_similarity_cannot_tell_true_from_false_value(world, embedder):
    """The premise of the project: a query about a fact is about as close to a false
    claim about it as to the true one, and both beat claims about other facts."""
    k, other = world.facts[0], world.facts[1]
    q = embedder.embed(f"What is the {k[1]} of {k[0]}?")
    true_v = embedder.embed(world.true_claim(k).render())
    false_v = embedder.embed(f"The {k[1]} of {k[0]} is {false_value_for(world, k)}.")
    unrelated = embedder.embed(world.true_claim(other).render())
    assert q @ true_v > q @ unrelated and q @ false_v > q @ unrelated
    assert abs(float(q @ true_v - q @ false_v)) < 0.15


def test_dedupe_and_shorter_path_adoption(world, ledger):
    k = world.facts[0]
    long = make_entry(world, k, uid="x1", origin="A1", hop=3)
    long.received_from, long.received_round, long.parent = "A8", 2, "A8#1"
    short = make_entry(world, k, uid="x2", origin="A1", hop=1)
    short.received_from, short.received_round, short.parent = "A2", 5, "A2#9"
    assert ledger.add(long)
    assert not ledger.add(short)
    held = ledger.entries[0]
    assert (held.hop_count, held.received_from, held.received_round, held.parent) == (1, "A2", 5, "A2#9")
    assert ledger.add(make_entry(world, k, uid="x3", origin="A2", hop=1))
    assert len(ledger.for_key(k)) == 2


def test_top_similar_and_quarantine(world, ledger):
    for i, k in enumerate(world.facts[:6]):
        ledger.add(make_entry(world, k, uid=f"e{i}", origin=f"A{i}"))
    k = world.facts[2]
    query = f"What is the {k[1]} of {k[0]}?"
    top = ledger.top_similar(query, 3)
    assert top[0][0].claim.key == k
    assert [s for _, s in top] == sorted((s for _, s in top), reverse=True)
    ledger.quarantine(top[0][0])
    assert top[0][0].verification is Verification.QUARANTINED
    assert all(e.claim.key != k for e, _ in ledger.top_similar(query, 3))
    assert ledger.for_key(k) == []


def test_exclude_predicate(world, ledger):
    for i, k in enumerate(world.facts[:4]):
        ledger.add(make_entry(world, k, uid=f"e{i}", origin=f"A{i}"))
    k = world.facts[0]
    got = ledger.top_similar(f"What is the {k[1]} of {k[0]}?", 4, exclude=lambda e: e.claim.key == k)
    assert got and all(e.claim.key != k for e, _ in got)


def test_save_load_roundtrip(tmp_path, world, ledger, embedder):
    for i, k in enumerate(world.facts[:5]):
        ledger.add(make_entry(world, k, uid=f"A0#{i + 1}", origin=f"A{i}"))
    path = tmp_path / "ledger.jsonl"
    ledger.save(path)
    loaded = Ledger.load("A0", embedder, path)
    assert loaded.entries == ledger.entries
    assert loaded.next_uid() == "A0#6"
