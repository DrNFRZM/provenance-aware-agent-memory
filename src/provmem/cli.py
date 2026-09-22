"""Command line: `python -m provmem demo | bench | report`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from .experiments import (EVAL_SEED_BASE, EXPERIMENTS, PROFILES, SMOKE_EXPERIMENTS, build_jobs, default_jobs,
                          run_jobs, summarise)
from .faults import FaultMode, FaultSpec
from .report import write_outputs
from .retrieval import RetrievalConfig, Strategy
from .simulation import SimConfig, run


def cmd_demo(args: argparse.Namespace) -> int:
    print(f"scenario={args.scenario} seed={args.seed} (synthetic facts only)\n")
    header = f"{'strategy':<11}{'ASR(post)':>10}{'false-retr':>11}{'flip':>7}{'spread':>8}" \
             f"{'clean-acc':>10}{'FN-acc':>8}{'FP-rej':>8}{'tokens/q':>9}"
    print(header)
    for strat in Strategy:
        cfg = SimConfig(seed=args.seed, fault=FaultSpec(mode=FaultMode(args.scenario)),
                        retrieval=RetrievalConfig(strategy=strat))
        m = run(cfg).metrics
        print(f"{strat.value:<11}{m['asr_post_mean']:>10.2f}{m['false_retrieval_rate']:>11.2f}"
              f"{m['answer_flip_rate']:>7.2f}{m['propagation_final']:>8.2f}"
              f"{m['clean_accuracy_mean']:>10.2f}{m['fn_accept_injected']:>8.2f}"
              f"{m['fp_reject_rate']:>8.2f}{m['context_tokens_per_query']:>9.1f}")
    return 0


def cmd_bench(args: argparse.Namespace) -> int:
    n_seeds = args.seeds if args.seeds else PROFILES[args.profile]
    seeds = list(range(args.seed_base, args.seed_base + n_seeds))
    names = list(SMOKE_EXPERIMENTS if args.profile == "smoke" else EXPERIMENTS)
    if args.only:
        names = args.only
    jobs = build_jobs(names)
    print(f"{len(jobs)} configurations x {len(seeds)} seeds = {len(jobs) * len(seeds)} runs")
    raw = run_jobs(jobs, seeds, args.jobs)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    raw_path = out / "raw_runs.csv"
    raw.to_csv(raw_path, index=False, float_format="%.6g", lineterminator="\n")
    # Aggregate the serialized artifact, not a higher-precision in-memory copy. This keeps
    # summary.csv exactly traceable to the committed raw_runs.csv.
    summary = summarise(pd.read_csv(raw_path))
    summary.to_csv(out / "summary.csv", index=False, float_format="%.6g", lineterminator="\n")
    print(f"wrote {out / 'raw_runs.csv'} and {out / 'summary.csv'}")
    for path in write_outputs(summary, out, plots=not args.no_plots):
        print(f"wrote {path}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    out = Path(args.dir)
    for path in write_outputs(pd.read_csv(out / "summary.csv"), out):
        print(f"wrote {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="provmem", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo", help="compare the five strategies on one seed")
    d.add_argument("--scenario", default="forged_meta",
                   choices=[m.value for m in FaultMode])
    d.add_argument("--seed", type=int, default=0)
    d.set_defaults(fn=cmd_demo)
    b = sub.add_parser("bench", help="run the experiment grids and write CSVs and plots")
    b.add_argument("--profile", choices=list(PROFILES), default="quick")
    b.add_argument("--seeds", type=int, default=0, help="override the profile's seed count")
    b.add_argument("--seed-base", type=int, default=EVAL_SEED_BASE)
    b.add_argument("--only", nargs="+", choices=list(EXPERIMENTS))
    b.add_argument("--out", default="results/quick")
    b.add_argument("--jobs", type=int, default=default_jobs())
    b.add_argument("--no-plots", action="store_true")
    b.set_defaults(fn=cmd_bench)
    r = sub.add_parser("report", help="regenerate plots and report.md from an existing summary.csv")
    r.add_argument("--dir", default="results/quick")
    r.set_defaults(fn=cmd_report)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
