"""Gate-order integration tests against the CLI JSON payload.

One fixture per scenario, each with ground truth constructed by the seeded
generator and recorded in fixtures/manifest.json. For every fixture we assert
the VERDICT, the per-gate STATUSES, `stopped_at`, and (under CONTRACT v1.1)
`all_validity_failures`.

The v1.2 execution rule these tests encode:
  * gates 0/1/2 (design_integrity, srm, maturity) are VALIDITY gates and ALL
    THREE always evaluate and report, even after an earlier one fails;
  * the verdict is named by the FIRST failing validity gate;
  * gates 3/4 (guardrail, lift) are CONCLUSION gates and are BOTH NOT_RUN if
    any validity gate failed;
  * the as-of date resolves --asof > CSV column > the ask > TODAY, never
    max(exposure_date), and every fixture pins --asof so no verdict here is
    time-dependent (AMENDMENT 2).
"""

import datetime
import unittest

from _harness import (ALL_GATES, CONCLUSION_GATES, FIXTURES, GUARDRAIL_PP,
                      readout_args,
                      INVALID_FIXTURES, METRIC_WINDOW, STATUSES,
                      VALID_FIXTURES, VALIDITY_GATES, VERDICTS, ImplCase, fx,
                      walk)


def numbers_in(obj):
    out = []
    for _p, v in walk(obj):
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            out.append(float(v))
    return out


def strings_in(obj):
    return [v for _p, v in walk(obj) if isinstance(v, str)]


class TestPayloadShape(ImplCase):
    """Structural contract, checked on one representative valid and one
    representative invalid fixture."""

    def test_top_level_keys(self):
        for name in ("ship_clean", "srm_broken"):
            pay = self.payload(name)
            for k in ("experiment", "asof", "verdict", "verdict_reason",
                      "gates", "stopped_at"):
                self.assertIn(k, pay,
                              "payload must contain %r (fixture %s)" % (k, name))
            self.assertIn("all_validity_failures", pay,
                          "CONTRACT v1.1 requires the payload key "
                          "'all_validity_failures' (fixture %s)" % name)

    def test_all_five_gates_present(self):
        for name in ("ship_clean", "srm_broken", "immature", "missing_brief"):
            pay = self.payload(name)
            gates = pay.get("gates", {})
            for g in ALL_GATES:
                self.assertIn(g, gates,
                              "gates must contain %r on every run (fixture %s); "
                              "present: %s" % (g, name, sorted(gates)))

    def test_statuses_are_in_the_contract_vocabulary(self):
        for name in sorted(FIXTURES):
            pay = self.payload(name)
            for g in ALL_GATES:
                st = self.gate(pay, g, name).get("status")
                self.assertIn(st, STATUSES,
                              "gates.%s.status = %r is not one of %s "
                              "(fixture %s)" % (g, st, sorted(STATUSES), name))

    def test_verdict_is_in_the_taxonomy(self):
        for name in sorted(FIXTURES):
            v = self.payload(name).get("verdict")
            self.assertIn(v, VERDICTS,
                          "verdict %r not in the taxonomy %s (fixture %s)"
                          % (v, sorted(VERDICTS), name))

    def test_verdict_reason_is_non_empty(self):
        for name in sorted(FIXTURES):
            pay = self.payload(name)
            vr = pay.get("verdict_reason")
            self.assertIsInstance(vr, str, "verdict_reason must be a string "
                                           "(fixture %s)" % name)
            self.assertTrue(vr.strip(), "verdict_reason must not be empty "
                                        "(fixture %s)" % name)


class TestVerdicts(ImplCase):
    """verdict + stopped_at + all_validity_failures for every fixture."""

    def _check(self, name):
        e = fx(name)
        pay = self.payload(name)
        self.assertEqual(
            pay.get("verdict"), e["expect_verdict"],
            "fixture %s: %s\n  verdict_reason=%r" % (name, e["note"],
                                                     pay.get("verdict_reason")))
        self.assertEqual(
            pay.get("stopped_at"), e["expect_stopped_at"],
            "fixture %s: stopped_at must be %r (the FIRST failing validity "
            "gate), got %r" % (name, e["expect_stopped_at"],
                               pay.get("stopped_at")))
        # AMENDMENT 3B: all_validity_failures lists gates that FAILED;
        # validity_not_assessable lists gates that had NO INPUTS. Both are now
        # pinned exactly for every fixture -- nothing may be silently dropped
        # from the account.
        self.assertEqual(
            pay.get("all_validity_failures"),
            e["expect_all_validity_failures"],
            "fixture %s: all_validity_failures must be %r in gate order, got %r"
            % (name, e["expect_all_validity_failures"],
               pay.get("all_validity_failures")))
        self.assertIn("validity_not_assessable", pay,
                      "CONTRACT v1.3 requires the payload key "
                      "'validity_not_assessable' as a sibling to "
                      "'all_validity_failures' (fixture %s)" % name)
        self.assertEqual(
            pay.get("validity_not_assessable"),
            e["expect_validity_not_assessable"],
            "fixture %s: validity_not_assessable must be %r, got %r -- a gate "
            "whose inputs were missing must be accounted for separately from a "
            "gate that FAILED" % (name, e["expect_validity_not_assessable"],
                                  pay.get("validity_not_assessable")))
        for g, want in sorted(e["expect_validity_status"].items()):
            if want is None:
                continue        # contract genuinely ambiguous for this fixture
            got = self.gate(pay, g, name).get("status")
            self.assertEqual(got, want,
                             "fixture %s: gates.%s.status must be %r, got %r\n"
                             "  %s" % (name, g, want, got, e["note"]))

    # --- valid: all validity gates pass, conclusion gates run -------------
    def test_ship_clean(self):
        self._check("ship_clean")

    def test_srm_mild_does_not_trip(self):
        self._check("srm_mild")

    def test_maturity_exact_boundary(self):
        self._check("maturity_exact_boundary")

    def test_guardrail_breach_forces_no_ship(self):
        self._check("guardrail_breach")

    def test_guardrail_at_risk_still_ships(self):
        self._check("guardrail_at_risk")

    def test_sig_but_below_mde(self):
        self._check("sig_below_mde")

    def test_mde_ruled_out(self):
        self._check("mde_ruled_out")

    def test_inconclusive_underpowered(self):
        self._check("inconclusive")

    # --- invalid ----------------------------------------------------------
    def test_invalid_srm(self):
        self._check("srm_broken")

    def test_invalid_immature(self):
        self._check("immature")

    def test_invalid_partial_maturity(self):
        self._check("partial_maturity")

    def test_invalid_maturity_off_by_one(self):
        self._check("maturity_off_by_one")

    def test_invalid_claim_vs_data_span(self):
        self._check("claim_vs_data_span")

    def test_invalid_design_missing_metric_col(self):
        self._check("missing_metric_col")

    def test_invalid_design_missing_brief(self):
        self._check("missing_brief")

    def test_invalid_design_sealed_after_exposure(self):
        self._check("sealed_after_exposure")

    def test_precedence_srm_beats_maturity_and_guardrail(self):
        self._check("precedence_all_bad")

    def test_trap_real_data(self):
        self._check("trap_real_data")

    def test_real_dataset_shape(self):
        self._check("real_dataset_shape")

    def test_truncation_gradient(self):
        self._check("truncation_gradient")

    def test_flat_but_impossible(self):
        self._check("flat_but_impossible")

    def test_monotone_but_tiny(self):
        self._check("monotone_but_tiny")

    def test_dropped_at_2pct(self):
        self._check("dropped_at_2pct")

    def test_dropped_over_2pct(self):
        self._check("dropped_over_2pct")


