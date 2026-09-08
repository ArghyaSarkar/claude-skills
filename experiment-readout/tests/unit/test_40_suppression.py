"""THE SUPPRESSION TEST.

This is the single behaviour the whole scenario is built around: when the data
is invalid, the skill must not quietly hand the PM a number to latch onto.
Under CONTRACT v1.1 that covers BOTH conclusion gates -- the lift AND the
guardrail -- because a guardrail verdict on invalid data is a conclusion too.

Every invalid fixture is built to carry a large, fixture-unique REAL lift and a
REAL guardrail breach, so any leak is unambiguous rather than arguable.

Four independent layers, deliberately structural rather than eyeballed:

  L1 STRUCTURE   gates.lift and gates.guardrail are each exactly
                 {"status": "NOT_RUN", "reason": ...}. Two keys, so there is
                 nowhere for a number to sit.
  L2 KEY NAMES   no key that could only carry a conclusion appears anywhere in
                 the payload (rel_diff, ci_high, effect_size, ...). Scoped so
                 the SRM gate keeps its own legitimate p_value/dof.
  L3 NUMBERS     a recursive scan of every number in the payload -- including
                 numbers smuggled into strings -- proves none of them is the
                 true lift, its p, its t, its CI, the treatment mean, the
                 guardrail delta or the guardrail CI. Expected values come from
                 _ref.py run over the fixture CSV, not from the implementation.
  L4 REPORT      a SEMANTIC scan of the DEFAULT (human) stdout: forbidden
                 CONCEPTS and hedges rather than exact digits, because a leak
                 that got rounded in prose ("about +2%") never matches a
                 full-precision value, and an unrelated number can match one by
                 coincidence. See TestRenderedReportConcepts.

Plus: no BREACH / AT_RISK / PASS / FAIL guardrail claim may survive.
"""

import csv
import os
import re
import unittest

import _ref
from _harness import (CONCLUSION_GATES, FIXTURES, INVALID_FIXTURES,
                      ImplCase, all_numbers, all_keys, contains_number_token,
                      fx, number_forms, prune, readout_args, results_path, walk)

# Keys that could ONLY belong to a conclusion (a lift or a guardrail verdict).
# Forbidden ANYWHERE in the payload of an invalid run.
CONCLUSION_ONLY_KEYS = [
    "rel_diff", "reldiff", "rel_lift", "rellift", "relative_lift",
    "rel_ci_low", "rel_ci_high", "rel_ci", "relative_ci",
    "lift", "uplift", "abs_lift", "lift_pct", "lift_abs",
    "effect_size", "effectsize", "cohens_d", "cohen_d",
    "point_estimate", "practical_significance", "practically_significant",
    "mde_met", "meets_mde", "beats_mde", "above_mde",
    "significant", "is_significant", "stat_sig", "statistically_significant",
    "welch", "welch_t", "t_test", "ttest",
    "breach", "breached", "is_breach", "at_risk", "guardrail_diff",
    "guardrail_delta", "guardrail_ci_low", "guardrail_ci_high",
    "cancel_rate_diff", "cancel_rate_delta", "delta_pp", "diff_pp",
]

# Keys the SRM gate legitimately owns. Forbidden everywhere EXCEPT inside
# gates.srm (which is pruned before this scan runs).
SHARED_STAT_KEYS = [
    "p_value", "pvalue", "p", "t", "t_stat", "tstat", "t_value",
    "ci_low", "ci_high", "ci_lower", "ci_upper", "conf_int",
    "confidence_interval", "ci",
    "mean_a", "mean_b", "mean_treatment", "mean_control",
    "diff", "difference", "se", "std_err", "stderr", "sd_a", "sd_b",
]

# Guardrail/lift conclusion tokens that must not survive as claims.
FORBIDDEN_STATUS_TOKENS = ["BREACH", "AT_RISK", "AT RISK"]


