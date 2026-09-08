#!/usr/bin/env python3
"""Regenerate eval case inputs + golden answers, then verify every golden."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import gencases, verify

def main():
    verbose = "-v" in sys.argv or "--verbose" in sys.argv
    goldens = gencases.generate_all()
    print("generated %d cases under cases/\n" % len(goldens))
    ok, problems, notes = verify.verify_all(goldens)
    if verbose:
        for n in notes:
            print("  " + n)
        print("")
    for p in problems:
        print("  " + p)
    if not ok:
        print("\nFAIL: %d golden(s) have unsafe margins or inconsistent semantics." % len(problems))
        return 1
    print("OK: %d goldens verified against lib/refcalc.py (independent impl) "
          "with safe margins." % len(goldens))
    return 0

if __name__ == "__main__":
    sys.exit(main())
