import pytest

from conftest import false_value_for, make_entry
from provmem.schema import EvidenceKind, Verification
from provmem.scoring import (TRUST_FIELDS, ScoringConfig, agreement_score, apply_verification,
                             components, evidence_score, hop_score, provenance_trust,
                             recency_score)


def test_evidence_resolution(world):
    k = world.facts[0]
    good = make_entry(world, k)
    fake = make_entry(world, k, ref="doc-zz-1")
    wrong_fact = make_entry(world, k, ref=world.doc_ref(world.facts[1]))
    assert evidence_score(good, world.catalog) == 1.0
    assert evidence_score(fake, world.catalog) == evidence_score(wrong_fact, world.catalog) == 0.1
    obs = make_entry(world, k, kind=EvidenceKind.OBSERVATION)
    hearsay = make_entry(world, k, kind=EvidenceKind.HEARSAY)
    assert evidence_score(obs, world.catalog) > evidence_score(hearsay, world.catalog)


def test_hop_and_recency_decay(world):
    k = world.facts[0]
    assert hop_score(make_entry(world, k, hop=0), 0.85) == 1.0
    assert hop_score(make_entry(world, k, hop=3), 0.85) < hop_score(make_entry(world, k, hop=1), 0.85)
    assert recency_score(make_entry(world, k, round_=0), 8, 8.0) == pytest.approx(0.5)
    assert recency_score(make_entry(world, k, round_=8), 8, 8.0) == 1.0


def test_agreement_counts_distinct_origins_not_copies(world):
    k = world.facts[0]
    fv = false_value_for(world, k)
    honest = [make_entry(world, k, uid="h1", origin="A1"), make_entry(world, k, uid="h2", origin="A2")]
    liar = make_entry(world, k, fv, uid="l1", origin="A3")
    copies = [make_entry(world, k, fv, uid=f"l{i}", origin="A3") for i in range(2, 6)]
    peers = honest + [liar] + copies
    assert agreement_score(honest[0], peers) > agreement_score(liar, peers)
    assert agreement_score(liar, [liar]) == pytest.approx(0.5)


def test_provenance_ranks_honest_above_plain_forgery(world):
    k = world.facts[0]
    honest = [make_entry(world, k, uid="h1", origin="A1", hop=1, conf=0.8),
              make_entry(world, k, uid="h2", origin="A2", hop=2, conf=0.75)]
    forged = make_entry(world, k, false_value_for(world, k), uid="f", origin="A3", conf=0.9,
                        ref="doc-zz-1")
    peers = honest + [forged]
    cfg = ScoringConfig()
    assert (provenance_trust(honest[0], peers, 3, world.catalog, cfg)
            > provenance_trust(forged, peers, 3, world.catalog, cfg))


def test_forged_metadata_can_beat_honest_entry_without_agreement(world):
    """A limit worth pinning down: with a valid document reference, top confidence and a
    fresh hop count, a forged entry outscores an honest relayed one on metadata alone."""
    k = world.facts[0]
    honest = make_entry(world, k, uid="h", origin="A1", hop=3, conf=0.75,
                        kind=EvidenceKind.OBSERVATION)
    forged = make_entry(world, k, false_value_for(world, k), uid="f", origin="A2", hop=1, conf=0.99)
    cfg = ScoringConfig().without("agreement")
    peers = [honest, forged]
    assert (provenance_trust(forged, peers, 3, world.catalog, cfg)
            > provenance_trust(honest, peers, 3, world.catalog, cfg))


def test_ablation_configs_change_the_active_components(world):
    e = make_entry(world, world.facts[0])
    assert set(components(e, [e], 1, world.catalog, ScoringConfig())) == set(TRUST_FIELDS)
    assert "hop" not in components(e, [e], 1, world.catalog, ScoringConfig().without("hop"))
    only = components(e, [e], 1, world.catalog, ScoringConfig().only("agreement"))
    assert set(only) == {"agreement"}
    only_conf = ScoringConfig().only("confidence")
    assert provenance_trust(e, [e], 1, world.catalog, only_conf) == pytest.approx(e.confidence)


def test_trust_is_bounded(world):
    e = make_entry(world, world.facts[0], hop=9, conf=0.0, kind=EvidenceKind.NONE)
    assert 0.0 <= provenance_trust(e, [e], 50, world.catalog, ScoringConfig()) <= 1.0


def test_verification_adjustment():
    boost = 0.7
    assert apply_verification(0.5, Verification.UNVERIFIED, boost) == 0.5
    assert apply_verification(0.5, Verification.VERIFIED, boost) == pytest.approx(0.85)
    assert apply_verification(0.9, Verification.REFUTED, boost) == 0.0
    assert apply_verification(0.9, Verification.QUARANTINED, boost) == 0.0
