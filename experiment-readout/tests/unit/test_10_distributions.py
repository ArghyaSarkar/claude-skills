"""chi2_sf and t_sf -- the hand-rolled distribution functions.

These two are the most likely place for silent wrongness in the whole skill:
there is no scipy, so they are written from scratch, and nothing downstream
will visibly break if they are a few percent off -- an SRM at p=0.0009 simply
gets missed.

Tolerances (stated deliberately, not tuned to pass):
  MID_RTOL   1e-6   for p in [1e-12, 1]. A correct series/continued-fraction
                    implementation lands far inside this. A Wilson-Hilferty or
                    Abramowitz-Stegun style approximation (~1e-3 to 1e-4) will
                    fail, which is the point.
  DEEP_RTOL  1e-3   for p < 1e-12, where catastrophic cancellation is expected
                    to cost digits in any formulation.
  TABLE_RTOL 2e-4   against published critical values quoted to 6-7 sig figs.
  SRM_RTOL   1e-4   AT the SRM decision boundary (chi2=10.827566, dof=1,
                    p=0.001). This is the number the whole gate turns on, so it
                    gets the tightest table-anchored check.

Oracles: exact closed forms where they exist, published tables, and _ref.py.
"""

import math
import unittest

import _ref
from _harness import ImplCase, SRM_ALPHA

MID_RTOL = 1e-6
DEEP_RTOL = 1e-3
TABLE_RTOL = 2e-4
SRM_RTOL = 1e-4


class TestChi2SF(ImplCase):

    def chi2(self):
        return self.func("chi2_sf")

    def test_zero_and_tiny(self):
        f = self.chi2()
        for dof in (1, 2, 3, 5, 10):
            self.assertAlmostEqual(f(0.0, dof), 1.0, places=9,
                                   msg="chi2_sf(0,%d) must be 1.0" % dof)

    def test_dof1_against_exact_erfc(self):
        """dof=1 has the exact closed form erfc(sqrt(x/2))."""
        f = self.chi2()
        for x in (0.001, 0.5, 1.0, 2.0, 3.841459, 6.634897, 10.827566):
            want = math.erfc(math.sqrt(x / 2.0))
            self.assertRelClose(f(x, 1), want, MID_RTOL,
                                "chi2_sf(%g,1) vs erfc:" % x)

    def test_dof1_deep_tail_against_exact_erfc(self):
        f = self.chi2()
        for x in (20.0, 40.0, 60.0, 80.688, 120.0, 240.0):
            want = math.erfc(math.sqrt(x / 2.0))
            tol = MID_RTOL if want >= 1e-12 else DEEP_RTOL
            self.assertRelClose(f(x, 1), want, tol,
                                "chi2_sf(%g,1) deep tail vs erfc:" % x)

    def test_dof2_against_exact_exp(self):
        """dof=2 has the exact closed form exp(-x/2)."""
        f = self.chi2()
        for x in (0.1, 1.0, 5.991465, 9.210340, 13.815511, 30.0, 55.0):
            want = math.exp(-x / 2.0)
            tol = MID_RTOL if want >= 1e-12 else DEEP_RTOL
            self.assertRelClose(f(x, 2), want, tol,
                                "chi2_sf(%g,2) vs exp:" % x)

    def test_published_critical_values(self):
        f = self.chi2()
        for dof, x, p in [
                (1, 3.841459, 0.05), (1, 6.634897, 0.01),
                (2, 5.991465, 0.05), (2, 9.210340, 0.01), (2, 13.815511, 0.001),
                (3, 7.814728, 0.05), (3, 11.344867, 0.01), (3, 16.266236, 0.001),
                (4, 9.487729, 0.05), (4, 18.466827, 0.001),
                (5, 11.070498, 0.05), (5, 20.515006, 0.001),
                (10, 18.307038, 0.05), (10, 29.588298, 0.001),
                (20, 31.410433, 0.05), (20, 45.314744, 0.001),
                (30, 43.772972, 0.05)]:
            self.assertRelClose(f(x, dof), p, TABLE_RTOL,
                                "chi2_sf(%g, dof=%d) published p=%g:" % (x, dof, p))

    def test_srm_decision_boundary_dof1(self):
        """The number the SRM gate turns on. chi2(1) = 10.827566 is the exact
        published 0.001 critical value; a sloppy tail costs a caught SRM."""
        f = self.chi2()
        got = f(10.827566, 1)
        self.assertRelClose(got, SRM_ALPHA, SRM_RTOL,
                            "chi2_sf(10.827566, 1) must be alpha=0.001:")

    def test_srm_boundary_straddle(self):
        """Two 10,000-user splits that straddle alpha=0.001 by construction.

        5165/4835 : chi2 = 2*165^2/5000 = 10.89   -> p = 9.66848e-4  (< 0.001)
        5160/4840 : chi2 = 2*160^2/5000 = 10.24   -> p = 1.37428e-3  (> 0.001)
        A tail that drifts by more than ~30% relative here flips the verdict.
        """
        f = self.chi2()
        p_hi = f(10.89, 1)
        p_lo = f(10.24, 1)
        self.assertRelClose(p_hi, 9.6684828e-4, 1e-4, "chi2_sf(10.89,1):")
        self.assertRelClose(p_lo, 1.3742759e-3, 1e-4, "chi2_sf(10.24,1):")
        self.assertLess(p_hi, SRM_ALPHA,
                        "chi2=10.89 must be BELOW alpha=0.001 (SRM detected)")
        self.assertGreater(p_lo, SRM_ALPHA,
                           "chi2=10.24 must be ABOVE alpha=0.001 (no SRM)")

    def test_real_dataset_chi2(self):
        """The real arena dataset: 6492/5508 of 12000 -> chi2 = 80.688,
        p = 2.6e-19 per the contract's 'chi2~80.7, p~3e-19'."""
        f = self.chi2()
        want = math.erfc(math.sqrt(80.688 / 2.0))
        self.assertRelClose(f(80.688, 1), want, DEEP_RTOL,
                            "chi2_sf(80.688,1) (real dataset):")
        self.assertLess(f(80.688, 1), 1e-15)

    def test_matches_reference_across_grid(self):
        f = self.chi2()
        for dof in (1, 2, 3, 4, 5, 7, 10, 15, 20, 30):
            for x in (0.05, 0.5, 1.0, 2.5, 5.0, 10.0, 15.0, 25.0, 40.0, 70.0):
                want = _ref.chi2_sf(x, dof)
                tol = MID_RTOL if want >= 1e-12 else DEEP_RTOL
                self.assertRelClose(f(x, dof), want, tol,
                                    "chi2_sf(%g,%d) vs reference:" % (x, dof))

    def test_monotone_decreasing_in_x(self):
        f = self.chi2()
        for dof in (1, 2, 5, 10):
            prev = 2.0
            for x in [0.1 * i for i in range(1, 400)]:
                cur = f(x, dof)
                self.assertLessEqual(cur, prev + 1e-15,
                                     "chi2_sf must be non-increasing in x "
                                     "(dof=%d, x=%g)" % (dof, x))
                self.assertGreaterEqual(cur, 0.0)
                self.assertLessEqual(cur, 1.0 + 1e-12)
                prev = cur


