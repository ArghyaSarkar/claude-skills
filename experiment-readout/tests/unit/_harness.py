"""Shared test harness: path-based import of the implementation, fixture
access, CLI invocation with caching, and payload-scanning utilities.

Design notes
------------
* The implementation is imported BY PATH (importlib) so the suite runs from any
  cwd and never depends on sys.path or on the skill being installed.
* If scripts/*.py is absent or fails to import, that is reported as a CLEAN
  TEST FAILURE with a readable message -- never as a collection-time traceback.
  Every test that needs the implementation calls require_*() first.
* Expected values come from tests/fixtures/manifest.json (written by the seeded
  generator) and from tests/unit/_ref.py (an independent reference), never from
  the implementation's own output.
"""

import importlib.util
import json
import math
import os
import subprocess
import sys
import unittest

TESTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_ROOT = os.path.dirname(TESTS_DIR)
SCRIPTS_DIR = os.path.join(SKILL_ROOT, "scripts")
FIXTURES_DIR = os.path.join(TESTS_DIR, "fixtures")

PY = sys.executable or "/usr/bin/python3"
CLI_TIMEOUT = 180

# Contract constants (frozen; duplicated here deliberately so a test failure
# means the implementation drifted, not that a shared constant was edited).
SRM_ALPHA = 0.001
SIG_ALPHA = 0.05
POWER = 0.80
MDE_REL = 0.03
GUARDRAIL_PP = 0.01
METRIC_WINDOW = 28

VALIDITY_GATES = ["design_integrity", "srm", "maturity"]
CONCLUSION_GATES = ["guardrail", "lift"]
ALL_GATES = VALIDITY_GATES + CONCLUSION_GATES
VERDICTS = {"INVALID-DESIGN", "INVALID-SRM", "INVALID-IMMATURE",
            "NO-SHIP", "SHIP", "INCONCLUSIVE"}
# AMENDMENT 3B added NOT_ASSESSABLE as a status distinct from NOT_RUN:
#   NOT_RUN        = deliberately SUPPRESSED because a validity gate failed
#   NOT_ASSESSABLE = the gate had NO INPUTS, because gate 0 could not supply them
# "we chose not to conclude" and "we could not check" demand different next
# actions, so collapsing them into one word is a reporting bug.
STATUSES = {"PASS", "FAIL", "WARN", "NOT_RUN", "NOT_ASSESSABLE"}


# ------------------------------------------------------------- impl import --

