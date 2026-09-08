"""L6 -- A/B/n: every arm is reported, and k arms is k hypotheses.

The defect this file exists for was silent and green. GATE 1 checked all three arms of a
three-arm experiment against the designed split and said so; GATE 4 compared ONE treatment
arm against control, relabelled it "treatment", and dropped the other arm out of the
document entirely. A reader shipped on a +17% lift without learning that a second arm had
existed, let alone that its point estimate also cleared the MDE while being nowhere near
significant. Nothing in the suite noticed, because every fixture had exactly two arms.

So this file asserts two separate things, and both matter:

  PRESENCE     every arm in the data appears in the payload AND in the rendered report, and
               no arm is renamed into a generic "treatment". An arm you cannot see is an
               arm you cannot argue with.
  MULTIPLICITY k treatment arms is k hypotheses about one control, so the family-wise
               false-positive rate inflates -- 9.75% at k=2 against a nominal 5%. The
               thresholds are corrected by Holm-Bonferroni, and `holm_bonferroni` is
               checked against hand-computed values, including the part implementations
               get wrong: testing STOPS at the first hypothesis that fails its threshold,
               so every larger p-value is retained whatever its own threshold says.

The k == 1 regression class at the bottom is the other half. Holm at k == 1 is plain alpha,
so a two-arm readout must come out numerically identical to the one that existed before any
of this was written -- same p-value, same significance decision, same promoted keys.
"""

import csv
import os
import re
import unittest

import _ref
from _harness import (FIXTURES, SIG_ALPHA, ImplCase, brief_path, fx, results_path,
                      run_cli)


MULTIARM = ["multiarm_one_winner", "multiarm_none_survive_holm",
            "multiarm_guardrail_breach"]

# Keys that mean "the treatment arm" in the singular. Promoting one arm's answer into any
# of these on an A/B/n readout is exactly the defect: a downstream reader takes it as the
# experiment's answer and never learns the other arms exist.
SINGULAR_KEYS = ("arm", "treatment_arm", "mean_a", "mean_b", "diff", "rel_diff", "p_value",
                 "ci_low", "ci_high", "rel_ci_low", "rel_ci_high", "significant",
                 "meets_mde", "n_a", "n_b", "t", "se", "dof")


def read_arms(name, column):
    """{arm label: [numeric values]} straight from the fixture CSV, every arm.

    read_arm() in the harness returns a (treatment, control) pair and folds every label
    that is not "treatment" into control -- correct for a two-arm fixture and silently
    wrong for three, which is the same shape of bug this file is about.
    """
    out = {}
    with open(results_path(name)) as fh:
        for row in csv.DictReader(fh):
            try:
                val = float(row.get(column))
            except (TypeError, ValueError):
                continue
            out.setdefault(row["arm"], []).append(val)
    return out


def holm_reference(pvalues, alpha=0.05):
    """An independent Holm-Bonferroni, written from the procedure rather than from the
    implementation: walk the sorted p-values, and the moment one fails its alpha/(k-i)
    bar, everything from there on is retained."""
    k = len(pvalues)
    ranked = sorted(range(k), key=lambda i: (pvalues[i], i))
    thresholds = {}
    significant = {}
    failed_yet = False
    for position, i in enumerate(ranked):
        thresholds[i] = alpha / (k - position)
        if failed_yet or not pvalues[i] < thresholds[i]:
            failed_yet = True
            significant[i] = False
        else:
            significant[i] = True
    return [{"threshold": thresholds[i], "significant": significant[i]} for i in range(k)]


def report_text(case, name):
    """The rendered (non-JSON) report for a fixture."""
    e = FIXTURES[name]
    args = ["--results", results_path(name), "--brief", brief_path(name)]
    if e["asof"]:
        args += ["--asof", e["asof"]]
    proc = case.cli("run_readout.py", args)
    case.assertEqual(proc.returncode, 0,
                     "run_readout.py exited %d on %r\nSTDERR: %s"
                     % (proc.returncode, name, proc.stderr[:1000]))
    return proc.stdout