class TestPrecedence(ImplCase):
    """SRM is gate 1: it names the verdict even when later gates also fail --
    but AMENDMENT 1 forbids hiding those later failures."""

    MULTI = ["precedence_all_bad", "trap_real_data", "real_dataset_shape"]

    def test_srm_names_the_verdict(self):
        for name in self.MULTI:
            pay = self.payload(name)
            self.assertEqual(pay.get("verdict"), "INVALID-SRM",
                             "fixture %s fails SRM, maturity and the guardrail "
                             "at once; SRM is gate 1 so the verdict must be "
                             "INVALID-SRM" % name)
            self.assertEqual(pay.get("stopped_at"), "srm", "fixture %s" % name)

    def test_maturity_still_reports_a_real_fail(self):
        """The whole point of AMENDMENT 1: a stop-dead-at-gate-1 implementation
        would report NOT_RUN here and hide the second defect, so the PM reruns
        with a fixed split and still gets an unreadable result."""
        for name in self.MULTI:
            st = self.gate(self.payload(name), "maturity", name).get("status")
            self.assertEqual(st, "FAIL",
                             "fixture %s: maturity must still evaluate to FAIL "
                             "after the SRM failure, not %r -- otherwise the "
                             "second defect is hidden" % (name, st))

    def test_design_integrity_still_reports_pass(self):
        for name in self.MULTI:
            st = self.gate(self.payload(name), "design_integrity", name).get("status")
            self.assertEqual(st, "PASS", "fixture %s" % name)

    def test_all_validity_failures_enumerates_both_in_gate_order(self):
        for name in self.MULTI:
            avf = self.payload(name).get("all_validity_failures")
            self.assertEqual(avf, ["srm", "maturity"],
                             "fixture %s: all_validity_failures must enumerate "
                             "EVERY failing validity gate in gate order, got %r"
                             % (name, avf))


class TestConclusionGateGating(ImplCase):
    """Gates 3 and 4 run if and only if all validity gates passed."""

    def test_not_run_on_every_invalid_fixture(self):
        for name in INVALID_FIXTURES:
            pay = self.payload(name)
            for g in CONCLUSION_GATES:
                gd = self.gate(pay, g, name)
                self.assertEqual(
                    gd.get("status"), "NOT_RUN",
                    "fixture %s failed validity gate %r, so gates.%s.status "
                    "must be NOT_RUN, got %r"
                    % (name, pay.get("stopped_at"), g, gd.get("status")))

    def test_not_run_dict_is_exactly_status_and_reason(self):
        """The contract spells the suppressed gate out literally as
        {"status": "NOT_RUN", "reason": "<gate> failed"} -- no other keys, so
        there is nowhere for a leaked number to sit."""
        for name in INVALID_FIXTURES:
            pay = self.payload(name)
            first = pay.get("stopped_at")
            for g in CONCLUSION_GATES:
                gd = self.gate(pay, g, name)
                self.assertEqual(
                    set(gd), {"status", "reason"},
                    "fixture %s: gates.%s must be exactly "
                    "{'status','reason'}, got keys %s"
                    % (name, g, sorted(gd)))
                reason = str(gd.get("reason", "")).lower()
                self.assertIn(
                    str(first).lower(), reason,
                    "fixture %s: gates.%s.reason should name the first failing "
                    "gate (%r), got %r" % (name, g, first, gd.get("reason")))
                self.assertIn(
                    "fail", reason,
                    "fixture %s: gates.%s.reason should say the gate failed, "
                    "got %r" % (name, g, gd.get("reason")))

    def test_both_run_on_every_valid_fixture(self):
        for name in VALID_FIXTURES:
            pay = self.payload(name)
            for g in CONCLUSION_GATES:
                st = self.gate(pay, g, name).get("status")
                self.assertNotEqual(
                    st, "NOT_RUN",
                    "fixture %s passes every validity gate, so gates.%s must "
                    "actually run" % (name, g))