def load_impl(basename):
    """Import scripts/<basename>.py by path. Returns (module, error_string)."""
    path = os.path.join(SCRIPTS_DIR, basename + ".py")
    if not os.path.isdir(SCRIPTS_DIR):
        return None, ("implementation directory missing: %s -- nothing to test"
                      % SCRIPTS_DIR)
    if not os.path.exists(path):
        return None, ("implementation missing: expected %s (the skill has not "
                      "written %s.py yet)" % (path, basename))
    try:
        spec = importlib.util.spec_from_file_location("_impl_" + basename, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        return mod, None
    except BaseException as exc:            # noqa: BLE001 - report, never crash
        return None, ("implementation failed to import: %s raised %s: %s"
                      % (path, type(exc).__name__, exc))


GATES, GATES_ERR = load_impl("gates")


def script_path(name):
    return os.path.join(SCRIPTS_DIR, name)


# ---------------------------------------------------------------- fixtures --

def _load_manifest():
    p = os.path.join(FIXTURES_DIR, "manifest.json")
    if not os.path.exists(p):
        raise RuntimeError(
            "fixtures/manifest.json missing -- run "
            "tests/fixtures/generate_fixtures.py first")
    with open(p) as fh:
        return json.load(fh)


MANIFEST = _load_manifest()
FIXTURES = MANIFEST["fixtures"]

INVALID_FIXTURES = sorted(k for k, v in FIXTURES.items() if v["invalid"])
VALID_FIXTURES = sorted(k for k, v in FIXTURES.items() if not v["invalid"])


def fx(name):
    return FIXTURES[name]


def results_path(name):
    return os.path.join(FIXTURES_DIR, FIXTURES[name]["results"])


def brief_path(name):
    return os.path.join(FIXTURES_DIR, FIXTURES[name]["brief"])


def read_arm(name, column):
    """Return (treatment_values, control_values) for a numeric column, read
    straight from the fixture CSV. Used to build oracle expectations.

    NON-NUMERIC CELLS ARE SKIPPED. Some fixtures deliberately carry the
    unparseable sentinel "n/a" (AMENDMENT 3A), and a helper that raises on it
    would abort its caller in SETUP -- the test would report an ERROR instead of
    an assertion result, which is the worst failure mode a test can have: it
    looks environmental and gets waved through. Helpers must never be the thing
    that fails.
    """
    import csv
    t, c = [], []
    with open(results_path(name)) as fh:
        for row in csv.DictReader(fh):
            raw = row.get(column)
            try:
                val = float(raw)
            except (TypeError, ValueError):
                continue
            (t if row["arm"] == "treatment" else c).append(val)
    return t, c


# --------------------------------------------------------------- CLI calls --

_CLI_CACHE = {}


def run_cli(script, args, cwd=None):
    """Run scripts/<script> with args. Returns a CompletedProcess, or None if
    the script does not exist. Results are cached per (script, args, cwd)."""
    key = (script, tuple(args), cwd)
    if key in _CLI_CACHE:
        return _CLI_CACHE[key]
    path = script_path(script)
    if not os.path.exists(path):
        _CLI_CACHE[key] = None
        return None
    proc = subprocess.run(
        [PY, path] + list(args),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd=cwd or SKILL_ROOT, timeout=CLI_TIMEOUT, universal_newlines=True)
    _CLI_CACHE[key] = proc
    return proc


def readout_args(name, asof="fixture", as_json=True):
    """Build run_readout.py argv for a fixture. asof='fixture' uses the
    manifest's asof (which may be None); pass an explicit date to override, or
    None to force the inferred default."""
    e = FIXTURES[name]
    args = ["--results", results_path(name), "--brief", brief_path(name)]
    use = e["asof"] if asof == "fixture" else asof
    if use:
        args += ["--asof", use]
    if as_json:
        args += ["--json"]
    return args


def run_readout(name, asof="fixture", as_json=True):
    return run_cli("run_readout.py", readout_args(name, asof, as_json))


# ---------------------------------------------------------- payload walking --

def walk(obj, path="$"):
    """Yield (json_path, value) for every leaf and container in a payload."""
    yield path, obj
    if isinstance(obj, dict):
        for k, v in obj.items():
            for item in walk(v, "%s.%s" % (path, k)):
                yield item
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            for item in walk(v, "%s[%d]" % (path, i)):
                yield item


def all_numbers(obj):
    """Every numeric leaf in the payload, as (json_path, float)."""
    out = []
    for p, v in walk(obj):
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)) and not (
                isinstance(v, float) and math.isnan(v)):
            out.append((p, float(v)))
        elif isinstance(v, str):
            # numbers smuggled into strings count too
            for tok in _numeric_tokens(v):
                out.append((p, tok))
    return out


_NUM_RE = None


def _numeric_tokens(s):
    global _NUM_RE
    if _NUM_RE is None:
        import re
        _NUM_RE = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
    out = []
    for m in _NUM_RE.finditer(s):
        try:
            out.append(float(m.group(0)))
        except ValueError:
            pass
    return out


def all_keys(obj):
    """Every dict key appearing anywhere in the payload, lowercased."""
    out = set()
    for _p, v in walk(obj):
        if isinstance(v, dict):
            out.update(str(k).lower() for k in v)
    return out


def prune(obj, drop_paths):
    """Deep copy of obj with the given dotted top-level gate paths removed.
    drop_paths are like 'gates.srm'."""
    import copy
    out = copy.deepcopy(obj)
    for dp in drop_paths:
        parts = dp.split(".")
        cur = out
        ok = True
        for p in parts[:-1]:
            if isinstance(cur, dict) and p in cur:
                cur = cur[p]
            else:
                ok = False
                break
        if ok and isinstance(cur, dict):
            cur.pop(parts[-1], None)
    return out


