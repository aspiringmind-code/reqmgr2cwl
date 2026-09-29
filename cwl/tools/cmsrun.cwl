cwlVersion: v1.2
class: CommandLineTool
label: "cmsRun"
doc: |
  Runs cmsRun on the tweaked PSet of one step. The previous step's output,
  if any, is staged as input.root (the name pset_tweak.cwl wrote into the PSet).
  Fails on a non-zero cmsRun exit code and on errors in the framework job report.

requirements:
  InlineJavascriptRequirement: {}
  NetworkAccess:
    networkAccess: true   # conditions (Frontier) and pileup (xrootd)
  ResourceRequirement:
    coresMin: $(inputs.number_of_threads)
    ramMin: $(inputs.memory_mb)
  InitialWorkDirRequirement:
    listing:
      - entryname: Pset.pkl
        entry: $(inputs.pset_pkl)
      - '$(inputs.input_file === null ? null : {"entryname": "input.root", "entry": inputs.input_file})'
      - entryname: Pset_cmsRun.py
        entry: |
          import FWCore.ParameterSet.Config as cms  # WMCore does this, so do we
          import pickle
          with open('Pset.pkl', 'rb') as f:
              process = pickle.load(f)

hints:
  DockerRequirement:
    dockerPull: cmssw/el7:x86_64   # needs /cvmfs bound into the container, see cwl/README.md

baseCommand: [bash, -c]
arguments:
  - |
    . "$(inputs.env_script.path)"
    cmssw_env_setup
    cmssw_project_enter "$(inputs.cmssw_project.path)" "$(inputs.scram_arch)"
    export FRONTIER_LOG_LEVEL=warning
    cmsRun -j job_report.xml Pset_cmsRun.py
    cmssw_check_cmsrun $? job_report.xml

inputs:
  cmssw_project:
    type: Directory
    doc: Project area from scram_project.cwl.
  scram_arch:
    type: string
  pset_pkl:
    type: File
    doc: Tweaked PSet from pset_tweak.cwl.
  output_module:
    type: string
  input_file:
    type: File?
    doc: Output of the previous step. Unset for a generator step.
  number_of_threads:
    type: int
  memory_mb:
    type: int
  step_label:
    type: string
    doc: Prefix of the log and job report files (e.g. cmsRun1-stdout.log).
  env_script:
    type: File
    doc: Shell helpers shared by all tools. Not meant to be overridden.
    default:
      class: File
      location: ../scripts/cmssw_env.sh

stdout: $(inputs.step_label)-stdout.log
stderr: $(inputs.step_label)-stderr.log

outputs:
  output:
    type: File
    doc: The file written by output_module; input of the next step.
    outputBinding:
      glob: $(inputs.output_module).root
  root_files:
    type: File[]
    doc: Every ROOT file the step wrote (e.g. step 1 also writes LHEoutput.root).
    outputBinding:
      glob: "*.root"
      outputEval: $(self.filter(function(f) { return f.basename != "input.root"; }))
  job_report:
    type: File
    outputBinding:
      glob: job_report.xml
      outputEval: ${ self[0].basename = inputs.step_label + "-job_report.xml"; return self[0]; }
  stdout_log:
    type: stdout
  stderr_log:
    type: stderr