class TestGuardrailGate(ImplCase):
    """Guardrail thresholds, on fixtures whose validity is clean so the gate
    actually runs. BREACH if point diff > +1pp; AT_RISK if diff <= 1pp but the
    95% CI upper exceeds 1pp."""

    def test_flat_guardrail_passes(self):
        for name in ("ship_clean", "srm_mild", "sig_below_mde", "mde_ruled_out"):
            st = self.gate(self.payload(name), "guardrail", name).get("status")
            self.assertEqual(st, "PASS",
                             "fixture %s has a guardrail diff of 0.0 and a CI "
                             "upper of ~+0.13pp, well inside 1pp, so the "
                             "guardrail must PASS, got %r" % (name, st))

    def test_breach_is_a_fail(self):
        """cancel_rate worse by exactly +1.50pp > the +1pp threshold.
        CONTRACT NOTE: the contract names the outcome 'BREACH' but constrains
        `status` to {PASS,FAIL,WARN,NOT_RUN}; FAIL is the only mapping that
        preserves BREACH-worse-than-AT_RISK."""
        gd = self.gate(self.payload("guardrail_breach"), "guardrail",
                       "guardrail_breach")
        self.assertEqual(gd.get("status"), "FAIL",
                         "a +1.50pp guardrail BREACH must map to status FAIL, "
                         "got %r" % gd.get("status"))

    def test_at_risk_is_a_warn(self):
        """cancel_rate diff +0.95pp (<= 1pp, so not a breach) with a CI upper of
        +1.104pp (> 1pp), i.e. AT_RISK -> WARN."""
        gd = self.gate(self.payload("guardrail_at_risk"), "guardrail",
                       "guardrail_at_risk")
        self.assertEqual(gd.get("status"), "WARN",
                         "a +0.95pp diff with a +1.10pp CI upper is AT_RISK, "
                         "which must map to status WARN, got %r"
                         % gd.get("status"))

    def test_breach_reports_the_true_diff(self):
        """The gate ran, so the number must be right: exactly the constructed
        +1.50pp."""
        e = fx("guardrail_breach")
        gd = self.gate(self.payload("guardrail_breach"), "guardrail",
                       "guardrail_breach")
        want = e["diff_guardrail"]
        near = [v for v in numbers_in(gd)
                if abs(v - want) <= 1e-6 or abs(v - want * 100.0) <= 1e-4]
        self.assertTrue(near,
                        "the guardrail gate must report the point difference "
                        "%.6f (or %.4fpp); no matching number found in %r"
                        % (want, want * 100.0, gd))

    def test_breach_beats_a_significant_positive_lift(self):
        """guardrail_breach also has a significant +8.00% primary lift. The
        guardrail must win."""
        pay = self.payload("guardrail_breach")
        self.assertEqual(pay.get("verdict"), "NO-SHIP")
        self.assertNotEqual(self.gate(pay, "lift", "guardrail_breach").get("status"),
                            "NOT_RUN",
                            "validity is clean here, so the lift must still be "
                            "computed -- it is the guardrail, not a validity "
                            "gate, that forces NO-SHIP")


class TestMaturityGate(ImplCase):
    """Metric window, as-of provenance, cutoff, mature_share, exposure span."""

    def test_mature_share_matches_ground_truth(self):
        for name in sorted(FIXTURES):
            e = fx(name)
            gd = self.gate(self.payload(name), "maturity", name)
            if gd.get("status") in ("NOT_RUN", "NOT_ASSESSABLE"):
                continue        # no inputs: see TestNotAssessable
            self.assertIn("mature_share", gd,
                          "the maturity gate must report 'mature_share' "
                          "(fixture %s); keys: %s" % (name, sorted(gd)))
            self.assertRelClose(float(gd["mature_share"]), e["mature_share"],
                                1e-9 if e["mature_share"] else 1e-12,
                                "fixture %s mature_share:" % name)

    def test_partial_maturity_is_a_fail(self):
        """mature_share = 3074/6000 = 0.512333 -- a majority mature, and still
        a FAIL. An implementation using a 'most users are mature' heuristic
        passes here when it must not."""
        e = fx("partial_maturity")
        gd = self.gate(self.payload("partial_maturity"), "maturity",
                       "partial_maturity")
        self.assertGreater(e["mature_share"], 0.5)
        self.assertLess(e["mature_share"], 1.0)
        self.assertEqual(gd.get("status"), "FAIL",
                         "0 < mature_share < 1 is still a FAIL (AMENDMENT 1)")
        self.assertEqual(self.payload("partial_maturity").get("verdict"),
                         "INVALID-IMMATURE")

    def test_off_by_one_single_immature_user_is_a_fail(self):
        """2999/3000 mature = 0.999667. One user, one day short, and the whole
        readout is invalid. Rounding, tolerances, or a >=99% rule all fail."""
        e = fx("maturity_off_by_one")
        self.assertEqual(e["mature_count"], 2999)
        gd = self.gate(self.payload("maturity_off_by_one"), "maturity",
                       "maturity_off_by_one")
        self.assertEqual(gd.get("status"), "FAIL",
                         "mature_share = 0.999667 < 1.0 must FAIL, got %r"
                         % gd.get("status"))

    def test_exact_boundary_counts_as_mature(self):
        """exposure + W == asof exactly. The rule is 'exposure + W <= asof', so
        this is MATURE and the gate must PASS. '<' instead of '<=' fails here."""
        e = fx("maturity_exact_boundary")
        self.assertEqual(e["mature_share"], 1.0)
        gd = self.gate(self.payload("maturity_exact_boundary"), "maturity",
                       "maturity_exact_boundary")
        self.assertEqual(gd.get("status"), "PASS",
                         "exposure_date + 28d == asof is MATURE (the rule is "
                         "<=), so this must PASS, got %r" % gd.get("status"))

    def test_reports_metric_window(self):
        for name in ("ship_clean", "immature", "trap_real_data"):
            gd = self.gate(self.payload(name), "maturity", name)
            self.assertIn(float(METRIC_WINDOW), numbers_in(gd),
                          "the maturity gate must report the metric window W=28 "
                          "(fixture %s); gate=%r" % (name, gd))

    def test_reports_exposure_span_days(self):
        for name in sorted(FIXTURES):
            e = fx(name)
            gd = self.gate(self.payload(name), "maturity", name)
            if gd.get("status") in ("NOT_RUN", "NOT_ASSESSABLE"):
                continue
            self.assertIn("exposure_span_days", gd,
                          "the contract requires the maturity gate to report "
                          "'exposure_span_days' (fixture %s); keys: %s"
                          % (name, sorted(gd)))
            span = int(gd["exposure_span_days"])
            excl = e["exposure_span_days_exclusive"]
            # CONTRACT AMBIGUITY: inclusive (max-min+1) vs exclusive (max-min)
            # day counting is unspecified. Accept either.
            self.assertIn(span, (excl, excl + 1),
                          "fixture %s: exposure_span_days should be %d "
                          "(exclusive) or %d (inclusive), got %d"
                          % (name, excl, excl + 1, span))

    def test_reports_the_cutoff_date(self):
        """v1.1: report the cutoff date (asof - W) after which exposures cannot
        be mature."""
        for name in ("ship_clean", "immature", "partial_maturity",
                     "real_dataset_shape"):
            e = fx(name)
            gd = self.gate(self.payload(name), "maturity", name)
            found = [s for s in strings_in(gd)
                     if e["maturity_cutoff_date"] in s]
            self.assertTrue(found,
                            "fixture %s: the maturity gate must report the "
                            "cutoff date %s (asof %s minus W=28); gate=%r"
                            % (name, e["maturity_cutoff_date"], e["asof_used"],
                               gd))

    def test_reports_asof_provenance_given(self):
        """v1.2 resolution order: an explicit --asof is provenance "given".
        Every fixture pins one, so every fixture must say so."""
        for name in ("ship_clean", "immature", "real_dataset_shape",
                     "srm_broken", "flat_but_impossible"):
            pay = self.payload(name)
            gd = self.gate(pay, "maturity", name)
            blob = " ".join(strings_in(gd)).lower()
            self.assertIn("given", blob,
                          "fixture %s is run with an explicit --asof, so the "
                          "maturity gate must record the provenance as "
                          "'given'; strings found: %r" % (name, strings_in(gd)))
            self.assertNotIn(
                "assumed", blob,
                "fixture %s supplied --asof, so nothing may be labelled an "
                "assumption" % name)

    def test_omitted_asof_defaults_to_today_not_max_exposure(self):
        """AMENDMENT 2. max(exposure_date) is REMOVED as the default because it
        makes mature_share == 1.0 arithmetically impossible for any W > 0, i.e.
        a gate that can never pass. The fallback is now the SYSTEM DATE, which
        is an upper bound on any possible extract date.

        Asserted against today as computed HERE, never a hardcoded literal, and
        this is the ONLY test allowed to omit --asof: every other fixture pins
        it so no verdict is time-dependent.
        """
        name = "ship_clean"
        today = datetime.date.today().isoformat()
        pay = self.payload(name, asof=None)
        self.assertEqual(
            str(pay.get("asof")), today,
            "with no --asof the resolved as-of date must be today (%s), got %r"
            % (today, pay.get("asof")))
        self.assertNotEqual(
            str(pay.get("asof")), fx(name)["max_exposure_date"],
            "max(exposure_date) was REMOVED as the default in AMENDMENT 2 -- it "
            "guarantees mature_share < 1.0 and so makes the maturity gate "
            "incapable of ever passing")

    def test_omitted_asof_is_labelled_an_assumption(self):
        """The assumption must stay auditable: provenance says it was assumed,
        and names today."""
        pay = self.payload("ship_clean", asof=None)
        gd = self.gate(pay, "maturity", "ship_clean")
        blob = " ".join(strings_in(gd) + [str(pay.get("asof"))]).lower()
        self.assertIn("assumed", blob,
                      "omitting --asof must be labelled an assumption, not "
                      "presented as fact; strings: %r" % strings_in(gd))
        self.assertIn("today", blob,
                      "the assumption is specifically 'assumed: today', so the "
                      "gate must say which assumption it made; strings: %r"
                      % strings_in(gd))
        self.assertIn(datetime.date.today().isoformat(),
                      " ".join(strings_in(gd) + [str(pay.get("asof"))]),
                      "the resolved date must be recorded in the payload so the "
                      "assumption is auditable")

    def test_given_asof_is_echoed(self):
        for name in ("ship_clean", "srm_broken", "guardrail_breach"):
            e = fx(name)
            self.assertEqual(str(self.payload(name).get("asof")), e["asof"],
                             "fixture %s: payload['asof'] must echo the "
                             "supplied --asof %s" % (name, e["asof"]))