# ===========================================================================
# The correction itself, against values computed by hand.
# ===========================================================================
class TestHolmBonferroni(ImplCase):

    def holm(self):
        return self.func("holm_bonferroni")

    def test_one_hypothesis_is_plain_alpha(self):
        """k == 1: the threshold IS alpha, so nothing about a two-arm readout moves."""
        got = self.holm()([0.04], alpha=0.05)
        self.assertEqual(len(got), 1)
        self.assertAlmostEqual(got[0]["threshold"], 0.05, places=12)
        self.assertTrue(got[0]["significant"])
        self.assertFalse(self.holm()([0.06], alpha=0.05)[0]["significant"])

    def test_boundary_is_strict(self):
        """p exactly equal to its threshold does NOT reject: the rule is p < threshold,
        the same strict inequality the single-arm gate uses against alpha."""
        self.assertFalse(self.holm()([0.05], alpha=0.05)[0]["significant"])

    def test_the_two_arm_case_by_hand(self):
        """p = [3.23e-07, 0.249] at k = 2. Sorted, the smallest faces 0.05/2 = 0.025 and
        clears it; the largest faces 0.05/1 = 0.05 and does not."""
        got = self.holm()([3.23e-07, 0.249], alpha=0.05)
        self.assertAlmostEqual(got[0]["threshold"], 0.025, places=12)
        self.assertTrue(got[0]["significant"])
        self.assertAlmostEqual(got[1]["threshold"], 0.05, places=12)
        self.assertFalse(got[1]["significant"])

    def test_stops_at_the_first_failure(self):
        """THE part that gets implemented wrong. p = [0.01, 0.03, 0.04] at k = 3:
        thresholds 0.0167, 0.025, 0.05. 0.01 clears 0.0167. 0.03 fails 0.025, and the
        procedure ends there -- so 0.04 is retained even though 0.04 < 0.05."""
        got = self.holm()([0.01, 0.03, 0.04], alpha=0.05)
        self.assertAlmostEqual(got[0]["threshold"], 0.05 / 3.0, places=12)
        self.assertAlmostEqual(got[1]["threshold"], 0.05 / 2.0, places=12)
        self.assertAlmostEqual(got[2]["threshold"], 0.05, places=12)
        self.assertEqual([g["significant"] for g in got], [True, False, False],
                         "0.04 is below its own 0.05 threshold but must be RETAINED, "
                         "because the smaller p-value 0.03 already failed at 0.025")

    def test_all_three_can_reject(self):
        got = self.holm()([0.001, 0.002, 0.003], alpha=0.05)
        self.assertEqual([g["significant"] for g in got], [True, True, True])

    def test_results_come_back_in_input_order(self):
        """Sorting happens inside; the caller gets its own order back, or a caller would
        have to re-pair thresholds with arms and would eventually pair them wrong."""
        got = self.holm()([0.2, 0.001, 0.03], alpha=0.05)
        self.assertEqual([g["p_value"] for g in got], [0.2, 0.001, 0.03])
        self.assertEqual([g["rank"] for g in got], [2, 0, 1])
        self.assertEqual([g["significant"] for g in got], [False, True, False])

    def test_ties_are_handled(self):
        got = self.holm()([0.02, 0.02], alpha=0.05)
        self.assertEqual([g["significant"] for g in got], [True, True])
        self.assertEqual(sorted(g["threshold"] for g in got), [0.025, 0.05])

    def test_threshold_is_alpha_over_k_minus_rank(self):
        ps = [0.5, 0.001, 0.2, 0.04]
        got = self.holm()(ps, alpha=0.05)
        for g in got:
            self.assertAlmostEqual(g["threshold"], 0.05 / (4 - g["rank"]), places=12)
            self.assertEqual(g["k"], 4)
            self.assertEqual(g["alpha"], 0.05)

    def test_empty_family(self):
        self.assertEqual(self.holm()([], alpha=0.05), [])

    def test_alpha_must_be_a_probability(self):
        for bad in (0.0, 1.0, -0.1, 2.0):
            self.assertRaises(ValueError, self.holm(), [0.01], bad)

    def test_matches_the_independent_reference(self):
        for ps in ([0.01, 0.03, 0.04], [3.23e-07, 0.249], [0.5, 0.001, 0.2, 0.04],
                   [0.049, 0.049, 0.049], [0.0001]):
            got = self.holm()(ps, alpha=0.05)
            want = holm_reference(ps, alpha=0.05)
            self.assertEqual([g["significant"] for g in got],
                             [w["significant"] for w in want], ps)
            for g, w in zip(got, want):
                self.assertAlmostEqual(g["threshold"], w["threshold"], places=12)


