# Reproduction check

## 11 November 2026 maintenance verification

The AI-assisted maintenance pass used Python 3.12.16 on Windows with NumPy
2.3.5, pandas 2.2.3, and Matplotlib 3.10.8. The shared audit environment passed
its dependency consistency check.

All 70 tests passed. A fresh quick benchmark with two workers completed
275 configurations over eight seeds (2,200 runs). Its `raw_runs.csv` (2,200 rows)
and `summary.csv` (275 rows) matched the committed files within relative and
absolute tolerance 1e-12. The report and figures were regenerated in a separate
local directory; PNG bytes were not compared.

The original result artifacts were retained. This check used invented facts
and the deterministic mock reader; no real-model adapter or paid API was used.
It does not validate defenses for real LLM agents.

## Earlier verification record

The project was installed with `pip install -e ".[dev]"` in a fresh Python
3.12.14 virtual environment on Linux, CPU only. Dependencies resolved to NumPy
2.5.4, pandas 3.0.6, and Matplotlib 3.11.2; `pip check` reported no conflicts.

All 70 tests passed. The `forged_meta` demo completed, followed by a fresh
`python -m provmem bench --profile quick --out /tmp/provmem-verification`.
That run evaluated 275 configurations over eight seeds, producing 2,200 runs.

The fresh `raw_runs.csv` and `summary.csv` were compared with the committed
files in `results/quick/`. Their rows and columns agreed, and all numerical
fields matched within relative and absolute tolerances of 1e-12. Both figures
and the Markdown report were also regenerated; PNG byte equality was not
required.

These checks cover the deterministic mock backend and the synthetic facts used
by the reported experiment. The optional local-model adapter was not exercised.
They do not establish performance or safety for real LLM agents.
