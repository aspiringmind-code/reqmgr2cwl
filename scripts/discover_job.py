#!/usr/bin/env python3
"""
scripts/discover_job.py

Inspects the four artifacts a person drops under artifacts/:

  1. <workflow>-Sandbox_tar.bz2   (or *Sandbox*.tar.bz2 / *_tar.bz2)
  2. Job_<id>_tar.bz2             (or Job_<id>.tar.bz2)
  3. JobPackage.pkl               (any *JobPackage*.pkl)
  4. <anything>.json              (the ReqMgr2 request document)

...and produces a CWL job-order file (inputs.yml) that the generic
workflows/workgraph.cwl can run, WITHOUT any workflow-specific code.
Nothing here is hardcoded to a particular request name, job index, or
step name -- everything is read out of the four files themselves:

  - job index, workflow name, task/step path, requestType, worker OS,
    allocated cores/memory -> parsed out of wmagentJob.log inside the
    Job_<id> tarball (the "Job Instance = {...}" line WMAgent itself
    writes there).
  - the matching Step<N>/Task<N> definition (splitting algo, config
    cache id, CMSSW version, ScramArch, campaign, etc.) -> looked up in
    the ReqMgr2 JSON by matching the step/task name parsed above,
    handling both StepChain ("StepN"/"StepName") and TaskChain
    ("TaskN"/"TaskName") shapes, and both the wrapped
    ({"<name>": {...}}) and flat ({"RequestName": ..., ...}) JSON forms
    ReqMgr2 uses.
  - Unpacker.py -> extracted directly from WMCore.zip inside the
    sandbox tarball (WMCore/WMRuntime/Unpacker.py), so it never needs
    to be supplied as a separate file.

Usage:
    python3 scripts/discover_job.py \
        --artifacts-dir artifacts \
        --output artifacts/.generated/inputs.yml
"""
import argparse
import ast
import glob
import json
import os
import re
import shutil
import sys
import tarfile
import zipfile

WORKER_OS_TO_CONTAINER = {
    "slc6": "cmssw-el6",
    "rhel6": "cmssw-el6",
    "slc7": "cmssw-el7",
    "rhel7": "cmssw-el7",
    "rhel8": "cmssw-el8",
    "rhel9": "cmssw-el9",
    "alma8": "cmssw-el8",
    "alma9": "cmssw-el9",
}

def container_for_scram_arch(scram_arch):
    """Pick the cmssw-elN container from the ScramArch string itself.

    This is the RIGHT signal, not the job's recorded worker_os: worker_os
    describes the physical grid execute node's OS, which can (and did, in
    practice) differ from what a given CMSSW release actually needs.
    ScramArch directly encodes the OS family the release was built for
    (slc7_*, el8_*, el9_*, ...), so deriving the container from it avoids
    that mismatch entirely.
    """
    if not scram_arch:
        return None
    sa = scram_arch.lower()
    if sa.startswith("slc6") or sa.startswith("rhel6") or sa.startswith("el6"):
        return "cmssw-el6"
    if sa.startswith("slc7") or sa.startswith("rhel7") or sa.startswith("el7"):
        return "cmssw-el7"
    if sa.startswith("el8") or sa.startswith("rhel8"):
        return "cmssw-el8"
    if sa.startswith("el9") or sa.startswith("rhel9"):
        return "cmssw-el9"
    return None

STEP_KEY_RE = re.compile(r"^(Step|Task)(\d+)$")


def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def find_one(patterns, label, root):
    """Glob each pattern under root; require exactly one match across all of them."""
    candidates = []
    for pat in patterns:
        candidates.extend(glob.glob(os.path.join(root, pat)))
    candidates = sorted(set(candidates))
    if not candidates:
        die(f"No {label} found under {root} (tried patterns: {patterns})")
    if len(candidates) > 1:
        die(
            f"Multiple candidate {label} files found under {root}: {candidates}\n"
            f"Keep only one, or pass an explicit override flag."
        )
    return candidates[0]


