"""CLI contract tests for scripts/run_readout.py and scripts/power.py.

  --json prints ONLY parseable JSON and nothing else
  exit 0 on a successful run, whatever the verdict
  exit 1 only on a genuine runtime/input error
  --asof overrides the inferred as-of date and can flip maturity FAIL -> PASS
         on the SAME CSV
"""

import datetime
import json
import math
import os
import subprocess
import unittest

import _ref
from _harness import (FIXTURES, FIXTURES_DIR, MDE_REL, METRIC_WINDOW, PY,
                      ImplCase, fx, all_numbers, all_keys, brief_path,
                      read_arm, readout_args, results_path, script_path,
                      SKILL_ROOT, walk)


class TestJsonMode(ImplCase):

    def test_json_stdout_is_only_json(self):
        for name in sorted(FIXTURES):
            proc = self.cli("run_readout.py", readout_args(name, "fixture", True))
            out = proc.stdout
            self.assertTrue(out.strip(),
                            "--json produced empty stdout for %s" % name)
            stripped = out.strip()
            self.assertTrue(stripped.startswith("{") and stripped.endswith("}"),
                            "--json stdout must be the JSON payload and nothing "
                            "else (fixture %s); stdout starts %r and ends %r"
                            % (name, stripped[:60], stripped[-60:]))
            try:
                json.loads(out)
            except ValueError as exc:
                self.fail("--json stdout is not parseable JSON for %s: %s\n%r"
                          % (name, exc, out[:1000]))

    def test_json_mode_prints_no_human_report(self):
        """A human report leaking onto stdout alongside the JSON breaks any
        caller that pipes --json into jq."""
        for name in ("ship_clean", "srm_broken", "immature"):
            proc = self.cli("run_readout.py", readout_args(name, "fixture", True))
            self.assertEqual(
                proc.stdout.count("{"), proc.stdout.count("}"),
                "unbalanced braces suggest mixed output for %s" % name)
            pay = json.loads(proc.stdout)
            self.assertEqual(json.loads(json.dumps(pay)), pay)


