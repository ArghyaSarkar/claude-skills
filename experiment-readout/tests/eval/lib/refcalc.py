"""Independent reference statistics for GOLDEN ANSWER verification.

WHY THIS EXISTS AND WHY IT DOES NOT IMPORT scripts/gates.py
-----------------------------------------------------------
A golden answer computed by the code under test is not a golden answer; it is a
tautology. Every number in cases/*/golden.json is verified by THIS module, which
is a deliberately separate, deliberately simpler implementation:

  * normal approximation (math.erf) instead of an exact Student-t survival fn
  * Wilson-Hilferty / direct erf approximation for the chi-squared upper tail
  * plain two-pass arithmetic for means and variances

Because it is an approximation, it is only trustworthy for WIDE margins. That is
a design constraint on the eval cases, not a defect here: every case is
constructed so its verdict is unambiguous (p < 0.005 or p > 0.20, lift at least
1.5x or at most 0.5x the MDE). verify_goldens.py enforces those margins, so a
disagreement between this module and the skill's gates.py is a real signal
rather than floating-point noise.

stdlib only. Python 3.9 compatible.
"""

import math

Z_975 = 1.959963984540054   # two-sided alpha=0.05
Z_80 = 0.8416212335729143   # power=0.80


def norm_sf(z):
    """Upper tail of the standard normal."""
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def two_sided_p_from_z(z):
    return 2.0 * norm_sf(abs(z))


def mean(xs):
    return sum(xs) / float(len(xs))


def var_sample(xs):
    n = len(xs)
    if n < 2:
        return 0.0
    m = mean(xs)
    return sum((x - m) ** 2 for x in xs) / float(n - 1)


def sd_sample(xs):
    return math.sqrt(var_sample(xs))


def welch_z(a, b):
    """Welch two-sample comparison using a NORMAL approximation.

    a = treatment, b = control. Returns the fields the eval needs to pin a
    verdict, using z rather than t. For the sample sizes in these cases
    (n >= 1200 per arm) the difference between z and t is far below the
    margins the cases are built to.
    """
    na, nb = len(a), len(b)
    ma, mb = mean(a), mean(b)
    va, vb = var_sample(a), var_sample(b)
    se = math.sqrt(va / na + vb / nb)
    diff = ma - mb
    z = diff / se if se > 0 else float("inf")
    lo = diff - Z_975 * se
    hi = diff + Z_975 * se
    return {
        "n_a": na, "n_b": nb,
        "mean_a": ma, "mean_b": mb,
        "diff": diff, "se": se, "z": z,
        "p_value": two_sided_p_from_z(z),
        "ci_low": lo, "ci_high": hi,
        "rel_diff": diff / mb if mb else float("nan"),
        "rel_ci_low": lo / mb if mb else float("nan"),
        "rel_ci_high": hi / mb if mb else float("nan"),
    }


def chi2_sf_1dof(x):
    """Upper tail of chi-squared with 1 dof. Exact: P = 2*(1-Phi(sqrt(x)))."""
    if x <= 0:
        return 1.0
    return 2.0 * norm_sf(math.sqrt(x))


def srm_chisq(counts, ratio):
    """Two-arm chi-squared goodness of fit. counts/ratio keyed by arm name."""
    total = float(sum(counts.values()))
    rsum = float(sum(ratio.values()))
    expected = {k: total * (ratio[k] / rsum) for k in ratio}
    chi2 = sum((counts[k] - expected[k]) ** 2 / expected[k] for k in expected)
    return {
        "observed": dict(counts),
        "expected": expected,
        "chi2": chi2,
        "dof": len(counts) - 1,
        "p_value": chi2_sf_1dof(chi2),
    }


def sample_size_per_arm(baseline_mean, baseline_sd, mde_rel):
    """n = 2*(z_{a/2}+z_b)^2 * sd^2 / (mde_rel*mean)^2 -- matches the contract."""
    delta = mde_rel * baseline_mean
    if delta <= 0:
        raise ValueError("mde_rel*mean must be > 0")
    n = 2.0 * (Z_975 + Z_80) ** 2 * (baseline_sd ** 2) / (delta ** 2)
    return int(math.ceil(n))


def duration_days(n_per_arm, daily_users_per_arm, metric_window_days):
    exposure = int(math.ceil(n_per_arm / float(daily_users_per_arm)))
    total = exposure + metric_window_days
    return {
        "exposure_days": exposure,
        "maturation_days": metric_window_days,
        "total_days": total,
        "total_weeks": round(total / 7.0, 1),
    }


def pearson(xs, ys):
    """Pearson correlation. Used for the truncation-gradient diagnostic."""
    n = len(xs)
    if n < 3:
        return 0.0
    mx, my = mean(xs), mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return 0.0
    return num / (dx * dy)