# ===========================================================================
# Presence: no arm may go missing, and no arm may be renamed.
# ===========================================================================
class TestEveryArmIsReported(ImplCase):

    def test_payload_compares_every_treatment_arm(self):
        for name in MULTIARM:
            lift = self.gate(self.payload(name), "lift", name)
            got = sorted(c["arm"] for c in lift["comparisons"])
            want = sorted(fx(name)["treatment_arms"])
            self.assertEqual(got, want,
                             "%s: GATE 4 must compare EVERY treatment arm against control; "
                             "the arms in the data are %s" % (name, want))
            self.assertEqual(lift.get("family_size"), len(want))
            self.assertEqual(lift.get("control_arm"), "control")

    def test_no_single_arm_is_promoted_to_be_the_experiment(self):
        for name in MULTIARM:
            lift = self.gate(self.payload(name), "lift", name)
            leaked = [k for k in SINGULAR_KEYS if k in lift]
            self.assertFalse(
                leaked,
                "%s: gates.lift carries %s at the TOP level. With %d treatment arms that "
                "is one arm's answer wearing the whole experiment's clothes -- the exact "
                "defect this class exists for. Per-arm answers belong in comparisons[]."
                % (name, leaked, lift.get("family_size")))

    def test_every_arm_appears_in_the_rendered_report(self):
        for name in MULTIARM:
            text = report_text(self, name)
            for arm in FIXTURES[name]["arm_names"]:
                self.assertIn(arm, text,
                              "%s: arm %r is in the data but never appears in the rendered "
                              "report. An arm a reader cannot see is an arm they cannot "
                              "argue with." % (name, arm))

    def test_no_arm_is_relabelled_generically(self):
        """The fixtures' arms are treatment_a / treatment_b / control. A row in the
        per-arm table labelled with anything else -- "treatment" above all -- means an arm
        was renamed, and a renamed arm cannot be traced back to the variant it was."""
        for name in MULTIARM:
            arms = set(FIXTURES[name]["arm_names"])
            text = report_text(self, name)
            block = text.split("PRIMARY METRIC")[1].split("\n\n")[0]
            labels = set()
            for line in block.split("\n")[2:]:
                m = re.match(r"^\s{2}(\S+)\s", line)
                if m and not m.group(1).startswith("95%"):
                    labels.add(m.group(1))
            unknown = {x for x in labels
                       if x not in arms and x not in ("arm", "MULTIPLICITY", "vs")}
            self.assertFalse(unknown,
                             "%s: the per-arm table labels %s, which are not arms in the "
                             "data (%s)" % (name, sorted(unknown), sorted(arms)))
            self.assertTrue(arms <= labels | {"control"},
                            "%s: table labels %s do not cover every arm %s"
                            % (name, sorted(labels), sorted(arms)))

    def test_the_dropped_arm_is_the_one_that_would_be_cherry_picked(self):
        """multiarm_one_winner is built so the SECOND treatment arm clears the MDE on its
        point estimate while being nowhere near significant. That is the result someone
        quotes six weeks later, so it has to be on the page."""
        lift = self.gate(self.payload("multiarm_one_winner"), "lift", "multiarm_one_winner")
        b = next(c for c in lift["comparisons"] if c["arm"] == "treatment_b")
        self.assertTrue(b["meets_mde"], "treatment_b's point estimate should clear the MDE")
        self.assertFalse(b["significant"], "treatment_b should not be significant")
        self.assertIn("treatment_b", report_text(self, "multiarm_one_winner"))


# ===========================================================================
# Multiplicity, as it lands in the payload and the report.
# ===========================================================================
class TestMultiplicityInThePayload(ImplCase):

    def test_thresholds_match_an_independent_holm(self):
        """p-values recomputed from the CSV with the independent Welch reference, then
        corrected by the independent Holm above. Nothing here reads the implementation's
        own p-values."""
        for name in MULTIARM:
            metric = FIXTURES[name]["primary_metric"]
            by_arm = read_arms(name, metric)
            lift = self.gate(self.payload(name), "lift", name)
            comps = lift["comparisons"]
            want_p = [_ref.welch(by_arm[c["arm"]], by_arm["control"])["p_value"]
                      for c in comps]
            for c, p in zip(comps, want_p):
                self.assertRelClose(c["p_value"], p, 1e-6,
                                    "%s %s p-value" % (name, c["arm"]))
            want = holm_reference(want_p, alpha=SIG_ALPHA)
            for c, w in zip(comps, want):
                self.assertAlmostEqual(c["holm_threshold"], w["threshold"], places=12,
                                       msg="%s %s Holm threshold" % (name, c["arm"]))
                self.assertEqual(c["significant"], w["significant"],
                                 "%s %s significance after Holm" % (name, c["arm"]))

    def test_thresholds_are_alpha_over_two_and_alpha(self):
        """Two treatment arms, so the bars are 0.025 and 0.05 and nothing else."""
        for name in MULTIARM:
            lift = self.gate(self.payload(name), "lift", name)
            self.assertEqual(sorted(round(c["holm_threshold"], 10)
                                    for c in lift["comparisons"]),
                             [0.025, 0.05], name)

    def test_significance_matches_the_ground_truth_pattern(self):
        for name in MULTIARM:
            want = fx(name)["expect_significant_after_holm"]
            lift = self.gate(self.payload(name), "lift", name)
            got = {c["arm"]: c["significant"] for c in lift["comparisons"]}
            self.assertEqual(got, want, "%s: %s" % (name, fx(name)["note"]))

    def test_the_uncorrected_answer_is_kept_beside_the_corrected_one(self):
        """multiarm_none_survive_holm has an arm at p between 0.025 and 0.05: significant
        alone, not significant in a family of two. Both readings are recorded, because a
        reader who cannot see the difference cannot see what the correction did."""
        lift = self.gate(self.payload("multiarm_none_survive_holm"), "lift",
                         "multiarm_none_survive_holm")
        a = next(c for c in lift["comparisons"] if c["arm"] == "treatment_a")
        self.assertLess(a["p_value"], SIG_ALPHA)
        self.assertTrue(a["significant_uncorrected"])
        self.assertFalse(a["significant"])

    def test_the_report_says_the_correction_was_applied_and_what_it_was(self):
        for name in MULTIARM:
            text = report_text(self, name)
            self.assertIn("MULTIPLICITY", text, "%s: the report must state that the "
                                                "thresholds were corrected" % name)
            self.assertIn("Holm", text, name)
            self.assertIn("0.025", text, "%s: the corrected threshold must be shown, not "
                                         "just named" % name)


