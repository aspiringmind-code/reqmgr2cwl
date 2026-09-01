#!/usr/bin/env cwl-runner
# tools/run-wmcore-job.cwl
#
# Fully generic: unpacks and runs whatever resolved WMAgent job it is
# given (sandbox + JobPackage.pkl + job index + Unpacker.py), inside the
# worker OS container that job actually recorded. No workflow-, job-, or
# step-specific values are hardcoded here -- everything comes in as
# CWL inputs, populated by scripts/discover_job.py from the four
# artifacts under artifacts/.
#
# Analog of LHCb's tools/lb-ap-run-app.cwl / crab-cwl's embedded cmsRun
# CommandLineTool: one generic runner fed a resolved job description.

cwlVersion: v1.2
class: CommandLineTool

requirements:
  InlineJavascriptRequirement: {}
  InitialWorkDirRequirement:
    listing:
      - entry: $(inputs.sandbox)
      - entry: $(inputs.job_package)
      - entry: $(inputs.unpacker_script)
      - entry: $(inputs.run_script)
  EnvVarRequirement:
    envDef:
      SANDBOX: $(inputs.sandbox.basename)
      JOBPACKAGE: $(inputs.job_package.basename)
      JOB_INDEX: $(String(inputs.job_index))
      UNPACKER: $(inputs.unpacker_script.basename)
      CMSSW_CONTAINER: $(inputs.cmssw_container)
      CMSSW_SCRAM_ARCH: $(inputs.scram_arch)

hints:
  ResourceRequirement:
    coresMin: $(inputs.num_cores)
    ramMin: $(inputs.memory_mb)
  # CVMFS + apptainer are required on the execution host; not expressible
  # as a standard CWL requirement, so recorded as an ignorable, namespaced
  # hint (same pattern as dirac:/cms: in the LHCb / crab-cwl examples).
  wmcore:ExecutionEnvironment:
    container: $(inputs.cmssw_container)
    cvmfsRequired: true

baseCommand: ["bash"]
arguments:
  - valueFrom: $(inputs.run_script.basename)

inputs:
  sandbox:
    type: File
    doc: "<workflow>-Sandbox.tar.bz2"
  job_package:
    type: File
    doc: "JobPackage.pkl for the JobCollection this job belongs to"
  unpacker_script:
    type: File
    doc: "Unpacker.py (extracted from the sandbox's WMCore.zip by discover_job.py)"
  run_script:
    type: File
    doc: "Wrapper implementing the unpack + container + Startup.py sequence"
  job_index:
    type: int
    doc: "WMBS job index within the package"
  num_cores:
    type: int
    default: 1
  memory_mb:
    type: int
    default: 2000
  cmssw_container:
    type: string
    default: "cmssw-el7"
    doc: "apptainer wrapper matching the job's recorded worker_os"
  scram_arch:
    type: string
    default: "slc7_amd64_gcc900"
    doc: "ScramArch for this step; used to pick the right CVMFS COMP init.sh paths"

outputs:
  job_output:
    type: Directory
    outputBinding:
      glob: job-output
  job_dir:
    type: Directory
    outputBinding:
      glob: job
    doc: "Full unpacked WMTaskSpace, for debugging"

$namespaces:
  wmcore: "https://cms.cern/wmcore-cwl-extensions#"
