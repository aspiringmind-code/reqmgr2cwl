#!/usr/bin/env python3
"""Mock scram: project / build ProjectRename / runtime -sh."""
import os
import sys

MOCK_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
args = sys.argv[1:]
if args[:1] == ["project"]:
    area = args[1]
    os.makedirs(os.path.join(area, ".SCRAM"))
    os.makedirs(os.path.join(area, "src"))
    with open(os.path.join(area, ".SCRAM", "arch"), "w") as f:
        f.write(os.environ["SCRAM_ARCH"])
    # Real areas link into /cvmfs; make sure such links survive the CWL staging.
    os.symlink(os.path.join(MOCK_ROOT, "external_area"), os.path.join(area, "external"))
elif args[:2] == ["build", "ProjectRename"] or args[:2] == ["b", "ProjectRename"]:
    if not os.path.isdir(".SCRAM"):
        sys.exit("scram: not in a project area")
    open(os.path.join(".SCRAM", "renamed"), "w").close()
elif args[:2] == ["runtime", "-sh"]:
    with open(os.path.join(".SCRAM", "arch")) as f:
        arch = f.read()
    if arch != os.environ.get("SCRAM_ARCH"):
        sys.exit("scram: area is %s, SCRAM_ARCH is %s" % (arch, os.environ.get("SCRAM_ARCH")))
    if not os.path.isfile(os.path.join("external", "README")):
        sys.exit("scram: external link is broken")
    print("export CMSSW_BASE='%s'; export CMSSW_VERSION='%s';" % (os.getcwd(), os.path.basename(os.getcwd())))
else:
    sys.exit("mock scram: unsupported arguments %s" % args)
