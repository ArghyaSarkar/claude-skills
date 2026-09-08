"""Unit tests for the statistical functions in scripts/gates.py.

Every expected value here is either hand-computed (derivation in the
docstring/comment) or produced by _ref.py, an independently written second
method. Nothing is read off the implementation's own output.
"""

import math
import unittest

import _ref
from _harness import (GUARDRAIL_PP, MDE_REL, POWER, SIG_ALPHA, SRM_ALPHA,
                      ImplCase, read_arm)

RTOL = 1e-9        # algebra that should be exact to float precision
P_RTOL = 1e-6      # p-values, which route through the tail functions


# =========================================================================
# srm_chisq
# =========================================================================
class TestSrmChisq(ImplCase):
    """Two-arm chi-squared goodness-of-fit, dof = k-1 = 1, alpha = 0.001.

    For a designed 50/50 with total n, expected = n/2 per arm and
        chi2 = (o_t - n/2)^2/(n/2) + (o_c - n/2)^2/(n/2)
             = 2*d^2/(n/2) where d = |o_t - n/2|.
    """

    RATIO = {"treatment": 0.5, "control": 0.5}

    def call(self, t, c, ratio=None):
        fn = self.func("srm_chisq")
        return fn({"treatment": t, "control": c}, ratio or self.RATIO)

    def test_exact_5050_gives_zero_chi2(self):
        """5000/5000: deviation is 0, so chi2 must be exactly 0 and p exactly 1.
        Any epsilon here means the expected counts are computed wrong."""
        r = self.call(5000, 5000)
        self.assertAlmostEqual(r["chi2"], 0.0, places=12,
                               msg="exact 50/50 must give chi2 == 0")
        self.assertAlmostEqual(r["p_value"], 1.0, places=9,
                               msg="chi2 == 0 must give p == 1")
        self.assertEqual(r["dof"], 1, "two arms -> dof = k-1 = 1")
        self.assertFalse(r["srm_detected"])
        self.assertEqual(r["observed"], {"treatment": 5000, "control": 5000})
        for arm in ("treatment", "control"):
            self.assertAlmostEqual(float(r["expected"][arm]), 5000.0, places=9)

    def test_odd_total_expected_is_half(self):
        """5001 total -> expected 2500.5 per arm, not an integer.
        chi2 for 2501/2500 = 2*(0.5)^2/2500.5 = 0.5/2500.5 = 1.99960e-4."""
        r = self.call(2501, 2500)
        self.assertAlmostEqual(float(r["expected"]["treatment"]), 2500.5, places=9)
        self.assertRelClose(r["chi2"], 0.5 / 2500.5, RTOL, "odd-total chi2:")

    def test_mild_imbalance_does_not_trip_alpha_0001(self):
        """5050/4950 of 10000: chi2 = 2*50^2/5000 = 1.0 exactly, and
        p = erfc(sqrt(0.5)) = 0.3173105. Nowhere near 0.001 -- a gate that
        fires here would block almost every real experiment."""
        r = self.call(5050, 4950)
        self.assertRelClose(r["chi2"], 1.0, RTOL, "mild-imbalance chi2:")
        self.assertRelClose(r["p_value"], math.erfc(math.sqrt(0.5)), P_RTOL,
                            "mild-imbalance p:")
        self.assertGreater(r["p_value"], SRM_ALPHA)
        self.assertFalse(r["srm_detected"],
                         "5050/4950 (p=0.317) must NOT be flagged as SRM")

    def test_clear_imbalance_trips_alpha_0001(self):
        """5400/4600 of 10000: chi2 = 2*400^2/5000 = 64.0 exactly, and
        p = erfc(sqrt(32)) = 1.24419e-15. Unambiguous SRM."""
        r = self.call(5400, 4600)
        self.assertRelClose(r["chi2"], 64.0, RTOL, "clear-imbalance chi2:")
        self.assertRelClose(r["p_value"], math.erfc(math.sqrt(32.0)), 1e-3,
                            "clear-imbalance p:")
        self.assertLess(r["p_value"], SRM_ALPHA)
        self.assertTrue(r["srm_detected"],
                        "5400/4600 (p=1.2e-15) must be flagged as SRM")

    def test_alpha_boundary_straddle(self):
        """A pair that straddles alpha=0.001 by construction, so the gate's
        decision (not just its arithmetic) is pinned.

        5165/4835: chi2 = 2*165^2/5000 = 10.89 -> p = 9.66848e-4 -> DETECTED
        5160/4840: chi2 = 2*160^2/5000 = 10.24 -> p = 1.37428e-3 -> NOT detected
        """
        hi = self.call(5165, 4835)
        lo = self.call(5160, 4840)
        self.assertRelClose(hi["chi2"], 10.89, RTOL, "straddle-hi chi2:")
        self.assertRelClose(lo["chi2"], 10.24, RTOL, "straddle-lo chi2:")
        self.assertRelClose(hi["p_value"], 9.6684828e-4, 1e-4, "straddle-hi p:")
        self.assertRelClose(lo["p_value"], 1.3742759e-3, 1e-4, "straddle-lo p:")
        self.assertTrue(hi["srm_detected"],
                        "5165/4835 (p=9.67e-4 < 0.001) must be an SRM")
        self.assertFalse(lo["srm_detected"],
                         "5160/4840 (p=1.37e-3 > 0.001) must NOT be an SRM")

    def test_alpha_is_a_parameter_and_defaults_to_0001(self):
        """The default must be 0.001, and a caller-supplied alpha must be
        honoured. 5050/4950 (p=0.317) is not an SRM at 0.001 but is at 0.5."""
        fn = self.func("srm_chisq")
        counts = {"treatment": 5050, "control": 4950}
        self.assertFalse(fn(counts, self.RATIO)["srm_detected"])
        self.assertTrue(fn(counts, self.RATIO, alpha=0.5)["srm_detected"])

    def test_real_dataset_split(self):
        """The real arena split 6492/5508 of 12000:
        d = 492, chi2 = 2*492^2/6000 = 80.688, p = erfc(sqrt(40.344)) = 2.64e-19.
        The contract quotes chi2~80.7, p~3e-19."""
        r = self.call(6492, 5508)
        self.assertRelClose(r["chi2"], 80.688, 1e-9, "real-dataset chi2:")
        self.assertRelClose(r["p_value"], math.erfc(math.sqrt(40.344)), 1e-3,
                            "real-dataset p:")
        self.assertTrue(r["srm_detected"])

    def test_unequal_designed_ratio(self):
        """A 90/10 design with a 90/10 observation is NOT an SRM. chi2 must use
        the designed ratio, not an assumed 50/50: expected = 9000/1000, so
        chi2 = 0. If the implementation hardcodes 50/50 this blows up to
        (9000-5000)^2/5000 * 2 = 6400."""
        r = self.call(9000, 1000, {"treatment": 0.9, "control": 0.1})
        self.assertAlmostEqual(r["chi2"], 0.0, places=9,
                               msg="observed 9000/1000 against a designed 90/10 "
                                   "must give chi2 == 0")
        self.assertFalse(r["srm_detected"])

    def test_returns_all_contract_keys(self):
        r = self.call(5050, 4950)
        for k in ("observed", "expected", "chi2", "dof", "p_value",
                  "srm_detected"):
            self.assertIn(k, r, "srm_chisq must return %r" % k)
        self.assertIsInstance(r["srm_detected"], bool)


