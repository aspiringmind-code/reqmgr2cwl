#!/usr/bin/env python3
"""Mock tweak: merge the tweak JSON into the mock pickle."""
import argparse
import json

p = argparse.ArgumentParser()
p.add_argument("--input_pkl", required=True)
p.add_argument("--output_pkl", required=True)
p.add_argument("--json", required=True)
p.add_argument("--create_untracked_psets", action="store_true")
a = p.parse_args()
with open(a.input_pkl) as f:
    pkl = json.load(f)
with open(a.json) as f:
    pkl["tweak"].update(json.load(f))
with open(a.output_pkl, "w") as f:
    json.dump(pkl, f)
