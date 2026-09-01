#!/bin/bash
# tests/run_tests.sh
# Thin shim to tests/run_tests.py, kept as .sh for parity with the
# lhcb-cwl-example / crab-cwl naming convention.
set -euo pipefail
exec python3 "$(dirname "${BASH_SOURCE[0]}")/run_tests.py"