class TestTruncationGradient(ImplCase):
    """AMENDMENT 2 fix 3: the maturity gate must report the primary metric's
    mean by exposure date and read the trend.

    A genuinely truncated N-day metric MUST show late cohorts lower, because
    they had less follow-up time. Two readings, two fixtures:

      truncation_gradient  corr = -0.9955, late-vs-early = -25.69%
                           -> positive evidence of truncation, from the data
                              alone, no as-of date needed.
      flat_but_impossible  corr = -0.1392, late-vs-early =  -0.50%
                           -> FLAT, yet the timeline makes maturity impossible
                              for the last cohorts. That is a DATA INTEGRITY
                              concern: the values do not show the
                              follow-up-time dependence they must have.

    NOTE ON THE CORRELATION: for a flat series the correlation of cohort index
    with cohort mean is scale-free and therefore not stably bounded -- near-equal
    means can correlate at any value. So flatness is asserted on the
    late-vs-early MAGNITUDE, which is controllable, and only the gradient
    fixture gets a correlation bound. The contract's measured -0.031 on the real
    data is consistent with this: it is a noise artefact, not a stable quantity.
    """

    def _grad(self, name):
        return fx(name)["gradient"]

    def test_reports_a_cohort_trend(self):
        """The gate must report the trend, both readings included."""
        for name in ("truncation_gradient", "flat_but_impossible",
                     "real_dataset_shape", "monotone_but_tiny"):
            g = self._grad(name)
            gd = self.gate(self.payload(name), "maturity", name)
            nums = numbers_in(gd)
            want_rel = g["late_vs_early_rel"]
            hit = [v for v in nums
                   if abs(v - want_rel) <= 1e-4 * max(1e-3, abs(want_rel))
                   or abs(v - want_rel * 100.0) <= 1e-4 * max(1e-3,
                                                              abs(want_rel * 100.0))
                   or abs(v - g["late_vs_early_delta"]) <= 1e-4 * max(
                       1e-3, abs(g["late_vs_early_delta"]))]
            self.assertTrue(
                hit,
                "fixture %s: the maturity gate must report the late-half vs "
                "early-half trend (delta %+.6f, i.e. %+.4f%%); no matching "
                "number found.\nmaturity gate numbers: %s"
                % (name, g["late_vs_early_delta"], 100.0 * want_rel,
                   sorted(set(nums))))

    def test_reports_the_cohort_correlation(self):
        for name in ("truncation_gradient", "flat_but_impossible",
                     "real_dataset_shape", "monotone_but_tiny"):
            g = self._grad(name)
            gd = self.gate(self.payload(name), "maturity", name)
            nums = numbers_in(gd)
            want = g["truncation_corr"]
            hit = [v for v in nums if abs(v - want) <= 0.02]
            self.assertTrue(
                hit,
                "fixture %s: the maturity gate must report the correlation of "
                "cohort index with cohort mean (%.4f); no number within 0.02 "
                "found.\nmaturity gate numbers: %s"
                % (name, want, sorted(set(nums))))

    def test_gradient_present_reads_as_truncation(self):
        """corr -0.9955 and a -25.69% late-vs-early gap is what truncation
        looks like, and the gate must say so."""
        name = "truncation_gradient"
        g = self._grad(name)
        self.assertLess(g["truncation_corr"], -0.7, "fixture wiring")
        self.assertLess(g["late_vs_early_rel"], -0.20, "fixture wiring")
        gd = self.gate(self.payload(name), "maturity", name)
        blob = " ".join(strings_in(gd)).lower()
        self.assertIn("truncat", blob,
                      "fixture %s has an unmistakable truncation gradient, so "
                      "the maturity gate must name it as evidence of "
                      "truncation; strings: %r" % (name, strings_in(gd)))
        self.assertEqual(self.payload(name).get("verdict"), "INVALID-IMMATURE")

    def test_flat_but_impossible_reads_as_a_data_integrity_concern(self):
        """The stronger finding. Flat cohort means plus a timeline that makes
        maturity impossible means the values do not show the follow-up-time
        dependence they must have -- which is a data problem, not a waiting
        problem. This is the real arena dataset's shape."""
        for name in ("flat_but_impossible", "real_dataset_shape",
                     "monotone_but_tiny"):
            g = self._grad(name)
            self.assertLess(abs(g["late_vs_early_rel"]), 0.01,
                            "fixture %s must be genuinely flat (got %+.4f%%)"
                            % (name, 100.0 * g["late_vs_early_rel"]))
            self.assertLess(fx(name)["mature_share"], 1.0, "fixture wiring")
            gd = self.gate(self.payload(name), "maturity", name)
            blob = " ".join(strings_in(gd)).lower()
            self.assertIn(
                "integrit", blob,
                "fixture %s is FLAT (%+.3f%% late-vs-early) while only %.1f%% "
                "of users can be mature, so AMENDMENT 2 requires the gate to "
                "raise a DATA INTEGRITY concern rather than report ordinary "
                "truncation; strings: %r"
                % (name, 100.0 * g["late_vs_early_rel"],
                   100.0 * fx(name)["mature_share"], strings_in(gd)))

    def test_flat_case_is_not_mislabelled_as_truncation_evidence(self):
        """The two readings must not collapse into one. A flat series is not
        evidence of truncation, and calling it that hides the real finding."""
        for name in ("flat_but_impossible", "real_dataset_shape",
                     "monotone_but_tiny"):
            gd = self.gate(self.payload(name), "maturity", name)
            blob = " ".join(strings_in(gd)).lower()
            self.assertNotIn(
                "evidence of truncation", blob,
                "fixture %s is flat, so it is NOT evidence of truncation" % name)

    def test_gradient_case_is_not_mislabelled_as_a_data_integrity_concern(self):
        gd = self.gate(self.payload("truncation_gradient"), "maturity",
                       "truncation_gradient")
        blob = " ".join(strings_in(gd)).lower()
        self.assertNotIn(
            "integrit", blob,
            "truncation_gradient shows exactly the follow-up-time dependence a "
            "truncated metric must show, so there is no integrity concern to "
            "raise; strings: %r" % strings_in(gd))

    def test_cohort_trend_is_arm_blind(self):
        """The trend is a maturity diagnostic, so it must be pooled across arms.
        A per-arm cohort breakdown would itself leak the lift on an invalid
        readout -- which the suppression suite would also catch, but the reason
        belongs here."""
        for name in ("truncation_gradient", "flat_but_impossible"):
            gd = self.gate(self.payload(name), "maturity", name)
            keys = set()
            for _p, v in walk(gd):
                if isinstance(v, dict):
                    keys.update(str(k).lower() for k in v)
            for bad in ("treatment", "control", "by_arm", "per_arm", "arm"):
                self.assertNotIn(
                    bad, keys,
                    "fixture %s: the cohort trend must be pooled across arms, "
                    "but the maturity gate carries a %r key" % (name, bad))