def _read(name, column):
    """Read one numeric column, arm-split, SKIPPING non-numeric cells.

    The AMENDMENT 3A fixtures deliberately contain the unparseable sentinel
    "n/a" in cancel_rate. An unguarded float() here raised in SETUP and took
    three suppression tests -- the headline behaviour of the whole skill -- out
    of the run as ERRORs rather than assertions. A test that errors before it
    asserts is worse than a failing test, because it reads as environmental.
    """
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


def suppressed_quantities(name):
    """The conclusion numbers that MUST NOT appear, computed independently by
    _ref.py from the fixture CSV. Returns {label: value}."""
    e = fx(name)
    out = {}
    if e["primary_col_present"]:
        a, b = _read(name, "completed_orders_28d")
        w = _ref.welch(a, b)
        for k in ("diff", "rel_diff", "t", "p_value", "ci_low", "ci_high",
                  "rel_ci_low", "rel_ci_high", "mean_a"):
            out["lift." + k] = w[k]
        out["lift.rel_pct"] = w["rel_diff"] * 100.0
    gt, gc = _read(name, "cancel_rate")
    if len(gt) >= 2 and len(gc) >= 2:
        g = _ref.welch(gt, gc)
        for k in ("diff", "t", "p_value", "ci_low", "ci_high", "mean_a"):
            out["guardrail." + k] = g[k]
        out["guardrail.diff_pp"] = g["diff"] * 100.0
    return out


class TestNotRunStructure(ImplCase):
    """L1 -- the shape of a suppressed gate."""

    def test_both_conclusion_gates_are_not_run(self):
        failures = []
        for name in INVALID_FIXTURES:
            pay = self.payload(name)
            for g in CONCLUSION_GATES:
                gd = self.gate(pay, g, name)
                if gd.get("status") != "NOT_RUN":
                    failures.append("%s: gates.%s.status = %r (expected "
                                    "NOT_RUN); gate = %r"
                                    % (name, g, gd.get("status"), gd))
        self.assertFalse(failures, "\n\nSUPPRESSION FAILURE -- a conclusion gate "
                                   "ran on invalid data:\n  " +
                                   "\n  ".join(failures))

    def test_not_run_gate_has_exactly_two_keys(self):
        failures = []
        for name in INVALID_FIXTURES:
            pay = self.payload(name)
            for g in CONCLUSION_GATES:
                gd = self.gate(pay, g, name)
                if set(gd) != {"status", "reason"}:
                    failures.append("%s: gates.%s keys = %s (contract says "
                                    "exactly {'status','reason'}); gate = %r"
                                    % (name, g, sorted(gd), gd))
        self.assertFalse(failures, "\n\nSUPPRESSION FAILURE -- a suppressed gate "
                                   "carries extra keys, which is where a number "
                                   "hides:\n  " + "\n  ".join(failures))

    def test_reason_carries_no_numbers_of_its_own(self):
        """The reason names a gate; it must not smuggle a statistic."""
        failures = []
        for name in INVALID_FIXTURES:
            pay = self.payload(name)
            forb = suppressed_quantities(name)
            for g in CONCLUSION_GATES:
                reason = str(self.gate(pay, g, name).get("reason", ""))
                for label, val in forb.items():
                    for form in number_forms(val):
                        if contains_number_token(reason, form):
                            failures.append("%s: gates.%s.reason=%r contains "
                                            "%s (%s = %.10g)"
                                            % (name, g, reason, form, label, val))
        self.assertFalse(failures, "\n\nSUPPRESSION FAILURE:\n  " +
                                   "\n  ".join(failures))


