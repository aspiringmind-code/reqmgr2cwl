cwlVersion: v1.2
class: Workflow
label: "One StepChain step: scram project -> PSet tweak -> cmsRun"
doc: |
  The per-step flow of ep_scripts/execute_stepchain.sh as three CWL steps.
  The CMS environment itself is loaded inside each tool (see
  cwl/scripts/cmssw_env.sh), because environment changes do not carry over
  from one CWL step to the next.

requirements:
  InlineJavascriptRequirement: {}
  StepInputExpressionRequirement: {}
  MultipleInputFeatureRequirement: {}
  SchemaDefRequirement:
    types:
      - $import: types/step_params.yml

inputs:
  params:
    type: types/step_params.yml#StepParams
  input_file:
    type: File?
    doc: Output of the previous step. Unset for the first step.
  step_label:
    type: string
    doc: Name of the step in this job (cmsRun1, cmsRun2, ...); prefixes its log, report and tweak files.
  report_to_condor:
    type: boolean
    default: false
    doc: Add the Condor status service, reporting under step_label.

steps:
  project:
    run: tools/scram_project.cwl
    in:
      cmssw_version: {source: params, valueFrom: $(self.cmssw_version)}
      scram_arch: {source: params, valueFrom: $(self.scram_arch)}
    out: [cmssw_project]

  tweak:
    run: tools/pset_tweak.cwl
    in:
      cmssw_project: project/cmssw_project
      scram_arch: {source: params, valueFrom: $(self.scram_arch)}
      base_pset: {source: params, valueFrom: $(self.pset)}
      output_module: {source: params, valueFrom: $(self.output_module)}
      number_of_threads: {source: params, valueFrom: $(self.number_of_threads)}
      number_of_streams: {source: params, valueFrom: $(self.number_of_streams)}
      max_events: {source: params, valueFrom: $(self.max_events)}
      first_event: {source: params, valueFrom: $(self.first_event)}
      first_lumi: {source: params, valueFrom: $(self.first_lumi)}
      first_run: {source: params, valueFrom: $(self.first_run)}
      input_file_name: {source: input_file, valueFrom: '$(self === null ? null : "input.root")'}
      step_label: step_label
      condor_status_name: {source: [report_to_condor, step_label], valueFrom: '$(self[0] ? self[1] : null)'}
    out: [pset_pkl, tweak_json]

  cmsrun:
    run: tools/cmsrun.cwl
    in:
      cmssw_project: project/cmssw_project
      scram_arch: {source: params, valueFrom: $(self.scram_arch)}
      pset_pkl: tweak/pset_pkl
      output_module: {source: params, valueFrom: $(self.output_module)}
      input_file: input_file
      number_of_threads: {source: params, valueFrom: $(self.number_of_threads)}
      memory_mb: {source: params, valueFrom: $(self.memory_mb)}
      step_label: step_label
    out: [output, root_files, job_report, stdout_log, stderr_log]

outputs:
  output:
    type: File
    outputSource: cmsrun/output
  root_files:
    type: File[]
    outputSource: cmsrun/root_files
  tweak_json:
    type: File
    outputSource: tweak/tweak_json
  job_report:
    type: File
    outputSource: cmsrun/job_report
  stdout_log:
    type: File
    outputSource: cmsrun/stdout_log
  stderr_log:
    type: File
    outputSource: cmsrun/stderr_log
