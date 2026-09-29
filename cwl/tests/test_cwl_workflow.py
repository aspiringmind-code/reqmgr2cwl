#!/usr/bin/env python3
"""
Tests for the CWL StepChain workflow in cwl/.

The workflow is run end to end with cwltool against a mock CMSSW environment
(cwl/tests/mock: fake scram, cmssw-wm-tools and cmsRun), which checks the CWL
wiring without /cvmfs: step order, releases, PSets, tweaks and file chaining.
Real CMSSW runs are described in cwl/README.md.

Needs cwltool and node (for the CWL JavaScript expressions); tests that run
cwltool are skipped otherwise.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

CWL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_DIR = os.path.dirname(CWL_DIR)
#REPO_DIR = os.path.join(REPO_DIR, "cwl")
#CWL_DIR = os.path.join(CWL_DIR, "cwl")
SAMPLE_DIR = os.path.join(CWL_DIR, "samples")
MOCK_CMS_DIR = os.path.join(CWL_DIR, "tests", "mock", "cms")
WORKFLOW = os.path.join(CWL_DIR, "stepchain_6steps.cwl")
JOB38_JSON = os.path.join(CWL_DIR, "jobs", "job38.json")

sys.path.insert(0, os.path.join(CWL_DIR, "scripts"))
import make_job_inputs  # noqa: E402

CWLTOOL = shutil.which("cwltool") or (
    os.path.join(os.path.dirname(sys.executable), "cwltool")
    if os.path.isfile(os.path.join(os.path.dirname(sys.executable), "cwltool")) else None)
HAVE_CWLTOOL = CWLTOOL is not None and shutil.which("node") is not None


def run_cwltool(outdir, job_file, extra_env=None):
    env = dict(os.environ, VO_CMS_SW_DIR=MOCK_CMS_DIR, **(extra_env or {}))
    cmd = [CWLTOOL, "--no-container", "--outdir", outdir, "--preserve-environment", "VO_CMS_SW_DIR"]
    for name in extra_env or {}:
        cmd += ["--preserve-environment", name]
    return subprocess.run(cmd + [WORKFLOW, job_file], env=env, capture_output=True, text=True)


def generate_job_file(path, max_events=None, extra_lines=""):
    with open(os.path.join(SAMPLE_DIR, "request.json")) as f:
        req = json.load(f)
    with open(JOB38_JSON) as f:
        job = json.load(f)
    steps = make_job_inputs.build_step_params(req, job, os.path.join(SAMPLE_DIR, "PSets"), max_events=max_events)
    with open(path, "w") as f:
        f.write(make_job_inputs.to_yaml(job["job_index"], req["RequestName"], steps, os.path.dirname(path)))
        f.write(extra_lines)


class TestMakeJobInputs(unittest.TestCase):
    def test_committed_job_files_are_up_to_date(self):
        for name, max_events in (("job38.yml", None), ("job38_10events.yml", 10)):
            committed = os.path.join(CWL_DIR, "jobs", name)
            # Written next to the committed file so the relative PSet paths match.
            fd, fresh = tempfile.mkstemp(dir=os.path.dirname(committed), suffix=".yml")
            os.close(fd)
            try:
                generate_job_file(fresh, max_events=max_events)
                with open(fresh) as f1, open(committed) as f2:
                    self.assertEqual(f1.read(), f2.read(), "%s is stale; rerun make_job_inputs.py" % name)
            finally:
                os.remove(fresh)

    def test_job38_values(self):
        with open(os.path.join(SAMPLE_DIR, "request.json")) as f:
            req = json.load(f)
        with open(JOB38_JSON) as f:
            job = json.load(f)
        steps = make_job_inputs.build_step_params(req, job, os.path.join(SAMPLE_DIR, "PSets"))
        self.assertEqual(list(steps), ["step%d" % i for i in range(1, 7)])
        step1 = steps["step1"]
        self.assertEqual((step1["first_lumi"], step1["max_events"], step1["first_event"], step1["first_run"]),
                         (38, 830, 30711, 1))
        self.assertEqual(steps["step3"]["cmssw_version"], "CMSSW_9_4_14_UL_patch1")
        self.assertEqual(steps["step3"]["scram_arch"], "slc7_amd64_gcc630")
        self.assertEqual([steps["step%d" % i]["output_module"] for i in range(1, 7)],
                         ["RAWSIMoutput", "RAWSIMoutput", "RAWSIMoutput", "AODSIMoutput",
                          "MINIAODSIMoutput", "NANOEDMAODSIMoutput"])
        self.assertTrue(all(steps["step%d" % i]["max_events"] == -1 for i in range(2, 7)))

    def test_tweak_int(self):
        self.assertEqual(make_job_inputs.tweak_int("k", "customTypeCms.untracked.uint32(38)"), 38)
        self.assertEqual(make_job_inputs.tweak_int(
            "k", "customTypeCms.untracked.PSet(input=cms.untracked.int32(-1))"), -1)


@unittest.skipUnless(HAVE_CWLTOOL, "cwltool and node are needed to run the CWL workflow")
class TestWorkflowOnMock(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cwl-test-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.job_file = os.path.join(self.tmp, "job38.yml")

    def test_validate(self):
        result = subprocess.run([CWLTOOL, "--validate", WORKFLOW], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_six_steps_chain_like_job38(self):
        generate_job_file(self.job_file, max_events=10, extra_lines="report_to_condor: true\n")
        result = run_cwltool(os.path.join(self.tmp, "out"), self.job_file)
        self.assertEqual(result.returncode, 0, result.stderr[-5000:])
        out = json.loads(result.stdout)

        # Follow the last output back to step 1: six cmsRun executions, in order.
        with open(out["nanoaodsim"]["path"]) as f:
            record = json.load(f)
        chain = []
        while record:
            chain.append(record)
            record = record["input"]
        chain.reverse()
        self.assertEqual([r["module"] for r in chain],
                         ["RAWSIMoutput", "RAWSIMoutput", "RAWSIMoutput", "AODSIMoutput",
                          "MINIAODSIMoutput", "NANOEDMAODSIMoutput"])
        self.assertEqual([r["cmssw_version"] for r in chain],
                         ["CMSSW_10_6_47"] * 2 + ["CMSSW_9_4_14_UL_patch1"] + ["CMSSW_10_6_47"] * 3)
        self.assertEqual([r["condor_status_name"] for r in chain], ["cmsRun%d" % i for i in range(1, 7)])
        self.assertTrue(all(r["nevents_handled"] for r in chain))
        for step_num, r in enumerate(chain, 1):
            pset = [p for p in os.listdir(os.path.join(SAMPLE_DIR, "PSets"))
                    if p.startswith("PSet_cmsRun%d_" % step_num)][0]
            with open(os.path.join(SAMPLE_DIR, "PSets", pset), "rb") as f:
                self.assertEqual(r["pset_md5"], hashlib.md5(f.read()).hexdigest())

        # The applied tweaks are Marco's job38.json tweaks, except for file wiring and the test's maxEvents.
        with open(JOB38_JSON) as f:
            reference = json.load(f)["tweaks"]
        self.assertEqual([t["basename"] for t in out["tweaks"]], ["cmsRun%d-tweak.json" % i for i in range(1, 7)])
        file_keys = re.compile(r"^process\.(source\.fileNames|\w+\.fileName)$")
        for step_num, tweak_file in enumerate(out["tweaks"], 1):
            with open(tweak_file["path"]) as f:
                applied = json.load(f)
            expected = dict(reference[str(step_num)])
            if step_num == 1:
                expected["process.maxEvents"] = "customTypeCms.untracked.PSet(input=cms.untracked.int32(10))"
            else:
                self.assertEqual(applied["process.source.fileNames"], "customTypeCms.untracked.vstring(['file:input.root'])")
            self.assertEqual({k: v for k, v in applied.items() if not file_keys.match(k)},
                             {k: v for k, v in expected.items() if not file_keys.match(k)})

        self.assertEqual([f["basename"] for f in out["job_reports"]],
                         ["cmsRun%d-job_report.xml" % i for i in range(1, 7)])
        self.assertEqual(len(out["logs"]), 12)
        self.assertEqual(out["aodsim"]["basename"], "AODSIMoutput.root")
        self.assertEqual(out["miniaodsim"]["basename"], "MINIAODSIMoutput.root")

    def test_failure_in_job_report_fails_the_step(self):
        generate_job_file(self.job_file, max_events=10)
        result = run_cwltool(os.path.join(self.tmp, "out"), self.job_file, {"MOCK_CMSRUN_FJR_ERROR": "8001"})
        self.assertNotEqual(result.returncode, 0)
        # Process exit codes are 8 bits, so the CMS code 8001 reaches cwltool as 8001 % 256 = 65.
        self.assertIn("[job cmsrun] exited with status: %d" % (8001 % 256), result.stderr)
        self.assertRegex(result.stderr, r"\[job cmsrun\] completed permanentFail")
        self.assertNotIn("starting step tweak_2", result.stderr, "step 2 must not start after step 1 failed")


if __name__ == "__main__":
    unittest.main()
