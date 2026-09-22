# provenance-aware-agent-memory

**An empirical exploration of provenance-aware agent memory.** When an agent stores and relays
claims from other agents, does recording *where a claim came from* and *how it got here* make
the memory safer? This repository is a small, deterministic multi-agent simulation for asking
that question with synthetic, harmless misinformation, plus the tests, docs and results that
go with it.

It is a research testbed, not a library to drop into an agent framework, and not a claim of
a new method. Provenance tracking, trust scoring and quarantine are established ideas. What
this repo adds is a reproducible place to see where they help, where they do not, and why.

> Defensive AI-safety work. All facts are invented (fictional stations, planets, guilds).
> No real-world exploits, no harmful content, no network access needed. See
> [docs/threat_model.md](docs/threat_model.md) and [SECURITY.md](SECURITY.md).

## What is in the simulation

* **Memory entries** with content, originating agent, round, evidence, source confidence, hop
  count, verification state and trust score ([docs/memory_model.md](docs/memory_model.md)).
* **Five retrieval strategies:** naive similarity; similarity + confidence; provenance-aware;
  provenance + independent verification; verification + quarantine/repair.
* **Four adversary tiers** of increasing provenance forgery: `plain` (cites a document that does
  not exist), `forged_meta` (valid citation, confidence 0.99, hop 0, impersonated origin),
  `sybil` (fabricated identities), `sybil_evasive` (avoids what the verifier can check).
* **Metrics:** false-retrieval rate, answer-flip rate (counterfactual), propagation via honest
  relaying, clean accuracy, false-positive rejection, false-negative acceptance, recovery
  time, token and lookup overhead.
* **Sweeps:** trust threshold, hop cut-off, number of agents, source agreement, retrieval k,
  verifier coverage and noise, and ablations by provenance field.
* **Backends:** `DeterministicMockLLM` for everything reported. An optional adapter for a local
  OpenAI-compatible server exists and is never required. No secrets, no downloads.

## Quick start

```bash
pip install -e ".[dev]"          # numpy, pandas, matplotlib, pytest
python -m pytest                 # 70 tests, about 30 s
python -m provmem demo --scenario forged_meta --seed 0
python -m provmem bench --profile quick --out results/quick   # regenerates the results below
```

Without installing: `PYTHONPATH=src python -m provmem demo` works from the repo root.

Example `demo` output (one seed, so noisy; the table below is the 8-seed result):

```
strategy    ASR(post) false-retr   flip  spread clean-acc  FN-acc  FP-rej tokens/q
naive            0.20       0.70   0.19    0.50      0.86    1.00    0.00     36.5
confidence       0.20       0.70   0.19    0.50      0.86    1.00    0.00     39.5
provenance       0.17       0.70   0.17    0.50      0.86    1.00    0.00     51.5
verified         0.06       0.36   0.05    0.27      0.86    0.70    0.00     54.5
quarantine       0.00       0.00   0.00    0.00      0.90    0.00    0.03     54.5
```

## Results snapshot

Real measurements from `results/quick/` (8 evaluation seeds 1000-1007, 275 configurations,
2,200 runs, mock reader). Values below are mean ± sample standard deviation across seeds.
The spread describes sensitivity to seeded simulator variation; it is not a confidence interval
or evidence about a population of real agents. Full tables:
[results/quick/report.md](results/quick/report.md); raw runs: `results/quick/raw_runs.csv`;
aggregated: `results/quick/summary.csv`.

Attack success rate (false answers on targeted facts after injection; the no-attack control is
0.05 to 0.08 because honest errors exist):

| strategy | plain | forged_meta | sybil | sybil_evasive |
|---|---|---|---|---|
| naive similarity | 0.136 ± 0.116 | 0.136 ± 0.116 | 0.457 ± 0.142 | 0.482 ± 0.101 |
| similarity + confidence | 0.208 ± 0.131 | 0.268 ± 0.109 | 0.523 ± 0.156 | 0.518 ± 0.099 |
| provenance-aware | 0.080 ± 0.117 | 0.247 ± 0.111 | 0.515 ± 0.157 | 0.504 ± 0.092 |
| provenance + verification | 0.058 ± 0.107 | 0.153 ± 0.114 | 0.309 ± 0.178 | 0.537 ± 0.121 |
| verification + quarantine | 0.059 ± 0.105 | 0.071 ± 0.134 | 0.111 ± 0.241 | 0.552 ± 0.122 |

![strategy comparison](results/quick/strategy_comparison.png)
![threshold tradeoff](results/quick/threshold_tradeoff.png)