# ===========================================================================
# The verdict, and the arm it names.
# ===========================================================================
class TestMultiArmVerdict(ImplCase):

    def test_verdict_matches_ground_truth(self):
        for name in MULTIARM:
            pay = self.payload(name)
            self.assertEqual(pay["verdict"], fx(name)["expect_verdict"],
                             "%s: %s" % (name, fx(name)["note"]))

    def test_winning_arms_are_named(self):
        for name in MULTIARM:
            pay = self.payload(name)
            self.assertEqual(pay.get("winning_arms"), fx(name)["expect_winning_arms"],
                             "%s: the payload must name the arm(s) that won" % name)
            for arm in fx(name)["expect_winning_arms"]:
                self.assertIn(arm, pay["verdict_reason"],
                              "%s: 'ship it' is not an instruction anyone can follow when "
                              "there were three versions of it -- the verdict reason must "
                              "name %r" % (name, arm))

    def test_a_ship_verdict_names_an_arm_in_the_report(self):
        for name in ("multiarm_one_winner", "multiarm_guardrail_breach"):
            text = report_text(self, name)
            self.assertTrue(text.startswith("VERDICT: SHIP\n"), name)
            why = [l for l in text.split("\n") if l.startswith("WHY:")][0]
            self.assertIn("treatment_a", why,
                          "%s: the WHY line must name the winning arm" % name)

    def test_no_winner_and_nothing_ruled_out_is_inconclusive(self):
        """Not a soft NO-SHIP: one arm is unanswered rather than answered no."""
        pay = self.payload("multiarm_none_survive_holm")
        self.assertEqual(pay["verdict"], "INCONCLUSIVE")
        self.assertEqual(pay["winning_arms"], [])

    def test_verdict_token_is_still_one_of_six(self):
        for name in MULTIARM:
            self.assertIn(self.payload(name)["verdict"],
                          {"INVALID-DESIGN", "INVALID-SRM", "INVALID-IMMATURE",
                           "NO-SHIP", "SHIP", "INCONCLUSIVE"}, name)


# ===========================================================================
# GATE 3 across arms.
# ===========================================================================
class TestGuardrailPerArm(ImplCase):

    def test_every_arm_gets_its_own_guardrail_comparison(self):
        for name in MULTIARM:
            guard = self.gate(self.payload(name), "guardrail", name)
            self.assertEqual(sorted(c["arm"] for c in guard["comparisons"]),
                             sorted(fx(name)["treatment_arms"]),
                             "%s: a guardrail breach in ANY arm is a finding, so every arm "
                             "is measured" % name)

    def test_a_breach_in_one_arm_is_reported_as_that_arms_breach(self):
        name = "multiarm_guardrail_breach"
        pay = self.payload(name)
        guard = self.gate(pay, "guardrail", name)
        self.assertEqual(guard["status"], "FAIL")
        self.assertEqual(guard["breaching_arms"], ["treatment_b"])
        per_arm = {c["arm"]: c["assessment"] for c in guard["comparisons"]}
        self.assertEqual(per_arm, {"treatment_a": "OK", "treatment_b": "BREACH"})
        text = report_text(self, name)
        self.assertIn("BREACH", text)
        self.assertIn("treatment_b", text.split("GUARDRAIL")[1])

    def test_a_breach_bars_its_own_arm_and_no_other(self):
        """treatment_b broke the promise; treatment_a did not. Reading one arm's guardrail
        onto another arm is the same mixing-of-arms error as reading one arm's lift as the
        experiment's, so the clean winner still ships -- with the breach in the same
        breath."""
        pay = self.payload("multiarm_guardrail_breach")
        self.assertEqual(pay["verdict"], "SHIP")
        self.assertEqual(pay["winning_arms"], ["treatment_a"])
        self.assertNotIn("treatment_b", pay["winning_arms"])
        self.assertIn("BREACH", pay["verdict_reason"])
        self.assertIn("treatment_b", pay["verdict_reason"])