class TestTSF(ImplCase):

    def tsf(self):
        return self.func("t_sf")

    def test_at_zero_is_half(self):
        f = self.tsf()
        for dof in (1, 2, 5, 10, 100, 5997.3):
            self.assertRelClose(f(0.0, dof), 0.5, 1e-9,
                                "t_sf(0,%g) must be 0.5:" % dof)

    def test_dof1_against_exact_cauchy(self):
        f = self.tsf()
        for t in (0.1, 0.5, 1.0, 2.0, 3.077684, 6.313752, 12.7062, 63.657):
            want = 0.5 - math.atan(t) / math.pi
            self.assertRelClose(f(t, 1), want, MID_RTOL,
                                "t_sf(%g,1) vs Cauchy closed form:" % t)

    def test_dof2_against_exact_algebraic(self):
        f = self.tsf()
        for t in (0.1, 1.0, 2.919986, 4.302653, 9.9248, 31.599, 100.0):
            want = 0.5 * (1.0 - t / math.sqrt(2.0 + t * t))
            tol = MID_RTOL if want >= 1e-12 else DEEP_RTOL
            self.assertRelClose(f(t, 2), want, tol,
                                "t_sf(%g,2) vs algebraic closed form:" % t)

    def test_published_critical_values(self):
        """Published one-tail t critical values across dof and tail depth,
        including the 0.0005 tail (deep enough to expose a bad tail)."""
        f = self.tsf()
        for dof, t, p in [
                (1, 12.7062, 0.025),
                (2, 4.302653, 0.025), (2, 9.924843, 0.005),
                (3, 3.182446, 0.025), (3, 5.840909, 0.005),
                (5, 2.015048, 0.05), (5, 2.570582, 0.025),
                (5, 4.032143, 0.005), (5, 6.868827, 0.0005),
                (10, 1.812461, 0.05), (10, 2.228139, 0.025),
                (10, 3.169273, 0.005), (10, 4.586894, 0.0005),
                (20, 2.085963, 0.025), (20, 2.845340, 0.005),
                (20, 3.849516, 0.0005),
                (30, 2.042272, 0.025), (30, 2.749996, 0.005),
                (30, 3.645959, 0.0005),
                (60, 2.000298, 0.025), (60, 2.660283, 0.005),
                (100, 1.983972, 0.025),
                (120, 1.979930, 0.025), (120, 2.617421, 0.005)]:
            self.assertRelClose(f(t, dof), p, TABLE_RTOL,
                                "t_sf(%g, dof=%d) published p=%g:" % (t, dof, p))

    def test_deep_tail_matches_reference(self):
        """The deep tail matters: a Welch t of 7+ on n=3000/arm is routine, and
        the SHIP/NO-SHIP call must not hinge on a mangled 1e-13."""
        f = self.tsf()
        for dof, t in [(5, 12.0), (10, 8.0), (30, 6.0), (100, 5.5),
                       (1000, 5.0), (5997.4, 7.15), (11997.9, 3.12)]:
            want = _ref.t_sf(t, dof)
            tol = MID_RTOL if want >= 1e-12 else DEEP_RTOL
            self.assertRelClose(f(t, dof), want, tol,
                                "t_sf(%g,%g) deep tail vs reference:" % (t, dof))

    def test_fractional_dof(self):
        """Welch dof is fractional, so t_sf must accept a float dof and
        interpolate strictly between its integer neighbours."""
        f = self.tsf()
        for dof in (1.5, 2.7, 5.88235294, 6.5, 12.34, 41.7):
            want = _ref.t_sf(2.0, dof)
            self.assertRelClose(f(2.0, dof), want, MID_RTOL,
                                "t_sf(2.0, %g) fractional dof:" % dof)
        lo = f(2.0, 6.0)
        mid = f(2.0, 6.5)
        hi = f(2.0, 7.0)
        self.assertTrue(hi < mid < lo,
                        "t_sf(2.0, dof) must decrease strictly with dof: "
                        "dof=6 -> %.10g, dof=6.5 -> %.10g, dof=7 -> %.10g"
                        % (lo, mid, hi))

    def test_absolute_value_semantics(self):
        """The contract documents t_sf as 'upper tail, |t|', so the sign of t
        must not change the answer."""
        f = self.tsf()
        for dof in (1, 2, 5.88235294, 30, 5997.4):
            for t in (0.7, 2.0, 4.5):
                self.assertRelClose(
                    f(-t, dof), f(t, dof), 1e-12,
                    "t_sf must use |t| (dof=%g, t=%g):" % (dof, t))

    def test_matches_reference_across_grid(self):
        f = self.tsf()
        for dof in (1, 2, 3, 5, 8, 12, 30, 60, 120, 1000):
            for t in (0.05, 0.5, 1.0, 1.96, 2.5, 3.5, 5.0):
                want = _ref.t_sf(t, dof)
                tol = MID_RTOL if want >= 1e-12 else DEEP_RTOL
                self.assertRelClose(f(t, dof), want, tol,
                                    "t_sf(%g,%g) vs reference:" % (t, dof))

    def test_significance_boundary(self):
        """alpha=0.05 two-sided means the one-tail 0.025 boundary must be
        exactly right, or SHIP/INCONCLUSIVE flips."""
        f = self.tsf()
        # z_{0.975}: large dof must converge to 0.025.
        self.assertRelClose(f(1.9599639845, 2_000_000), 0.025, 1e-4,
                            "t_sf(1.95996, huge dof) vs 0.025:")
        # 2*t_sf(t_crit) == 0.05 at the published dof=5997 style value.
        for dof in (10, 30, 100, 5997.4):
            tc = _ref.t_crit_two_sided(0.05, dof)
            self.assertRelClose(2.0 * f(tc, dof), 0.05, 1e-5,
                                "two-sided p at t_crit(dof=%g):" % dof)


if __name__ == "__main__":
    unittest.main()
