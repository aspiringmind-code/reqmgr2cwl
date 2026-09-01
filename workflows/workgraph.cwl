#!/usr/bin/env cwl-runner
# workflows/workgraph.cwl
#
# Generic outermost Workgraph for a ReqMgr2 request. No request name,
# job index, or step details are hardcoded -- this file is identical
# for every workflow/job combination you point scripts/discover_job.py
# at. Mirrors the LHCb DiracX Workgraph pattern: the DAG is expressed as
# ordinary CWL dataflow, and all ReqMgr2-specific orchestration metadata
# travels as an ignorable `wmcore:` hint built from input expressions.
#
# SCOPE, STATED EXPLICITLY (same for every request run through this file):
#   Only the ONE step backed by a resolved WMAgent job (the job you
#   pointed discover_job.py at) is wired as an executable `steps:` entry.
#   Any other Step<N>/Task<N> entries present in the ReqMgr2 request are
#   NOT executed here -- they require either their own resolved job
#   package (same manual-extraction procedure) or a reimplementation of
#   WMCore's job-splitting algorithm against DBS, neither of which this
#   PoC attempts. The full request document is attached below
#   (reqmgr2_json) so those other steps remain inspectable/traceable
#   even though they aren't run.

cwlVersion: v1.2
class: Workflow

requirements:
  SubworkflowFeatureRequirement: {}
  InlineJavascriptRequirement: {}

hints:
  wmcore:Workgraph:
    requestName: $(inputs.request_name)
    requestType: $(inputs.request_type)
    requestStatus: $(inputs.request_status)
    requestor: $(inputs.requestor)
    prepID: $(inputs.prep_id)
    campaign: $(inputs.campaign)
    dbsUrl: $(inputs.dbs_url)
    configCacheUrl: $(inputs.config_cache_url)
    siteWhitelist: $(inputs.site_whitelist)
    outputDatasets: $(inputs.output_datasets)
    # Full source request, for traceability of steps/tasks not wired as
    # executable CWL steps in this PoC (see header comment above).
    requestDocument: $(inputs.reqmgr2_json)

inputs:
  sandbox: File
  job_package: File
  unpacker_script: File
  run_script: File
  reqmgr2_json: File
  job_index: int
  num_cores:
    type: int
    default: 1
  memory_mb:
    type: int
    default: 2000
  cmssw_container:
    type: string
    default: "cmssw-el7"

  step_name: string
  request_name: string
  request_type: string
  request_status: string
  requestor: string
  prep_id: string
  dbs_url: string
  config_cache_url: string
  campaign: string
  splitting_algo: string
  events_per_job: string
  primary_dataset: string
  input_dataset: string
  config_cache_id: string
  cmssw_version: string
  scram_arch: string
  global_tag: string
  acquisition_era: string
  processing_string: string
  site_whitelist: string[]
  output_datasets: string[]

outputs:
  job_output:
    type: Directory
    outputSource: Step/job_output
  job_dir:
    type: Directory
    outputSource: Step/job_dir

steps:
  Step:
    run: step.cwl
    in:
      sandbox: sandbox
      job_package: job_package
      unpacker_script: unpacker_script
      run_script: run_script
      job_index: job_index
      num_cores: num_cores
      memory_mb: memory_mb
      cmssw_container: cmssw_container
      step_name: step_name
      request_type: request_type
      splitting_algo: splitting_algo
      events_per_job: events_per_job
      primary_dataset: primary_dataset
      input_dataset: input_dataset
      campaign: campaign
      acquisition_era: acquisition_era
      processing_string: processing_string
      global_tag: global_tag
      cmssw_version: cmssw_version
      scram_arch: scram_arch
      config_cache_id: config_cache_id
    out: [job_output, job_dir]

$namespaces:
  wmcore: "https://cms.cern/wmcore-cwl-extensions#"