def extract_wmagent_job_log(job_tar_path, work_dir):
    dest = os.path.join(work_dir, "job_tar_extracted")
    os.makedirs(dest, exist_ok=True)
    with tarfile.open(job_tar_path, "r:bz2") as tf:
        tf.extractall(dest)
    matches = glob.glob(os.path.join(dest, "**", "wmagentJob.log"), recursive=True)
    if not matches:
        die(f"No wmagentJob.log found inside {job_tar_path}")
    return matches[0]


def parse_job_instance(wmagent_log_path):
    with open(wmagent_log_path, "r", errors="replace") as f:
        text = f.read()

    dict_str = extract_balanced_braces(text, "Job Instance = {")
    if dict_str is None:
        die(f"Could not find a 'Job Instance = {{...}}' entry in {wmagent_log_path}")

    # Deliberately NOT eval-ing the whole dict. It can contain fields
    # whose printed repr isn't valid Python at all -- e.g. a non-empty
    # 'runs' set prints its WMCore.DataStructs.Run.Run elements as
    # '<WMCore.DataStructs.Run.Run object at 0x...>', which is a live
    # object's default repr, not reconstructible literal syntax.
    #
    # We only ever need six scalar top-level fields, none of which sit
    # inside the problematic input_files/runs structures, so pull just
    # those out directly with targeted regexes instead.
    job_instance = {}

    m = re.search(r"'id':\s*(\d+)", dict_str)
    if m:
        job_instance["id"] = int(m.group(1))

    m = re.search(r"'workflow':\s*'((?:[^'\\]|\\.)*)'", dict_str)
    if m:
        job_instance["workflow"] = m.group(1)

    m = re.search(r"'task':\s*'((?:[^'\\]|\\.)*)'", dict_str)
    if m:
        job_instance["task"] = m.group(1)

    m = re.search(r"'requestType':\s*'((?:[^'\\]|\\.)*)'", dict_str)
    if m:
        job_instance["requestType"] = m.group(1)

    m = re.search(r"'numberOfCores':\s*(\d+)", dict_str)
    if m:
        job_instance["numberOfCores"] = int(m.group(1))

    m = re.search(r"'estimatedMemoryUsage':\s*([\d.]+)", dict_str)
    if m:
        job_instance["estimatedMemoryUsage"] = float(m.group(1))

    missing = [k for k in ("id", "workflow", "task") if k not in job_instance]
    if missing:
        die(
            f"Could not extract required field(s) {missing} from the Job "
            f"Instance dict in {wmagent_log_path}.\n"
            f"First 300 chars extracted:\n{dict_str[:300]}"
        )

    worker_os = None
    m2 = re.search(r'"worker_os":\s*"([^"]+)"', text)
    if m2:
        worker_os = m2.group(1)

    return job_instance, worker_os


def extract_balanced_braces(text, marker):
    """Find `marker` (ending in '{') and return the full balanced {...}
    expression that follows, regardless of line wrapping. More robust
    than a single-line regex: correctly skips braces that appear inside
    quoted strings (LFNs, paths) instead of treating them as structural."""
    start_marker = text.find(marker)
    if start_marker == -1:
        return None
    start = start_marker + len(marker) - 1

    depth = 0
    in_string = None
    i = start
    n = len(text)
    while i < n:
        ch = text[i]
        if in_string:
            if ch == "\\":
                i += 2
                continue
            if ch == in_string:
                in_string = None
        else:
            if ch in ("'", '"'):
                in_string = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        i += 1
    return None


def extract_unpacker(sandbox_tar_path, work_dir):
    dest = os.path.join(work_dir, "sandbox_extracted")
    os.makedirs(dest, exist_ok=True)
    with tarfile.open(sandbox_tar_path, "r:bz2") as tf:
        tf.extractall(dest)

    wmcore_zip_matches = glob.glob(os.path.join(dest, "**", "WMCore.zip"), recursive=True)
    if not wmcore_zip_matches:
        die(f"No WMCore.zip found inside sandbox {sandbox_tar_path}")
    wmcore_zip = wmcore_zip_matches[0]

    with zipfile.ZipFile(wmcore_zip) as zf:
        member = "WMCore/WMRuntime/Unpacker.py"
        if member not in zf.namelist():
            die(f"{member} not found inside {wmcore_zip}")
        extracted_path = zf.extract(member, dest)

    unpacker_dest = os.path.join(work_dir, "Unpacker.py")
    shutil.copy(extracted_path, unpacker_dest)
    return unpacker_dest


