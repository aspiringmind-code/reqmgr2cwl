#!/usr/bin/env python3
"""
tests/run_tests.sh (Python, invoked via the shell shim below)

Validates all CWL documents, then builds a small SYNTHETIC set of the
four artifacts (a fabricated TaskChain request, different job index,
different step, different worker OS than any real example) and runs
the full discover_job.py -> cwltool pipeline against it with a mocked
runner. This is the genericness test: it proves discover_job.py and
the CWL files make no assumption specific to any one real workflow.

No CVMFS needed. Safe to run in plain CI.
"""
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CWLTOOL = os.environ.get("CWLTOOL", "cwltool")


def run(cmd, **kw):
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, check=True, **kw)


def validate_cwl():
    print("== Validating CWL documents ==")
    for sub in ["tools", "workflows"]:
        d = os.path.join(REPO_ROOT, sub)
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".cwl"):
                run([CWLTOOL, "--validate", os.path.join(d, fn)])


def build_synthetic_artifacts(artifacts_dir):
    """A fabricated TaskChain request, deliberately different in shape
    from any real example: TaskChain (not StepChain), flat JSON (not
    wrapped in a top-level request-name key), matches the SECOND task
    entry (not the first), a different worker OS (rhel8 -> cmssw-el8)."""
    os.makedirs(artifacts_dir, exist_ok=True)

    workflow = "synthuser_SynthExample_TaskChain_990101_000000_0001"
    job_index = 42

    # -- Job_<id>_tar.bz2 --
    with tempfile.TemporaryDirectory() as tmp:
        job_dir = os.path.join(tmp, f"Job_{job_index}")
        os.makedirs(job_dir)
        job_instance = (
            "{'input_files': [], 'id': %d, 'jobgroup': 1, 'name': 'x-0', "
            "'state': 'new', 'task': '/%s/RecoStep', 'workflow': '%s', "
            "'owner': 'synthuser', 'estimatedJobTime': 1000, "
            "'estimatedMemoryUsage': 3000.0, 'jobType': 'Production', "
            "'requestType': 'TaskChain', 'numberOfCores': 2}"
            % (job_index, workflow, workflow)
        )
        with open(os.path.join(job_dir, "wmagentJob.log"), "w") as f:
            f.write("2026-01-01 00:00:00,000:INFO:Startup:Loading task\n")
            f.write(f"Job Instance = {job_instance}\n")
            f.write('    "worker_os": "rhel8"\n')
        job_tar_path = os.path.join(artifacts_dir, f"Job_{job_index}_tar.bz2")
        with tarfile.open(job_tar_path, "w:bz2") as tf:
            tf.add(job_dir, arcname=f"Job_{job_index}")

    # -- <workflow>-Sandbox_tar.bz2, containing WMCore.zip with a stub Unpacker.py --
    with tempfile.TemporaryDirectory() as tmp:
        wmcore_zip_path = os.path.join(tmp, "WMCore.zip")
        stub = (
            "import sys, os\n"
            "print('MOCK Unpacker.py invoked with:', sys.argv)\n"
            "os.makedirs('job', exist_ok=True)\n"
            "open('job/Startup.py', 'w').write('print(1)\\n')\n"
        )
        with zipfile.ZipFile(wmcore_zip_path, "w") as zf:
            zf.writestr("WMCore/WMRuntime/Unpacker.py", stub)
        sandbox_tar_path = os.path.join(artifacts_dir, f"{workflow}-Sandbox_tar.bz2")
        with tarfile.open(sandbox_tar_path, "w:bz2") as tf:
            tf.add(wmcore_zip_path, arcname="WMCore.zip")

    # -- JobPackage.pkl (content irrelevant to discover_job.py; only the
    #    path is used, the real Unpacker.py is what reads it for real) --
    with open(os.path.join(artifacts_dir, "JobPackage.pkl"), "wb") as f:
        f.write(b"not a real pickle, only the path matters for this test")

    # -- ReqMgr2 JSON: flat form, TaskChain, two tasks, job matches Task2 --
    request = {
        "RequestName": workflow,
        "RequestType": "TaskChain",
        "RequestStatus": "running-open",
        "Requestor": "synthuser",
        "PrepID": "SYNTH-TEST-001",
        "Campaign": "SynthCampaign",
        "DbsUrl": "https://cmsweb-testbed.cern.ch/dbs/int/global/DBSReader",
        "ConfigCacheUrl": "https://cmsweb.cern.ch/couchdb",
        "SiteWhitelist": ["T2_CH_CERN"],
        "OutputDatasets": ["/SynthPrimary/SynthProcessing-v1/RECO"],
        "Task1": {
            "TaskName": "GenStep",
            "SplittingAlgo": "EventBased",
            "EventsPerJob": 500,
            "PrimaryDataset": "SynthPrimary",
            "ConfigCacheID": "aaaa1111",
            "CMSSWVersion": "CMSSW_14_0_0",
            "ScramArch": ["el8_amd64_gcc12"],
            "GlobalTag": "SYNTH_GT_v1",
            "AcquisitionEra": "SynthEra1",
        },
        "Task2": {
            "TaskName": "RecoStep",
            "SplittingAlgo": "EventAwareLumiBased",
            "InputStep": "GenStep",
            "ConfigCacheID": "bbbb2222",
            "CMSSWVersion": "CMSSW_14_0_1",
            "ScramArch": ["el8_amd64_gcc12"],
            "GlobalTag": "SYNTH_GT_v2",
            "AcquisitionEra": "SynthEra2",
        },
    }
    with open(os.path.join(artifacts_dir, f"{workflow}.json"), "w") as f:
        json.dump(request, f)

    return workflow, job_index


def main():
    validate_cwl()

    with tempfile.TemporaryDirectory() as tmp:
        artifacts_dir = os.path.join(tmp, "artifacts")
        workflow, job_index = build_synthetic_artifacts(artifacts_dir)

        print(f"\n== Running discover_job.py against synthetic workflow '{workflow}' ==")
        mock_run_script = os.path.join(REPO_ROOT, "tests", "mocks", "run_wmcore_job.sh")
        result = subprocess.run(
            [
                sys.executable,
                os.path.join(REPO_ROOT, "scripts", "discover_job.py"),
                "--artifacts-dir", artifacts_dir,
                "--run-script", mock_run_script,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        print(result.stdout)
        inputs_yml = result.stdout.strip().splitlines()[-1]

        assert f"job index    : {job_index}" in result.stdout
        assert "step name    : RecoStep" in result.stdout
        assert "matched step : Task2" in result.stdout
        assert "container: cmssw-el8" in result.stdout
        print("== discover_job.py resolved the synthetic Task2/RecoStep correctly ==")

        print("\n== Running full CWL workflow against synthetic inputs (mocked runner) ==")
        outdir = os.path.join(tmp, "results")
        run([CWLTOOL, "--outdir", outdir,
             os.path.join(REPO_ROOT, "workflows", "workgraph.cwl"),
             inputs_yml])

        assert os.path.isfile(os.path.join(outdir, "job", "Startup.py"))
        assert os.path.isfile(os.path.join(outdir, "job-output", "result.txt"))
        print("== Outputs present as expected ==")

    print("\n== All tests passed ==")


if __name__ == "__main__":
    main()
