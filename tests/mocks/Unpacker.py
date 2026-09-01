#!/usr/bin/env python3
# tests/mocks/Unpacker.py
#
# Standalone copy kept for reference / manual test invocation. The
# actual synthetic-fixture test in run_tests.sh builds its own tiny
# WMCore.zip with an equivalent stub baked in (so that discover_job.py's
# real extraction-from-WMCore.zip code path is exercised, not bypassed).
import sys
import os

print("MOCK Unpacker.py invoked with:", sys.argv)
os.makedirs("job", exist_ok=True)
with open("job/Startup.py", "w") as f:
    f.write("print('mock startup ran')\n")
