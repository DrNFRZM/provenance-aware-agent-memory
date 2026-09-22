import pandas as pd

from provmem.cli import main
from provmem.experiments import EXPERIMENTS, build_jobs, run_jobs, summarise


def _tiny_jobs():
    return build_jobs(["strategies"])[:6]


def test_every_experiment_builds_jobs():
    for name, fn in EXPERIMENTS.items():
        jobs = list(fn())
        assert jobs, name
        assert all(j.experiment == name for j in jobs)


def test_grid_is_deterministic_and_independent_of_worker_count():
    jobs = _tiny_jobs()
    a = run_jobs(jobs, [0, 1], n_jobs=1)
    b = run_jobs(jobs, [0, 1], n_jobs=1)
    c = run_jobs(jobs, [0, 1], n_jobs=2)
    pd.testing.assert_frame_equal(a, b)
    pd.testing.assert_frame_equal(a, c)


def test_summary_shape():
    raw = run_jobs(_tiny_jobs(), [0, 1, 2], n_jobs=1)
    s = summarise(raw)
    assert len(s) == len(_tiny_jobs())
    assert (s.n_seeds == 3).all()
    assert {"asr_post_mean_mean", "asr_post_mean_sd", "clean_accuracy_mean_mean"} <= set(s.columns)
    assert not any(c.endswith("_sem") for c in s.columns)


def test_cli_bench_writes_reproducible_csvs(tmp_path):
    for name in ("a", "b"):
        rc = main(["bench", "--profile", "smoke", "--seeds", "1", "--only", "strategies",
                   "--jobs", "1", "--no-plots", "--out", str(tmp_path / name)])
        assert rc == 0
    for f in ("raw_runs.csv", "summary.csv"):
        assert (tmp_path / "a" / f).read_bytes() == (tmp_path / "b" / f).read_bytes()


def test_cli_demo_runs(capsys):
    assert main(["demo", "--scenario", "plain", "--seed", "1"]) == 0
    out = capsys.readouterr().out
    assert "quarantine" in out and "naive" in out


def test_report_regenerates_from_committed_summary(tmp_path):
    import shutil
    from pathlib import Path
    src = Path(__file__).resolve().parents[1] / "results" / "quick" / "summary.csv"
    shutil.copy(src, tmp_path / "summary.csv")
    assert main(["report", "--dir", str(tmp_path)]) == 0
    text = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "## strategies" in text and "## ablation" in text
    assert (tmp_path / "strategy_comparison.png").stat().st_size > 5000
