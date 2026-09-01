#!/bin/bash
# tools/scripts/run_wmcore_job.sh
#
# Reproduces the documented "Running a WMCore Job Interactively or
# Manually" procedure:
#   1. Unpack the job (sandbox + JobPackage.pkl + job index -> Unpacker.py)
#   2. Enter the worker OS environment via apptainer (container name
#      chosen by discover_job.py to match the job's recorded worker_os)
#   3. Source the CVMFS COMP environment for that arch
#   4. Run the job wrapper (Startup.py)
#
# Generic across workflows/jobs: everything it needs comes in via env
# vars set by tools/run-wmcore-job.cwl's EnvVarRequirement, itself
# populated from artifacts/.generated/inputs.yml by discover_job.py.

set -euo pipefail

: "${SANDBOX:?SANDBOX (sandbox tarball path) must be set}"
: "${JOBPACKAGE:?JOBPACKAGE (JobPackage.pkl path) must be set}"
: "${JOB_INDEX:?JOB_INDEX must be set}"
: "${UNPACKER:?UNPACKER (Unpacker.py path) must be set}"

CMSSW_CONTAINER="${CMSSW_CONTAINER:-cmssw-el7}"
WORKDIR="$(pwd)"
OUTDIR="${WORKDIR}/job-output"
mkdir -p "${OUTDIR}"

echo "== [1/3] Unpacking job ${JOB_INDEX} from ${JOBPACKAGE} =="
python3 "${UNPACKER}" \
    --sandbox="${SANDBOX}" \
    --package="${JOBPACKAGE}" \
    --index="${JOB_INDEX}"

if [ ! -d "${WORKDIR}/job" ]; then
    echo "ERROR: Unpacker.py did not produce a job/ directory" >&2
    exit 1
fi

echo "== [2/3] Entering ${CMSSW_CONTAINER} (apptainer, CVMFS-backed) =="
echo "== [3/3] Running Startup.py inside the container =="

# NOTE on arch: the CVMFS init.sh paths below assume the "COMP" area
# layout is consistent across arches (slc7_amd64_gcc900, el8_amd64_gcc12,
# etc). If a given container image ships a different python3/py3-future
# version, override CVMFS_PYTHON3_INIT / CVMFS_PY3FUTURE_INIT env vars
# rather than editing this script.
CVMFS_PYTHON3_INIT="${CVMFS_PYTHON3_INIT:-/cvmfs/cms.cern.ch/COMP/${CMSSW_SCRAM_ARCH:-slc7_amd64_gcc900}/external/python3/3.8.2/etc/profile.d/init.sh}"
CVMFS_PY3FUTURE_INIT="${CVMFS_PY3FUTURE_INIT:-/cvmfs/cms.cern.ch/COMP/${CMSSW_SCRAM_ARCH:-slc7_amd64_gcc900}/external/py3-future/0.18.2/etc/profile.d/init.sh}"

"${CMSSW_CONTAINER}" --bind /cvmfs --bind "${WORKDIR}" -- /bin/bash -c "
    set -euo pipefail
    cd '${WORKDIR}/job'

    if [ -f '${CVMFS_PYTHON3_INIT}' ]; then source '${CVMFS_PYTHON3_INIT}'; fi
    if [ -f '${CVMFS_PY3FUTURE_INIT}' ]; then source '${CVMFS_PY3FUTURE_INIT}'; fi

    export WMAGENTJOBDIR=\"\$PWD\"
    export PYTHONPATH=\"\$PWD/WMCore.zip:\$PWD:\$PYTHONPATH\"

    python3 Startup.py
"

echo "== Collecting job report(s) =="
find "${WORKDIR}/job" -name 'Report*.pkl' -exec cp {} "${OUTDIR}/" \; || true
find "${WORKDIR}/job" -maxdepth 2 -name '*.log' -exec cp {} "${OUTDIR}/" \; || true

echo "== Done. Output collected under ${OUTDIR} =="