def load_reqmgr2_request(json_path, workflow_name):
    with open(json_path) as f:
        data = json.load(f)

    # Wrapped form: {"<workflow_name>": {...}}
    if workflow_name in data and isinstance(data[workflow_name], dict):
        return data[workflow_name]

    # Flat form: the document itself is the request
    if "RequestName" in data:
        return data

    # Single-key wrapped form with an unexpected/different key
    if len(data) == 1:
        (only_value,) = data.values()
        if isinstance(only_value, dict):
            return only_value

    die(
        f"Could not locate the ReqMgr2 request body in {json_path} "
        f"for workflow '{workflow_name}' (looked for a top-level key "
        f"matching the workflow name, a flat 'RequestName' document, "
        f"or a single wrapped entry)."
    )


def find_matching_step(request, step_or_task_name):
    """Find the StepN/TaskN entry whose StepName/TaskName matches, else None."""
    for key, value in request.items():
        if not STEP_KEY_RE.match(key):
            continue
        if not isinstance(value, dict):
            continue
        name = value.get("StepName") or value.get("TaskName")
        if name == step_or_task_name:
            return key, value
    return None, None


def field(matched, request, key, default=None):
    if matched and key in matched:
        return matched[key]
    return request.get(key, default)


def per_step_dict_or_str(matched, request, key, step_name, default=None):
    """Handles fields that are either a plain string on the matched step,
    or a top-level dict keyed by step name (e.g. AcquisitionEra, ProcessingString)."""
    if matched and key in matched and not isinstance(matched[key], dict):
        return matched[key]
    top = request.get(key)
    if isinstance(top, dict):
        return top.get(step_name, default)
    if isinstance(top, str):
        return top
    return default