class TestNotAssessableVsNotRun(ImplCase):
    """AMENDMENT 3B. Two statuses that must never be confused.

      NOT_RUN        = deliberately SUPPRESSED because a validity gate failed.
                       Next action: fix the validity problem, then re-read out.
      NOT_ASSESSABLE = the gate had NO INPUTS, because gate 0 could not supply
                       them. Next action: go and get the missing input.

    Rendering them identically is a reporting bug: "we chose not to conclude"
    and "we could not check" demand different next actions.
    """

    def test_missing_brief_makes_srm_and_maturity_not_assessable(self):
        """With no brief there is no designed ratio and no metric name, so
        neither gate has anything to evaluate. That is NOT_ASSESSABLE."""
        pay = self.payload("missing_brief")
        for g in ("srm", "maturity"):
            st = self.gate(pay, g, "missing_brief").get("status")
            self.assertEqual(
                st, "NOT_ASSESSABLE",
                "gates.%s must be NOT_ASSESSABLE when the brief is absent: the "
                "gate could not be CHECKED, which is a different finding from "
                "a suppressed conclusion. Got %r." % (g, st))
            self.assertNotEqual(
                st, "NOT_RUN",
                "gates.%s must NOT be NOT_RUN: nothing was suppressed here, the "
                "input was missing" % g)

    def test_not_assessable_reason_names_the_missing_input(self):
        pay = self.payload("missing_brief")
        for g, expect_any in (("srm", ("ratio", "designed", "brief", "split")),
                              ("maturity", ("metric", "window", "brief"))):
            gd = self.gate(pay, g, "missing_brief")
            reason = str(gd.get("reason", ""))
            self.assertTrue(reason.strip(),
                            "gates.%s must carry a reason naming the missing "
                            "input" % g)
            low = reason.lower()
            self.assertTrue(
                any(tok in low for tok in expect_any),
                "gates.%s reason must name WHICH input was missing (one of %s "
                "expected); got %r" % (g, list(expect_any), reason))

    def test_not_assessable_is_listed_not_dropped(self):
        pay = self.payload("missing_brief")
        self.assertEqual(
            pay.get("validity_not_assessable"), ["srm", "maturity"],
            "both unassessable validity gates must be listed under "
            "validity_not_assessable, in gate order")
        self.assertEqual(
            pay.get("all_validity_failures"), ["design_integrity"],
            "all_validity_failures lists gates that FAILED; an unassessable "
            "gate did not fail, so it must not appear there")

    def test_suppressed_gates_are_not_run_not_not_assessable(self):
        """The converse direction. On every invalid fixture the conclusion
        gates were suppressed -- they had their inputs, we chose not to
        conclude -- so they must be NOT_RUN and never NOT_ASSESSABLE."""
        failures = []
        for name in INVALID_FIXTURES:
            pay = self.payload(name)
            for g in CONCLUSION_GATES:
                st = self.gate(pay, g, name).get("status")
                if st == "NOT_ASSESSABLE":
                    failures.append(
                        "%s: gates.%s is NOT_ASSESSABLE but it was merely "
                        "SUPPRESSED -- its inputs existed" % (name, g))
        self.assertFalse(failures, "\n\nSTATUS COLLISION:\n  " +
                                   "\n  ".join(failures))

    def test_the_two_statuses_never_collide_anywhere(self):
        """Sweep every fixture and every gate. A gate is NOT_ASSESSABLE only if
        it appears in validity_not_assessable, and NOT_RUN only if it does not.
        This is the invariant that keeps the two meanings from blurring."""
        failures = []
        for name in sorted(FIXTURES):
            pay = self.payload(name)
            na = pay.get("validity_not_assessable") or []
            for g in ALL_GATES:
                st = self.gate(pay, g, name).get("status")
                if st == "NOT_ASSESSABLE" and g not in na:
                    failures.append("%s: gates.%s is NOT_ASSESSABLE but is "
                                    "absent from validity_not_assessable %r"
                                    % (name, g, na))
                if st == "NOT_RUN" and g in na:
                    failures.append("%s: gates.%s is listed as unassessable but "
                                    "reports NOT_RUN" % (name, g))
                if g in na and st != "NOT_ASSESSABLE":
                    failures.append("%s: gates.%s is listed in "
                                    "validity_not_assessable but its status is "
                                    "%r" % (name, g, st))
        self.assertFalse(failures, "\n\nSTATUS COLLISION:\n  " +
                                   "\n  ".join(failures))

    def test_not_assessable_only_on_validity_gates(self):
        """Gates 3-4 are suppressed, never unassessable: the contract assigns
        NOT_RUN to them explicitly."""
        for name in sorted(FIXTURES):
            for g in CONCLUSION_GATES:
                st = self.gate(self.payload(name), g, name).get("status")
                self.assertNotEqual(
                    st, "NOT_ASSESSABLE",
                    "fixture %s: NOT_ASSESSABLE belongs to validity gates whose "
                    "inputs gate 0 could not supply, not to conclusion gate %r"
                    % (name, g))

    def test_the_report_distinguishes_them_in_words(self):
        """A reader must be able to tell them apart without reading JSON.

        Checked PER GATE. My first version stripped the not-assessable wording
        and then looked for "NOT RUN" anywhere in the report -- but NOT RUN
        legitimately appears there for the SUPPRESSED conclusion gates in the
        same output, so the test conflated the two things it was meant to
        separate.
        """
        proc = self.cli("run_readout.py",
                        readout_args("missing_brief", "fixture", False))
        lines = proc.stdout.splitlines()

        def gate_line(gate):
            for ln in lines:
                if gate.upper() in ln.upper() and "GATE" in ln.upper():
                    return ln
            return None

        srm_ln = gate_line("srm")
        lift_ln = gate_line("lift")
        self.assertTrue(srm_ln, "no report line found for the srm gate")
        self.assertTrue(lift_ln, "no report line found for the lift gate")
        self.assertNotIn(
            "NOT RUN", srm_ln.upper(),
            "srm was UNASSESSABLE (no designed ratio), but its report line uses "
            "the NOT RUN wording reserved for suppressed conclusions, which "
            "tells the reader the wrong next action: %r" % srm_ln.strip())
        self.assertIn(
            "NOT RUN", lift_ln.upper(),
            "the lift gate WAS suppressed, so its line should say NOT RUN: %r"
            % lift_ln.strip())
        self.assertNotEqual(
            srm_ln.strip()[:12].upper(), lift_ln.strip()[:12].upper(),
            "an unassessable gate and a suppressed gate must not render with "
            "the same status label")

    def test_unassessable_gates_are_not_counted_as_passes(self):
        """'We could not check' must not read as 'we checked and it was fine'."""
        proc = self.cli("run_readout.py",
                        readout_args("missing_brief", "fixture", False))
        up = proc.stdout.upper()
        self.assertNotIn(
            "[PASS    ] GATE 1", up,
            "an unassessable srm gate must never render as a PASS")
        self.assertNotIn(
            "[PASS    ] GATE 2", up,
            "an unassessable maturity gate must never render as a PASS")


