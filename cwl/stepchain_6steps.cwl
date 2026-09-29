cwlVersion: v1.2
class: Workflow
label: "One job of a 6-step Monte Carlo StepChain"
doc: |
  Runs cmsRun six times, each step reading the previous step's output:

    step1 GEN-SIM (wmLHEGS)  ->  step2 DIGI  ->  step3 HLT
      ->  step4 RECO (AODSIM)  ->  step5 MiniAODv2  ->  step6 NanoAODv9

  Every job of the request uses this same workflow; only the input values
  change (see cwl/jobs/job38.yml and cwl/scripts/make_job_inputs.py).
  Written for request
  cmsunified_task_SMP-RunIISummer20UL17pp5TeVwmLHEGS-00007__v1_T_251014_173511_792,
  where steps 4, 5 and 6 have KeepOutput=true.

requirements:
  SubworkflowFeatureRequirement: {}
  MultipleInputFeatureRequirement: {}
  SchemaDefRequirement:
    types:
      - $import: types/step_params.yml

inputs:
  step1: types/step_params.yml#StepParams
  step2: types/step_params.yml#StepParams
  step3: types/step_params.yml#StepParams
  step4: types/step_params.yml#StepParams
  step5: types/step_params.yml#StepParams
  step6: types/step_params.yml#StepParams
  report_to_condor:
    type: boolean
    default: false
    doc: Add the Condor status service to every step (only useful inside an HTCondor job).

steps:
  cmsRun1:
    run: cmssw_step.cwl
    in:
      params: step1
      step_label: {default: cmsRun1}
      report_to_condor: report_to_condor
    out: [output, root_files, tweak_json, job_report, stdout_log, stderr_log]

  cmsRun2:
    run: cmssw_step.cwl
    in:
      params: step2
      input_file: cmsRun1/output
      step_label: {default: cmsRun2}
      report_to_condor: report_to_condor
    out: [output, root_files, tweak_json, job_report, stdout_log, stderr_log]

  cmsRun3:
    run: cmssw_step.cwl
    in:
      params: step3
      input_file: cmsRun2/output
      step_label: {default: cmsRun3}
      report_to_condor: report_to_condor
    out: [output, root_files, tweak_json, job_report, stdout_log, stderr_log]

  cmsRun4:
    run: cmssw_step.cwl
    in:
      params: step4
      input_file: cmsRun3/output
      step_label: {default: cmsRun4}
      report_to_condor: report_to_condor
    out: [output, root_files, tweak_json, job_report, stdout_log, stderr_log]

  cmsRun5:
    run: cmssw_step.cwl
    in:
      params: step5
      input_file: cmsRun4/output
      step_label: {default: cmsRun5}
      report_to_condor: report_to_condor
    out: [output, root_files, tweak_json, job_report, stdout_log, stderr_log]

  cmsRun6:
    run: cmssw_step.cwl
    in:
      params: step6
      input_file: cmsRun5/output
      step_label: {default: cmsRun6}
      report_to_condor: report_to_condor
    out: [output, root_files, tweak_json, job_report, stdout_log, stderr_log]

outputs:
  # Steps with KeepOutput=true; steps 1-3 are intermediate.
  aodsim:
    type: File
    outputSource: cmsRun4/output
  miniaodsim:
    type: File
    outputSource: cmsRun5/output
  nanoaodsim:
    type: File
    outputSource: cmsRun6/output

  # Per-step bookkeeping, in step order, for the later report / stage-out work.
  job_reports:
    type: File[]
    outputSource: [cmsRun1/job_report, cmsRun2/job_report, cmsRun3/job_report,
                   cmsRun4/job_report, cmsRun5/job_report, cmsRun6/job_report]
    linkMerge: merge_flattened
  tweaks:
    type: File[]
    outputSource: [cmsRun1/tweak_json, cmsRun2/tweak_json, cmsRun3/tweak_json,
                   cmsRun4/tweak_json, cmsRun5/tweak_json, cmsRun6/tweak_json]
    linkMerge: merge_flattened
  logs:
    type: File[]
    outputSource: [cmsRun1/stdout_log, cmsRun1/stderr_log, cmsRun2/stdout_log, cmsRun2/stderr_log,
                   cmsRun3/stdout_log, cmsRun3/stderr_log, cmsRun4/stdout_log, cmsRun4/stderr_log,
                   cmsRun5/stdout_log, cmsRun5/stderr_log, cmsRun6/stdout_log, cmsRun6/stderr_log]
    linkMerge: merge_flattened
