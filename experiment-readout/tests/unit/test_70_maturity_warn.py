"""AMENDMENT 4 — an assumed as-of date can never produce a maturity PASS.

The defect this guards against, so nobody relaxes these tests without knowing
the cost:

A metric named `..._Nd` counts N days of behaviour per user, and those counts
were computed once, at some extraction time, and then FROZEN in the CSV.
Calendar time passing afterwards does not mature data already written to disk.
So when the as-of date is merely ASSUMED (today's date, because nothing better
was supplied), today's date being past the maturity cutoff shows only that
maturity was POSSIBLE by now -- never that the frozen values were extracted
that late. A clean PASS on that basis is a false pass.

A false FAIL is loud. A false PASS is silent. Hence: assumed as-of tops out at
WARN.

---------------------------------------------------------------------------
CLOCK DEPENDENCE -- READ BEFORE "FIXING" ANYTHING HERE
---------------------------------------------------------------------------
The WARN branch fires ONLY when the as-of date is assumed, which by
construction means the system clock decides the numbers. These cases are the
one place the suite's `test_every_case_pins_asof` rule CANNOT apply: pinning
--asof here would move the run onto the `given` path and silently delete all
coverage of the rule.

So every assumed-branch assertion below is restricted to properties that hold
on ANY date: the status word, the provenance prefix, the shape of the wording,
the presence of the caveat. None of them asserts a date or a mature count.
Anything date-specific pins --asof explicitly and lives in the FAIL tests.

If you are here because a test looks non-deterministic: it is deliberate, it is
bounded, and the fix is NOT to pin the flag.
"""

import re
import unittest

from _harness import (FIXTURES, ImplCase, run_readout, readout_args)

CONCLUSION_VERDICTS = {"SHIP", "NO-SHIP", "INCONCLUSIVE"}
BLOCKED = {"NOT_RUN"}


def _mature_under_assumed(name):
    """Fixtures whose maturity gate reaches WARN (not FAIL) with no --asof.

    Discovered at runtime rather than hardcoded: which fixtures are fully
    mature depends on today's date, and a hardcoded list would rot.
    """
    proc = run_readout(name, asof=None, as_json=True)
    if proc is None or proc.returncode != 0:
        return False
    import json
    try:
        p = json.loads(proc.stdout)
    except ValueError:
        return False
    return p.get("gates", {}).get("maturity", {}).get("status") == "WARN"


class TestAssumedAsofCannotPass(ImplCase):
    """RULE: mature_share == 1.0 under an assumed as-of is WARN, never PASS."""

    def test_supplied_asof_passes_but_assumed_only_warns(self):
        """The contrast IS the rule: same fixture, same data, two provenances."""
        given = self.payload("ship_clean")            # manifest pins --asof
        self.assertEqual(given["gates"]["maturity"]["status"], "PASS",
                         "a supplied as-of on fully mature data must PASS")
        self.assertEqual(given["asof_provenance"], "given")

        assumed = self.payload("ship_clean", asof=None)   # no --asof
        self.assertTrue(assumed["asof_provenance"].startswith("assumed"),
                        "omitting --asof must yield assumed provenance, got %r"
                        % assumed["asof_provenance"])
        self.assertEqual(
            assumed["gates"]["maturity"]["status"], "WARN",
            "fully mature data under an ASSUMED as-of must WARN, not PASS: "
            "calendar time passing does not mature values already frozen in "
            "the file")

    def test_maturity_unconfirmed_flag_tracks_the_warn(self):
        assumed = self.payload("ship_clean", asof=None)
        self.assertIs(assumed["gates"]["maturity"].get("maturity_unconfirmed"),
                      True, "the WARN must carry maturity_unconfirmed: True")
        given = self.payload("ship_clean")
        self.assertNotEqual(
            given["gates"]["maturity"].get("maturity_unconfirmed"), True,
            "a supplied as-of must not be flagged unconfirmed")

    def test_validity_warnings_lists_the_gate(self):
        assumed = self.payload("ship_clean", asof=None)
        self.assertIn("maturity", assumed.get("validity_warnings", []),
                      "validity_warnings must name the warning gate")


class TestWarnDoesNotBlock(ImplCase):
    """RULE: a validity WARN does not block, and it travels with the verdict.

    NOTE: this is the INVERSE of test_40_suppression. A WARN means one
    assumption is unconfirmed, not that the data is unreadable, so the
    conclusion gates MUST run. Do not reuse a suppression helper here.
    """

    def test_conclusion_gates_still_run(self):
        p = self.payload("ship_clean", asof=None)
        self.assertIsNone(p.get("stopped_at"),
                          "a WARN must not halt the run")
        for gate in ("guardrail", "lift"):
            self.assertNotIn(
                p["gates"][gate]["status"], BLOCKED,
                "gate %r must still run under a WARN (got %r)"
                % (gate, p["gates"][gate]["status"]))

    def test_verdict_is_reached_and_lift_is_present(self):
        p = self.payload("ship_clean", asof=None)
        self.assertIn(p["verdict"], CONCLUSION_VERDICTS,
                      "a WARN must still yield a conclusion verdict, got %r"
                      % p["verdict"])
        lift = p["gates"]["lift"]
        self.assertTrue(
            any(k in lift for k in ("p_value", "rel_diff", "diff")),
            "the lift must actually be computed under a WARN; got keys %r"
            % sorted(lift))

    def test_warn_gate_is_not_in_the_failures_list(self):
        p = self.payload("ship_clean", asof=None)
        self.assertNotIn("maturity", p.get("all_validity_failures", []),
                         "a WARN is not a failure and must not appear in "
                         "all_validity_failures")

    def test_caveat_travels_with_the_verdict(self):
        """The reader must not be able to take the verdict without the caveat."""
        proc = self.cli("run_readout.py",
                        readout_args("ship_clean", asof=None, as_json=False))
        text = proc.stdout
        head = text[:text.index("GATES")] if "GATES" in text else text
        self.assertRegex(
            head.upper(), r"CAVEAT|WARN|NOT REPRODUCIBLE",
            "the maturity caveat must appear above the gate table, next to the "
            "verdict -- not buried further down")


