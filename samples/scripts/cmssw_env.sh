# CMSSW environment helpers, sourced by the CWL tools in cwl/tools/.
#
# Each CWL step runs in a fresh process, so the "environment" pre-step cannot be
# a CWL step of its own: every tool that needs CMSSW sources this file and calls
# these functions itself. Only functions are defined here; nothing runs at source time.
#
# Exit codes follow ep_scripts/execute_stepchain.sh
# (https://twiki.cern.ch/twiki/bin/view/CMSPublic/JobExitCodes).

EXIT_NO_CMSSET=11003         # CMS software area (cmsset_default.sh) not found
EXIT_SCRAM=71                # Failed to initiate Scram project
EXIT_CFG_GEN=10040           # Failed to generate cmsRun cfg file at runtime
EXIT_CMSRUN_UNKNOWN=50116    # Could not determine exit code of cmsRun executable at runtime

log() {
    echo "[cwl-cmssw] $*" >&2
}

# Source cmsset_default.sh (same lookup as setup_cmsset in ep_scripts/submit_env.sh,
# minus the OSG_APP fallback). VO_CMS_SW_DIR wins, then /cvmfs/cms.cern.ch.
cmssw_env_setup() {
    local cms_dir="${VO_CMS_SW_DIR:-/cvmfs/cms.cern.ch}"
    if [ ! -f "$cms_dir/cmsset_default.sh" ]; then
        log "cmsset_default.sh not found in $cms_dir (is /cvmfs mounted?)"
        exit $EXIT_NO_CMSSET
    fi
    log "Loading CMS environment from $cms_dir"
    . "$cms_dir/cmsset_default.sh"
}

# Create a scram project area in the current directory.
# Usage: cmssw_project_create <CMSSW_VERSION> <SCRAM_ARCH>
cmssw_project_create() {
    export SCRAM_ARCH="$2"
    log "scram project $1 (SCRAM_ARCH=$SCRAM_ARCH)"
    scram project "$1" || { log "scram project failed"; exit $EXIT_SCRAM; }
}

# Load the runtime environment of a project area made by an earlier CWL step.
# The staged area may be read-only and may sit at a different path than where it
# was created, so work on a private copy (cp -a keeps the /cvmfs symlinks as
# symlinks) and let scram fix the paths recorded inside it.
# Usage: cmssw_project_enter <staged project dir> <SCRAM_ARCH>
cmssw_project_enter() {
    local area_copy
    export SCRAM_ARCH="$2"
    area_copy="${TMPDIR:-/tmp}/$(basename "$1")"
    rm -rf "$area_copy"
    cp -a "$1" "$area_copy" || { log "cannot copy project area $1"; exit $EXIT_SCRAM; }
    chmod -R u+w "$area_copy"
    pushd "$area_copy" > /dev/null
    scram build ProjectRename > /dev/null || { log "scram ProjectRename failed in $area_copy"; exit $EXIT_SCRAM; }
    eval "$(scram runtime -sh)" || { log "scram runtime failed in $area_copy"; exit $EXIT_SCRAM; }
    popd > /dev/null
    log "Using $CMSSW_VERSION from $CMSSW_BASE"
}

# Exit with a meaningful code after cmsRun. cmsRun can exit 0 despite a failure,
# so the framework job report is checked as well (same logic as execute_stepchain.sh).
# Usage: cmssw_check_cmsrun <cmsRun exit code> <job_report.xml>
cmssw_check_cmsrun() {
    local rc="$1" report="$2" report_exit
    if [ "$rc" -ne 0 ]; then
        log "cmsRun failed (exit code $rc)"
        exit "$rc"
    fi
    if [ -f "$report" ] && grep -qE 'FrameworkError|Status="Failed"' "$report"; then
        report_exit=$(grep -oE 'ExitStatus="[0-9]+"' "$report" | head -1 | grep -oE '[0-9]+')
        log "Job report indicates cmsRun failure (ExitStatus=${report_exit:-unknown})"
        exit "${report_exit:-$EXIT_CMSRUN_UNKNOWN}"
    fi
    log "cmsRun completed"
}
