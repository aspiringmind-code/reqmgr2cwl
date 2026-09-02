# ReqMgr2 → CWL — generic, artifact-driven

Drop four files under `artifacts/` and run. This repo figures out the
rest: which workflow, which job, which step, which splitting algorithm,
which CMSSW release/arch, which container to run it in -- all discovered
from the files themselves.

## The four artifacts

Place these under `artifacts/` (any filenames matching the patterns
below; exact names don't matter):

| # | What | Typical filename | Where it comes from |
|---|------|-------------------|----------------------|
| 1 | Sandbox tarball | `<workflow>-Sandbox_tar.bz2` | `WorkQueueManager/cache/<workflow>/` on the agent |
| 2 | One job's tarball | `Job_<id>_tar.bz2` | `JobCreator/JobCache/<workflow>/<task>/.../job_<id>/` |
| 3 | Job package | `JobPackage.pkl` | same `JobCreator`/`WorkQueueManager` cache directory |
| 4 | ReqMgr2 request document | `<anything>.json` | `https://<cmsweb-instance>/reqmgr2/data/request/<workflow>` |

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

## Scope of this PoC

For **whichever** request you point this at: only the ONE step backed by
the resolved job you supplied is wired as an executable CWL step. Any
other `Step<N>`/`Task<N>` entries in that request's JSON are not
executed -- they'd need their own resolved job package (same manual
extraction) or a reimplementation of WMCore's job-splitting algorithm
against DBS, neither of which this repo attempts. The full request
document is always attached to the outer `Workgraph`'s `wmcore:Workgraph`
hint (`requestDocument`) so those other steps stay inspectable even
though they aren't run.

# ReqMgr2 → CWL: Project Summary and Way Ahead

## What this project set out to do

Convert a CMS ReqMgr2/WMAgent production request into Common Workflow
Language (CWL), and actually **run** the result. The scope was deliberately narrowed early
on, following the pattern of two prior efforts we studied
(`lhcb-cwl-example`, `crab-cwl`): represent **one already-resolved,
already-split WMAgent job** as CWL, rather than attempting to solve
dataset resolution and job splitting inside CWL itself.

### Verified against real job

The pipeline was proven against an example workflow `cmsunified_task_TOP-RunIII2024Summer24GS-00003__v1_T_250915_213421_7140` :

| Job | Type | Remarks |
|---|---|---|
| Job 1459333 (merge task) | StepChain, real production job | `el8_amd64_gcc12`, real merged input files, non-empty `runs` sets |

Job 1459333 reached and completed the actual `cmsRun`
step (`Chirp_WMCore_cmsRun1_ExitCode 0`) — a full replay of a
real production merge job's processing step, executed via `cwltool` on
lxplus.

### 4. What's explicitly out of scope, by design

For **any** request run through this pipeline: only the one step
backed by a supplied, resolved job is executed. Any other
`Step<N>`/`Task<N>` entries in that request's JSON are not run — they'd
need their own resolved job package (same manual extraction) or a
reimplementation of WMCore's job-splitting algorithm against DBS,
neither of which this project attempted. This mirrors what both
`lhcb-cwl-example` (DIRAC feeder resolution) and `crab-cwl`
(`EventBased`-only splitting) also defer.

---

## Way ahead: how much of this could become "real" CWL?

Right now, the honest description of this pipeline is: **a CWL
wrapper around a WMCore job replay**, not a CWL-native reimplementation
of what a CMS job does. The actual work — unpacking, PSet tweaking,
`cmsRun` invocation, stage-out — all happens *inside* `Startup.py`,
opaque to CWL. CWL only sees "run this script, get back a directory."

### What's WMCore-dependent right now, and why

| Artifact / step | Why it's needed today |
|---|---|
| `JobPackage.pkl` | Contains the pickled `WMBS`-shaped job description (input file list, mask, output module config) that `Startup.py` unpickles via `Bootstrap.loadJobDefinition()`. No public, non-pickle form of this exists. |
| Sandbox's `WMWorkload.pkl` | `Bootstrap.loadTask()` needs this to resolve the task's step configuration (`SetupCMSSWPset`, output modules, stage-out rules). |
| `Unpacker.py` / `Startup.py` | WMCore's own job wrapper — handles PSet tweaking (`edm_pset_tweak.py`, random seeds, DQM file saver config, GUID enforcement), stage-out, log archiving, and job-report generation. Reimplementing this correctly is a large undertaking (see below). |
| `scram project` + `cmsenv` inside our script | CMSSW's own environment bootstrap; not CWL's concern, but currently invoked imperatively rather than declaratively. |

### Where a more CWL-native version is plausible

1. **Direct `PSet.py` extraction + a real `cmsRun` `CommandLineTool`.**
   Once `SetupCMSSWPset` has run once for a given `ConfigCacheID` (as
   we've now watched it do, end-to-end, for a real merge job), the
   resulting `PSet.py` is just a plain CMSSW python config file. In
   principle, a `ConfigCacheID` could be fetched directly from
   `ConfigCacheUrl` (bypassing `JobPackage.pkl` and `Bootstrap`
   entirely) and turned into a genuine CWL `CommandLineTool` whose
   `inputs` are real CWL `File[]` (resolved input LFNs/PFNs) and whose
   command is literally `cmsRun PSet.py` — visible to and validated by
   `cwltool` itself, not hidden inside a Python wrapper it can't see
   into. This is the next step: it would let CWL
   actually own the executable step, the way `crab-cwl`'s embedded
   `cmsRun` tool does, instead of delegating to an opaque script.

2. **Input resolution via DBS instead of `JobPackage.pkl`.** The input
   file list currently comes pre-resolved inside the pickle. For steps
   with a real `InputDataset`, that list
   could instead come from a live DBS query against `DbsUrl` — turning
   "supply a JobPackage.pkl" into "supply a dataset name and let CWL
   discovery resolve files," which is a meaningfully more portable and
   inspectable starting point, and doesn't depend on artifacts pulled
   from one specific historical agent run.

3. **`EventBased` splitting as a real CWL scatter.** This is the one
   splitting algorithm that's pure arithmetic
   (`ceil(totalUnits / unitsPerJob)`, implementable as a `ScatterFeatureRequirement`
   over a computed job count, with no DBS dependency. This alone would
   let the pipeline auto-expand `GenSimFull`-style requests into their full N jobs
   without needing N separately extracted job packages.

4. **`EventAwareLumiBased` and others remain the hard, unsolved
   piece** Reproducing it would mean either porting WMCore's
   `JobSplitting` algorithm to run standalone against DBS
   block/file/lumi data, or querying a live WMAgent's
   `WorkQueue`/`JobCreator` state — neither trivial, and
   arguably a separate project in its own right.

5. **`scram project`/`cmsenv` as a declared `SoftwareRequirement`,
   not an imperative script step** — if a CVMFS-backed CMSSW
   `SoftwareRequirement` resolver were available to `cwltool` (some
   sites run one), the explicit `scram`/`cmsenv` shell sequence we
   added could become a declarative requirement instead, letting the
   runner handle environment setup rather than our script.
