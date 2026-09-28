cwlVersion: v1.2
class: CommandLineTool
label: "Pre-step: create the scram project area"
doc: |
  Loads the CMS environment from /cvmfs and runs `scram project` for the
  release of one step. The project area is passed on as a Directory to the
  pset tweak and cmsRun tools of the same step.

requirements:
  InlineJavascriptRequirement: {}

hints:
  DockerRequirement:
    dockerPull: cmssw/el7:x86_64   # needs /cvmfs bound into the container, see cwl/README.md

baseCommand: [bash, -c]
arguments:
  - |
    . "$(inputs.env_script.path)"
    cmssw_env_setup
    cmssw_project_create "$(inputs.cmssw_version)" "$(inputs.scram_arch)"

inputs:
  cmssw_version:
    type: string
  scram_arch:
    type: string
  env_script:
    type: File
    doc: Shell helpers shared by all tools. Not meant to be overridden.
    default:
      class: File
      location: ../scripts/cmssw_env.sh

outputs:
  cmssw_project:
    type: Directory
    outputBinding:
      glob: $(inputs.cmssw_version)