class TestGradientMagnitudePrecedence(ImplCase):
    """AMENDMENT 3C. The flat / late_lower determination must key PRIMARILY off
    the late-vs-early MAGNITUDE, with Pearson r as supporting context only.

    This matters more than it looks: the DATA INTEGRITY branch fires on "flat",
    so before this correction the single strongest finding in the readout rested
    on a statistic that is not stably bounded over a near-flat series.

    The discriminating fixture is `monotone_but_tiny`:
        r        = -0.9064   -> an r-driven implementation says late_lower
        magnitude = -0.32%   -> a magnitude-driven implementation says flat
    Only one of those can be the contract-correct answer, and it is `flat`.
    """

    def test_magnitude_decides_when_it_disagrees_with_r(self):
        name = "monotone_but_tiny"
        g = fx(name)["gradient"]
        # Fixture wiring: the two statistics really do disagree.
        self.assertLess(g["truncation_corr"], -0.7,
                        "fixture must have a strongly negative r")
        self.assertLess(abs(g["late_vs_early_rel"]), 0.01,
                        "fixture must have a trivially small magnitude")
        gd = self.gate(self.payload(name), "maturity", name)
        blob = " ".join(strings_in(gd)).lower()
        self.assertIn(
            "flat", blob,
            "fixture %s has r = %.4f (strongly negative) but a late-vs-early "
            "magnitude of only %+.4f%%. AMENDMENT 3C makes the MAGNITUDE "
            "decide, so the determination must be FLAT. Reading 'late_lower' "
            "off r is exactly the unstable-statistic bug the amendment "
            "removes.\nmaturity strings: %r"
            % (name, g["truncation_corr"], 100.0 * g["late_vs_early_rel"],
               strings_in(gd)))
        self.assertNotIn(
            "late_lower", blob,
            "fixture %s must NOT be called late_lower: that is the r-driven "
            "answer, and r is supporting context only" % name)

    def test_flat_call_drives_the_data_integrity_branch(self):
        """Because the call is flat and the timeline still makes maturity
        impossible, the stronger finding must fire -- now resting on the stable
        quantity rather than on r."""
        name = "monotone_but_tiny"
        gd = self.gate(self.payload(name), "maturity", name)
        blob = " ".join(strings_in(gd)).lower()
        self.assertIn(
            "integrit", blob,
            "fixture %s is flat (by magnitude) while only %.1f%% of users can "
            "be mature, so the DATA INTEGRITY branch must fire"
            % (name, 100.0 * fx(name)["mature_share"]))

    def test_magnitude_is_reported_before_r(self):
        """'Never present r as the headline evidence for flatness. Report the
        magnitude first.'

        Checked in DOCUMENT order over the whole report, not per line: the
        implementation legitimately devotes a separate follow-up line to r as
        supporting context, so a per-line rule flagged that line for lacking a
        magnitude -- a false positive in my first version of this test.
        """
        MAG = ("late-half", "late half", "late-vs-early", "late vs early",
               "late_vs_early")
        failures = []
        for name in ("truncation_gradient", "flat_but_impossible",
                     "monotone_but_tiny", "real_dataset_shape"):
            proc = self.cli("run_readout.py",
                            readout_args(name, "fixture", False))
            low = proc.stdout.lower()
            i_corr = min([low.index(t) for t in ("corr(", "corr=", " corr ")
                          if t in low] or [10 ** 9])
            i_mag = min([low.index(t) for t in MAG if t in low] or [10 ** 9])
            if i_mag == 10 ** 9:
                failures.append("%s: the report never states the late-vs-early "
                                "magnitude at all" % name)
            elif i_corr < i_mag:
                failures.append("%s: r is mentioned at offset %d, before the "
                                "magnitude at %d -- r must never be the "
                                "headline evidence" % (name, i_corr, i_mag))
        self.assertFalse(
            failures,
            "\n\nAMENDMENT 3C: the magnitude is the stable quantity and must "
            "be reported FIRST, with r as supporting context:\n  " +
            "\n  ".join(failures))

    def test_r_bound_asserted_only_on_the_engineered_gradient(self):
        """Guard on the SUITE, not the implementation: only a fixture with a
        real engineered gradient may carry an r bound, because r over a
        near-flat series is noise. Flatness is asserted on magnitude.
        """
        engineered = {"truncation_gradient", "monotone_but_tiny"}
        for name in sorted(FIXTURES):
            g = (fx(name).get("gradient") or {})
            corr = g.get("truncation_corr")
            if corr is None:
                continue
            if name in engineered:
                continue
            if (g.get("n_cohorts") or 0) < 4:
                # DEGENERATE, not noisy: Pearson r over two cohort means is
                # mathematically +/-1 regardless of the data, which is itself a
                # small illustration of why r cannot carry this decision. The
                # implementation reports 'insufficient_cohorts' here.
                continue
            self.assertLess(
                abs(corr), 0.75,
                "fixture %s has no engineered gradient yet shows |r| = %.3f. "
                "If a test ever bounds r here it is bounding noise."
                % (name, abs(corr)))

    def test_rule_is_auditable(self):
        """AMENDMENT 3C made the rule inspectable: flat_band, decided_by and
        corr_agrees_with_magnitude. A rule you cannot read off the output is a
        rule nobody can review."""
        for name in ("truncation_gradient", "flat_but_impossible",
                     "monotone_but_tiny", "real_dataset_shape"):
            gd = self.gate(self.payload(name), "maturity", name)
            grad = None
            for _p, v in walk(gd):
                if isinstance(v, dict) and "late_vs_early_rel" in v:
                    grad = v
                    break
            self.assertIsNotNone(
                grad, "fixture %s: no gradient block found in the maturity "
                      "gate" % name)
            for field in ("flat_band", "decided_by",
                          "corr_agrees_with_magnitude"):
                self.assertIn(
                    field, grad,
                    "fixture %s: the gradient block must expose %r so the rule "
                    "is auditable; keys: %s" % (name, field, sorted(grad)))
            self.assertEqual(
                float(grad["flat_band"]), 0.02,
                "fixture %s: the flat band is +/-2%%" % name)
            decided = str(grad["decided_by"]).lower()
            self.assertIn(
                "magnitude", decided,
                "fixture %s: decided_by must record that the MAGNITUDE decided "
                "the branch, got %r" % (name, grad["decided_by"]))

    def test_branch_keys_only_off_the_magnitude(self):
        """The branch must follow late_vs_early_rel against the flat band, for
        every gradient fixture, whatever r says."""
        for name in ("truncation_gradient", "flat_but_impossible",
                     "monotone_but_tiny", "real_dataset_shape"):
            g = fx(name)["gradient"]
            gd = self.gate(self.payload(name), "maturity", name)
            blob = " ".join(strings_in(gd)).lower()
            inside = abs(g["late_vs_early_rel"]) <= 0.02
            want = "flat" if inside else "late_lower"
            self.assertIn(
                want, blob,
                "fixture %s: magnitude %+.4f%% is %s the +/-2%% flat band, so "
                "the branch must be %r regardless of r = %.4f"
                % (name, 100.0 * g["late_vs_early_rel"],
                   "inside" if inside else "outside", want,
                   g["truncation_corr"]))
            self.assertEqual(
                want, fx(name)["expect_gradient_label"],
                "fixture wiring: manifest label disagrees with the band rule")

    def test_monotone_but_tiny_branch_is_flat(self):
        """Half one of the case the skill agent found. r <= -0.5 with p < 0.05
        and a magnitude INSIDE the flat band: the branch must still be flat,
        because r never touches the branch."""
        name = "monotone_but_tiny"
        g = fx(name)["gradient"]
        self.assertLessEqual(g["truncation_corr"], -0.5, "fixture wiring")
        self.assertLessEqual(abs(g["late_vs_early_rel"]), 0.02,
                             "fixture wiring: magnitude must be inside the band")
        gd = self.gate(self.payload(name), "maturity", name)
        blob = " ".join(strings_in(gd)).lower()
        self.assertIn("flat", blob)
        self.assertNotIn("late_lower", blob)

    def test_monotone_but_tiny_reading_acknowledges_the_decline(self):
        """Half two. Magnitude-only would call this flat and then assert that
        the values do not move with follow-up time -- which for THIS dataset is
        false: they move monotonically (r=-0.906, p=7.9e-06), just far too
        little for a 28-day truncation. r must inform the WORDING."""
        gd = self.gate(self.payload("monotone_but_tiny"), "maturity",
                       "monotone_but_tiny")
        blob = " ".join(strings_in(gd)).lower()
        self.assertTrue(
            "monotone" in blob or "monotonic" in blob,
            "the reading must acknowledge that a monotone decline IS present, "
            "otherwise the flat branch sits next to a false statement about the "
            "data; strings: %r" % strings_in(gd))
        self.assertTrue(
            any(t in blob for t in ("too small", "inside the flat band",
                                    "weaker", "far weaker")),
            "the reading must say the decline is too SMALL for a 28-day "
            "truncation, which is the accurate framing; strings: %r"
            % strings_in(gd))

    def test_monotone_but_tiny_reading_does_not_claim_values_fail_to_move(self):
        """Half two, strict form, exactly as specified: the reading must not
        claim the values fail to move with follow-up time.

        JUDGEMENT CALL, REPORTED: the implementation keeps the sentence "the
        values do not move with follow-up time" and appends a qualifying
        "Nuance:" clause rather than rewriting it. The paragraph as a whole is
        accurate; the sentence in isolation is not, and a skimming reader stops
        at the sentence. Asserted strictly per the instruction so the
        coordinator can rule on it rather than have it silently absorbed.
        """
        gd = self.gate(self.payload("monotone_but_tiny"), "maturity",
                       "monotone_but_tiny")
        blob = " ".join(strings_in(gd)).lower()
        for phrase in ("do not move with follow-up",
                       "does not move with follow-up",
                       "values do not move"):
            self.assertNotIn(
                phrase, blob,
                "for THIS fixture the values DO move with follow-up time "
                "(monotone, r=-0.906, p=7.9e-06) -- they move too little, which "
                "is a different claim. Saying %r is false here even when a "
                "later clause qualifies it." % phrase)

    def test_r_is_still_reported_as_supporting_context(self):
        """Demoting r must not mean dropping it."""
        for name in ("truncation_gradient", "monotone_but_tiny",
                     "flat_but_impossible"):
            g = fx(name)["gradient"]
            gd = self.gate(self.payload(name), "maturity", name)
            nums = numbers_in(gd)
            self.assertTrue(
                any(abs(v - g["truncation_corr"]) <= 0.02 for v in nums),
                "fixture %s: r (%.4f) must still be reported as supporting "
                "context, just not as the headline" % (name,
                                                       g["truncation_corr"]))


