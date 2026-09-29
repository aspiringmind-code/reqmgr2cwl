# StepChain job in CWL

One job of the 6-step Monte Carlo StepChain in `samples/cmsunified_task_SMP-RunIISummer20UL17pp5TeVwmLHEGS-00007__v1_T_251014_173511_792/`,
described in [CWL v1.2](https://www.commonwl.org/v1.2/) instead of the bash loop in `ep_scripts/execute_stepchain.sh` [Marco's stepchain](https://github.com/mmascher/WorkflowOrchestrator/blob/main/ep_scripts/execute_stepchain.sh).
The directory is self-contained: `samples/` holds a copy of that request's `request.json`, `splitting.json` and `PSets/`.
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
├── samples/                request.json, splitting.json and PSets/ of the request (copy)
├── jobs/
│   ├── job38.json           job 38 as produced by event_splitter.py
│   ├── job38.yml            CWL inputs for job 38 (830 events)
│   └── job38_10events.yml   same, 10 events in step 1, for quick tests
└── tests/                   mock CMSSW environment + unittest
```

## Making the inputs for a job (Refer to https://github.com/mmascher/WorkflowOrchestrator/blob/main/src/python/job_splitters/README.md )

```bash
export PYTHONPATH=<path>/WMCore/src/python      # needed by event_splitter only
S=cwl/samples
src/python/job_splitters/event_splitter.py --request $S/request.json --splitting $S/splitting.json --output-dir /tmp/split
cwl/scripts/make_job_inputs.py --request $S/request.json --job /tmp/split/job38.json \
    --psets $S/PSets --output cwl/jobs/job38.yml [--max-events 10]
```

Every job uses the same CWL; only this file changes. For job 38: lumi 38, 830 events, first event 30711, run 1.

## Running

### On the mock environment (no /cvmfs needed)

Requirements: `pip install -r cwl/requirements.txt` (cwltool) and `node` for the JavaScript expressions.

```bash
cd cwl
python3 -m unittest tests/test_cwl_workflow.py -v
```

This runs the whole 6-step workflow with fake `scram`, cmssw-wm-tools and `cmsRun`
(`tests/mock/`). They record which PSet, release, tweak and input file each step got, so the test can follow
the final NANOAODSIM file back through all six steps and compare the tweaks with `jobs/job38.json`.
It also checks that a failure written only to the job report stops the workflow.
The files in `tests/mock/bin/` must keep their names and be executable (`chmod +x tests/mock/bin/*`),
otherwise the real CMS tools on `PATH` are picked up instead.

### With real CMSSW on lxplus9

The CMSSW 10_6 / 9_4 releases of this request need an EL7 userland. `cwltool` runs on the EL9 host and
starts every step in the `cmssw/el7:x86_64` image with Apptainer (the tools carry a `DockerRequirement`
hint for it). This recipe ran all six steps of job 38 (10 events) on lxplus9.

**One-time setup**

```bash
# cwltool >= 3.3 needs Python >= 3.10; the system python3 on lxplus9 is 3.9
python3.11 -m venv ~/cwl-venv
source ~/cwl-venv/bin/activate
pip install -r requirements.txt
```

A valid Grid user certificate in `~/.globus/` is needed for the proxy (renew it at the CERN CA when it expires).

**Every session**

```bash
source ~/cwl-venv/bin/activate
cd <path>/cwl

# Proxy for the pileup read over xrootd in step 2. Keep it OUT of /tmp:
# cwltool mounts a private directory over /tmp inside the container, which would hide it.
voms-proxy-init -voms cms -valid 192:00 -out $HOME/.globus/x509up_cwl
export X509_USER_PROXY=$HOME/.globus/x509up_cwl

# What the container needs from the host: CMS software, grid CA certificates, the proxy.
export APPTAINER_BINDPATH=/cvmfs,/etc/grid-security,$X509_USER_PROXY

# Keep the ~1 GB image off AFS (the default ~/.apptainer/cache overflows the AFS quota).
export APPTAINER_CACHEDIR=/tmp/$USER/apptainer-cache
export CWL_SINGULARITY_CACHE=/tmp/$USER/sif      # or an EOS directory, to reuse it across lxplus nodes
mkdir -p $APPTAINER_CACHEDIR $CWL_SINGULARITY_CACHE

cwltool --singularity --preserve-environment X509_USER_PROXY \
    --leave-tmpdir --cachedir /tmp/$USER/cwl-cache \
    --outdir /tmp/$USER/job38-out \
    stepchain_6steps.cwl jobs/job38_10events.yml
```

- The first run downloads the image into `CWL_SINGULARITY_CACHE` (as `cmssw_s_el7:x86___64.sif`); later
  runs print `Already cached`. Copy that file to EOS and point `CWL_SINGULARITY_CACHE` there to reuse it
  on any lxplus node.
- `--cachedir` stores each finished step: a rerun reuses them (`Using cached output`), so a failure in
  step 5 does not repeat the hours of GEN-SIM in step 1.
- `--leave-tmpdir` keeps the working directory of a failed step, so its `cmsRunN-stdout.log` /
  `cmsRunN-stderr.log` can be read. The directory is the one printed in the `[job cmsrun_N] /tmp/...$` line.
- `--outdir` must be empty or new: cwltool will not overwrite the read-only files of an earlier run
  (`Permission denied` at the very end). Remove it with `chmod -R u+w <dir> && rm -rf <dir>`.
- Add `report_to_condor: true` to the job inputs when running inside an HTCondor job.

**Checking the result**

```bash
ls -la /tmp/$USER/job38-out/
grep -H "<TotalEvents>" /tmp/$USER/job38-out/cmsRun*-job_report.xml
```

**Troubleshooting**

| Symptom | Cause |
|---|---|
| `slc7 ... on host with operating system 'el9'` warnings, cmsRun fails | ran without `--singularity`: CMSSW 10_6 needs the EL7 image |
| `disk quota exceeded` while pulling the image | `APPTAINER_CACHEDIR` not set, the image went to AFS |
| `cmsset_default.sh not found in /cvmfs/cms.cern.ch` | `/cvmfs` missing from `APPTAINER_BINDPATH` |
| step 2 exits with status 92 (= CMS 8028, `FallbackFileOpenError`) | pileup could not be opened: proxy under `/tmp`, or `/etc/grid-security` not bound |
| `PermissionError: '/proc/1/stat'` tracebacks | harmless: cwltool's memory monitor on lxplus |

## Status

Verified:

- `cwltool --validate`, and the full run on the mock environment (chaining, per-step releases, tweaks
  identical to the splitter's apart from file wiring, failure handling).
- **A real run of job 38 on lxplus9** (10 events, recipe above): all six steps completed, including the
  pileup read in step 2 and the switch to `CMSSW_9_4_14_UL_patch1` in step 3. `scram project`, staging
  the project area between CWL steps (`ProjectRename` + `scram runtime`) and the cmssw-wm-tools all
  work on both releases.

Known gaps / next steps:

- **Compare with `execute_stepchain.sh`:** run it on the same job and compare job reports and event counts.
- **Exit codes:** process exit codes are 8 bits, so CMS codes such as 8001, 8028, 10040 or 50116 arrive
  truncated (8001 → 65, 8028 → 92). This is also true of `execute_stepchain.sh`. The real code is in the step's
  stderr log and job report; the reporting step should take it from there.
- **Random seeds:** neither the splitter nor this workflow re-seeds `RandomNumberGeneratorService`
  per job (WMCore does). Needs fixing before running more than one job.
- **Stage-out and reporting:** wrap `ep_scripts/stage_out.py` and `create_report.py` as tools after `cmsRun6`.
- **Pileup** is the list baked into the step 2 PSet; a per-job `pileupconf.json` (`src/python/pileup_generator/`) would replace it.
- **NumCopies > 1** for step 1 is not supported yet (`make_job_inputs.py` refuses it); in CWL it would be a scatter over the copies.
- The top-level workflow is written for this 6-step request (which steps are kept). Generating it from
  `request.json` is the step after that.
