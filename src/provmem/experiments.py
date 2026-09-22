"""Experiment grids, the (parallel, order-preserving) runner and result aggregation."""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, replace
from typing import Iterator

import pandas as pd

from .faults import FaultMode, FaultSpec
from .retrieval import RetrievalConfig, Strategy
from .scoring import TRUST_FIELDS, ScoringConfig
from .simulation import SimConfig, run

SCENARIOS: dict[str, FaultSpec] = {
    "none": FaultSpec(mode=FaultMode.NONE),
    "plain": FaultSpec(mode=FaultMode.PLAIN),
    "forged_meta": FaultSpec(mode=FaultMode.FORGED_META),
    "sybil": FaultSpec(mode=FaultMode.SYBIL),
    "sybil_evasive": FaultSpec(mode=FaultMode.SYBIL, evasive=True),
}
ATTACKS = ("plain", "forged_meta", "sybil", "sybil_evasive")

PROFILES = {"smoke": 2, "quick": 8, "full": 30}
# Seeds 0-999 were used informally during development and in the tests; reported
# results use seeds from 1000 upward, which no design decision was made on.
EVAL_SEED_BASE = 1000

METRICS = ["asr_final", "asr_post_mean", "false_retrieval_rate", "answer_flip_rate",
           "propagation_final", "propagation_peak", "exposure_final", "clean_accuracy_final",
           "clean_accuracy_mean", "clean_unknown_final", "target_accuracy_final",
           "fp_reject_rate", "fn_accept_rate", "fn_accept_injected", "recovery_rounds",
           "recovered", "context_tokens_per_query", "scored_per_query", "verifier_lookups",
           "messages"]


@dataclass(frozen=True)
class Job:
    experiment: str
    scenario: str
    strategy: str
    variant: str
    param: str
    value: str
    cfg: SimConfig

    def labels(self) -> dict[str, str]:
        return {"experiment": self.experiment, "scenario": self.scenario,
                "strategy": self.strategy, "variant": self.variant, "param": self.param,
                "value": self.value}


def _retrieval(strategy: Strategy, **kw) -> RetrievalConfig:
    return RetrievalConfig(strategy=strategy, **kw)


def _job(exp: str, scenario: str, strategy: Strategy, variant: str = "default", param: str = "",
         value: object = "", retrieval: RetrievalConfig | None = None, **sim_kw) -> Job:
    fault = sim_kw.pop("fault", SCENARIOS[scenario])
    cfg = SimConfig(fault=fault, retrieval=retrieval or _retrieval(strategy), **sim_kw)
    return Job(exp, scenario, strategy.value, variant, param, str(value), cfg)


def exp_strategies() -> Iterator[Job]:
    for sc in SCENARIOS:
        for st in Strategy:
            yield _job("strategies", sc, st)


def exp_threshold() -> Iterator[Job]:
    for sc in ("none", "plain", "forged_meta"):
        for st in (Strategy.CONFIDENCE, Strategy.PROVENANCE, Strategy.VERIFIED):
            for tau in (0.2, 0.35, 0.5, 0.65, 0.8):
                yield _job("threshold", sc, st, param="threshold", value=tau,
                           retrieval=_retrieval(st, threshold=tau))


def exp_hops() -> Iterator[Job]:
    for sc in ("none", "forged_meta"):
        for st in (Strategy.PROVENANCE, Strategy.VERIFIED):
            for h in (1, 2, 3, 4, None):
                yield _job("hops", sc, st, param="max_hops", value=h if h is not None else "none",
                           retrieval=_retrieval(st, max_hops=h))


def exp_agents() -> Iterator[Job]:
    for sc in ("none", "forged_meta"):
        for st in (Strategy.NAIVE, Strategy.PROVENANCE, Strategy.VERIFIED, Strategy.QUARANTINE):
            for n in (4, 6, 10, 16):
                yield _job("agents", sc, st, param="n_agents", value=n, n_agents=n)


def exp_agreement() -> Iterator[Job]:
    for st in (Strategy.NAIVE, Strategy.PROVENANCE, Strategy.VERIFIED):
        for honest in (1, 2, 3):
            for colluders in (1, 2, 3):
                fault = replace(SCENARIOS["forged_meta"], n_faulty=colluders)
                yield _job("agreement", "forged_meta", st, variant=f"honest{honest}_faulty{colluders}",
                           param="honest_sources", value=honest, fault=fault, n_agents=8,
                           honest_sources=honest)


