# ReqMgr2 → CWL — generic, artifact-driven

Drop four files under `artifacts/` and run. This repo figures out the
rest: which workflow, which job, which step, which splitting algorithm,
which CMSSW release/arch, which container to run it in -- all discovered
from the files themselves. Nothing here is hardcoded to any particular
ReqMgr2 request.

## The four artifacts

Place these under `artifacts/` (any filenames matching the patterns
below; exact names don't matter):

| # | What | Typical filename | Where it comes from |
|---|------|-------------------|----------------------|
| 1 | Sandbox tarball | `<workflow>-Sandbox_tar.bz2` | `WorkQueueManager/cache/<workflow>/` on the agent |
| 2 | One job's tarball | `Job_<id>_tar.bz2` | `JobCreator/JobCache/<workflow>/<task>/.../job_<id>/` |
| 3 | Job package | `JobPackage.pkl` | same `JobCreator`/`WorkQueueManager` cache directory |
| 4 | ReqMgr2 request document | `<anything>.json` | `https://<cmsweb-instance>/reqmgr2/data/request/<workflow>` |

`Unpacker.py` is **not** a fifth file you need to supply -- it's
extracted automatically from `WMCore.zip` inside the sandbox tarball
(`WMCore/WMRuntime/Unpacker.py`).

## Running

```
./run.sh
```

That's it. Behind the scenes, `run.sh`:

1. Runs `scripts/discover_job.py`, which:
   - parses `wmagentJob.log` out of the `Job_<id>` tarball to learn the
     job index, workflow name, task/step path, requestType, allocated
     cores/memory, and worker OS;
   - extracts `Unpacker.py` from the sandbox's `WMCore.zip`;
   - loads the ReqMgr2 JSON (handling both the wrapped
     `{"<workflow>": {...}}` form and the flat `{"RequestName": ..., ...}`
     form) and finds the `Step<N>`/`Task<N>` entry whose
     `StepName`/`TaskName` matches the step this job actually ran, for
     either `StepChain` or `TaskChain` requests;
   - writes a CWL job-order file (`artifacts/.generated/inputs.yml`)
     with everything discovered.
2. Validates `workflows/workgraph.cwl` with `cwltool --validate`.
3. Runs it for real with `cwltool`.

To point at a different set of artifacts (a different workflow/job)
later, just replace the four files under `artifacts/` and run `./run.sh`
again -- no code changes.

```
ARTIFACTS_DIR=/path/to/other/artifacts ./run.sh
```

## Layout

```
scripts/
  discover_job.py       The generalization: artifacts -> CWL inputs.yml
tools/
  run-wmcore-job.cwl     Generic CommandLineTool -- unpack + run one job
  scripts/run_wmcore_job.sh   The unpack/container/Startup.py sequence
workflows/
  step.cwl               Generic single-step wrapper (StepChain/TaskChain step)
  workgraph.cwl           Generic outermost Workgraph
tests/
  run_tests.sh / run_tests.py   Validation + a synthetic-fixture wiring test
  mocks/                  Stand-ins used by the mocked test
artifacts/                Where you place the four real files (gitignored)
run.sh                    Convenience: discover + validate + execute
.github/workflows/
  cwl-execute.yml          validate (any runner) + execute (self-hosted, CVMFS)
```

## Design choices, and why

**The tool wraps the real WMAgent job wrapper, not a hand-built `cmsRun`
command.** `tools/scripts/run_wmcore_job.sh` reproduces the documented
"Running a WMCore Job Interactively or Manually" procedure: `Unpacker.py`
→ enter the worker OS container → source the CVMFS COMP environment →
`Startup.py`. Same design as LHCb's `lb-ap-run-app.cwl`: one generic
runner, fed a resolved job description.

**All ReqMgr2/WMAgent-specific values are inputs, not literals.** Every
`.cwl` file in `workflows/` and `tools/` is identical no matter which
workflow you point `discover_job.py` at -- step name, splitting algo,
campaign, config cache ID, CMSSW version, worker OS/container, etc. are
all CWL inputs, populated at run time. Orchestration metadata is carried
in a `wmcore:` hint namespace built from those same inputs via CWL
expressions (`InlineJavascriptRequirement`), so it's ignored by any
conformant runner that doesn't know the vocabulary -- same pattern as
`dirac:` in `lhcb-cwl-example` and `cms:` in `crab-cwl`.

**Verified generic, not just designed to be.** `tests/run_tests.py`
fabricates a second, structurally different request from scratch --
`TaskChain` instead of `StepChain`, the flat JSON form instead of the
wrapped form, a job matching the *second* task entry instead of the
first, `rhel8`→`cmssw-el8` instead of `rhel7`→`cmssw-el7` -- and runs the
full pipeline against it. This is in addition to the pipeline having been
run successfully against a real request's real artifacts during
development.

## Scope of this PoC — still applies, per-request

For **whichever** request you point this at: only the ONE step backed by
the resolved job you supplied is wired as an executable CWL step. Any
other `Step<N>`/`Task<N>` entries in that request's JSON are not
executed -- they'd need their own resolved job package (same manual
extraction) or a reimplementation of WMCore's job-splitting algorithm
against DBS, neither of which this repo attempts. The full request
document is always attached to the outer `Workgraph`'s `wmcore:Workgraph`
hint (`requestDocument`) so those other steps stay inspectable even
though they aren't run.

## Environment requirement: CVMFS + `cmssw-elN`

Real execution needs `/cvmfs/cms.cern.ch` mounted and the appropriate
`cmssw-elN` apptainer wrapper available (`discover_job.py` picks the
right one from the job's recorded `worker_os`: `rhel7`/`slc7` →
`cmssw-el7`, `rhel8` → `cmssw-el8`, `rhel9` → `cmssw-el9`). lxplus
satisfies this natively.

**Before relying on this for any given job:** confirm the job's
`CMSSWVersion`+`ScramArch` combination actually resolves on CVMFS inside
that container (`cmssw-elN`, then `scram list <version>`). A missing
release/arch combination is a genuine CVMFS gap, not a bug in this
pipeline -- it will faithfully reproduce whatever the original job hit.

## CI

`.github/workflows/cwl-execute.yml`:

- **`validate`** -- GitHub-hosted, no CVMFS. Runs `tests/run_tests.sh`
  (CWL validation + the synthetic-fixture wiring test) on every push/PR.
- **`execute`** -- self-hosted, labeled `[self-hosted, cvmfs, cmssw]`.
  Runs `run.sh` against whatever real artifacts are present in
  `artifacts/` in the checked-out branch/runner workspace. Register a
  CVMFS-mounted host (lxplus or similar) with those labels for this job
  to pick it up -- mirrors how `lhcb-cwl-example` runs its real test tier
  on a `cvmfs`-tagged runner.

Since `artifacts/` is gitignored, populate it on the self-hosted runner's
workspace directly (or adapt the `execute` job to fetch/copy the four
files from wherever you keep them) rather than committing real job
artifacts to the repo.