What the numbers support, in plain terms (details and caveats in
[docs/research_note.md](docs/research_note.md)):

* Provenance metadata is a good filter against a **careless** fabricator (false retrieval
  0.711 to 0.122) and gives **no retrieval benefit** once the adversary can copy valid-looking
  metadata (0.711 to 0.711); its ASR point estimate is even higher than naive's.
* Self-reported confidence never helped, and a high confidence threshold made things worse.
* Most of the robust gain came from an **independent check** and from **distrusting the origin**
  after a refutation (quarantine cascade), not from the metadata fields themselves.
* That gain disappears against an attacker who avoids the facts the verifier can check.
* At the default threshold, mean clean accuracy stayed between 0.93 and 0.95 in the
  control. Costs show up at thresholds of 0.65 and above, with a noisy verifier (10% error takes
  quarantine clean accuracy from 0.94 to 0.84), and from impersonation collateral.
* Overhead per query: about 1.4x context tokens for provenance annotations, 4x candidates scored,
  about 0.28 verifier lookups per query at 50% coverage.
* Which field matters: evidence resolvability against a sloppy fabricator; multi-origin agreement
  is the only field that helped against a single forger, and it fails against fabricated identities.

## Limitations, up front

The reader is a deterministic mock, not a real LLM; the verifier is an oracle on the facts it
covers; claims are structured; the world has 45 static facts; there are 8 seeds; trust weights are
hand-set; attackers barely adapt. These results are about a *retrieval and relaying policy in a
toy world*. They are not evidence that any deployed agent is safe or unsafe.
See [docs/research_note.md](docs/research_note.md) section 5.

## Repository map

```
src/provmem/
  schema.py        MemoryEntry, Claim, Evidence, JSONL (de)serialisation
  ledger.py        per-agent store: similarity index, claim-key index, quarantine
  scoring.py       provenance trust components and ablation switches
  retrieval.py     the five strategies, acceptance rule, context rendering
  verify.py        independent verifier (coverage, noise), cached lookups
  quarantine.py    refutation -> quarantine, origin cascade, retractions, audit
  world.py         invented facts and value pools
  faults.py        fault modes (plain / forged_meta / sybil) and evasion
  agents.py        honest agent: observe, relay, answer
  simulation.py    gossip rounds, probes, metrics
  experiments.py   experiment grids, deterministic parallel runner, aggregation
  report.py plots.py cli.py   markdown tables, figures, `python -m provmem`
  llm.py embedding.py seeding.py   mock reader (+ optional adapter), embedders, seeded RNG
tests/             70 tests: serialisation, retrieval, scoring, faults, quarantine,
                   determinism, thresholds, CLI
docs/              memory_model, threat_model, research_note, design_decisions,
                   interview_guide, learning_roadmap
results/quick/     raw_runs.csv, summary.csv, report.md, two PNG plots
```

## Reproducibility

Every random choice is a `random.Random` seeded from a blake2b digest of (seed, label). Python's
salted `hash()` is not used, and the parallel runner preserves job order. A test asserts identical
frames for 1 and 2 workers and byte-identical CSVs across invocations. `summary.csv` is computed
from the serialized `raw_runs.csv`, so the aggregate has a direct artifact trail. Development and
tests use seeds below 1000; reported results use 1000 and above.

## Optional pieces

* Semantic embeddings: `pip install -e ".[embeddings]"`, then pass
  `SentenceTransformerEmbedder` to `Ledger`. Not used in any reported number; the model is downloaded
  by that library on first use and is not part of this repo.
* Local LLM: `OpenAICompatibleLLM(base_url="http://localhost:11434/v1", model=...)` for a local
  llama.cpp/Ollama/vLLM server. Untested against a live server; not used in any reported number.

## Docs

| file | contents |
|---|---|
| [docs/memory_model.md](docs/memory_model.md) | exact schema, trust formula, retrieval scoring, metric definitions |
| [docs/threat_model.md](docs/threat_model.md) | assumptions, adversary tiers, security reasoning, out-of-scope |
| [docs/research_note.md](docs/research_note.md) | question, results, verdict on the hypothesis, threats to validity |
| [docs/design_decisions.md](docs/design_decisions.md) | why it is built this way, including three things I got wrong first |
| [docs/interview_guide.md](docs/interview_guide.md) | 26 hard questions with technical answers |
| [docs/learning_roadmap.md](docs/learning_roadmap.md) | next steps and reading |
| [SECURITY.md](SECURITY.md) | safe scope and responsible reporting |

## Author and license

Farzam Nikbakhsh Jorshari (nikbakhshfarzam@gmail.com). MIT license.