# =========================================================================
# welch_ttest
# =========================================================================
class TestWelchTTest(ImplCase):
    """Welch (unequal-variance) two-sample t-test. a = treatment, b = control.

    CASE 1 -- equal n, unequal variance, fully hand-computed:
      a = [10,12,14,16,18]  mean 14, SS = 16+4+0+4+16 = 40, s_a^2 = 40/4 = 10
      b = [ 9,10,11,12,13]  mean 11, SS =  4+1+0+1+ 4 = 10, s_b^2 = 10/4 = 2.5
      diff = 3
      s_a^2/n_a = 10/5 = 2.0 ; s_b^2/n_b = 2.5/5 = 0.5
      se   = sqrt(2.5)                                   = 1.58113883008419
      t    = 3/sqrt(2.5)                                 = 1.89736659610103
      dof  = (2.0+0.5)^2 / (2.0^2/4 + 0.5^2/4)
           = 6.25 / (1.0 + 0.0625) = 6.25/1.0625         = 5.88235294117647
      rel_diff = 3/11                                    = 0.272727272727273
      (Pooled Student would give dof = 8, so dof is the discriminator.)

    CASE 2 -- unequal n AND wildly unequal variance:
      a = [0, 20]           mean 10,   s_a^2 = 200,   s_a^2/n_a = 100
      b = [9,10,11,12]      mean 10.5, s_b^2 = 5/3,   s_b^2/n_b = 5/12
      diff = -0.5
      se   = sqrt(100 + 5/12)                            = 10.0208116770
      dof  = (100+5/12)^2 / (100^2/1 + (5/12)^2/3)       = 1.00834485912
      (Pooled Student would give dof = 4.)
    """

    A1 = [10.0, 12.0, 14.0, 16.0, 18.0]
    B1 = [9.0, 10.0, 11.0, 12.0, 13.0]
    A2 = [0.0, 20.0]
    B2 = [9.0, 10.0, 11.0, 12.0]

    def test_case1_hand_computed(self):
        r = self.func("welch_ttest")(self.A1, self.B1)
        self.assertEqual(r["n_a"], 5)
        self.assertEqual(r["n_b"], 5)
        self.assertRelClose(r["mean_a"], 14.0, RTOL, "mean_a:")
        self.assertRelClose(r["mean_b"], 11.0, RTOL, "mean_b:")
        self.assertRelClose(r["diff"], 3.0, RTOL, "diff:")
        self.assertRelClose(r["se"], math.sqrt(2.5), RTOL, "se:")
        self.assertRelClose(r["t"], 3.0 / math.sqrt(2.5), RTOL, "t:")
        self.assertRelClose(r["dof"], 6.25 / 1.0625, 1e-9, "welch dof:")
        self.assertRelClose(r["rel_diff"], 3.0 / 11.0, RTOL, "rel_diff:")

    def test_case1_dof_is_welch_not_pooled(self):
        """dof must be 5.88235..., not the pooled n_a+n_b-2 = 8."""
        r = self.func("welch_ttest")(self.A1, self.B1)
        self.assertNotAlmostEqual(
            r["dof"], 8.0, places=2,
            msg="dof=8 means a POOLED Student test was used, not Welch")

    def test_case1_p_and_ci_against_reference(self):
        r = self.func("welch_ttest")(self.A1, self.B1)
        w = _ref.welch(self.A1, self.B1)
        self.assertRelClose(r["p_value"], w["p_value"], P_RTOL, "p_value:")
        self.assertRelClose(r["ci_low"], w["ci_low"], 1e-6, "ci_low:")
        self.assertRelClose(r["ci_high"], w["ci_high"], 1e-6, "ci_high:")
        self.assertRelClose(r["rel_ci_low"], w["rel_ci_low"], 1e-6, "rel_ci_low:")
        self.assertRelClose(r["rel_ci_high"], w["rel_ci_high"], 1e-6,
                            "rel_ci_high:")

    def test_case1_ci_is_symmetric_about_diff(self):
        """A t-CI is diff +/- t_crit*se, so the midpoint must be diff exactly."""
        r = self.func("welch_ttest")(self.A1, self.B1)
        self.assertRelClose(0.5 * (r["ci_low"] + r["ci_high"]), r["diff"],
                            1e-9, "CI midpoint must equal diff:")

    def test_case1_rel_fields_divide_by_control_mean(self):
        """The contract says rel_* are divided by mean_b (control)."""
        r = self.func("welch_ttest")(self.A1, self.B1)
        self.assertRelClose(r["rel_diff"], r["diff"] / r["mean_b"], 1e-12,
                            "rel_diff must be diff/mean_b:")
        self.assertRelClose(r["rel_ci_low"], r["ci_low"] / r["mean_b"], 1e-12,
                            "rel_ci_low must be ci_low/mean_b:")
        self.assertRelClose(r["rel_ci_high"], r["ci_high"] / r["mean_b"], 1e-12,
                            "rel_ci_high must be ci_high/mean_b:")

    def test_case2_unequal_n_and_variance(self):
        r = self.func("welch_ttest")(self.A2, self.B2)
        self.assertEqual(r["n_a"], 2)
        self.assertEqual(r["n_b"], 4)
        self.assertRelClose(r["mean_a"], 10.0, RTOL, "mean_a:")
        self.assertRelClose(r["mean_b"], 10.5, RTOL, "mean_b:")
        self.assertRelClose(r["diff"], -0.5, RTOL, "diff (negative):")
        self.assertRelClose(r["se"], math.sqrt(100.0 + 5.0 / 12.0), 1e-9, "se:")
        self.assertRelClose(r["dof"], 1.00834485912, 1e-8,
                            "Welch-Satterthwaite dof with unequal n and var:")
        self.assertRelClose(r["rel_diff"], -0.5 / 10.5, RTOL,
                            "rel_diff must be signed:")
        self.assertNotAlmostEqual(
            r["dof"], 4.0, places=2,
            msg="dof=4 means pooled Student was used, not Welch")

    def test_case2_p_against_reference(self):
        r = self.func("welch_ttest")(self.A2, self.B2)
        self.assertRelClose(r["p_value"], _ref.welch(self.A2, self.B2)["p_value"],
                            1e-5, "p_value with dof ~ 1:")

    def test_variance_is_sample_not_population(self):
        """s^2 must use the n-1 denominator. With a = [10,12,14,16,18] the
        population variance is 8 and the sample variance is 10; se would be
        sqrt(8/5 + 2/5) = sqrt(2.0) = 1.41421 instead of sqrt(2.5) = 1.58114."""
        r = self.func("welch_ttest")(self.A1, self.B1)
        self.assertRelClose(r["se"], 1.5811388300841898, 1e-9,
                            "se must use the n-1 (sample) variance:")

    def test_two_sided_p(self):
        """p must be TWO-sided: alpha=0.05 two-sided. For case 1 the one-sided
        p is 0.0537656 and the two-sided is 0.1075312."""
        r = self.func("welch_ttest")(self.A1, self.B1)
        one = _ref.t_sf(abs(r["t"]), r["dof"])
        self.assertRelClose(r["p_value"], 2.0 * one, 1e-6,
                            "p_value must be two-sided (2 * upper tail):")

    def test_zero_difference(self):
        """Identical arms: diff 0, t 0, p 1, and a CI straddling 0."""
        a = [1.0, 2.0, 3.0, 4.0, 5.0]
        r = self.func("welch_ttest")(a, list(a))
        self.assertAlmostEqual(r["diff"], 0.0, places=12)
        self.assertAlmostEqual(r["t"], 0.0, places=12)
        self.assertRelClose(r["p_value"], 1.0, 1e-9, "p at t=0:")
        self.assertLess(r["ci_low"], 0.0)
        self.assertGreater(r["ci_high"], 0.0)

    def test_on_real_fixture_matches_reference(self):
        """End-to-end on the n=3000/arm SHIP fixture: the implementation's
        Welch must agree with the independent reference to 1e-6 relative."""
        a, b = read_arm("ship_clean", "completed_orders_28d")
        r = self.func("welch_ttest")(a, b)
        w = _ref.welch(a, b)
        for k in ("mean_a", "mean_b", "diff", "se", "t", "dof",
                  "rel_diff", "ci_low", "ci_high", "rel_ci_low", "rel_ci_high"):
            self.assertRelClose(r[k], w[k], 1e-9, "ship_clean %s:" % k)
        self.assertRelClose(r["p_value"], w["p_value"], 1e-5,
                            "ship_clean p_value:")

    def test_returns_all_contract_keys(self):
        r = self.func("welch_ttest")(self.A1, self.B1)
        for k in ("n_a", "n_b", "mean_a", "mean_b", "diff", "se", "t", "dof",
                  "p_value", "ci_low", "ci_high", "rel_diff", "rel_ci_low",
                  "rel_ci_high"):
            self.assertIn(k, r, "welch_ttest must return %r" % k)