class TestExitCodes(ImplCase):

    def test_exit_zero_for_every_verdict(self):
        seen = {}
        for name in sorted(FIXTURES):
            proc = self.cli("run_readout.py", readout_args(name, "fixture", True))
            self.assertEqual(
                proc.returncode, 0,
                "run_readout.py must exit 0 whenever it produced a verdict "
                "(fixture %s, expected verdict %s); got %d\nSTDERR: %s"
                % (name, fx(name)["expect_verdict"], proc.returncode,
                   proc.stderr[:1000]))
            seen.setdefault(fx(name)["expect_verdict"], 0)
            seen[fx(name)["expect_verdict"]] += 1
        # Every verdict in the taxonomy that we have a fixture for is covered.
        for v in ("SHIP", "NO-SHIP", "INCONCLUSIVE", "INVALID-DESIGN",
                  "INVALID-SRM", "INVALID-IMMATURE"):
            self.assertIn(v, seen, "no fixture exercises verdict %s" % v)

    def test_exit_zero_in_human_mode_too(self):
        for name in ("ship_clean", "srm_broken", "missing_brief"):
            proc = self.cli("run_readout.py", readout_args(name, "fixture", False))
            self.assertEqual(proc.returncode, 0,
                             "human mode must also exit 0 for %s; STDERR: %s"
                             % (name, proc.stderr[:1000]))

    def test_missing_results_file_is_exit_one(self):
        """A missing RESULTS file is a genuine input error, not a gate result."""
        proc = self.cli("run_readout.py", [
            "--results", os.path.join(FIXTURES_DIR, "does_not_exist.csv"),
            "--brief", brief_path("ship_clean"), "--json"])
        self.assertEqual(proc.returncode, 1,
                         "a nonexistent --results path must exit 1, got %d\n"
                         "STDOUT: %s\nSTDERR: %s"
                         % (proc.returncode, proc.stdout[:500],
                            proc.stderr[:500]))

    def test_missing_brief_is_a_gate_failure_not_an_input_error(self):
        """CONTRACT: gate 0 is 'brief present/parseable', so an absent brief is
        a GATE result -> INVALID-DESIGN with exit 0. (Flagged as a contract
        ambiguity: a missing file could also be read as an input error. Tested
        to the contract as written.)"""
        proc = self.cli("run_readout.py", readout_args("missing_brief",
                                                       "fixture", True))
        self.assertEqual(proc.returncode, 0,
                         "an absent brief is gate 0's job, so exit must be 0; "
                         "got %d\nSTDERR: %s"
                         % (proc.returncode, proc.stderr[:500]))
        self.assertEqual(json.loads(proc.stdout).get("verdict"),
                         "INVALID-DESIGN")

    def test_malformed_primary_metric_value_is_exit_one(self):
        """A non-numeric value in the primary-metric column is unparseable
        input, not a design finding.

        The fixture is valid in every other respect and is run with
        --asof 2026-08-24 so all three validity gates PASS -- otherwise
        maturity would fail first and the bad cell would never be parsed.
        """
        proc = self.cli("run_readout.py", [
            "--results", os.path.join(FIXTURES_DIR, "malformed_results.csv"),
            "--brief", os.path.join(FIXTURES_DIR, "malformed_brief.yaml"),
            "--asof", "2026-08-24", "--json"])
        self.assertEqual(proc.returncode, 1,
                         "a CSV with 'NOT_A_NUMBER' in completed_orders_28d "
                         "must exit 1, got %d\nSTDOUT: %s\nSTDERR: %s"
                         % (proc.returncode, proc.stdout[:800],
                            proc.stderr[:500]))

    def test_malformed_guardrail_value_is_dropped_and_surfaced(self):
        """AMENDMENT 3A resolves what was ambiguous here: a bad cell in a
        SECONDARY column is dropped, not fatal -- but never silent.

        This fixture drops 1 of 6 rows = 16.7%, which EXCEEDS the 2% escalation
        threshold, so it must now FAIL gate 0 rather than proceed. That is a
        behaviour change from v1.2, where it produced a SHIP.
        """
        proc = self.cli("run_readout.py", [
            "--results", os.path.join(FIXTURES_DIR,
                                      "malformed_guardrail_results.csv"),
            "--brief", os.path.join(FIXTURES_DIR, "malformed_brief.yaml"),
            "--asof", "2026-08-24", "--json"])
        self.assertEqual(proc.returncode, 0,
                         "a secondary-column bad cell is NOT exit 1 under 3A; "
                         "got %d\nSTDERR: %s"
                         % (proc.returncode, proc.stderr[:500]))
        pay = json.loads(proc.stdout)
        dg = self.gate(pay, "design_integrity", "malformed_guardrail")
        self.assertEqual(
            dg.get("status"), "FAIL",
            "1 of 6 rows (16.7%%) unparseable EXCEEDS the 2%% threshold, so "
            "gate 0 must FAIL: a file that cannot parse 2%% of a column is a "
            "data-quality problem, not a rounding nuisance. gate = %r" % dg)
        self.assertEqual(pay.get("verdict"), "INVALID-DESIGN")
        nums = [v for _p, v in all_numbers(dg)]
        self.assertIn(5.0, nums,
                      "the run must state how many rows were usable (5 of 6); "
                      "design gate numbers: %s" % sorted(set(nums)))

    def test_dropped_rows_name_the_offending_column(self):
        """'report it in the GATE 0 design row ... naming the column'."""
        for fixture in ("dropped_at_2pct", "dropped_over_2pct"):
            dg = self.gate(self.payload(fixture), "design_integrity", fixture)
            blob = " ".join(str(v) for _p, v in walk(dg)
                            if isinstance(v, str))
            self.assertIn(
                "cancel_rate", blob,
                "fixture %s: gate 0 must NAME the column whose cells could not "
                "be parsed, otherwise the reader cannot act on it; strings: %r"
                % (fixture, blob[:400]))

    def test_drop_accounting_fields_are_present(self):
        """AMENDMENT 3A implementation fields: rows_dropped,
        rows_dropped_by_column and drop_escalation_share, so the escalation rule
        is auditable rather than a hidden constant."""
        for fixture in ("dropped_at_2pct", "dropped_over_2pct"):
            e = fx(fixture)
            dg = self.gate(self.payload(fixture), "design_integrity", fixture)
            flat = {}
            for _p, v in walk(dg):
                if isinstance(v, dict):
                    flat.update(v)
            for field in ("rows_dropped", "rows_dropped_by_column",
                          "drop_escalation_share"):
                self.assertIn(
                    field, flat,
                    "fixture %s: gate 0 must expose %r; keys seen: %s"
                    % (fixture, field, sorted(flat)))
            self.assertEqual(
                int(flat["rows_dropped"]), e["rows_dropped"],
                "fixture %s: rows_dropped must be %d" % (fixture,
                                                         e["rows_dropped"]))
            self.assertAlmostEqual(
                float(flat["drop_escalation_share"]), 0.02, places=9,
                msg="fixture %s: the escalation threshold is 2%%" % fixture)
            by_col = flat["rows_dropped_by_column"]
            self.assertIsInstance(by_col, dict,
                                  "rows_dropped_by_column must be a mapping")
            self.assertEqual(
                by_col.get("cancel_rate"), e["rows_dropped"],
                "fixture %s: rows_dropped_by_column must attribute all %d "
                "drops to cancel_rate, got %r"
                % (fixture, e["rows_dropped"], by_col))

    def test_dropped_rows_report_totals_and_usable_counts(self):
        for fixture in ("dropped_at_2pct", "dropped_over_2pct"):
            e = fx(fixture)
            dg = self.gate(self.payload(fixture), "design_integrity", fixture)
            nums = [v for _p, v in all_numbers(dg)]
            for label in ("rows_total", "rows_usable", "rows_dropped"):
                want = float(e[label])
                self.assertIn(
                    want, nums,
                    "fixture %s: gate 0 must report %s = %d; design gate "
                    "numbers: %s" % (fixture, label, e[label],
                                     sorted(set(nums))))


