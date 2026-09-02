#!/usr/bin/env cwl-runner
# workflows/step.cwl
#
# Generic wrapper for one StepChain/TaskChain step, backed by one
# resolved WMAgent job. No step name, splitting algorithm, campaign, or
# any other value is hardcoded -- everything is passed in as inputs,
# populated by scripts/discover_job.py from the artifacts under
# artifacts/. This file is identical regardless of which ReqMgr2
# request or which job you point discover_job.py at.
#
# Follows the LHCb / crab-cwl pattern: the `run` body is plain, portable
# CWL wrapping the actual executable step; all WMAgent/ReqMgr2-specific
# bookkeeping travels as an ignorable `wmcore:` hint, built entirely from
# input expressions so it reflects whatever request/step was discovered.

cwlVersion: v1.2
class: Workflow

requirements:
  SubworkflowFeatureRequirement: {}
  InlineJavascriptRequirement: {}

hints:
  wmcore:Transformation:
    stepName: $(inputs.step_name)
    requestType: $(inputs.request_type)
    splittingAlgo: $(inputs.splitting_algo)
    eventsPerJob: $(inputs.events_per_job)
    primaryDataset: $(inputs.primary_dataset)
    inputDataset: $(inputs.input_dataset)
    campaign: $(inputs.campaign)
    acquisitionEra: $(inputs.acquisition_era)
    processingString: $(inputs.processing_string)
    globalTag: $(inputs.global_tag)
    cmsswVersion: $(inputs.cmssw_version)
    scramArch: $(inputs.scram_arch)
    configCacheID: $(inputs.config_cache_id)

inputs:
  sandbox: File
  job_package: File
  unpacker_script: File
  run_script: File
  job_index: int
  num_cores:
    type: int
    default: 1
  memory_mb:
    type: int
    default: 2000
  cmssw_container:
    type: string
    default: "cmssw-el8"

  # Metadata, purely descriptive at this level (carried into the
  # wmcore:Transformation hint above) but also passed functionally down
  # to the tool where relevant (scram_arch).
  step_name: string
  request_type: string
  splitting_algo: string
  events_per_job: string
  primary_dataset: string
  input_dataset: string
  campaign: string
  acquisition_era: string
  processing_string: string
  global_tag: string
  cmssw_version: string
  scram_arch: string
  config_cache_id: string

outputs:
  job_output:
    type: Directory
    outputSource: run_job/job_output
  job_dir:
    type: Directory
    outputSource: run_job/job_dir

steps:
  run_job:
    run: ../tools/run-wmcore-job.cwl
    in:
      sandbox: sandbox
      job_package: job_package
      unpacker_script: unpacker_script
      run_script: run_script
      job_index: job_index
      num_cores: num_cores
      memory_mb: memory_mb
      cmssw_container: cmssw_container
      scram_arch: scram_arch
      cmssw_version: cmssw_version
    out: [job_output, job_dir]

$namespaces:
  wmcore: "https://cms.cern/wmcore-cwl-extensions#"