# ===========================================================================
# k == 1: the A/B path must not have moved a single digit.
# ===========================================================================
TWO_ARM_VALID = ["ship_clean", "srm_mild", "guardrail_at_risk", "guardrail_breach",
                 "sig_below_mde", "mde_ruled_out", "inconclusive",
                 "maturity_exact_boundary"]


class TestTwoArmUnchanged(ImplCase):

    def test_family_of_one(self):
        for name in TWO_ARM_VALID:
            lift = self.gate(self.payload(name), "lift", name)
            self.assertEqual(lift["family_size"], 1, name)
            self.assertEqual(len(lift["comparisons"]), 1, name)

    def test_holm_reduces_to_plain_alpha(self):
        for name in TWO_ARM_VALID:
            c = self.gate(self.payload(name), "lift", name)["comparisons"][0]
            self.assertAlmostEqual(c["holm_threshold"], SIG_ALPHA, places=12, msg=name)
            self.assertEqual(c["significant"], c["p_value"] < SIG_ALPHA, name)
            self.assertEqual(c["significant"], c["significant_uncorrected"], name)

    def test_the_promoted_keys_are_still_there_and_still_agree(self):
        """Downstream tools read gates.lift.rel_diff by name. With one treatment arm there
        is no ambiguity about whose answer that is, so the key stays and must equal the
        single comparison it came from."""
        for name in TWO_ARM_VALID:
            lift = self.gate(self.payload(name), "lift", name)
            c = lift["comparisons"][0]
            for key in ("arm", "n_a", "n_b", "mean_a", "mean_b", "diff", "p_value",
                        "ci_low", "ci_high", "rel_diff", "rel_ci_low", "rel_ci_high",
                        "significant", "ci_excludes_zero", "meets_mde", "mde_ruled_out"):
                self.assertIn(key, lift, "%s: gates.lift lost the key %r" % (name, key))
                self.assertEqual(lift[key], c[key], "%s: gates.lift.%s" % (name, key))

    def test_numbers_still_match_the_independent_reference(self):
        """The point of the regression: Holm at k == 1 changes no arithmetic."""
        for name in TWO_ARM_VALID:
            metric = FIXTURES[name]["primary_metric"]
            by_arm = read_arms(name, metric)
            want = _ref.welch(by_arm["treatment"], by_arm["control"])
            lift = self.gate(self.payload(name), "lift", name)
            for key in ("mean_a", "mean_b", "diff", "p_value", "ci_low", "ci_high",
                        "rel_diff"):
                self.assertRelClose(lift[key], want[key], 1e-9, "%s %s" % (name, key))

    def test_the_two_arm_report_says_nothing_about_multiplicity(self):
        """There is no family to correct, so the A/B report must not grow a section about
        one. The two-arm document is byte-for-byte what it always was."""
        for name in TWO_ARM_VALID:
            text = report_text(self, name)
            self.assertNotIn("MULTIPLICITY", text, name)
            self.assertNotIn("Holm", text, name)
            self.assertIn("PRIMARY METRIC", text, name)
            self.assertIn("  treatment n=", text,
                          "%s: the A/B layout is unchanged, including its labels" % name)

    def test_guardrail_keeps_its_two_arm_shape(self):
        for name in TWO_ARM_VALID:
            guard = self.gate(self.payload(name), "guardrail", name)
            self.assertEqual(guard["family_size"], 1, name)
            c = guard["comparisons"][0]
            for key in ("assessment", "diff", "ci_low", "ci_high", "threshold",
                        "mean_treatment", "mean_control", "detail"):
                self.assertEqual(guard[key], c[key], "%s: gates.guardrail.%s" % (name, key))


if __name__ == "__main__":
    unittest.main()
