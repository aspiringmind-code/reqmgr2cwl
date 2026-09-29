# StepChain job in CWL

One job of the 6-step Monte Carlo StepChain in `samples/cmsunified_task_SMP-RunIISummer20UL17pp5TeVwmLHEGS-00007__v1_T_251014_173511_792/`,
described in [CWL v1.2](https://www.commonwl.org/v1.2/) instead of the bash loop in `ep_scripts/execute_stepchain.sh`.
It does not use the WMAgent sandbox or job wrapper: every `cmsRun` is an explicit step.

## From `execute_stepchain.sh` to CWL

| `execute_stepchain.sh` | CWL |
|---|---|
| `for STEP_NUM in $(seq 1 6)` | `stepchain_6steps.cwl`: six named steps `cmsRun1` … `cmsRun6`, each a `cmssw_step.cwl` |
| `jobN.json` precomputed tweaks | `jobs/jobN.yml`: one `StepParams` record per step (`types/step_params.yml`), made by `scripts/make_job_inputs.py` |
| `setup_cmsset` | `cmssw_env_setup` in `scripts/cmssw_env.sh`, called by every tool (see below) |
| `scram project` + `scram runtime -sh` | `tools/scram_project.cwl` (outputs the project area as a `Directory`) + `cmssw_project_enter` |
| `edm_pset_pickler.py` → `edm_pset_tweak.py` → `cmssw_handle_nEvents.py` (→ `cmssw_handle_condor_status_service.py`) | `tools/pset_tweak.cwl`, which builds `tweak.json` from the step's parameters |
| `cmsRun -j job_report.xml` + job report check | `tools/cmsrun.cwl` |
| `file:../stepN/Module.root` | a CWL `File` passed from step to step, staged as `input.root` |
| `stage_out.py`, `create_report.py` | not yet (the workflow already outputs every job report, tweak and log) |

Each step is therefore three CWL steps, the pre-steps Alan described:

```
cmsRunN = scram_project  ->  pset_tweak  ->  cmsrun
             (project)     (job's values)   (cmsRun -j job_report.xml)
```

**Why "environment" is not a CWL step of its own.** Each CWL step runs in a fresh process, so
sourcing `cmsset_default.sh` or `scram runtime` in one step would not carry over to the next. Every tool
sources `scripts/cmssw_env.sh` and loads the environment itself; the project area is the only thing
passed between them. Because the staged area can be read-only and sit at a different path than
where it was made, `cmssw_project_enter` works on a copy and runs `scram build ProjectRename`.

**Why file names are not taken from `jobN.json`.** The splitter writes `fileNames` as
`file:../step1/RAWSIMoutput.root`, which only works with the sibling directories of the bash loop.
In CWL each step runs in its own directory, so `pset_tweak.cwl` sets `fileNames = file:input.root`
(the name `cmsrun.cwl` stages the previous output under) and names each step's output `<output_module>.root`.
All the other values are applied exactly as the splitter computed them. The test checks this against `jobs/job38.json`.

## Layout

```
cwl/
├── stepchain_6steps.cwl     top-level workflow: one job, six cmsRun steps
├── cmssw_step.cwl           one step: scram_project -> pset_tweak -> cmsrun
├── tools/                   scram_project.cwl, pset_tweak.cwl, cmsrun.cwl
├── types/step_params.yml    StepParams record (per-request + per-job values of one step)
├── scripts/
│   ├── cmssw_env.sh         environment helpers sourced by the tools
│   └── make_job_inputs.py   jobN.json + request.json -> jobN.yml
├── jobs/
│   ├── job38.json           job 38 as produced by event_splitter.py
│   ├── job38.yml            CWL inputs for job 38 (830 events)
│   └── job38_10events.yml   same, 10 events in step 1, for quick tests
└── tests/                   mock CMSSW environment + unittest
```

## Making the inputs for a job

```bash
export PYTHONPATH=<path>/WMCore/src/python      # needed by event_splitter only
S=samples/cmsunified_task_SMP-RunIISummer20UL17pp5TeVwmLHEGS-00007__v1_T_251014_173511_792
src/python/job_splitters/event_splitter.py --request $S/request.json --splitting $S/splitting.json --output-dir /tmp/split
cwl/scripts/make_job_inputs.py --request $S/request.json --job /tmp/split/job38.json \
    --psets $S/PSets --output cwl/jobs/job38.yml [--max-events 10]
```

Every job uses the same CWL; only this file changes. For job 38: lumi 38, 830 events, first event 30711, run 1.

## Running

Requirements: `pip install -r cwl/requirements.txt` (cwltool) and `node` for the JavaScript expressions.

### On the mock environment (no /cvmfs needed)

```bash
python -m unittest cwl/tests/test_cwl_workflow.py -v
```

This runs the whole 6-step workflow with fake `scram`, cmssw-wm-tools and `cmsRun`
(`tests/mock/`). They record which PSet, release, tweak and input file each step got, so the test can follow
the final NANOAODSIM file back through all six steps and compare the tweaks with `jobs/job38.json`.
It also checks that a failure written only to the job report stops the workflow.

### With real CMSSW (not yet tried)

The CMSSW 10_6 / 9_4 releases of this request need an EL7 userland and `/cvmfs`. The tools carry a
`DockerRequirement` hint for `cmssw/el7:x86_64`; with Apptainer on an EL9 host such as lxplus:

```bash
export APPTAINER_BINDPATH=/cvmfs            # the image does not include /cvmfs
cwltool --singularity \
    --preserve-environment X509_USER_PROXY \
    --outdir /tmp/job38-out \
    cwl/stepchain_6steps.cwl cwl/jobs/job38_10events.yml
```

Step 2 reads pileup over xrootd, so a grid proxy is needed (and the proxy file has to be visible
inside the container, e.g. put it under a bound directory). Add `report_to_condor: true` to the inputs
when running inside an HTCondor job.

## Status

Verified here: `cwltool --validate`, and a full run on the mock environment (chaining, per-step
releases, tweaks identical to the splitter's apart from file wiring, failure handling).

Not verified yet, to check on the first real run:

1. The container route above (image name, `/cvmfs` bind, proxy visibility).
2. `scram build ProjectRename` + `scram runtime -sh` on a project area staged by the CWL runner.
3. The cmssw-wm-tools on the 9_4_14 release (execute_stepchain.sh already runs them there).

Known gaps / next steps:

- **Exit codes:** process exit codes are 8 bits, so CMS codes such as 8001, 10040 or 50116 arrive
  truncated (8001 → 65). This is also true of `execute_stepchain.sh`. The real code is in the step's
  stderr log and job report; the reporting step should take it from there.
- **Random seeds:** neither the splitter nor this workflow re-seeds `RandomNumberGeneratorService`
  per job (WMCore does). Needs checking before running more than one job.
- **Stage-out and reporting:** wrap `ep_scripts/stage_out.py` and `create_report.py` as tools after `cmsRun6`.
- **NumCopies > 1** for step 1 is not supported yet (`make_job_inputs.py` refuses it); in CWL it would be a scatter over the copies.
- The top-level workflow is written for this 6-step request (which steps are kept). Generating it from
  `request.json` is the step after that.
