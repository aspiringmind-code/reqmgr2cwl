# Mock of /cvmfs/cms.cern.ch/cmsset_default.sh for cwl/tests: puts the mock
# scram, cmsRun and cmssw-wm-tools first on PATH.
MOCK_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="$MOCK_ROOT/bin:$PATH"