def first_if_list(value):
    if isinstance(value, list) and value:
        return value[0]
    return value


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifacts-dir", default="artifacts")
    ap.add_argument("--work-dir", default=None, help="default: <artifacts-dir>/.generated")
    ap.add_argument("--output", default=None, help="default: <work-dir>/inputs.yml")
    ap.add_argument("--run-script", default="tools/scripts/run_wmcore_job.sh")
    ap.add_argument("--container-override", default=None, help="Force the container (e.g. cmssw-el9) instead of deriving it from the job's recorded worker_os.")
    args = ap.parse_args()

    artifacts_dir = os.path.abspath(args.artifacts_dir)
    work_dir = os.path.abspath(args.work_dir or os.path.join(artifacts_dir, ".generated"))
    output_path = os.path.abspath(args.output or os.path.join(work_dir, "inputs.yml"))
    # Wipe any previous scratch content before extracting -- job_tar_extracted/
    # and sandbox_extracted/ are fixed paths reused every run, so leftovers
    # from a previous (different) job/workflow can silently get picked up
    # by glob.glob() instead of the new artifact.
    if os.path.isdir(work_dir):
        shutil.rmtree(work_dir)
    os.makedirs(work_dir, exist_ok=True)

    print(f"== Discovering artifacts under {artifacts_dir} ==")

    sandbox_tar = find_one(["*[Ss]andbox*tar.bz2", "*[Ss]andbox*.tar.bz2"], "sandbox tarball", artifacts_dir)
    job_tar = find_one(["Job_*tar.bz2", "Job_*.tar.bz2", "job_*tar.bz2"], "job tarball", artifacts_dir)
    job_package = find_one(["*JobPackage*.pkl", "*jobpackage*.pkl"], "JobPackage.pkl", artifacts_dir)
    reqmgr2_json = find_one(["*.json"], "ReqMgr2 request JSON", artifacts_dir)

    print(f"  sandbox      : {sandbox_tar}")
    print(f"  job tarball  : {job_tar}")
    print(f"  job package  : {job_package}")
    print(f"  reqmgr2 json : {reqmgr2_json}")

    print("== Parsing job tarball (wmagentJob.log) ==")
    wmagent_log = extract_wmagent_job_log(job_tar, work_dir)
    job_instance, worker_os = parse_job_instance(wmagent_log)

    job_index = job_instance["id"]
    workflow_name = job_instance["workflow"]
    task_path = job_instance["task"]
    step_name = task_path.rstrip("/").split("/")[-1]
    request_type_from_job = job_instance.get("requestType")
    num_cores = job_instance.get("numberOfCores", 1)
    est_memory_mb = int(job_instance.get("estimatedMemoryUsage", 2000))

    print(f"  job index    : {job_index}")
    print(f"  workflow     : {workflow_name}")
    print(f"  task path    : {task_path}")
    print(f"  step name    : {step_name}")
    print(f"  worker_os    : {worker_os}")
    print(f"  num_cores    : {num_cores}")
    print(f"  est. memory  : {est_memory_mb} MB")

    print("== Extracting Unpacker.py from sandbox (WMCore.zip) ==")
    unpacker_path = extract_unpacker(sandbox_tar, work_dir)
    print(f"  unpacker     : {unpacker_path}")

    print("== Loading ReqMgr2 request ==")
    request = load_reqmgr2_request(reqmgr2_json, workflow_name)

    matched_key, matched = find_matching_step(request, step_name)
    if matched:
        print(f"  matched step : {matched_key} (StepName/TaskName == '{step_name}')")
    else:
        print(
            f"  WARNING: no Step<N>/Task<N> entry in the JSON matched "
            f"step name '{step_name}'; falling back to top-level request "
            f"fields only. (Fine for single-task requests; check spelling "
            f"otherwise.)"
        )

    splitting_algo = field(matched, request, "SplittingAlgo", "unknown")
    events_per_job = field(matched, request, "EventsPerJob")
    primary_dataset = field(matched, request, "PrimaryDataset")
    input_dataset = field(matched, request, "InputDataset")
    config_cache_id = field(matched, request, "ConfigCacheID")
    cmssw_version = field(matched, request, "CMSSWVersion", request.get("CMSSWVersion"))
    scram_arch = first_if_list(field(matched, request, "ScramArch", request.get("ScramArch")))
    global_tag = field(matched, request, "GlobalTag", request.get("GlobalTag"))
    campaign = field(matched, request, "Campaign", request.get("Campaign"))
    acquisition_era = per_step_dict_or_str(matched, request, "AcquisitionEra", step_name)
    processing_string = per_step_dict_or_str(matched, request, "ProcessingString", step_name)

    memory_mb = int(field(matched, request, "Memory", est_memory_mb) or est_memory_mb)
    multicore = int(field(matched, request, "Multicore", num_cores) or num_cores)
    # Prefer what the job actually recorded as allocated, it's ground truth
    # for THIS run; reqmgr2 value is the fallback/default.
    final_cores = int(num_cores) if num_cores else multicore

    request_name = request.get("RequestName", workflow_name)
    request_type = request.get("RequestType", request_type_from_job or "unknown")
    request_status = request.get("RequestStatus", "unknown")
    requestor = request.get("Requestor", "unknown")
    prep_id = request.get("PrepID", "")
    dbs_url = request.get("DbsUrl", "")
    config_cache_url = request.get("ConfigCacheUrl", "")
    site_whitelist = request.get("SiteWhitelist", [])
    output_datasets = request.get("OutputDatasets", [])

    container_from_scram_arch = container_for_scram_arch(scram_arch)
    container_from_worker_os = WORKER_OS_TO_CONTAINER.get((worker_os or "").lower())

    if args.container_override:
        container = args.container_override
        print(f"  NOTE: container FORCED to '{container}' via --container-override")
    elif container_from_scram_arch:
        container = container_from_scram_arch
        if container_from_worker_os and container_from_worker_os != container:
            print(
                f"  NOTE: container '{container}' chosen from ScramArch "
                f"'{scram_arch}'. This differs from what the job's recorded "
                f"worker_os ('{worker_os}') would suggest "
                f"('{container_from_worker_os}') -- using ScramArch, since "
                f"that's what the CMSSW release actually needs to match."
            )
    elif container_from_worker_os:
        container = container_from_worker_os
        print(
            f"  NOTE: could not derive a container from ScramArch "
            f"('{scram_arch}'); falling back to worker_os ('{worker_os}') "
            f"-> '{container}'."
        )
    else:
        container = "cmssw-el8"
        print(
            f"  NOTE: could not derive a container from ScramArch "
            f"('{scram_arch}') or worker_os ('{worker_os}'); defaulting "
            f"to '{container}'. Consider --container-override if this is wrong."
        )

    print("== Resolved step/request metadata ==")
    for k, v in {
        "splitting_algo": splitting_algo,
        "events_per_job": events_per_job,
        "primary_dataset": primary_dataset,
        "input_dataset": input_dataset,
        "config_cache_id": config_cache_id,
        "cmssw_version": cmssw_version,
        "scram_arch": scram_arch,
        "global_tag": global_tag,
        "campaign": campaign,
        "acquisition_era": acquisition_era,
        "processing_string": processing_string,
        "container": container,
        "request_type": request_type,
        "request_status": request_status,
    }.items():
        print(f"  {k}: {v}")

    other_steps = []
    for key, value in request.items():
        if STEP_KEY_RE.match(key) and key != matched_key and isinstance(value, dict):
            other_steps.append(
                (value.get("StepName") or value.get("TaskName") or key)
            )
    if other_steps:
        print(
            f"  NOTE: {len(other_steps)} other step(s)/task(s) in this request "
            f"are not wired as executable CWL steps (no resolved job for "
            f"them was supplied): {other_steps}"
        )

    def y(s):
        """YAML-safe string quoting. All metadata fields here are typed as
        CWL 'string' inputs (even ones that happen to hold digits, like
        events_per_job) -- they're carried for documentation/hints, not
        arithmetic, so always emit a quoted string rather than a YAML
        number to avoid CWL type-mismatch errors."""
        if s is None:
            return '""'
        return json.dumps(str(s))

    def y_list(lst):
        if not lst:
            return "[]"
        return "[" + ", ".join(json.dumps(str(x)) for x in lst) + "]"

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    run_script_path = os.path.abspath(os.path.join(repo_root, args.run_script))

    lines = []
    lines.append(f"sandbox: {{class: File, path: {y(os.path.abspath(sandbox_tar))}}}")
    lines.append(f"job_package: {{class: File, path: {y(os.path.abspath(job_package))}}}")
    lines.append(f"unpacker_script: {{class: File, path: {y(unpacker_path)}}}")
    lines.append(f"run_script: {{class: File, path: {y(run_script_path)}}}")
    lines.append(f"reqmgr2_json: {{class: File, path: {y(os.path.abspath(reqmgr2_json))}}}")
    lines.append(f"job_index: {int(job_index)}")
    lines.append(f"num_cores: {int(final_cores)}")
    lines.append(f"memory_mb: {int(memory_mb)}")
    lines.append(f"cmssw_container: {y(container)}")
    lines.append(f"step_name: {y(step_name)}")
    lines.append(f"request_name: {y(request_name)}")
    lines.append(f"request_type: {y(request_type)}")
    lines.append(f"request_status: {y(request_status)}")
    lines.append(f"requestor: {y(requestor)}")
    lines.append(f"prep_id: {y(prep_id)}")
    lines.append(f"dbs_url: {y(dbs_url)}")
    lines.append(f"config_cache_url: {y(config_cache_url)}")
    lines.append(f"campaign: {y(campaign)}")
    lines.append(f"splitting_algo: {y(splitting_algo)}")
    lines.append(f"events_per_job: {y(events_per_job)}")
    lines.append(f"primary_dataset: {y(primary_dataset)}")
    lines.append(f"input_dataset: {y(input_dataset)}")
    lines.append(f"config_cache_id: {y(config_cache_id)}")
    lines.append(f"cmssw_version: {y(cmssw_version)}")
    lines.append(f"scram_arch: {y(scram_arch)}")
    lines.append(f"global_tag: {y(global_tag)}")
    lines.append(f"acquisition_era: {y(acquisition_era)}")
    lines.append(f"processing_string: {y(processing_string)}")
    lines.append(f"site_whitelist: {y_list(site_whitelist)}")
    lines.append(f"output_datasets: {y_list(output_datasets)}")

    with open(output_path, "w") as f:
        f.write("\n".join(lines) + "\n")

    print(f"== Wrote CWL job-order to {output_path} ==")
    print(output_path)  # last line: machine-readable path for callers


if __name__ == "__main__":
    main()