# =========================================================================
# sample_size_per_arm
# =========================================================================
class TestSampleSizePerArm(ImplCase):
    """n = 2*(z_{alpha/2} + z_{beta})^2 * sd^2 / (mde_rel*mean)^2

    z_{0.975} = 1.9599639845400545
    z_{0.80}  = 0.8416212335729143
    (z_a + z_b)             = 2.8015852181129688
    (z_a + z_b)^2           = 7.848879238604116

    CASE A: mean=1.0, sd=1.0, mde_rel=0.10 -> delta = 0.1
      n = 2 * 7.848879238604116 * 1.0 / 0.01 = 1569.7758477208232 -> 1570
    CASE B: mean=2.0, sd=1.5, mde_rel=0.03 -> delta = 0.06
      n = 2 * 7.848879238604116 * 2.25 / 0.0036 = 9811.099667936363 -> 9812
    """

    def test_case_a(self):
        n = self.func("sample_size_per_arm")(1.0, 1.0, 0.10)
        self.assertEqual(int(n), n, "sample_size_per_arm must return an int")
        self.assertEqual(int(n), 1570,
                         "ceil(1569.7758) == 1570; got %r" % n)

    def test_case_b(self):
        n = self.func("sample_size_per_arm")(2.0, 1.5, 0.03)
        self.assertEqual(int(n), 9812,
                         "ceil(9811.0997) == 9812; got %r" % n)

    def test_rounds_up_not_down(self):
        """A required n must never be rounded DOWN -- that silently
        under-powers the rerun. Both cases have fractional exact values."""
        fn = self.func("sample_size_per_arm")
        self.assertGreaterEqual(fn(1.0, 1.0, 0.10),
                                _ref.sample_size_per_arm(1.0, 1.0, 0.10))
        self.assertGreaterEqual(fn(2.0, 1.5, 0.03),
                                _ref.sample_size_per_arm(2.0, 1.5, 0.03))

    def test_scaling_laws(self):
        """Analytic invariants that hold for any correct implementation:
        halving the MDE quadruples n; doubling the sd quadruples n; scaling
        mean and sd together leaves n unchanged (n depends on the CV only)."""
        fn = self.func("sample_size_per_arm")
        base = fn(2.0, 1.0, 0.04)
        self.assertAlmostEqual(fn(2.0, 1.0, 0.02) / float(base), 4.0, delta=0.01,
                               msg="halving mde_rel must quadruple n")
        self.assertAlmostEqual(fn(2.0, 2.0, 0.04) / float(base), 4.0, delta=0.01,
                               msg="doubling sd must quadruple n")
        self.assertAlmostEqual(fn(20.0, 10.0, 0.04) / float(base), 1.0,
                               delta=0.01,
                               msg="n depends on sd/mean only (scale-invariant)")

    def test_alpha_and_power_are_parameters(self):
        """Tightening alpha or raising power must increase n."""
        fn = self.func("sample_size_per_arm")
        base = fn(2.0, 1.0, 0.03)
        self.assertGreater(fn(2.0, 1.0, 0.03, alpha=0.01), base,
                           "alpha=0.01 must need more users than alpha=0.05")
        self.assertGreater(fn(2.0, 1.0, 0.03, power=0.95), base,
                           "power=0.95 must need more users than power=0.80")

    def test_defaults_are_contract_defaults(self):
        """Defaults must be alpha=0.05, power=0.80."""
        fn = self.func("sample_size_per_arm")
        self.assertEqual(fn(2.0, 1.0, 0.03),
                         fn(2.0, 1.0, 0.03, alpha=SIG_ALPHA, power=POWER))

    def test_matches_reference_on_control_arm_of_fixture(self):
        """Derived from the ship_clean control arm, the same way power.py must:
        baseline mean/sd estimated from control, MDE 3% relative."""
        _t, c = read_arm("ship_clean", "completed_orders_28d")
        m = sum(c) / len(c)
        sd = math.sqrt(sum((x - m) ** 2 for x in c) / (len(c) - 1))
        want = _ref.sample_size_per_arm(m, sd, MDE_REL)
        got = self.func("sample_size_per_arm")(m, sd, MDE_REL)
        self.assertEqual(got, math.ceil(want),
                         "expected ceil(%.6f) = %d, got %r"
                         % (want, math.ceil(want), got))


