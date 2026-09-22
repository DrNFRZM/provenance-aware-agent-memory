#!/usr/bin/env sh
# Runs the test suite and a small deterministic benchmark. No network, no API keys.
set -eu
cd "$(dirname "$0")/.."
export PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}"
python -m pytest
python -m provmem demo --scenario forged_meta --seed 0
python -m provmem bench --profile smoke --jobs 1 --out "${TMPDIR:-/tmp}/provmem-smoke"