class TestKeyNameSuppression(ImplCase):
    """L2 -- key absence, so the test does not depend on where a leak hides."""

    def test_no_conclusion_only_key_anywhere(self):
        failures = []
        for name in INVALID_FIXTURES:
            pay = self.payload(name)
            # gates.lift / gates.guardrail are the gate CONTAINERS; their own
            # names are legitimate, so scan with them removed.
            reduced = prune(pay, ["gates.lift", "gates.guardrail"])
            keys = all_keys(reduced)
            for bad in CONCLUSION_ONLY_KEYS:
                if bad in keys:
                    failures.append("%s: payload contains key %r, which can "
                                    "only carry a conclusion" % (name, bad))
        self.assertFalse(failures, "\n\nSUPPRESSION FAILURE -- conclusion-bearing "
                                   "key present on invalid data:\n  " +
                                   "\n  ".join(failures))

    def test_no_shared_stat_key_outside_the_srm_gate(self):
        """p_value / ci_* / diff / se are legitimate INSIDE gates.srm only."""
        failures = []
        for name in INVALID_FIXTURES:
            pay = self.payload(name)
            reduced = prune(pay, ["gates.srm", "gates.lift", "gates.guardrail"])
            keys = all_keys(reduced)
            for bad in SHARED_STAT_KEYS:
                if bad in keys:
                    failures.append("%s: statistic key %r appears outside "
                                    "gates.srm" % (name, bad))
        self.assertFalse(failures, "\n\nSUPPRESSION FAILURE:\n  " +
                                   "\n  ".join(failures))

    def test_no_guardrail_status_claim(self):
        """No BREACH / AT_RISK verdict may survive, and the guardrail gate's
        status must not be a pass/fail claim."""
        failures = []
        for name in INVALID_FIXTURES:
            pay = self.payload(name)
            blob = " ".join(str(v) for _p, v in walk(pay)
                            if isinstance(v, str))
            for tok in FORBIDDEN_STATUS_TOKENS:
                if tok in blob:
                    failures.append("%s: payload contains the guardrail claim "
                                    "token %r" % (name, tok))
            st = self.gate(pay, "guardrail", name).get("status")
            if st in ("PASS", "FAIL", "WARN"):
                failures.append("%s: gates.guardrail.status = %r is a pass/fail "
                                "claim on invalid data" % (name, st))
        self.assertFalse(failures, "\n\nSUPPRESSION FAILURE:\n  " +
                                   "\n  ".join(failures))


class TestNumericSuppression(ImplCase):
    """L3 -- the loud one. No number anywhere in the payload may be a
    conclusion quantity, to 1e-9 relative. A leaked value would be exact, so
    a tight tolerance means no false positives from coincidence."""

    RTOL = 1e-9

    def _scan(self, name, payload, where):
        forb = suppressed_quantities(name)
        found = []
        for path, val in all_numbers(payload):
            for label, want in forb.items():
                if want == 0.0:
                    continue
                if abs(val - want) <= self.RTOL * abs(want):
                    found.append("%s: %s at %s = %.12g matches %s (%.12g)"
                                 % (name, where, path, val, label, want))
        return found

    def test_no_conclusion_number_in_payload(self):
        failures = []
        for name in INVALID_FIXTURES:
            failures += self._scan(name, self.payload(name), "payload")
        self.assertFalse(
            failures,
            "\n\n=== SUPPRESSION FAILURE: a conclusion number LEAKED into the "
            "JSON of an invalid readout ===\n  " + "\n  ".join(failures) +
            "\n\nThese fixtures deliberately carry a large real lift and a real "
            "guardrail breach. Any match above means the PM can read a number "
            "off a readout the skill just declared unusable.")

    def test_no_conclusion_number_in_any_string(self):
        """Numbers hidden inside prose strings count as a leak."""
        failures = []
        for name in INVALID_FIXTURES:
            pay = self.payload(name)
            forb = suppressed_quantities(name)
            strings = [(p, v) for p, v in walk(pay) if isinstance(v, str)]
            for path, s in strings:
                for label, want in forb.items():
                    for form in number_forms(want):
                        if contains_number_token(s, form):
                            failures.append(
                                "%s: string at %s contains %r (%s = %.10g): %r"
                                % (name, path, form, label, want, s[:200]))
        self.assertFalse(failures, "\n\n=== SUPPRESSION FAILURE: conclusion "
                                   "number rendered into payload prose ===\n  " +
                                   "\n  ".join(failures))

    def test_sanity_valid_fixtures_do_report_their_lift(self):
        """Control for the test itself: on a VALID fixture the same scan MUST
        find the lift. If this fails, the scan is looking in the wrong place and
        the suppression tests above prove nothing."""
        misses = []
        for name in ("ship_clean", "sig_below_mde", "inconclusive"):
            pay = self.payload(name)
            a, b = _read(name, "completed_orders_28d")
            want = _ref.welch(a, b)["rel_diff"]
            hit = any(abs(v - want) <= 1e-6 * abs(want) or
                      abs(v - want * 100.0) <= 1e-6 * abs(want * 100.0)
                      for _p, v in all_numbers(pay))
            if not hit:
                misses.append("%s: rel_diff %.10g (or %.6f%%) not found in the "
                              "payload of a VALID readout"
                              % (name, want, want * 100.0))
        self.assertFalse(misses,
                         "\n\nSCAN CONTROL FAILED -- the suppression scan cannot "
                         "see a lift even when one is legitimately reported, so "
                         "it would not catch a leak either:\n  " +
                         "\n  ".join(misses))