# =========================================================================
# duration_days
# =========================================================================
class TestDurationDays(ImplCase):
    """exposure_days = ceil(n_per_arm / daily_users_per_arm)
       total_days    = exposure_days + metric_window_days
    """

    def test_exact_division(self):
        """1000 users at 500/day = 2 exposure days; + a 26-day window = 28 days
        total = exactly 4 weeks, so total_weeks is unambiguous here."""
        r = self.func("duration_days")(1000, 500, 26)
        self.assertEqual(r["exposure_days"], 2)
        self.assertEqual(r["maturation_days"], 26)
        self.assertEqual(r["total_days"], 28)
        self.assertRelClose(float(r["total_weeks"]), 4.0, 1e-9, "total_weeks:")

    def test_ceils_exposure_days(self):
        """9812 users at 500/day is 19.624 days, which must round UP to 20 --
        rounding down under-recruits."""
        r = self.func("duration_days")(9812, 500, 28)
        self.assertEqual(r["exposure_days"], 20,
                         "ceil(9812/500) = 20, got %r" % r["exposure_days"])
        self.assertEqual(r["maturation_days"], 28)
        self.assertEqual(r["total_days"], 48)
        # CONTRACT AMBIGUITY: total_weeks is not specified as exact or ceiled.
        # 48/7 = 6.857. Accept either the exact ratio or a ceil to 7.
        tw = float(r["total_weeks"])
        self.assertTrue(abs(tw - 48.0 / 7.0) < 0.02 or tw == 7.0,
                        "total_weeks should be 48/7 = 6.857 or ceil -> 7, "
                        "got %r" % r["total_weeks"])

    def test_one_extra_user_adds_a_day(self):
        r0 = self.func("duration_days")(1000, 500, 28)
        r1 = self.func("duration_days")(1001, 500, 28)
        self.assertEqual(r0["exposure_days"], 2)
        self.assertEqual(r1["exposure_days"], 3,
                         "1001 users at 500/day must need 3 days, not 2")

    def test_total_is_exposure_plus_window(self):
        for n, daily, w in [(5000, 700, 28), (12000, 900, 7), (300, 25, 14)]:
            r = self.func("duration_days")(n, daily, w)
            self.assertEqual(r["total_days"],
                             r["exposure_days"] + r["maturation_days"],
                             "total_days must be exposure + maturation "
                             "(n=%d daily=%d w=%d)" % (n, daily, w))
            self.assertEqual(r["maturation_days"], w)
            self.assertEqual(r["exposure_days"], math.ceil(n / float(daily)))

    def test_returns_all_contract_keys(self):
        r = self.func("duration_days")(1000, 500, 28)
        for k in ("exposure_days", "maturation_days", "total_days",
                  "total_weeks"):
            self.assertIn(k, r, "duration_days must return %r" % k)