class TestDropEscalationBoundary(ImplCase):
    """AMENDMENT 3A: dropped rows EXCEEDING 2% escalate gate 0 to FAIL.

    The two fixtures are ONE ROW apart -- 20/1000 = 2.000% and 21/1000 =
    2.100% -- so the test pins the boundary itself, not merely the two regimes.
    "Exceed 2%" is exclusive, so exactly 2% must still only WARN.
    """

    def test_exactly_two_percent_only_warns(self):
        name = "dropped_at_2pct"
        e = fx(name)
        self.assertEqual(e["dropped_share"], 0.02, "fixture wiring")
        pay = self.payload(name)
        dg = self.gate(pay, "design_integrity", name)
        self.assertEqual(
            dg.get("status"), "WARN",
            "20 of 1000 rows is exactly 2.000%%, which does NOT exceed 2%%, so "
            "gate 0 must WARN and let the readout proceed; got %r"
            % dg.get("status"))
        self.assertEqual(pay.get("all_validity_failures"), [],
                         "a WARN is not a failure")
        self.assertEqual(pay.get("stopped_at"), None)
        self.assertEqual(pay.get("verdict"), "SHIP",
                         "with validity intact the readout must conclude "
                         "normally")

    def test_one_row_more_escalates_to_fail(self):
        name = "dropped_over_2pct"
        e = fx(name)
        self.assertEqual(e["rows_dropped"], 21, "fixture wiring")
        self.assertGreater(e["dropped_share"], 0.02, "fixture wiring")
        pay = self.payload(name)
        dg = self.gate(pay, "design_integrity", name)
        self.assertEqual(
            dg.get("status"), "FAIL",
            "21 of 1000 rows is 2.100%%, which EXCEEDS 2%%, so gate 0 must "
            "FAIL; got %r" % dg.get("status"))
        self.assertEqual(pay.get("verdict"), "INVALID-DESIGN")
        self.assertEqual(pay.get("stopped_at"), "design_integrity")
        self.assertEqual(pay.get("all_validity_failures"), ["design_integrity"])

    def test_the_boundary_is_one_row_wide(self):
        """The only difference between the two fixtures is a single dropped
        row, so nothing else can be responsible for the flip."""
        a, b = fx("dropped_at_2pct"), fx("dropped_over_2pct")
        self.assertEqual(a["rows_total"], b["rows_total"])
        self.assertEqual(b["rows_dropped"], a["rows_dropped"] + 1)
        pa, pb = self.payload("dropped_at_2pct"), self.payload("dropped_over_2pct")
        self.assertEqual(self.gate(pa, "srm", "at").get("status"), "PASS")
        self.assertEqual(self.gate(pb, "srm", "over").get("status"), "PASS")
        self.assertEqual(self.gate(pa, "maturity", "at").get("status"), "PASS")
        self.assertEqual(self.gate(pb, "maturity", "over").get("status"), "PASS")
        self.assertNotEqual(pa["verdict"], pb["verdict"],
                            "one dropped row must flip the verdict at the 2% "
                            "boundary")

    def test_escalation_still_suppresses_the_conclusions(self):
        """dropped_over_2pct carries a real +11.22% lift and a +2.46pp
        guardrail breach; a gate-0 FAIL must suppress both."""
        pay = self.payload("dropped_over_2pct")
        for g in ("guardrail", "lift"):
            gd = self.gate(pay, g, "dropped_over_2pct")
            self.assertEqual(gd.get("status"), "NOT_RUN",
                             "gates.%s must be suppressed by the gate-0 "
                             "failure, got %r" % (g, gd.get("status")))
            self.assertEqual(set(gd), {"status", "reason"})

    def test_primary_column_keeps_the_stricter_rule(self):
        """AMENDMENT 3A explicitly preserves the asymmetry: 'You cannot read out
        a primary metric you cannot parse.' A single bad PRIMARY cell is exit 1
        even though the same proportion in a secondary column would only WARN.
        malformed_results.csv has 1 of 6 primary cells bad."""
        proc = self.cli("run_readout.py", [
            "--results", os.path.join(FIXTURES_DIR, "malformed_results.csv"),
            "--brief", os.path.join(FIXTURES_DIR, "malformed_brief.yaml"),
            "--asof", "2026-08-24", "--json"])
        self.assertEqual(
            proc.returncode, 1,
            "an unparseable PRIMARY metric value must exit 1, not be dropped "
            "and surfaced; got %d\nSTDOUT: %s\nSTDERR: %s"
            % (proc.returncode, proc.stdout[:400], proc.stderr[:400]))

    def test_the_asymmetry_is_real(self):
        """Same file shape, same 1-of-6 proportion, different column -> a
        different rule. Pins the asymmetry rather than either half of it."""
        args = ["--brief", os.path.join(FIXTURES_DIR, "malformed_brief.yaml"),
                "--asof", "2026-08-24", "--json"]
        primary = self.cli("run_readout.py", [
            "--results", os.path.join(FIXTURES_DIR, "malformed_results.csv")]
            + args)
        secondary = self.cli("run_readout.py", [
            "--results", os.path.join(FIXTURES_DIR,
                                      "malformed_guardrail_results.csv")] + args)
        self.assertEqual(primary.returncode, 1,
                         "primary column: exit 1")
        self.assertEqual(secondary.returncode, 0,
                         "secondary column: a verdict, not an input error")
        self.assertEqual(json.loads(secondary.stdout).get("verdict"),
                         "INVALID-DESIGN")


