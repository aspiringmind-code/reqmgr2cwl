#!/bin/bash
# run.sh
#
# Convenience entry point: discover whatever is under artifacts/, then
# validate and run the CWL workgraph against it.
#
#   ./run.sh                     # uses ./artifacts, real run_wmcore_job.sh
#   ARTIFACTS_DIR=other ./run.sh # point at a different artifacts folder
#   RUN_SCRIPT=tests/mocks/run_wmcore_job.sh ./run.sh   # mocked wiring run
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARTIFACTS_DIR="${ARTIFACTS_DIR:-$REPO_ROOT/artifacts}"
RUN_SCRIPT="${RUN_SCRIPT:-$REPO_ROOT/tools/scripts/run_wmcore_job.sh}"
OUTDIR="${OUTDIR:-$REPO_ROOT/results}"
CONTAINER_ARGS=()
if [ -n "${CONTAINER_OVERRIDE:-}" ]; then
    CONTAINER_ARGS=(--container-override "$CONTAINER_OVERRIDE")
fi

echo "== Step 1/3: discovering job from artifacts under $ARTIFACTS_DIR =="
INPUTS_YML="$(python3 "$REPO_ROOT/scripts/discover_job.py" \
    --artifacts-dir "$ARTIFACTS_DIR" \
    --run-script "$RUN_SCRIPT" \
    "${CONTAINER_ARGS[@]}" | tail -1)"

echo "== Step 2/3: validating CWL =="
cwltool --validate "$REPO_ROOT/workflows/workgraph.cwl"

echo "== Step 3/3: running =="
cwltool --outdir "$OUTDIR" \
    "$REPO_ROOT/workflows/workgraph.cwl" \
    "$INPUTS_YML"

echo "== Done. Output under $OUTDIR =="