# =========================================================================
# parse_metric_window
# =========================================================================
class TestParseMetricWindow(ImplCase):
    """Contract: window W parsed from the metric name via regex _(\\d+)d$."""

    def test_windowed_name(self):
        self.assertEqual(self.func("parse_metric_window")("completed_orders_28d"),
                         28)

    def test_other_windows(self):
        fn = self.func("parse_metric_window")
        self.assertEqual(fn("gmv_7d"), 7)
        self.assertEqual(fn("retention_1d"), 1)
        self.assertEqual(fn("orders_365d"), 365)
        self.assertEqual(fn("a_b_c_14d"), 14)

    def test_unwindowed_name_returns_none(self):
        fn = self.func("parse_metric_window")
        self.assertIsNone(fn("completed_orders"),
                          "an unwindowed metric name must return None, not 0")

    def test_near_misses_return_none(self):
        """The regex is anchored at the end and needs the _<digits>d shape."""
        fn = self.func("parse_metric_window")
        for name in ("orders_28days", "orders_28", "orders28d", "orders_d",
                     "orders_2.8d", "d28_orders"):
            self.assertIsNone(fn(name),
                              "%r does not match _(\\d+)d$ and must give None"
                              % name)

    def test_scenario_brief_parenthetical(self):
        """SCENARIO.md's brief writes the metric as
        'completed_orders_28d (mean per user)'. The literal contract regex is
        end-anchored, so this does NOT match and must return None -- the
        parenthetical has to be stripped by the brief parser, not here.
        Flagged as a contract ambiguity; asserted to the contract as written."""
        self.assertIsNone(
            self.func("parse_metric_window")("completed_orders_28d (mean per user)"),
            "the end-anchored regex _(\\d+)d$ cannot match a trailing "
            "parenthetical; stripping belongs to the brief parser")


if __name__ == "__main__":
    unittest.main()
