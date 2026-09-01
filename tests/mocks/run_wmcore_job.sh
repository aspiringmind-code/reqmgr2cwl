#!/bin/bash
# tests/mocks/run_wmcore_job.sh
#
# Mocked replacement for tools/scripts/run_wmcore_job.sh. Exercises the
# same env-var contract (SANDBOX/JOBPACKAGE/JOB_INDEX/UNPACKER) but skips
# cmssw-el7/CVMFS entirely, so wiring can be tested anywhere cwltool runs.
set -euo pipefail

echo "MOCK run_wmcore_job.sh: SANDBOX=$SANDBOX JOBPACKAGE=$JOBPACKAGE JOB_INDEX=$JOB_INDEX UNPACKER=$UNPACKER CMSSW_CONTAINER=${CMSSW_CONTAINER:-unset}"

python3 "$UNPACKER" --sandbox="$SANDBOX" --package="$JOBPACKAGE" --index="$JOB_INDEX"

mkdir -p job-output
echo "mock ok" > job-output/result.txt