# ---------------------------------------------------------------------------
# L2 -- SEMANTIC scan of the RENDERED REPORT.
#
# Digit-matching prose is fragile in BOTH directions:
#   FALSE POSITIVE  an unrelated number coincidentally matches at low precision
#                   (the pooled cohort mean "2.1422" vs a guardrail CI of
#                   0.021444 -> both render "2.14").
#   FALSE NEGATIVE  worse: a leak that got ROUNDED in prose ("the lift was
#                   about +2%") never matches a full-precision value at all.
#
# So the report is scanned for forbidden CONCEPTS, not digits. Two rules:
#
#   RULE A  conclusion-only vocabulary is forbidden outright. These words
#           cannot belong to a validity gate, so there is no legitimate use.
#   RULE B  no single clause may name a METRIC and an ARM in the same breath.
#           An arm comparison on a metric IS the conclusion. This is the rule
#           that survives contact with the legitimate content:
#             - the SRM gate names arms and counts but no metric      -> allowed
#             - the design gate echoes metric names but no arms       -> allowed
#             - the truncation gradient names the primary metric but is POOLED
#               across arms, so it names no arm                      -> allowed
#           and a leak like "worth noting the treatment was ahead on
#           completed_orders_28d" trips it.
#
# Pooled cohort means are deliberately NOT in any forbidden set: they are a
# legitimate arm-blind data-quality diagnostic.
# ---------------------------------------------------------------------------

# RULE A -- vocabulary that can only describe a conclusion.
FORBIDDEN_CONCEPTS = [
    "lift", "uplift", "effect size", "effect-size", "cohen",
    "confidence interval", "conf. interval", "credible interval",
    "moved the metric", "moved the needle", "practical significance",
    "practically significant", "point estimate", "relative change",
    "percent change", "percentage change", "% change",
]

# RULE A -- the hedged forms, which are the realistic failure mode: the skill
# does not brazenly print a p-value, it "just mentions" the number.
FORBIDDEN_HEDGES = [
    "directionally", "for context", "for what it is worth",
    "for what it's worth", "fwiw", "worth noting", "worth mentioning",
    "if the srm were fixed", "if the srm is fixed", "if we ignore",
    "ignoring the srm", "setting that aside", "that said, the treatment",
    "the guardrail at least", "at least the guardrail", "guardrail looks fine",
    "looks fine", "no cause for concern", "was ahead", "did better",
    "came out ahead", "trending up", "trending positive", "looks positive",
    "looks promising", "the good news",
]

# RULE A -- regex forms needing a word boundary so "CI" does not match
# "decision" and "p=" does not match "chi2 p=" style validity statistics.
FORBIDDEN_CONCEPT_RES = [
    r"\bCI\b", r"\bCIs\b", r"\bMDE was (?:met|cleared|beaten)\b",
]

