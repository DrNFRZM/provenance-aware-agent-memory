# Reproduction check

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
