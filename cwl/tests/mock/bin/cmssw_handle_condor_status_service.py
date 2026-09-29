#!/usr/bin/env python3
"""Mock: record the Condor status service name."""
import argparse
import json

p = argparse.ArgumentParser()
p.add_argument("--input_pkl", required=True)
p.add_argument("--output_pkl", required=True)
p.add_argument("--name", required=True)
a = p.parse_args()
with open(a.input_pkl) as f:
    pkl = json.load(f)
pkl["condor_status_name"] = a.name
with open(a.output_pkl, "w") as f:
    json.dump(pkl, f)