# RULE B -- a metric named in the same clause as an arm is an arm comparison.
METRIC_TOKENS = ["completed_orders_28d", "cancel_rate"]
ARM_TOKENS = ["treatment", "control", "variant", "baseline",
              "test arm", "the arms"]


def _numeric_tokens_in(text):
    """Every number appearing in the text, parsed. Used for precision-agnostic
    comparison, which string matching cannot do."""
    out = []
    for m in re.finditer(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", text):
        try:
            out.append(float(m.group(0)))
        except ValueError:
            pass
    return out


def clauses(text):
    """Split the report into clauses: newlines plus sentence-ending punctuation.

    Deliberately does NOT split on ':' or on runs of spaces. The report is a
    fixed-width table, so "completed_orders_28d: treatment 2.16 vs control 2"
    is ONE statement; splitting it apart was what made RULE B toothless (its
    own control test caught that).
    """
    import re
    out = []
    for line in text.splitlines():
        for part in re.split(r"(?<=[.;!?])\s+", line):
            part = part.strip()
            if part:
                out.append(part)
    return out


# A concept term is only a LEAK when it is asserted with a value. The report
# legitimately (a) labels the suppressed gate "GATE 4 lift" and (b) states the
# denial "contains NO lift, no p-value, no confidence interval" -- which is the
# behaviour we want, not a violation. So a hit requires:
#   * a number somewhere in the clause (an assertion carries a value), and
#   * no negator immediately before the term.
NEGATOR_RE = re.compile(r"\b(no|not|never|without|nor|zero|neither)\b[\s,'\"]*$",
                        re.I)
SUPPRESSION_MARKERS = ("not run", "not_run", "deliberately", "suppress",
                       "withheld", "omitted", "cannot be", "is unavailable")


def concept_leak(clause, term):
    """True if `term` is ASSERTED in `clause` rather than labelled or denied."""
    low = clause.lower()
    if any(mk in low for mk in SUPPRESSION_MARKERS):
        return False
    if not re.search(r"\d", clause):
        return False
    for m in re.finditer(re.escape(term), low):
        before = clause[max(0, m.start() - 16):m.start()]
        if NEGATOR_RE.search(before):
            continue
        return True
    return False


class TestRenderedReportConcepts(ImplCase):
    """L2 -- the report must not describe a conclusion, in any wording."""

    def _report(self, name):
        proc = self.cli("run_readout.py", readout_args(name, "fixture", False))
        if proc.returncode != 0:
            self.fail("run_readout.py exited %d rendering the human report for "
                      "%r\nSTDERR: %s" % (proc.returncode, name,
                                          proc.stderr[:2000]))
        return proc.stdout

    def test_no_conclusion_vocabulary(self):
        """RULE A. Catches the rounded-prose leak a digit scan cannot see
        ("the lift was about +2%") while allowing the report to NAME the
        suppressed gate and to STATE that it is withholding the number."""
        failures = []
        for name in INVALID_FIXTURES:
            for cl in clauses(self._report(name)):
                for term in FORBIDDEN_CONCEPTS:
                    if concept_leak(cl, term):
                        failures.append("%s: clause asserts %r with a value: %r"
                                        % (name, term, cl[:220]))
                for pat in FORBIDDEN_CONCEPT_RES:
                    m = re.search(pat, cl)
                    if m and concept_leak(cl, m.group(0)):
                        failures.append("%s: clause asserts %r: %r"
                                        % (name, m.group(0), cl[:220]))
        self.assertFalse(
            failures,
            "\n\n=== SUPPRESSION FAILURE: the report of an INVALID readout "
            "describes a conclusion ===\n  " + "\n  ".join(failures))

    def test_no_hedged_leak(self):
        """RULE A, hedges. 'Directionally the treatment was ahead' is the leak
        that actually happens, and it does no less damage for being hedged."""
        failures = []
        for name in INVALID_FIXTURES:
            for cl in clauses(self._report(name)):
                low = cl.lower()
                if any(mk in low for mk in SUPPRESSION_MARKERS):
                    continue          # the clause is explaining the withholding
                for term in FORBIDDEN_HEDGES:
                    if term in low:
                        failures.append("%s: report hedges with %r: %r"
                                        % (name, term, cl[:220]))
        self.assertFalse(
            failures,
            "\n\n=== SUPPRESSION FAILURE: hedged conclusion in the report of "
            "an INVALID readout ===\n  " + "\n  ".join(failures))

    def test_no_clause_names_a_metric_and_an_arm_together(self):
        """RULE B. An arm comparison on a metric IS the conclusion."""
        failures = []
        for name in INVALID_FIXTURES:
            for cl in clauses(self._report(name)):
                low = cl.lower()
                mets = [m for m in METRIC_TOKENS if m in low]
                arms = [a for a in ARM_TOKENS if a in low]
                if mets and arms:
                    failures.append("%s: clause names metric %s AND arm %s -- "
                                    "that is an arm comparison: %r"
                                    % (name, mets, arms, cl[:220]))
        self.assertFalse(
            failures,
            "\n\n=== SUPPRESSION FAILURE: the report of an INVALID readout "
            "compares arms on a metric ===\n  " + "\n  ".join(failures))

    def test_report_states_the_verdict(self):
        for name in INVALID_FIXTURES:
            text = self._report(name)
            want = fx(name)["expect_verdict"]
            self.assertIn(want, text,
                          "the rendered report for %s must state the verdict %r"
                          % (name, want))

    def test_no_guardrail_claim_token(self):
        failures = []
        for name in INVALID_FIXTURES:
            text = self._report(name)
            for tok in FORBIDDEN_STATUS_TOKENS:
                if tok in text:
                    failures.append("%s: report contains the guardrail claim "
                                    "token %r" % (name, tok))
        self.assertFalse(failures, "\n\nSUPPRESSION FAILURE:\n  " +
                                   "\n  ".join(failures))

    def test_sanity_rule_a_fires_on_a_synthetic_leak(self):
        """CONTROL for RULE A's negation logic: a denial must pass and an
        assertion must fail, including the rounded form a digit scan misses."""
        allowed = [
            "Validity gate(s) srm failed, so this readout deliberately "
            "contains NO lift, no p-value, no confidence interval.",
            "[NOT RUN] GATE 4 lift              srm failed",
        ]
        leaks = [
            "For context the lift was about +2% anyway.",
            "The confidence interval was +5% to +11%.",
            "Effect size looked like roughly 0.1.",
        ]
        for cl in allowed:
            hits = [t for t in FORBIDDEN_CONCEPTS if concept_leak(cl, t)]
            self.assertFalse(hits, "RULE A false-positives on a legitimate "
                                   "denial/label: %r flagged %s" % (cl, hits))
        for cl in leaks:
            hits = [t for t in FORBIDDEN_CONCEPTS if concept_leak(cl, t)]
            self.assertTrue(hits, "RULE A fails to catch the leak %r -- this is "
                                  "the rounded-prose case a digit scan cannot "
                                  "see" % cl)

    def test_sanity_a_valid_report_does_use_conclusion_vocabulary(self):
        """CONTROL for RULE A. On a VALID readout the same scan must FIRE --
        otherwise the vocabulary list is misspelt and proves nothing."""
        hits = [t for cl in clauses(self._report("ship_clean"))
                for t in FORBIDDEN_CONCEPTS if concept_leak(cl, t)]
        self.assertTrue(
            hits,
            "SCAN CONTROL FAILED: a valid SHIP readout should freely use "
            "conclusion vocabulary (lift, confidence interval, ...), but the "
            "scan found none of %s in it -- so its absence on invalid "
            "fixtures proves nothing." % FORBIDDEN_CONCEPTS[:6])

    def test_sanity_a_valid_report_does_compare_arms_on_a_metric(self):
        """CONTROL for RULE B."""
        found = []
        for cl in clauses(self._report("ship_clean")):
            low = cl.lower()
            if any(m in low for m in METRIC_TOKENS) and \
                    any(a in low for a in ARM_TOKENS):
                found.append(cl)
        self.assertTrue(
            found,
            "SCAN CONTROL FAILED: a valid SHIP readout must compare the arms on "
            "the primary metric somewhere, but RULE B found no such clause -- so "
            "its absence on invalid fixtures proves nothing.")


class TestCohortLevelsVsTrendSplit(ImplCase):
    """Pooled cohort means are a legitimate diagnostic, but ABSOLUTE LEVELS
    belong in the JSON for auditability while the PROSE carries trend only
    (cohorts, late-vs-early %, correlation, direction).

    Absolute per-cohort levels in prose are exactly what caused the earlier
    false positive, and more importantly they are a metric level printed next to
    an invalid readout -- an invitation to eyeball a comparison.
    """

    LEVEL_FIXTURES = ["truncation_gradient", "flat_but_impossible",
                      "real_dataset_shape", "immature"]

    def _report(self, name):
        proc = self.cli("run_readout.py", readout_args(name, "fixture", False))
        if proc.returncode != 0:
            self.fail("run_readout.py exited %d rendering %r; STDERR: %s"
                      % (proc.returncode, name, proc.stderr[:1000]))
        return proc.stdout

    def test_absolute_levels_are_in_the_json(self):
        from _harness import all_numbers
        for name in self.LEVEL_FIXTURES:
            g = fx(name)["gradient"]
            nums = [v for _p, v in all_numbers(self.payload(name))]
            for label in ("early_half_mean", "late_half_mean"):
                want = g[label]
                self.assertTrue(
                    any(abs(v - want) <= 1e-6 * abs(want) for v in nums),
                    "fixture %s: the pooled %s (%.6f) must be present in the "
                    "JSON payload for auditability" % (name, label, want))

    def test_absolute_levels_are_absent_from_the_prose(self):
        """Two mechanisms, each precise, no loose middle ground:

          (a) formatted-string scan  -- catches a ROUNDED rendering ("2.09");
          (b) numeric-token scan at 1e-9 relative -- catches a FULL-PRECISION
              rendering ("2.0938572760580003"), which (a) misses entirely
              because its rounded forms never appear as whole tokens in it.

        Mechanism (b) was added after a mutant that printed `early_mean` in
        place of `direction` slipped past mechanism (a).
        """
        failures = []
        for name in self.LEVEL_FIXTURES:
            g = fx(name)["gradient"]
            text = self._report(name)
            tokens = _numeric_tokens_in(text)
            for label in ("early_half_mean", "late_half_mean"):
                want = g[label]
                if want is None:
                    continue
                for form in number_forms(want):
                    if contains_number_token(text, form):
                        failures.append(
                            "%s: rendered report prints the absolute pooled %s "
                            "as the rounded token %r; prose must carry the "
                            "TREND only and leave levels in the JSON"
                            % (name, label, form))
                for tok in tokens:
                    if abs(tok - want) <= 1e-9 * abs(want):
                        failures.append(
                            "%s: rendered report prints the absolute pooled %s "
                            "at full precision (%.12g); prose must carry the "
                            "TREND only" % (name, label, tok))
        self.assertFalse(failures, "\n\nLEVELS LEAKED INTO PROSE:\n  " +
                                   "\n  ".join(failures))

    def test_trend_is_in_the_prose(self):
        """The trend must actually be communicated -- suppressing the levels
        must not suppress the finding."""
        for name in ("truncation_gradient", "flat_but_impossible"):
            low = self._report(name).lower()
            self.assertTrue(
                "cohort" in low or "late" in low,
                "fixture %s: the report must communicate the cohort trend, not "
                "drop it along with the levels" % name)


if __name__ == "__main__":
    unittest.main()