class TestRequiredColumns(ImplCase):
    def test_missing_required_column_is_a_gate_zero_failure(self):
        """CONTRACT gate 0: 'required cols present'. An absent `arm` column is
        therefore a DESIGN finding (exit 0, INVALID-DESIGN), not an input
        error -- the mirror image of the malformed-value case above."""
        proc = self.cli("run_readout.py", [
            "--results", os.path.join(FIXTURES_DIR, "no_arm_col_results.csv"),
            "--brief", os.path.join(FIXTURES_DIR, "malformed_brief.yaml"),
            "--asof", "2026-08-24", "--json"])
        self.assertEqual(proc.returncode, 0,
                         "a missing required column is gate 0's business, so "
                         "exit must be 0; got %d\nSTDERR: %s"
                         % (proc.returncode, proc.stderr[:500]))
        pay = json.loads(proc.stdout)
        self.assertEqual(pay.get("verdict"), "INVALID-DESIGN")
        self.assertEqual(pay.get("stopped_at"), "design_integrity")

    def test_unparseable_asof_is_exit_one(self):
        proc = self.cli("run_readout.py", [
            "--results", results_path("ship_clean"),
            "--brief", brief_path("ship_clean"),
            "--asof", "not-a-date", "--json"])
        self.assertEqual(proc.returncode, 1,
                         "--asof not-a-date must exit 1, got %d"
                         % proc.returncode)

    def test_error_message_goes_to_stderr_not_stdout(self):
        proc = self.cli("run_readout.py", [
            "--results", os.path.join(FIXTURES_DIR, "does_not_exist.csv"),
            "--brief", brief_path("ship_clean"), "--json"])
        self.assertFalse(
            proc.stdout.strip(),
            "on a genuine input error --json stdout must stay empty so callers "
            "never parse half a payload; got %r" % proc.stdout[:300])


