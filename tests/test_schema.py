import pytest

from conftest import make_entry
from provmem.schema import Claim, MemoryEntry, Verification, dump_jsonl, load_jsonl


def test_dict_roundtrip(world):
    e = make_entry(world, world.facts[0], hop=2)
    e.trust_score = 0.42
    assert MemoryEntry.from_dict(e.to_dict()) == e


def test_jsonl_roundtrip(tmp_path, world):
    entries = [make_entry(world, k, uid=f"e{i}", origin=f"A{i}") for i, k in enumerate(world.facts[:5])]
    entries[2].verification = Verification.REFUTED
    path = tmp_path / "mem.jsonl"
    assert dump_jsonl(entries, path) == 5
    assert list(load_jsonl(path)) == entries


def test_jsonl_is_stable_across_dumps(tmp_path, world):
    entries = [make_entry(world, world.facts[0])]
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    dump_jsonl(entries, a)
    dump_jsonl(entries, b)
    assert a.read_bytes() == b.read_bytes()


@pytest.mark.parametrize("kwargs", [{"conf": 1.5}, {"conf": -0.1}, {"hop": -1}])
def test_validation(world, kwargs):
    with pytest.raises(ValueError):
        make_entry(world, world.facts[0], **kwargs)


def test_content_must_match_claim(world):
    d = make_entry(world, world.facts[0]).to_dict()
    d["content"] = "The lead researcher of Nowhere is nobody."
    with pytest.raises(ValueError):
        MemoryEntry.from_dict(d)


def test_relay_extends_path_and_resets_local_state(world):
    e = make_entry(world, world.facts[0], hop=1)
    e.verification = Verification.VERIFIED
    e.verified_round = 3
    e.trust_score = 0.9
    r = e.relayed("A5", "A2#1", 4)
    assert (r.hop_count, r.lineage, r.received_from, r.parent) == (2, ("A5",), "A5", e.uid)
    assert r.origin == e.origin and r.evidence == e.evidence and r.confidence == e.confidence
    assert r.verification is Verification.UNVERIFIED and r.trust_score is None
    assert e.hop_count == 1


def test_claim_render_and_key():
    c = Claim("Kelvara Station", "lead researcher", "Ilsa Voren")
    assert c.render() == "The lead researcher of Kelvara Station is Ilsa Voren."
    assert c.key == ("Kelvara Station", "lead researcher")