class TestSrmGate(ImplCase):
    """The SRM gate on real fixtures, cross-checked against the manifest's
    hand-derived chi-squared values."""

    def test_reports_chi2_and_counts(self):
        for name in ("srm_mild", "srm_broken", "trap_real_data",
                     "real_dataset_shape"):
            e = fx(name)
            gd = self.gate(self.payload(name), "srm", name)
            nums = numbers_in(gd)
            self.assertTrue(
                any(abs(v - e["srm_chi2"]) <= 1e-6 * max(1.0, e["srm_chi2"])
                    for v in nums),
                "fixture %s: the srm gate must report chi2 = %.6f; gate=%r"
                % (name, e["srm_chi2"], gd))
            for arm in ("treatment", "control"):
                self.assertIn(float(e["counts"][arm]), nums,
                              "fixture %s: the srm gate must report the observed "
                              "%s count %d; gate=%r"
                              % (name, arm, e["counts"][arm], gd))

    def test_exact_5050_passes(self):
        for name in ("ship_clean", "immature", "guardrail_breach"):
            e = fx(name)
            self.assertEqual(e["counts"]["treatment"], e["counts"]["control"])
            st = self.gate(self.payload(name), "srm", name).get("status")
            self.assertEqual(st, "PASS",
                             "fixture %s is an exact 50/50 split, so the SRM "
                             "gate must PASS, got %r" % (name, st))

    def test_mild_imbalance_passes(self):
        st = self.gate(self.payload("srm_mild"), "srm", "srm_mild").get("status")
        self.assertEqual(st, "PASS",
                         "3050/2950 gives chi2=1.667, p=0.197, which must not "
                         "trip alpha=0.001; got %r" % st)

    def test_broken_split_fails(self):
        for name in ("srm_broken", "precedence_all_bad", "trap_real_data",
                     "real_dataset_shape"):
            st = self.gate(self.payload(name), "srm", name).get("status")
            self.assertEqual(st, "FAIL", "fixture %s: %s" % (name, fx(name)["note"]))


