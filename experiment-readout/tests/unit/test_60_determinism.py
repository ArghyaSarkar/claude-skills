"""Determinism: the same inputs must produce a byte-identical JSON payload.

A readout that wobbles between runs cannot be cited in a decision, and it also
hides real changes in review. This bypasses the harness's CLI cache and shells
out twice for real.
"""

import hashlib
import os
import subprocess
import unittest

from _harness import (CLI_TIMEOUT, FIXTURES, PY, SKILL_ROOT, ImplCase,
                      brief_path, readout_args, results_path, script_path)


def _run(args, cwd):
    return subprocess.run([PY, script_path("run_readout.py")] + list(args),
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          cwd=cwd, timeout=CLI_TIMEOUT, universal_newlines=True)


class TestDeterminism(ImplCase):

    def _require(self):
        if not os.path.exists(script_path("run_readout.py")):
            self.fail("implementation missing: expected %s"
                      % script_path("run_readout.py"))

    def test_json_payload_is_byte_identical_across_runs(self):
        self._require()
        drift = []
        for name in sorted(FIXTURES):
            args = readout_args(name, "fixture", True)
            a = _run(args, SKILL_ROOT)
            b = _run(args, SKILL_ROOT)
            if a.stdout != b.stdout:
                drift.append("%s: stdout differs between two identical runs "
                             "(sha %s vs %s)"
                             % (name,
                                hashlib.sha256(a.stdout.encode()).hexdigest()[:12],
                                hashlib.sha256(b.stdout.encode()).hexdigest()[:12]))
            if a.returncode != b.returncode:
                drift.append("%s: exit code differs (%d vs %d)"
                             % (name, a.returncode, b.returncode))
        self.assertFalse(drift, "\n\nNON-DETERMINISM:\n  " + "\n  ".join(drift))

    def test_payload_does_not_depend_on_cwd(self):
        """Run from the skill root and from the fixtures directory with
        absolute paths: the payload must be identical. A difference means a
        relative path or a cwd-derived value leaked in."""
        self._require()
        drift = []
        other = os.path.join(SKILL_ROOT, "tests", "fixtures")
        for name in ("ship_clean", "srm_broken", "real_dataset_shape"):
            args = readout_args(name, "fixture", True)
            a = _run(args, SKILL_ROOT)
            b = _run(args, other)
            if a.stdout != b.stdout:
                drift.append("%s: payload depends on the working directory"
                             % name)
        self.assertFalse(drift, "\n\nCWD DEPENDENCE:\n  " + "\n  ".join(drift))

    def test_no_wall_clock_leaks_into_the_payload(self):
        """The payload must not embed a timestamp: that alone would break
        byte-identity and make golden comparison impossible. Covered by the
        byte-identity test above, but asserted explicitly on the key names so
        the failure message is readable."""
        self._require()
        import json
        pay = self.payload("ship_clean")
        from _harness import all_keys
        bad = [k for k in all_keys(pay)
               if k in ("now", "timestamp", "generated_at", "run_at",
                        "created_at", "today")]
        self.assertFalse(bad,
                         "the payload carries wall-clock key(s) %s, which "
                         "breaks determinism" % bad)


if __name__ == "__main__":
    unittest.main()
