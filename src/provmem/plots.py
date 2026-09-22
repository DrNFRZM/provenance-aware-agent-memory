"""Two figures generated from the summary table. Nothing is drawn that is not in the CSV."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

STRATEGY_ORDER = ["naive", "confidence", "provenance", "verified", "quarantine"]
COLORS = {"naive": "#7f7f7f", "confidence": "#E69F00", "provenance": "#0072B2",
          "verified": "#009E73", "quarantine": "#CC79A7"}
ATTACK_ORDER = ["plain", "forged_meta", "sybil", "sybil_evasive"]


def _style(ax) -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.grid(axis="y", alpha=0.25)


def strategy_comparison(summary: pd.DataFrame, path: Path) -> None:
    df = summary[summary.experiment == "strategies"]
    fig, (a, b) = plt.subplots(1, 2, figsize=(11, 4), gridspec_kw={"width_ratios": [2.3, 1]})
    width = 0.16
    x = np.arange(len(ATTACK_ORDER))
    for i, s in enumerate(STRATEGY_ORDER):
        rows = df[df.strategy == s].set_index("scenario").reindex(ATTACK_ORDER)
        a.bar(x + (i - 2) * width, rows.asr_post_mean_mean, width,
              yerr=rows.asr_post_mean_sd, color=COLORS[s], label=s, capsize=2)
    a.set_xticks(x, ATTACK_ORDER)
    a.set_ylabel("attack success rate")
    a.set_ylim(0, 1.0)
    a.set_title("False answers on targeted facts, after injection")
    a.legend(frameon=False, ncol=3, fontsize=8)
    _style(a)

    ctrl = df[df.scenario == "none"].set_index("strategy").reindex(STRATEGY_ORDER)
    b.bar(range(len(STRATEGY_ORDER)), ctrl.clean_accuracy_mean_mean,
          yerr=ctrl.clean_accuracy_mean_sd, color=[COLORS[s] for s in STRATEGY_ORDER], capsize=2)
    b.set_xticks(range(len(STRATEGY_ORDER)), STRATEGY_ORDER, rotation=35, ha="right")
    b.set_ylim(0, 1.0)
    b.set_ylabel("clean answer accuracy")
    b.set_title("No attack (control)")
    _style(b)
    fig.text(0.01, 0.005, f"mean over {int(df.n_seeds.iloc[0])} seeds, bars = sample SD; "
             "synthetic simulation with a deterministic mock reader", fontsize=7, alpha=0.7)
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    fig.savefig(path, dpi=140)
    plt.close(fig)


def threshold_tradeoff(summary: pd.DataFrame, path: Path) -> None:
    df = summary[summary.experiment == "threshold"]
    fig, (a, b) = plt.subplots(1, 2, figsize=(10, 3.8), sharex=True)
    for s in ("confidence", "provenance", "verified"):
        for ax, scenario, metric, title in (
                (a, "forged_meta", "asr_post_mean", "Attack success (forged_meta)"),
                (b, "none", "clean_accuracy_mean", "Clean accuracy (no attack)")):
            rows = df[(df.strategy == s) & (df.scenario == scenario)].copy()
            rows["t"] = rows.value.astype(float)
            rows = rows.sort_values("t")
            m, e = rows[f"{metric}_mean"], rows[f"{metric}_sd"]
            ax.plot(rows.t, m, marker="o", color=COLORS[s], label=s)
            ax.fill_between(rows.t, np.clip(m - e, 0, 1), np.clip(m + e, 0, 1),
                            color=COLORS[s], alpha=0.15)
            ax.set_title(title)
            ax.set_xlabel("acceptance threshold")
            ax.set_ylim(0, 1.0)
            _style(ax)
    a.set_ylabel("rate")
    a.legend(frameon=False, fontsize=8)
    fig.text(0.01, 0.005, f"mean over {int(df.n_seeds.iloc[0])} seeds, bands = sample SD; "
             "synthetic simulation with a deterministic mock reader", fontsize=7, alpha=0.7)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path, dpi=140)
    plt.close(fig)