class TestWarnWordingAssertsNothingAsFact(ImplCase):
    """A qualifying clause does not unsay a false sentence.

    Sibling of test_monotone_but_tiny_reading_does_not_claim_values_fail_to_move.
    The claim itself must be true as stated, not a false claim plus a hedge.
    """

    def _rendered(self, name):
        proc = self.cli("run_readout.py",
                        readout_args(name, asof=None, as_json=False))
        return proc.stdout

    def test_wording_is_conditional(self):
        text = self._rendered("ship_clean")
        self.assertRegex(
            text, r"\bIF\b|\bif the metric was extracted\b",
            "the assumed-as-of wording must state a conditional")
        self.assertIn(
            "--asof", text,
            "the wording must name the input that would settle it")

    def test_no_bare_claim_of_maturity_as_fact(self):
        """'all N users are mature' with no condition attached is the defect."""
        text = self._rendered("ship_clean")
        for m in re.finditer(r"all [\d,]+ users are mature", text):
            sent_start = text.rfind(".", 0, m.start()) + 1
            sent_end = text.find(".", m.end())
            sentence = text[sent_start:sent_end if sent_end > 0 else len(text)]
            self.assertRegex(
                sentence, r"\bIF\b|\bif\b",
                "found an unconditional maturity claim under an assumed "
                "as-of date: %r" % sentence.strip())


class TestFailBeatsWarn(ImplCase):
    """A genuine FAIL outranks the assumption caveat. Date-pinned on purpose."""

    def test_partial_maturity_fails_and_is_not_downgraded(self):
        p = self.payload("real_dataset_shape")     # manifest pins 2026-08-21
        mat = p["gates"]["maturity"]
        self.assertEqual(mat["status"], "FAIL",
                         "partial maturity under a supplied as-of must FAIL")
        self.assertIn("maturity", p["all_validity_failures"])
        self.assertNotIn("maturity", p.get("validity_warnings", []),
                         "a FAIL must never be reported as a mere WARN")
        self.assertEqual(p["verdict"], "INVALID-SRM")


class TestStatusListsNeverCollide(ImplCase):
    """Extends the two-list sweep to three. A gate lands in at most one."""

    def test_no_gate_in_two_lists_across_every_fixture(self):
        checked = 0
        for name in sorted(FIXTURES):
            for asof in ("fixture", None):
                proc = run_readout(name, asof=asof, as_json=True)
                if proc is None or proc.returncode != 0:
                    continue          # exit-1 fixtures are covered elsewhere
                import json
                try:
                    p = json.loads(proc.stdout)
                except ValueError:
                    continue
                checked += 1
                fails = set(p.get("all_validity_failures") or [])
                nas = set(p.get("validity_not_assessable") or [])
                warns = set(p.get("validity_warnings") or [])
                for a, b, an, bn in ((fails, nas, "failures", "not_assessable"),
                                     (fails, warns, "failures", "warnings"),
                                     (nas, warns, "not_assessable", "warnings")):
                    self.assertEqual(
                        a & b, set(),
                        "%s: gate(s) %r appear in both %s and %s"
                        % (name, sorted(a & b), an, bn))
        self.assertGreater(checked, 10,
                           "sweep covered too few fixtures to be meaningful")

    def test_every_listed_gate_has_the_matching_status(self):
        for name in sorted(FIXTURES):
            proc = run_readout(name, asof="fixture", as_json=True)
            if proc is None or proc.returncode != 0:
                continue
            import json
            try:
                p = json.loads(proc.stdout)
            except ValueError:
                continue
            gates = p.get("gates", {})
            for g in (p.get("validity_warnings") or []):
                self.assertEqual(
                    gates.get(g, {}).get("status"), "WARN",
                    "%s: %r is in validity_warnings but its status is %r"
                    % (name, g, gates.get(g, {}).get("status")))
            for g in (p.get("all_validity_failures") or []):
                self.assertEqual(
                    gates.get(g, {}).get("status"), "FAIL",
                    "%s: %r is in all_validity_failures but its status is %r"
                    % (name, g, gates.get(g, {}).get("status")))


if __name__ == "__main__":
    unittest.main()
