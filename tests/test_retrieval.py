import pytest

from conftest import false_value_for, make_entry
from provmem.retrieval import RetrievalConfig, Retriever, Strategy
from provmem.schema import EvidenceKind, Verification
from provmem.verify import Verifier


@pytest.fixture
def scene(world, ledger):
    k = world.facts[0]
    fv = false_value_for(world, k)
    ledger.add(make_entry(world, k, uid="h1", origin="A1", hop=1, conf=0.8))
    ledger.add(make_entry(world, k, uid="h2", origin="A2", hop=2, conf=0.75,
                          kind=EvidenceKind.OBSERVATION))
    ledger.add(make_entry(world, k, fv, uid="plain", origin="A3", conf=0.9, ref="doc-zz-1"))
    forged_value = false_value_for(world, k, seed=5)
    ledger.add(make_entry(world, k, forged_value, uid="forged", origin="A4", conf=0.99))
    for i, other in enumerate(world.facts[1:5]):
        ledger.add(make_entry(world, other, uid=f"f{i}", origin="A1"))
    query = f"What is the {k[1]} of {k[0]}?"
    return k, query, {"plain": fv, "forged": forged_value}


def make(world, strategy, coverage=1.0, **kw):
    cfg = RetrievalConfig(strategy=strategy, **kw)
    verifier = Verifier(world, coverage=coverage) if strategy.uses_verifier else None
    return Retriever(cfg, world.catalog, verifier)


def values(result):
    return {e.claim.value for e in result.entries}


def test_naive_retrieves_false_claims_like_any_other(world, ledger, scene):
    k, q, fakes = scene
    got = make(world, Strategy.NAIVE, k=4).retrieve(ledger, q, 1, "A0")
    assert set(fakes.values()) <= values(got)


def test_confidence_rewards_confident_forgery(world, ledger, scene):
    k, q, fakes = scene
    got = make(world, Strategy.CONFIDENCE, k=4, threshold=0.5).retrieve(ledger, q, 1, "A0")
    assert set(fakes.values()) <= values(got)
    strict = make(world, Strategy.CONFIDENCE, k=4, threshold=0.95).retrieve(ledger, q, 1, "A0")
    assert fakes["forged"] in values(strict) and world.truth[k] not in values(strict)


def test_provenance_rejects_unresolvable_evidence_but_not_forged_metadata(world, ledger, scene):
    k, q, fakes = scene
    got = make(world, Strategy.PROVENANCE, k=4, threshold=0.5).retrieve(ledger, q, 1, "A0")
    assert fakes["plain"] not in values(got)
    assert world.truth[k] in values(got)


def test_verification_rejects_what_metadata_cannot(world, ledger, scene):
    k, q, fakes = scene
    got = make(world, Strategy.VERIFIED, k=4, threshold=0.0).retrieve(ledger, q, 1, "A0")
    about_k = {e.claim.value for e in got.entries if e.claim.key == k}
    assert about_k == {world.truth[k]}


def test_refuted_is_a_hard_reject_even_at_threshold_zero(world, ledger, scene):
    k, q, fakes = scene
    r = make(world, Strategy.VERIFIED, k=4, threshold=0.0)
    got = r.retrieve(ledger, q, 1, "A0")
    assert {e.uid for e in got.newly_refuted} == {"plain", "forged"}
    assert all(e.verification is Verification.REFUTED for e in got.newly_refuted)


def test_uncovered_facts_stay_unverified_and_are_not_refuted(world, ledger, scene):
    k, q, fakes = scene
    got = make(world, Strategy.VERIFIED, coverage=0.0, k=4, threshold=0.0).retrieve(ledger, q, 1, "A0")
    assert got.newly_refuted == [] and fakes["forged"] in values(got)


def test_threshold_is_monotone_on_a_fixed_ledger(world, ledger, scene):
    k, q, _ = scene
    for strategy in (Strategy.CONFIDENCE, Strategy.PROVENANCE, Strategy.VERIFIED):
        r_prev = None
        for tau in (0.0, 0.2, 0.4, 0.6, 0.8, 1.01):
            r = make(world, strategy, threshold=tau, k=6)
            n_accept = sum(r.judge(ledger, e, 1, "A0")[0] for e in ledger.entries)
            n_ret = len(r.retrieve(ledger, q, 1, "A0", dry=True).entries)
            if r_prev is not None:
                assert n_accept <= r_prev[0] and n_ret <= r_prev[1]
            r_prev = (n_accept, n_ret)
        assert r_prev == (0, 0)


def test_max_hops_is_a_hard_cutoff(world, ledger, scene):
    k, q, _ = scene
    got = make(world, Strategy.PROVENANCE, k=6, threshold=0.0, max_hops=1).retrieve(ledger, q, 1, "A0")
    assert got.entries and all(e.hop_count <= 1 for e in got.entries)


def test_dry_retrieval_has_no_side_effects(world, ledger, scene):
    k, q, _ = scene
    r = make(world, Strategy.VERIFIED, k=4)
    before = [(e.verification, e.verified_round, e.trust_score) for e in ledger.entries]
    r.retrieve(ledger, q, 1, "A0", dry=True)
    assert [(e.verification, e.verified_round, e.trust_score) for e in ledger.entries] == before
    assert r.verifier.calls == 0
    r.retrieve(ledger, q, 1, "A0")
    assert r.verifier.calls > 0


def test_verifier_is_charged_once_per_entry(world, ledger, scene):
    k, q, _ = scene
    r = make(world, Strategy.VERIFIED, k=4)
    r.retrieve(ledger, q, 1, "A0")
    calls = r.verifier.calls
    r.retrieve(ledger, q, 2, "A0")
    assert r.verifier.calls == calls


def test_context_grows_with_the_provenance_shown(world, ledger, scene):
    k, q, _ = scene
    sizes = []
    for strategy in Strategy:
        got = make(world, strategy, k=2, threshold=0.0).retrieve(ledger, q, 1, "A0")
        sizes.append(sum(len(line.split()) for line in got.lines))
    assert sizes[0] < sizes[1] < sizes[2] < sizes[3] == sizes[4]


def test_verifying_strategies_require_a_verifier(world):
    with pytest.raises(ValueError):
        Retriever(RetrievalConfig(strategy=Strategy.VERIFIED), world.catalog, None)