class TestAsofOverride(ImplCase):
    """The same CSV, two as-of dates, two different maturity verdicts.

    AMENDMENT 2 note: both arms of the flip pass an EXPLICIT --asof. Relying on
    the omitted-asof path would make this test time-dependent -- it would start
    passing for the wrong reason once today drifts past 2026-08-24 -- which is
    exactly the landmine the amendment warns about. The omitted-asof path is
    tested separately, and only for its provenance label.
    """

    NAME = "ship_clean"
    EARLY = "2026-07-27"      # == max(exposure_date): cutoff 2026-06-29, 0% mature
    LATE = "2026-08-24"       # == last exposure + 28d: 100% mature

    def test_early_asof_fails_maturity(self):
        pay = self.payload(self.NAME, asof=self.EARLY)
        gd = self.gate(pay, "maturity", self.NAME)
        self.assertEqual(pay.get("asof"), self.EARLY)
        self.assertEqual(gd.get("status"), "FAIL",
                         "at asof %s the cutoff is 2026-06-29, before the first "
                         "exposure, so nothing can be mature; got %r"
                         % (self.EARLY, gd.get("status")))
        self.assertAlmostEqual(float(gd.get("mature_share", -1)), 0.0, places=12)
        self.assertEqual(pay.get("verdict"), "INVALID-IMMATURE")

    def test_late_asof_passes_maturity_on_the_same_csv(self):
        pay = self.payload(self.NAME, asof=self.LATE)
        gd = self.gate(pay, "maturity", self.NAME)
        self.assertEqual(pay.get("asof"), self.LATE)
        self.assertEqual(gd.get("status"), "PASS",
                         "at asof %s every exposure + 28d <= asof, so maturity "
                         "must PASS; got %r" % (self.LATE, gd.get("status")))
        self.assertAlmostEqual(float(gd.get("mature_share", -1)), 1.0, places=12)
        self.assertEqual(pay.get("verdict"), "SHIP")

    def test_maturity_gate_can_actually_pass(self):
        """The bug AMENDMENT 2 fixed: under the old max(exposure_date) default,
        mature_share == 1.0 was arithmetically impossible for any W > 0, so this
        gate could never pass and INVALID-IMMATURE became the only answer. A
        gate that cannot pass carries no information."""
        gd = self.gate(self.payload(self.NAME, asof=self.LATE), "maturity",
                       self.NAME)
        self.assertEqual(float(gd["mature_share"]), 1.0,
                         "mature_share must be reachable at exactly 1.0")
        self.assertEqual(gd["status"], "PASS")

    def test_the_flip_is_driven_only_by_asof(self):
        a = self.payload(self.NAME, asof=self.EARLY)
        b = self.payload(self.NAME, asof=self.LATE)
        # The SRM RESULT must be asof-independent. Compared field by field
        # rather than as whole dicts: the contract does not fix the gate's
        # serialisation, and a valid run may legitimately carry extra narrative
        # keys that an invalid one does not.
        for field in ("status", "chi2", "p_value", "observed", "srm_detected"):
            if field in a["gates"]["srm"] or field in b["gates"]["srm"]:
                self.assertEqual(
                    a["gates"]["srm"].get(field), b["gates"]["srm"].get(field),
                    "the SRM %s cannot depend on --asof" % field)
        self.assertEqual(a["gates"]["design_integrity"]["status"],
                         b["gates"]["design_integrity"]["status"])
        self.assertNotEqual(a["verdict"], b["verdict"])
        self.assertEqual(a["stopped_at"], "maturity")
        self.assertIsNone(b["stopped_at"])

    def test_asof_one_day_early_still_fails(self):
        """2026-08-23 is one day short for the last cohort: most users are
        mature but not all, and partial maturity is still a FAIL."""
        pay = self.payload(self.NAME, asof="2026-08-23")
        gd = self.gate(pay, "maturity", self.NAME)
        share = float(gd.get("mature_share", -1))
        self.assertGreater(share, 0.8, "most users are mature at 2026-08-23")
        self.assertLess(share, 1.0)
        self.assertEqual(gd.get("status"), "FAIL",
                         "partial maturity is still a FAIL")
        self.assertEqual(pay.get("verdict"), "INVALID-IMMATURE")

    def test_asof_far_in_the_future_passes(self):
        pay = self.payload(self.NAME, asof="2026-12-31")
        self.assertEqual(self.gate(pay, "maturity", self.NAME).get("status"),
                         "PASS")
        self.assertEqual(pay.get("verdict"), "SHIP")

    def test_asof_fixes_only_maturity_not_srm(self):
        """The real dataset has BOTH defects. Supplying a generous asof fixes
        only the maturity one -- the SRM verdict must survive, with maturity now
        PASS and all_validity_failures shrinking to ['srm']."""
        pay = self.payload("real_dataset_shape", asof="2026-08-24")
        self.assertEqual(pay.get("verdict"), "INVALID-SRM")
        self.assertEqual(self.gate(pay, "maturity",
                                   "real_dataset_shape").get("status"), "PASS")
        self.assertEqual(pay.get("all_validity_failures"), ["srm"])


