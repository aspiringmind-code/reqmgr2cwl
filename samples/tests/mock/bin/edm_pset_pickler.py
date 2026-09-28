#!/usr/bin/env python3
"""Mock pickler: the 'pickle' is JSON describing the base PSet."""
import argparse
import hashlib
import json
import os
import re

p = argparse.ArgumentParser()
p.add_argument("--input", required=True)
p.add_argument("--output_pkl", required=True)
a = p.parse_args()
with open(a.input, "rb") as f:
    content = f.read()
modules = re.findall(r"^process\.(\w+)\s*=\s*cms\.OutputModule\(", content.decode(), re.M)
with open(a.output_pkl, "w") as f:
    json.dump({"pset_md5": hashlib.md5(content).hexdigest(),
               "cmssw_version": os.environ["CMSSW_VERSION"],
               "output_modules": modules, "tweak": {}}, f)
