"""Validate the independent reference (_ref.py) BEFORE it is used as an oracle.

These tests never touch the implementation. If they fail, the oracle is broken
and every downstream expected value is suspect, so they run first.

Two kinds of check:
  1. against EXACT closed forms that exist for special cases --
       chi2 dof=1  : P(X>x) = erfc(sqrt(x/2))
       chi2 dof=2  : P(X>x) = exp(-x/2)
       t    dof=1  : P(T>t) = 1/2 - atan(t)/pi          (Cauchy)
       t    dof=2  : P(T>t) = 1/2 * (1 - t/sqrt(2+t^2))
  2. against PUBLISHED critical-value tables (6-7 significant figures).
"""

import math
import unittest

import _ref

EXACT_RTOL = 1e-12      # vs closed forms
TABLE_RTOL = 2e-4       # vs 6-7 sig-fig published critical values


def rel(got, want):
    return abs(got - want) / abs(want)


class TestReferenceClosedForms(unittest.TestCase):

    def test_chi2_dof1_matches_erfc(self):
        for x in (1e-6, 0.5, 1.0, 3.841459, 6.634897, 10.827566, 20.0,
                  40.0, 64.0, 80.688, 240.0):
            want = math.erfc(math.sqrt(x / 2.0))
            self.assertLessEqual(rel(_ref.chi2_sf(x, 1), want), EXACT_RTOL,
                                 "chi2_sf(%g,1)" % x)

    def test_chi2_dof2_matches_exp(self):
        for x in (0.1, 1.0, 5.991465, 13.815511, 30.0, 100.0):
            want = math.exp(-x / 2.0)
            self.assertLessEqual(rel(_ref.chi2_sf(x, 2), want), EXACT_RTOL,
                                 "chi2_sf(%g,2)" % x)

    def test_t_dof1_matches_cauchy(self):
        for t in (0.1, 0.5, 1.0, 3.077684, 6.313752, 12.7062, 63.657):
            want = 0.5 - math.atan(t) / math.pi
            self.assertLessEqual(rel(_ref.t_sf(t, 1), want), 1e-10,
                                 "t_sf(%g,1)" % t)

    def test_t_dof2_matches_algebraic(self):
        for t in (0.1, 1.0, 2.919986, 4.302653, 9.9248, 31.599):
            want = 0.5 * (1.0 - t / math.sqrt(2.0 + t * t))
            self.assertLessEqual(rel(_ref.t_sf(t, 2), want), 1e-10,
                                 "t_sf(%g,2)" % t)

    def test_t_symmetry_and_median(self):
        for dof in (1, 2, 5, 10.5, 100, 5997.3):
            self.assertAlmostEqual(_ref.t_sf(0.0, dof), 0.5, places=12)
            for t in (0.3, 1.5, 4.0):
                self.assertAlmostEqual(_ref.t_sf(-t, dof),
                                       1.0 - _ref.t_sf(t, dof), places=12)


class TestReferencePublishedTables(unittest.TestCase):

    CHI2 = [  # (dof, critical value, upper-tail p)
        (1, 3.841459, 0.05), (1, 6.634897, 0.01), (1, 10.827566, 0.001),
        (2, 5.991465, 0.05), (2, 9.210340, 0.01), (2, 13.815511, 0.001),
        (3, 7.814728, 0.05), (3, 11.344867, 0.01), (3, 16.266236, 0.001),
        (4, 9.487729, 0.05), (4, 18.466827, 0.001),
        (5, 11.070498, 0.05), (5, 20.515006, 0.001),
        (10, 18.307038, 0.05), (10, 29.588298, 0.001),
        (20, 31.410433, 0.05), (20, 45.314744, 0.001),
        (30, 43.772972, 0.05),
    ]

    T = [  # (dof, critical value, one-tail p)
        (1, 12.7062, 0.025), (2, 4.302653, 0.025), (3, 3.182446, 0.025),
        (5, 2.570582, 0.025), (5, 2.015048, 0.05), (5, 6.868827, 0.0005),
        (10, 2.228139, 0.025), (10, 1.812461, 0.05), (10, 4.586894, 0.0005),
        (20, 2.085963, 0.025), (20, 3.849516, 0.0005),
        (30, 2.042272, 0.025), (30, 3.645959, 0.0005),
        (60, 2.000298, 0.025), (100, 1.983972, 0.025), (120, 1.979930, 0.025),
    ]

    def test_chi2_table(self):
        for dof, x, p in self.CHI2:
            self.assertLessEqual(rel(_ref.chi2_sf(x, dof), p), TABLE_RTOL,
                                 "chi2 dof=%d x=%g" % (dof, x))

    def test_t_table(self):
        for dof, t, p in self.T:
            self.assertLessEqual(rel(_ref.t_sf(t, dof), p), TABLE_RTOL,
                                 "t dof=%d t=%g" % (dof, t))

    def test_t_quantile_roundtrips(self):
        for dof in (1, 2, 5, 5.88235294, 10, 30, 5997.4):
            for alpha in (0.05, 0.01, 0.001):
                tc = _ref.t_crit_two_sided(alpha, dof)
                self.assertLessEqual(
                    rel(2.0 * _ref.t_sf(tc, dof), alpha), 1e-9,
                    "t_crit_two_sided(%g,%g)" % (alpha, dof))

    def test_large_dof_approaches_normal(self):
        # z_{0.975} = 1.9599639845; t with huge dof must agree to ~1e-5.
        self.assertLessEqual(rel(_ref.t_sf(1.9599639845, 5_000_000), 0.025), 1e-5)


class TestReferenceWelch(unittest.TestCase):
    """The Welch oracle, checked against fully hand-computed algebra.

    a = [10,12,14,16,18]: mean 14, deviations -4,-2,0,2,4, SS=40, s^2=40/4=10
    b = [ 9,10,11,12,13]: mean 11, deviations -2,-1,0,1,2, SS=10, s^2=10/4=2.5
    se   = sqrt(10/5 + 2.5/5) = sqrt(2.5)          = 1.5811388300842
    t    = 3 / sqrt(2.5)                            = 1.8973665961010
    dof  = (2+0.5)^2 / (2^2/4 + 0.5^2/4)
         = 6.25 / (1 + 0.0625) = 6.25/1.0625        = 5.8823529411765
    """

    def test_hand_computed(self):
        w = _ref.welch([10.0, 12.0, 14.0, 16.0, 18.0],
                       [9.0, 10.0, 11.0, 12.0, 13.0])
        self.assertAlmostEqual(w["mean_a"], 14.0, places=12)
        self.assertAlmostEqual(w["mean_b"], 11.0, places=12)
        self.assertAlmostEqual(w["diff"], 3.0, places=12)
        self.assertAlmostEqual(w["se"], math.sqrt(2.5), places=12)
        self.assertAlmostEqual(w["t"], 3.0 / math.sqrt(2.5), places=12)
        self.assertAlmostEqual(w["dof"], 6.25 / 1.0625, places=10)
        self.assertAlmostEqual(w["rel_diff"], 3.0 / 11.0, places=12)


if __name__ == "__main__":
    unittest.main()
