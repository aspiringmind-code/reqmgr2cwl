cwlVersion: v1.2
class: CommandLineTool
label: "Pre-step: apply this job's values to the base PSet"
doc: |
  Replaces WMCore's SetupCMSSWPset. Builds tweak.json from the job's
  parameters, then uses the cmssw-wm-tools shipped with CMSSW to pickle the
  base PSet, apply the tweak and fix up maxEvents, exactly as
  ep_scripts/execute_stepchain.sh does.

  Unlike the precomputed tweaks in jobN.json, file names are not hard-coded
  to ../stepN/ paths: the cmsRun tool stages the previous step's output as
  input.root, and every step writes <output_module>.root.

requirements:
  InlineJavascriptRequirement: {}
  InitialWorkDirRequirement:
    listing:
      - entryname: tweak.json
        entry: |
          ${
            function u32(v) { return "customTypeCms.untracked.uint32(" + v + ")"; }
            var t = {};
            t["process.options.numberOfThreads"] = u32(inputs.number_of_threads);
            t["process.options.numberOfStreams"] = u32(inputs.number_of_streams);
            if (inputs.first_lumi !== null) {
              t["process.source.firstLuminosityBlock"] = u32(inputs.first_lumi);
            }
            t["process.maxEvents"] =
              "customTypeCms.untracked.PSet(input=cms.untracked.int32(" + inputs.max_events + "))";
            if (inputs.first_event !== null) {
              t["process.source.firstEvent"] = u32(inputs.first_event);
            }
            t["process.source.firstRun"] = u32(inputs.first_run !== null ? inputs.first_run : 1);
            if (inputs.input_file_name !== null) {
              t["process.source.fileNames"] =
                "customTypeCms.untracked.vstring(['file:" + inputs.input_file_name + "'])";
            }
            t["process." + inputs.output_module + ".fileName"] =
              "customTypeCms.untracked.string('file:" + inputs.output_module + ".root')";
            return JSON.stringify(t, null, 2);
          }

hints:
  DockerRequirement:
    dockerPull: cmssw/el7:x86_64   # needs /cvmfs bound into the container, see cwl/README.md

baseCommand: [bash, -c]
arguments:
  - |
    . "$(inputs.env_script.path)"
    cmssw_env_setup
    cmssw_project_enter "$(inputs.cmssw_project.path)" "$(inputs.scram_arch)"
    cp "$(inputs.base_pset.path)" PSet_base.py
    edm_pset_pickler.py --input PSet_base.py --output_pkl Pset.pkl || exit $EXIT_CFG_GEN
    edm_pset_tweak.py --input_pkl Pset.pkl --output_pkl Pset.pkl --json tweak.json --create_untracked_psets || exit $EXIT_CFG_GEN
    cmssw_handle_nEvents.py --input_pkl Pset.pkl --output_pkl Pset.pkl || exit $EXIT_CFG_GEN
    $(inputs.condor_status_name === null ? "" :
      "cmssw_handle_condor_status_service.py --input_pkl Pset.pkl --output_pkl Pset.pkl --name " +
      inputs.condor_status_name + " || exit $EXIT_CFG_GEN")

inputs:
  cmssw_project:
    type: Directory
    doc: Project area from scram_project.cwl.
  scram_arch:
    type: string
  base_pset:
    type: File
  output_module:
    type: string
    doc: Output module whose file name is set to <output_module>.root.
  number_of_threads:
    type: int
  number_of_streams:
    type: int
  max_events:
    type: int
  first_event:
    type: long?
  first_lumi:
    type: int?
  first_run:
    type: int?
  input_file_name:
    type: string?
    doc: Name the input file will have in cmsRun's working directory. Unset for a generator step.
  step_label:
    type: string
    doc: Prefix of the provenance copy of tweak.json (e.g. cmsRun1-tweak.json).
  condor_status_name:
    type: string?
    doc: If set, add the Condor status service (Chirp) under this name, e.g. cmsRun1.
  env_script:
    type: File
    doc: Shell helpers shared by all tools. Not meant to be overridden.
    default:
      class: File
      location: ../scripts/cmssw_env.sh

outputs:
  pset_pkl:
    type: File
    outputBinding:
      glob: Pset.pkl
  tweak_json:
    type: File
    doc: The tweak that was applied, for provenance.
    outputBinding:
      glob: tweak.json
      outputEval: ${ self[0].basename = inputs.step_label + "-tweak.json"; return self[0]; }