class TestAsofDefault(ImplCase):
    """AMENDMENT 2: the fallback is the system date, and it must be labelled.

    These are the only tests in the suite that omit --asof, and they assert the
    provenance and the recorded date -- never a verdict, because a verdict from
    a system-date default is time-dependent by construction.
    """

    def test_default_is_today_computed_here(self):
        today = datetime.date.today().isoformat()
        pay = self.payload("ship_clean", asof=None)
        self.assertEqual(str(pay.get("asof")), today,
                         "omitting --asof must resolve to today (%s), got %r"
                         % (today, pay.get("asof")))

    def test_default_is_not_max_exposure_date(self):
        pay = self.payload("ship_clean", asof=None)
        self.assertNotEqual(
            str(pay.get("asof")), fx("ship_clean")["max_exposure_date"],
            "max(exposure_date) was removed as the default in AMENDMENT 2: it "
            "makes mature_share == 1.0 impossible for any W > 0, so the "
            "maturity gate could never pass")

    def test_default_is_labelled_assumed_today(self):
        pay = self.payload("ship_clean", asof=None)
        gd = self.gate(pay, "maturity", "ship_clean")
        blob = " ".join(v for _p, v in walk(gd) if isinstance(v, str)).lower()
        self.assertIn("assumed", blob,
                      "the system-date fallback must be labelled an assumption")
        self.assertIn("today", blob,
                      "the label must name WHICH assumption was made "
                      "('assumed: today')")

    def test_resolved_date_is_recorded_for_audit(self):
        pay = self.payload("ship_clean", asof=None)
        today = datetime.date.today().isoformat()
        blob = json.dumps(pay)
        self.assertIn(today, blob,
                      "the resolved as-of date must appear in the payload so "
                      "the assumption stays auditable")

    def test_explicit_asof_is_not_labelled_assumed(self):
        gd = self.gate(self.payload("ship_clean", asof="2026-08-24"),
                       "maturity", "ship_clean")
        blob = " ".join(v for _p, v in walk(gd) if isinstance(v, str)).lower()
        self.assertIn("given", blob)
        self.assertNotIn("assumed", blob,
                         "an explicitly supplied --asof is not an assumption")