def contains_number_token(text, form):
    """True if `form` appears in `text` as a COMPLETE numeric token.

    Plain substring matching produces false positives: the pooled cohort mean
    "2.1422" contains the substring "2.14", which is a different number. A
    leaked value would be rendered as a whole token, so we require that the
    match is not flanked by further digits or a decimal point.
    """
    import re as _re
    return _re.search(r"(?<![0-9.])" + _re.escape(form) + r"(?![0-9])",
                      text) is not None


def sig_digits(s):
    """Significant digits in a plain decimal rendering."""
    body = s.lstrip("-+").split("e")[0].replace(".", "").lstrip("0")
    return len(body)


def number_forms(x, min_sig=3):
    """String renderings a leaking implementation would plausibly emit for x.

    Only renderings carrying at least `min_sig` significant digits are kept:
    a 2-dp rendering of 0.0258 is "0.03", which would collide with the MDE and
    produce a false positive. Percent renderings are included because reports
    quote lifts and guardrail deltas in % and pp.
    """
    forms = set()
    if x is None:
        return forms
    for v in (x, x * 100.0):
        av = abs(v)
        if av >= 1e-4:
            for nd in (2, 3, 4, 5):
                s = "%.*f" % (nd, v)
                if sig_digits(s) >= min_sig:
                    forms.add(s)
                    forms.add(s.lstrip("-"))
        else:
            for nd in (2, 3):
                forms.add("%.*e" % (nd, v))
    return {f for f in forms if any(ch.isdigit() and ch != "0" for ch in f)}


# ------------------------------------------------------------- base classes --

class ImplCase(unittest.TestCase):
    """Base case that turns a missing/broken implementation into a clean,
    single-line failure instead of an import traceback."""

    def gates(self):
        if GATES is None:
            self.fail(GATES_ERR)
        return GATES

    def func(self, name):
        mod = self.gates()
        fn = getattr(mod, name, None)
        if fn is None:
            self.fail("gates.py does not define %s() (required by the contract)"
                      % name)
        if not callable(fn):
            self.fail("gates.%s exists but is not callable" % name)
        return fn

    def cli(self, script, args, cwd=None):
        proc = run_cli(script, args, cwd)
        if proc is None:
            self.fail("implementation missing: expected %s" % script_path(script))
        return proc

    def payload(self, name, asof="fixture"):
        """Parsed --json payload for a fixture, with clean failures on a
        missing script, a non-zero exit, or unparseable stdout."""
        proc = self.cli("run_readout.py", readout_args(name, asof, True))
        if proc.returncode != 0:
            self.fail("run_readout.py exited %d on fixture %r (expected 0; a "
                      "verdict is a result, not an error)\nSTDOUT: %s\nSTDERR: %s"
                      % (proc.returncode, name, proc.stdout[:2000],
                         proc.stderr[:2000]))
        try:
            return json.loads(proc.stdout)
        except ValueError as exc:
            self.fail("--json stdout is not parseable JSON for fixture %r: %s\n"
                      "STDOUT[:2000]: %r" % (name, exc, proc.stdout[:2000]))

    def gate(self, pay, name, fixture=""):
        gates = pay.get("gates")
        if not isinstance(gates, dict):
            self.fail("payload has no 'gates' dict %s" % (("(%s)" % fixture)
                                                          if fixture else ""))
        if name not in gates:
            self.fail("payload gates missing %r (present: %s) %s"
                      % (name, sorted(gates), fixture))
        g = gates[name]
        if not isinstance(g, dict):
            self.fail("gates[%r] is %r, expected a dict %s" % (name, g, fixture))
        return g

    def assertRelClose(self, got, want, rtol, msg=""):
        if want == 0:
            self.assertLessEqual(abs(got), rtol, "%s got=%r want=0" % (msg, got))
            return
        rel = abs(got - want) / abs(want)
        self.assertLessEqual(
            rel, rtol,
            "%s got=%.12g want=%.12g rel_err=%.3g (tol %.3g)"
            % (msg, got, want, rel, rtol))
