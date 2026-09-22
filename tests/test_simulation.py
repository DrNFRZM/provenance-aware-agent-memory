import math
import statistics as st

import pytest

from provmem.faults import FaultMode, FaultSpec
from provmem.retrieval import RetrievalConfig, Strategy
from provmem.simulation import SimConfig, run
from provmem.world import build_world


def cfg(strategy=Strategy.NAIVE, mode=FaultMode.PLAIN, seed=0, **kw):
    fault = kw.pop("fault", FaultSpec(mode=mode))
    ret = kw.pop("retrieval", RetrievalConfig(strategy=strategy))
    return SimConfig(seed=seed, fault=fault, retrieval=ret, **kw)


def mean_over(seeds, key, **kw):
    vals = [run(cfg(seed=s, **kw)).metrics[key] for s in seeds]
    return st.mean(v for v in vals if not math.isnan(v))


def test_world_is_deterministic_and_synthetic():
    a, b = build_world(3), build_world(3)
    assert a.truth == b.truth and a.catalog == b.catalog
    assert build_world(3).truth != build_world(4).truth
    assert all(s.split()[-1] in ("Station", "Planet", "Guild") for s in a.subjects)


def test_run_is_deterministic():
    c = cfg(Strategy.QUARANTINE, FaultMode.SYBIL, seed=4)
    r1, r2 = run(c), run(c)
    assert repr(r1.metrics) == repr(r2.metrics)
    assert repr(r1.timeline) == repr(r2.timeline) and r1.targets == r2.targets


def test_different_seeds_differ():
    assert run(cfg(seed=1)).timeline != run(cfg(seed=2)).timeline


def test_control_run_has_no_false_retrieval_or_exposure():
    m = run(cfg(Strategy.NAIVE, FaultMode.NONE)).metrics
    assert m["false_retrieval_rate"] < 0.1
    assert math.isnan(m["exposure_final"]) and math.isnan(m["fn_accept_injected"])


def test_injected_falsehood_reaches_answers_under_naive_retrieval():
    seeds = range(4)
    assert mean_over(seeds, "false_retrieval_rate") > 0.3
    assert mean_over(seeds, "asr_post_mean") > 0.05
    assert mean_over(seeds, "fn_accept_injected") == 1.0
    assert mean_over(seeds, "fp_reject_rate") == 0.0


def test_faults_only_touch_targeted_facts():
    m = run(cfg(Strategy.NAIVE, FaultMode.PLAIN, seed=2)).metrics
    ctrl = run(cfg(Strategy.NAIVE, FaultMode.NONE, seed=2)).metrics
    assert m["clean_accuracy_final"] == pytest.approx(ctrl["clean_accuracy_final"], abs=0.11)


def test_defences_reduce_false_retrieval_against_plain_forgery():
    seeds = range(4)
    naive = mean_over(seeds, "false_retrieval_rate", strategy=Strategy.NAIVE)
    prov = mean_over(seeds, "false_retrieval_rate", strategy=Strategy.PROVENANCE)
    ver = mean_over(seeds, "false_retrieval_rate", strategy=Strategy.VERIFIED)
    assert prov < naive and ver <= prov


def test_secondary_propagation_needs_honest_relays():
    m = run(cfg(Strategy.NAIVE, FaultMode.PLAIN, seed=1)).metrics
    assert m["propagation_final"] > 0 and m["exposure_final"] >= m["propagation_final"]
    q = run(cfg(Strategy.QUARANTINE, FaultMode.PLAIN, seed=1)).metrics
    assert q["propagation_final"] <= m["propagation_final"]


def test_evasive_attacker_targets_unverifiable_facts_only():
    from provmem.verify import is_covered
    r = run(cfg(Strategy.VERIFIED, fault=FaultSpec(mode=FaultMode.SYBIL, evasive=True), seed=3))
    assert r.targets and not any(is_covered(3, 0.5, key) for key in r.targets)
    plain = run(cfg(Strategy.VERIFIED, fault=FaultSpec(mode=FaultMode.SYBIL), seed=3))
    assert any(is_covered(3, 0.5, key) for key in plain.targets)
    with pytest.raises(ValueError, match="outside verifier coverage"):
        run(cfg(Strategy.VERIFIED, fault=FaultSpec(mode=FaultMode.SYBIL, evasive=True),
                verifier_coverage=1.0, seed=3))


def test_threshold_behaviour_in_the_simulation():
    seeds = range(4)

    def at(tau, key):
        return mean_over(seeds, key, retrieval=RetrievalConfig(strategy=Strategy.PROVENANCE, threshold=tau))

    assert at(0.05, "fp_reject_rate") <= at(0.95, "fp_reject_rate")
    assert at(0.05, "fn_accept_injected") >= at(0.95, "fn_accept_injected")
    assert at(0.95, "fp_reject_rate") == 1.0 and at(0.95, "fn_accept_injected") == 0.0


def test_metrics_are_in_range_and_timeline_is_complete():
    r = run(cfg(Strategy.QUARANTINE, FaultMode.FORGED_META, seed=5))
    assert len(r.timeline) == 10
    for key in ("asr_final", "false_retrieval_rate", "answer_flip_rate", "clean_accuracy_final",
                "fp_reject_rate", "fn_accept_rate", "propagation_final"):
        v = r.metrics[key]
        assert math.isnan(v) or 0.0 <= v <= 1.0
    assert r.metrics["verifier_lookups"] > 0 and r.metrics["context_tokens_per_query"] > 0


def test_recovery_time_is_censored_when_the_attack_never_clears():
    m = run(cfg(Strategy.NAIVE, FaultMode.SYBIL, seed=0)).metrics
    assert m["recovered"] in (0.0, 1.0)
    if not m["recovered"]:
        assert m["recovery_rounds"] == 10 - 3 + 1
    m2 = run(cfg(Strategy.QUARANTINE, FaultMode.PLAIN, seed=0)).metrics
    assert m2["recovered"] == 1.0 and m2["recovery_rounds"] <= 2


def test_overhead_is_ordered_by_how_much_provenance_is_shown():
    tok = {s: run(cfg(s, seed=0)).metrics["context_tokens_per_query"] for s in Strategy}
    assert tok[Strategy.NAIVE] < tok[Strategy.CONFIDENCE] < tok[Strategy.PROVENANCE] < tok[Strategy.VERIFIED]


def test_invalid_configs_are_rejected():
    with pytest.raises(ValueError):
        run(cfg(fault=FaultSpec(n_faulty=5), n_agents=6))
    with pytest.raises(ValueError):
        run(cfg(honest_sources=6, n_agents=6))


def test_agent_count_is_respected():
    assert run(cfg(n_agents=10)).metrics["n_honest"] == 9.0