class TestDesignIntegrityGate(ImplCase):

    def test_status_matches_ground_truth_on_valid_fixtures(self):
        """PASS normally, but WARN is legitimate under AMENDMENT 3A when rows
        were dropped from a secondary column without exceeding 2%."""
        for name in VALID_FIXTURES:
            want = fx(name)["expect_validity_status"]["design_integrity"]
            st = self.gate(self.payload(name), "design_integrity",
                           name).get("status")
            self.assertEqual(st, want, "fixture %s" % name)

    def test_missing_primary_column_fails(self):
        pay = self.payload("missing_metric_col")
        self.assertEqual(self.gate(pay, "design_integrity",
                                   "missing_metric_col").get("status"), "FAIL")
        self.assertEqual(pay.get("verdict"), "INVALID-DESIGN")

    def test_missing_brief_fails(self):
        pay = self.payload("missing_brief")
        self.assertEqual(self.gate(pay, "design_integrity",
                                   "missing_brief").get("status"), "FAIL")
        self.assertEqual(pay.get("verdict"), "INVALID-DESIGN")

    def test_sealed_after_first_exposure_fails(self):
        """sealed 2026-07-20 > first exposure 2026-07-14: the design was not
        sealed before the data existed."""
        pay = self.payload("sealed_after_exposure")
        self.assertEqual(self.gate(pay, "design_integrity",
                                   "sealed_after_exposure").get("status"), "FAIL")
        self.assertEqual(pay.get("verdict"), "INVALID-DESIGN")

    def test_other_validity_gates_still_evaluate(self):
        """v1.1: a gate-0 failure must not stop gates 1 and 2 from reporting,
        where their inputs exist. Both these fixtures have a parseable brief."""
        for name in ("missing_metric_col", "sealed_after_exposure"):
            pay = self.payload(name)
            for g in ("srm", "maturity"):
                st = self.gate(pay, g, name).get("status")
                self.assertEqual(
                    st, "PASS",
                    "fixture %s: gate %r has all its inputs (the brief parses, "
                    "arm and date columns exist), so under AMENDMENT 1 it must "
                    "still evaluate and PASS, got %r" % (name, g, st))


if __name__ == "__main__":
    unittest.main()