def exp_k() -> Iterator[Job]:
    for sc in ("none", "forged_meta"):
        for st in (Strategy.NAIVE, Strategy.PROVENANCE, Strategy.VERIFIED):
            for k in (1, 3, 5, 8):
                yield _job("k", sc, st, param="k", value=k, retrieval=_retrieval(st, k=k))


def exp_ablation() -> Iterator[Job]:
    base = ScoringConfig()
    prov_variants: dict[str, ScoringConfig] = {"full": base}
    for f in TRUST_FIELDS:
        prov_variants[f"drop_{f}"] = base.without(f)
    for f in TRUST_FIELDS:
        prov_variants[f"only_{f}"] = base.only(f)
    for sc in ("none", "plain", "forged_meta", "sybil"):
        for name, scoring in prov_variants.items():
            yield _job("ablation", sc, Strategy.PROVENANCE, variant=name,
                       retrieval=_retrieval(Strategy.PROVENANCE, scoring=scoring))
    for sc in ("none", "forged_meta", "sybil"):
        for name in ["full"] + [f"drop_{f}" for f in TRUST_FIELDS]:
            yield _job("ablation", sc, Strategy.VERIFIED, variant=name,
                       retrieval=_retrieval(Strategy.VERIFIED, scoring=prov_variants[name]))
    for sc in ("none", "forged_meta", "sybil", "sybil_evasive"):
        for name, kw in {"full": {}, "no_cascade": {"suspicion_limit": 10**6},
                         "no_retraction": {"retraction_quorum": 10**6},
                         "no_audit": {"audit_budget": 0}}.items():
            yield _job("ablation", sc, Strategy.QUARANTINE, variant=name, **kw)


def exp_coverage() -> Iterator[Job]:
    for sc in ("forged_meta", "sybil_evasive"):
        for st in (Strategy.VERIFIED, Strategy.QUARANTINE):
            # At full coverage there are no uncovered facts for an evasive attacker to target.
            coverages = (0.0, 0.25, 0.5, 0.75, 1.0) if sc == "forged_meta" else (0.0, 0.25, 0.5, 0.75)
            for c in coverages:
                yield _job("coverage", sc, st, param="verifier_coverage", value=c,
                           verifier_coverage=c)
    for st in (Strategy.VERIFIED, Strategy.QUARANTINE):
        for nz in (0.0, 0.1, 0.2):
            yield _job("coverage", "forged_meta", st, variant="noise", param="verifier_noise",
                       value=nz, verifier_noise=nz)


EXPERIMENTS = {"strategies": exp_strategies, "threshold": exp_threshold, "hops": exp_hops,
               "agents": exp_agents, "agreement": exp_agreement, "k": exp_k,
               "ablation": exp_ablation, "coverage": exp_coverage}
SMOKE_EXPERIMENTS = ("strategies", "threshold")


def _run_one(job_seed: tuple[Job, int]) -> dict:
    job, seed = job_seed
    result = run(replace(job.cfg, seed=seed))
    return {**job.labels(), "seed": seed, **result.metrics}


def run_jobs(jobs: list[Job], seeds: list[int], n_jobs: int = 1) -> pd.DataFrame:
    work = [(j, s) for j in jobs for s in seeds]
    if n_jobs > 1:
        with ProcessPoolExecutor(max_workers=n_jobs) as pool:
            rows = list(pool.map(_run_one, work, chunksize=8))
    else:
        rows = [_run_one(w) for w in work]
    return pd.DataFrame(rows)


def build_jobs(names: list[str]) -> list[Job]:
    return [j for n in names for j in EXPERIMENTS[n]()]


def default_jobs() -> int:
    return max(1, min(4, (os.cpu_count() or 2) - 1))


def summarise(raw: pd.DataFrame) -> pd.DataFrame:
    keys = ["experiment", "scenario", "strategy", "variant", "param", "value"]
    g = raw.groupby(keys, sort=False, dropna=False)
    out = g[METRICS].mean().add_suffix("_mean")
    spread = g[METRICS].std(ddof=1).add_suffix("_sd")
    out = out.join(spread)
    out.insert(0, "n_seeds", g.size())
    return out.reset_index()
