"""L5 — GOLDEN SNAPSHOTS of the RENDERED REPORT.

The category payload assertions cannot cover: duplication, ordering, and preamble
defects. Two layout regressions (the verdict landing on line 4, and a duplicated WHY
block) both shipped with a fully green suite. A byte-for-byte diff of the rendered
document catches that class instantly.

THREE ENVIRONMENT RULES, learned the hard way. A snapshot is only as portable as the
things it is allowed to contain, and the first version of this file was recorded through
its author's own runner and failed immediately under tests/run_tests.sh:

1. NO ABSOLUTE PATHS. The report echoes the brief path as supplied -- correct, useful
   behaviour -- and the report WRAPS long lines, so an absolute path arrives split across
   lines with an indent in the middle. No post-hoc regex can reliably rejoin that. The fix
   is upstream: every case runs with cwd=FIXTURES_DIR and RELATIVE filenames, so no
   machine path ever enters the output. `normalise()` remains as a net for anything else,
   and `test_no_absolute_path_in_output` fails loudly rather than letting a leak be
   recorded silently.
   SYMLINKS: one file can have TWO valid absolute spellings -- here ~/.claude/skills is a
   symlink to ~/github-repos/claude-skills. os.path.abspath normalises ".." but does NOT
   resolve symlinks, so a snapshot recorded via one spelling fails when replayed via the
   other, and a root token derived as one spelling would not match a leak printed as the
   other -- the guard would pass on a genuine leak. Every root is therefore reduced with
   os.path.realpath AND kept in its abspath form, and both spellings are redacted. Same
   disease as two sources of truth, one layer down: two spellings of one truth.
2. NO CLOCK. Every case pins --asof, so the `assumed: today` branch is unreachable.
   Asserted twice: statically over CASES, and dynamically on the payload
   (asof_provenance == "given", reproducible is True). Without this a snapshot recorded
   today fails tomorrow and nobody can tell whether the skill changed or the calendar did.
   --today is banned outright in snapshot cases: it is a clock override.
3. VERIFY FROM EVERY ENTRY POINT. Green under the author's harness and red under the real
   one is not yet a test. This file must pass via tests/run_tests.sh AND via a direct
   `python3 -m unittest` from tests/unit.

To (re)record after an INTENTIONAL layout change -- and only then, having read the diff:
    UPDATE_SNAPSHOTS=1 tests/run_tests.sh test_60_snapshot
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS_DIR = os.path.dirname(HERE)
SKILL_ROOT = os.path.dirname(TESTS_DIR)
SCRIPTS_DIR = os.path.join(SKILL_ROOT, "scripts")
FIXTURES_DIR = os.path.join(TESTS_DIR, "fixtures")
SNAP_DIR = os.path.join(HERE, "snapshots")
PY = sys.executable or "/usr/bin/python3"


def _spellings(path):
    """Every absolute spelling of one location: as-reached, and symlink-resolved."""
    if not path:
        return set()
    return {os.path.abspath(path), os.path.realpath(path)}

# name -> (results stem, brief stem or None for "no brief", extra argv)
# Every entry MUST pin --asof. Enforced by test_every_case_pins_asof.
CASES = {
    "real_dataset_shape": ("real_dataset_shape", "real_dataset_shape",
                           ["--asof", "2026-08-21", "--claimed-duration", "4 weeks"]),
    "ship_clean":         ("ship_clean", "ship_clean", ["--asof", "2026-08-24"]),
    "missing_brief":      ("missing_brief", None, ["--asof", "2026-08-24"]),
    # A/B/n. The per-arm table is a layout, so it is snapshotted for the same reason the
    # A/B one is: an arm silently dropping out of the document is a change no payload
    # assertion sees.
    "multiarm_one_winner": ("multiarm_one_winner", "multiarm_one_winner",
                            ["--asof", "2026-08-24"]),
    "multiarm_guardrail_breach": ("multiarm_guardrail_breach", "multiarm_guardrail_breach",
                                  ["--asof", "2026-08-24"]),
}

ABSENT_BRIEF = "__absent___brief.yaml"     # deliberately not a real file

# any /a/b/c-looking token -> <PATH>/basename (net; the cwd trick is the real fix)
_ABS_PATH_RE = re.compile(r"(?<![\w.])(/(?:[\w.@+-]+/)+)([\w.@+-]+)")

_MACHINE_DIRS = (SKILL_ROOT, TESTS_DIR, FIXTURES_DIR, SCRIPTS_DIR,
                 tempfile.gettempdir(), os.path.expanduser("~"))
# longest first, so a nested directory is redacted before its parent
_REDACTIONS = ([(p, "<FIXTURES>") for p in sorted(_spellings(FIXTURES_DIR), key=len, reverse=True)]
               + [(p, "<SKILL>") for p in sorted(_spellings(SKILL_ROOT), key=len, reverse=True)])
_REDACTIONS.sort(key=lambda kv: len(kv[0]), reverse=True)
# roots that must never appear at all, however mangled by line wrapping; derived from
# BOTH spellings of every machine directory, so a symlinked root cannot slip past
_ROOT_TOKENS = sorted({
    "/" + q.strip(os.sep).split(os.sep)[0]
    for p in _MACHINE_DIRS for q in _spellings(p) if q.strip(os.sep)
})


_REAL_FIXTURES = os.path.realpath(FIXTURES_DIR)
_REAL_SKILL = os.path.realpath(SKILL_ROOT)


def _resolve_token(token):
    """Map ONE absolute path token to a stable placeholder.

    realpath is applied to the TOKEN, not just to the roots. A symlink cannot be
    inverted -- from /Users/me/github-repos/... you cannot recover the
    /Users/me/.claude/skills/... spelling -- so enumerating root spellings can only
    ever cover the spellings we happened to think of. Resolving the text collapses
    ANY spelling, including ones this machine does not have yet.
    """
    real = os.path.realpath(token)
    for root, placeholder in ((_REAL_FIXTURES, "<FIXTURES>"), (_REAL_SKILL, "<SKILL>")):
        if real == root:
            return placeholder
        if real.startswith(root + os.sep):
            return placeholder + real[len(root):]
    return "<PATH>/" + os.path.basename(real)


def normalise(text):
    # cheap exact-string pass over every spelling we can enumerate ...
    for needle, placeholder in _REDACTIONS:
        text = text.replace(needle, placeholder)
    # ... then resolve whatever is left token by token, so an unenumerated symlink
    # spelling still collapses to the same bytes.
    text = _ABS_PATH_RE.sub(lambda m: _resolve_token(m.group(0)), text)
    return re.sub(r"[ \t]+$", "", text, flags=re.M)


def _argv(name, as_json=False):
    stem, brief, extra = CASES[name]
    argv = [PY, os.path.join(SCRIPTS_DIR, "run_readout.py"),
            "--results", "%s_results.csv" % stem,
            "--brief", ("%s_brief.yaml" % brief) if brief else ABSENT_BRIEF] + list(extra)
    return argv + (["--json"] if as_json else [])


def _run(name, as_json=False):
    """Run from INSIDE the fixtures directory with relative paths, so the rendered
    report cannot contain a machine-specific path in the first place."""
    proc = subprocess.run(_argv(name, as_json), capture_output=True, text=True,
                          cwd=FIXTURES_DIR, timeout=180)
    if proc.returncode != 0:
        raise AssertionError("run_readout.py exited %d for %r\nSTDERR: %s"
                             % (proc.returncode, name, proc.stderr[:2000]))
    return proc.stdout


def render(name):
    return normalise(_run(name))


def payload(name):
    return json.loads(_run(name, as_json=True))


class TestRenderedSnapshots(unittest.TestCase):
    maxDiff = None

    def _check(self, name):
        got = render(name)
        path = os.path.join(SNAP_DIR, "%s.txt" % name)
        if os.environ.get("UPDATE_SNAPSHOTS"):
            if not os.path.isdir(SNAP_DIR):
                os.makedirs(SNAP_DIR)
            with open(path, "w") as fh:
                fh.write(got)
            self.skipTest("snapshot rewritten: %s" % path)
        if not os.path.exists(path):
            self.fail("no snapshot for %r. Review the output, then re-run with "
                      "UPDATE_SNAPSHOTS=1 to record it:\n%s" % (name, got))
        with open(path) as fh:
            want = fh.read()
        self.assertEqual(
            got, want,
            "\n\n=== RENDERED REPORT CHANGED for %r ===\nIf intentional, re-record with "
            "UPDATE_SNAPSHOTS=1. If not, this is a layout regression: duplicated block, "
            "reordered section, or a preamble above the verdict.\n" % name)

    def test_real_dataset_shape(self):
        self._check("real_dataset_shape")

    def test_ship_clean(self):
        self._check("ship_clean")

    def test_missing_brief(self):
        self._check("missing_brief")

    def test_multiarm_one_winner(self):
        self._check("multiarm_one_winner")

    def test_multiarm_guardrail_breach(self):
        self._check("multiarm_guardrail_breach")


class TestSnapshotPortability(unittest.TestCase):
    """Nothing machine- or clock-derived may reach a snapshot."""

    def test_no_absolute_path_in_output(self):
        for name in CASES:
            text = _run(name)
            for tok in _ROOT_TOKENS:      # derived from every spelling, symlinks resolved
                self.assertNotIn(
                    tok, text,
                    "%s: rendered report contains the filesystem root %r, so the snapshot "
                    "would only match on this machine. Line wrapping can split a path "
                    "across lines, which no regex can reliably rejoin -- keep running the "
                    "case from cwd=FIXTURES_DIR with relative filenames." % (name, tok))
            for tok in _ABS_PATH_RE.findall(text):
                joined = "".join(tok) if isinstance(tok, tuple) else tok
                real = os.path.realpath(joined)
                for d in _MACHINE_DIRS:
                    self.assertFalse(
                        real == os.path.realpath(d)
                        or real.startswith(os.path.realpath(d) + os.sep),
                        "%s: %r resolves under the machine directory %r, so the snapshot "
                        "would be machine-specific. Note the check realpaths the TEXT, not "
                        "just the roots: a symlink cannot be inverted, so comparing raw "
                        "spellings would pass on a genuine leak." % (name, joined, d))
            leftover = _ABS_PATH_RE.search(text)
            self.assertIsNone(leftover, "%s: absolute-looking path %r reached the report"
                              % (name, leftover.group(0) if leftover else ""))

    def test_every_case_pins_asof(self):
        for name, (_stem, _brief, extra) in CASES.items():
            self.assertIn("--asof", extra,
                          "%s: every snapshot case must pin --asof, or the report falls back "
                          "to today's system date and the snapshot rots overnight" % name)
            val = extra[extra.index("--asof") + 1]
            self.assertRegex(val, r"^\d{4}-\d{2}-\d{2}$",
                             "%s: --asof must be an explicit date, got %r" % (name, val))
            self.assertNotIn("--today", extra,
                             "%s: --today is a clock override and is banned in snapshots" % name)

    def test_no_case_reaches_assumed_today(self):
        for name in CASES:
            text = _run(name)
            self.assertNotIn("assumed: today", text,
                             "%s: reached the system-date fallback" % name)
            self.assertNotIn("NOT REPRODUCIBLE", text,
                             "%s: rendered a non-reproducible run" % name)
            pay = payload(name)
            self.assertEqual(pay.get("asof_provenance"), "given",
                             "%s: asof_provenance must be 'given'" % name)
            self.assertIs(pay.get("reproducible"), True,
                          "%s: payload must report reproducible=True" % name)


class TestSnapshotInvariants(unittest.TestCase):
    """Structural rules asserted independently, so an intentional re-record cannot
    quietly bless a violation -- the failure mode snapshots normally introduce."""

    def test_verdict_is_line_one(self):
        for name in CASES:
            first = render(name).split("\n")[0]
            self.assertRegex(first, r"^VERDICT: (INVALID-DESIGN|INVALID-SRM|INVALID-IMMATURE|"
                                    r"NO-SHIP|SHIP|INCONCLUSIVE)$",
                             "%s: line 1 must be the bare verdict, got %r" % (name, first))

    def test_exactly_one_why_block(self):
        for name in CASES:
            n = len([l for l in render(name).split("\n") if l.startswith("WHY:")])
            self.assertEqual(n, 1, "%s: expected exactly 1 'WHY:' line, found %d" % (name, n))

    def test_no_section_header_appears_twice(self):
        for name in CASES:
            heads = [l for l in render(name).split("\n")
                     if l and l[0].isupper() and not l.startswith(" ") and l == l.rstrip()]
            dupes = {h for h in heads if heads.count(h) > 1}
            self.assertFalse(dupes, "%s: repeated section header(s) %s" % (name, dupes))


if __name__ == "__main__":
    unittest.main()