class TestHumanReport(ImplCase):

    def test_non_empty_and_states_the_verdict(self):
        for name in sorted(FIXTURES):
            proc = self.cli("run_readout.py", readout_args(name, "fixture", False))
            self.assertTrue(proc.stdout.strip(),
                            "the human report is empty for %s" % name)
            self.assertIn(fx(name)["expect_verdict"], proc.stdout,
                          "the human report for %s must state the verdict %s"
                          % (name, fx(name)["expect_verdict"]))

    def test_report_enumerates_every_validity_failure(self):
        """v1.1: the report must name every reason the data is unusable, not
        just the first."""
        for name in ("precedence_all_bad", "trap_real_data",
                     "real_dataset_shape"):
            proc = self.cli("run_readout.py", readout_args(name, "fixture", False))
            text = proc.stdout.lower()
            self.assertIn("srm", text,
                          "%s: the report must name the SRM failure" % name)
            self.assertTrue(
                "matur" in text or "immature" in text,
                "%s: the report must ALSO name the maturity failure -- "
                "enumerating only the first defect is what AMENDMENT 1 forbids"
                % name)


class TestPowerCli(ImplCase):
    """power.py: baseline mean/sd from CONTROL, then required n and duration."""

    NAME = "ship_clean"

    def expected_n(self, name):
        _t, c = read_arm(name, "completed_orders_28d")
        if len(c) < 2:
            self.fail("fixture %s has too few parseable control values to size "
                      "a rerun" % name)
        m = sum(c) / len(c)
        sd = math.sqrt(sum((x - m) ** 2 for x in c) / (len(c) - 1))
        return math.ceil(_ref.sample_size_per_arm(m, sd, MDE_REL))

    def run_power(self, name, as_json=True):
        args = ["--results", results_path(name), "--brief", brief_path(name)]
        if as_json:
            args.append("--json")
        return self.cli("power.py", args)

    def test_exit_zero_and_json_parses(self):
        proc = self.run_power(self.NAME)
        self.assertEqual(proc.returncode, 0,
                         "power.py must exit 0; STDERR: %s" % proc.stderr[:1000])
        stripped = proc.stdout.strip()
        self.assertTrue(stripped.startswith("{") and stripped.endswith("}"),
                        "power.py --json must print only JSON; got %r"
                        % stripped[:200])
        json.loads(proc.stdout)

    def test_reports_required_n_per_arm(self):
        """Cross-checked against an independent computation from the control
        arm. 1% tolerance absorbs a population-vs-sample sd choice."""
        pay = json.loads(self.run_power(self.NAME).stdout)
        want = self.expected_n(self.NAME)
        nums = [v for _p, v in all_numbers(pay)]
        hit = [v for v in nums if abs(v - want) <= max(2.0, 0.01 * want)]
        self.assertTrue(hit,
                        "power.py must report a required n per arm of about %d "
                        "for the 3%% MDE (estimated from the control arm); no "
                        "such number in the payload.\nnumbers: %s"
                        % (want, sorted(set(nums))[:60]))

    def test_reports_the_maturation_window(self):
        pay = json.loads(self.run_power(self.NAME).stdout)
        nums = [v for _p, v in all_numbers(pay)]
        self.assertIn(float(METRIC_WINDOW), nums,
                      "power.py must report the 28-day maturation window; "
                      "numbers: %s" % sorted(set(nums))[:60])

    def test_reports_days_and_weeks(self):
        pay = json.loads(self.run_power(self.NAME).stdout)
        keys = all_keys(pay)
        self.assertTrue(any("week" in k for k in keys),
                        "power.py must report total weeks; keys: %s"
                        % sorted(keys))
        self.assertTrue(any("day" in k for k in keys),
                        "power.py must report day counts; keys: %s"
                        % sorted(keys))

    def test_runs_even_on_an_invalid_experiment(self):
        """Practice question 2 asks for the rerun sizing off the SAME broken
        files, so power.py must not refuse just because the readout is invalid."""
        for name in ("real_dataset_shape", "immature"):
            proc = self.run_power(name)
            self.assertEqual(proc.returncode, 0,
                             "power.py must still size a rerun from %s; "
                             "STDERR: %s" % (name, proc.stderr[:800]))
            json.loads(proc.stdout)

    def test_missing_results_is_exit_one(self):
        proc = self.cli("power.py", [
            "--results", os.path.join(FIXTURES_DIR, "does_not_exist.csv"),
            "--brief", brief_path("ship_clean"), "--json"])
        self.assertEqual(proc.returncode, 1)


if __name__ == "__main__":
    unittest.main()
