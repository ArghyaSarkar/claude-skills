"""The maths behind the gates, and nothing else.

This environment has no scipy and no numpy, so the statistics are hand-written here
using only `math` and `re`. Nothing in this file reads a file, prints, or keeps state:
give a function the same inputs and it returns the same answer, every time. That keeps
run_readout.py (which does the deciding) small and keeps this file easy to test.

Known answers, used as a smoke test by the block at the bottom of the file:
  chi2_sf(3.841, 1) ~= 0.05      chi2_sf(6.635, 1) ~= 0.01
  t_sf(1.96, 1e6)   ~= 0.025     t_sf(2.776, 4)    ~= 0.025
"""

import math
import re

__all__ = [
    "chi2_sf",
    "t_sf",
    "norm_ppf",
    "t_ppf",
    "srm_chisq",
    "welch_ttest",
    "holm_bonferroni",
    "sample_size_per_arm",
    "duration_days",
    "parse_metric_window",
    "pearson_r",
    "truncation_gradient",
]

_TINY = 1e-300
_EPS = 1e-15
_MAXIT = 5000


# --------------------------------------------------------------------------
# Building block for the chi-squared p-value.
#
# The chi-squared tail has no closed form, so it is computed from the "incomplete
# gamma function". That function needs two different algorithms: a sum that
# converges quickly for small inputs, and a continued fraction for large ones.
# chi2_sf picks whichever one is in its comfortable range.
# --------------------------------------------------------------------------
def _gamma_p_series(a, x):
    """Lower incomplete gamma P(a,x), by adding up a series. Use when x < a+1."""
    ap = a
    total = 1.0 / a
    delta = total
    for _ in range(_MAXIT):
        ap += 1.0
        delta *= x / ap
        total += delta
        if abs(delta) < abs(total) * _EPS:
            break
    return total * math.exp(-x + a * math.log(x) - math.lgamma(a))


def _gamma_q_cf(a, x):
    """Upper incomplete gamma Q(a,x), by continued fraction (Lentz's method).

    Use when x >= a+1, where the series above converges too slowly.
    """
    b = x + 1.0 - a
    c = 1.0 / _TINY
    d = 1.0 / b if b != 0 else 1.0 / _TINY
    h = d
    for i in range(1, _MAXIT):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < _TINY:
            d = _TINY
        c = b + an / c
        if abs(c) < _TINY:
            c = _TINY
        d = 1.0 / d
        step = d * c
        h *= step
        if abs(step - 1.0) < _EPS:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def chi2_sf(x, dof):
    """How unlikely a chi-squared statistic this big is, if nothing is wrong.

    Returns P(X > x) for X ~ chi2(dof) -- the area in the far right tail. This is the
    p-value the SRM gate compares against its alpha. Returns 1.0 for x <= 0 (a
    statistic of zero is the least surprising result there is).
    """
    dof = float(dof)
    if dof <= 0:
        raise ValueError("dof must be positive")
    x = float(x)
    if x <= 0:
        return 1.0
    if math.isinf(x):
        return 0.0
    a = dof / 2.0
    xx = x / 2.0
    if xx < a + 1.0:
        return max(0.0, min(1.0, 1.0 - _gamma_p_series(a, xx)))
    return max(0.0, min(1.0, _gamma_q_cf(a, xx)))


# --------------------------------------------------------------------------
# Building block for the t-test p-value: the incomplete beta function, computed
# by continued fraction the same way as the gamma pair above.
# --------------------------------------------------------------------------
def _betacf(a, b, x):
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < _TINY:
        d = _TINY
    d = 1.0 / d
    h = d
    for m in range(1, _MAXIT):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < _TINY:
            d = _TINY
        c = 1.0 + aa / c
        if abs(c) < _TINY:
            c = _TINY
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < _TINY:
            d = _TINY
        c = 1.0 + aa / c
        if abs(c) < _TINY:
            c = _TINY
        d = 1.0 / d
        step = d * c
        h *= step
        if abs(step - 1.0) < _EPS:
            break
    return h


def _betainc_reg(a, b, x):
    """Incomplete beta I_x(a, b) -- the shape the t-distribution tail is built from."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(
        math.lgamma(a + b)
        - math.lgamma(a)
        - math.lgamma(b)
        + a * math.log(x)
        + b * math.log(1.0 - x)
    )
    if x < (a + 1.0) / (a + b + 2.0):
        return max(0.0, min(1.0, front * _betacf(a, b, x) / a))
    return max(0.0, min(1.0, 1.0 - front * _betacf(b, a, 1.0 - x) / b))


def t_sf(t, dof):
    """How unlikely a t-statistic this far from zero is, if nothing changed.

    Returns P(T > |t|), one tail. The two-sided p-value the lift gate reports is
    2 * t_sf(|t|, dof). The sign of t is ignored on purpose -- "how far from zero" is
    the question, not "which way".

    With very many degrees of freedom the t-distribution is indistinguishable from a
    normal one, so we switch to the normal formula: safer arithmetic, and the same
    answer to six or more decimal places.
    """
    dof = float(dof)
    if dof <= 0:
        raise ValueError("dof must be positive")
    t = abs(float(t))
    if math.isinf(t):
        return 0.0
    if dof >= 1e5:
        return 0.5 * math.erfc(t / math.sqrt(2.0))
    x = dof / (dof + t * t)
    return _betainc_reg(dof / 2.0, 0.5, x) / 2.0


# --------------------------------------------------------------------------
# The same questions asked backwards: given a probability, which cut-off produces
# it? Both are solved by binary search (halve the interval, 300 times), which is
# slower than a fitted formula but needs no hard-coded approximation constants --
# so there is nothing here that can silently be a little bit wrong.
# --------------------------------------------------------------------------
def norm_ppf(p):
    """The z-value with probability p below it, on a standard normal curve."""
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0,1)")
    lo, hi = -40.0, 40.0
    for _ in range(300):
        mid = (lo + hi) / 2.0
        if 0.5 * math.erfc(-mid / math.sqrt(2.0)) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def t_ppf(p, dof):
    """The t-value with probability p below it. Used for confidence-interval widths."""
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0,1)")
    if p == 0.5:
        return 0.0
    target_upper = 1.0 - p if p > 0.5 else p
    lo, hi = 0.0, 1.0
    while t_sf(hi, dof) > target_upper and hi < 1e12:
        hi *= 2.0
    for _ in range(300):
        mid = (lo + hi) / 2.0
        if t_sf(mid, dof) > target_upper:
            lo = mid
        else:
            hi = mid
    t = (lo + hi) / 2.0
    return t if p > 0.5 else -t


# --------------------------------------------------------------------------
# GATE 1 — sample ratio mismatch
# --------------------------------------------------------------------------
def srm_chisq(counts, ratio, alpha=0.001):
    """Did the arms come out the size the design asked for?

    Compares how many users each arm actually got against how many the designed ratio
    says it should have got, and returns how surprising the gap is.

    counts: {arm: n_users} -- what happened.
    ratio:  {arm: designed_share} -- what was designed. Any positive scale works;
            the shares are normalised here, so 50/50 and 1/1 mean the same thing.
    dof = k - 1, where k is the number of designed arms.
    Returns {observed, expected, chi2, dof, p_value, srm_detected}.

    The expected counts come from `ratio`. Passing in a ratio derived from `counts`
    would make chi2 ~0 no matter how broken the split is -- see the warning on
    run_readout.parse_assignment.
    """
    if not ratio:
        raise ValueError("designed ratio is empty")
    keys = list(ratio.keys())
    for k in counts:
        if k not in ratio:
            keys.append(k)
    total_n = float(sum(counts.get(k, 0) for k in keys))
    denom = float(sum(v for v in ratio.values() if v is not None))
    if denom <= 0:
        raise ValueError("designed ratio must sum to a positive number")

    observed = {}
    expected = {}
    chi2 = 0.0
    for k in keys:
        o = float(counts.get(k, 0))
        e = total_n * (float(ratio.get(k, 0.0)) / denom)
        observed[k] = o
        expected[k] = e
        if e > 0:
            chi2 += (o - e) ** 2 / e
        elif o > 0:
            chi2 = float("inf")

    dof = max(1, len(ratio) - 1)
    if total_n <= 0:
        return {
            "observed": observed,
            "expected": expected,
            "chi2": None,
            "dof": dof,
            "p_value": None,
            "srm_detected": False,
        }
    p = 0.0 if math.isinf(chi2) else chi2_sf(chi2, dof)
    return {
        "observed": observed,
        "expected": expected,
        "chi2": chi2,
        "dof": dof,
        "p_value": p,
        "srm_detected": bool(p < alpha),
    }


# --------------------------------------------------------------------------
# GATE 4 — lift
# --------------------------------------------------------------------------
def _mean(xs):
    return sum(xs) / float(len(xs))


def _var(xs):
    # Sample variance: divide by n-1, not n. With n in the thousands the difference
    # is tiny, but it is the correct estimator and the tests check for it.
    n = len(xs)
    m = _mean(xs)
    return sum((x - m) ** 2 for x in xs) / float(n - 1)


def welch_ttest(a, b, alpha=0.05):
    """Compare two groups' averages without assuming they are equally spread out.

    Welch's version of the t-test. The plain version assumes both groups have the same
    variance; Welch does not, which is why the degrees of freedom come out fractional.
    a = treatment, b = control, so a positive `diff` means treatment was higher.

    The `rel_*` fields are the same quantities divided by mean_b, the control mean --
    i.e. expressed as a fraction of the baseline, which is what the MDE is measured in.

    Returns n_a, n_b, mean_a, mean_b, diff, se, t, dof, p_value,
            ci_low, ci_high, rel_diff, rel_ci_low, rel_ci_high.
    """
    a = [float(x) for x in a]
    b = [float(x) for x in b]
    if len(a) < 2 or len(b) < 2:
        raise ValueError("each arm needs at least 2 observations")

    n_a, n_b = len(a), len(b)
    mean_a, mean_b = _mean(a), _mean(b)
    va, vb = _var(a), _var(b)
    diff = mean_a - mean_b
    se = math.sqrt(va / n_a + vb / n_b)

    if se == 0.0:
        t = 0.0 if diff == 0 else math.copysign(float("inf"), diff)
        dof = float(n_a + n_b - 2)
        p = 1.0 if diff == 0 else 0.0
        ci_low = ci_high = diff
    else:
        t = diff / se
        num = (va / n_a + vb / n_b) ** 2
        den = (va / n_a) ** 2 / (n_a - 1) + (vb / n_b) ** 2 / (n_b - 1)
        dof = num / den if den > 0 else float(n_a + n_b - 2)
        p = 2.0 * t_sf(t, dof)
        crit = t_ppf(1.0 - alpha / 2.0, dof)
        ci_low = diff - crit * se
        ci_high = diff + crit * se

    def rel(v):
        return v / mean_b if mean_b != 0 else None

    return {
        "n_a": n_a,
        "n_b": n_b,
        "mean_a": mean_a,
        "mean_b": mean_b,
        "diff": diff,
        "se": se,
        "t": t,
        "dof": dof,
        "p_value": min(1.0, p),
        "ci_low": ci_low,
        "ci_high": ci_high,
        "rel_diff": rel(diff),
        "rel_ci_low": rel(ci_low),
        "rel_ci_high": rel(ci_high),
    }


# --------------------------------------------------------------------------
# GATE 4 helper — multiplicity
# --------------------------------------------------------------------------
def holm_bonferroni(pvalues, alpha=0.05):
    """Correct a set of p-values for the fact that you asked more than one question.

    Test one hypothesis at alpha=0.05 and you accept a 5% chance of calling nothing
    something. Test k of them and that 5% applies to each one separately, so the chance
    that AT LEAST ONE comes back a false positive is 1 - (1-alpha)^k -- 9.75% at k=2,
    14.26% at k=3. Holm-Bonferroni puts that back where it was: it sorts the p-values
    smallest first and holds the i-th one (0-indexed) to alpha / (k - i), so the smallest
    faces the strictest bar and the largest faces plain alpha.

    The stop is the part people get wrong. Once one hypothesis fails its threshold,
    every LARGER p-value is retained too, whatever its own threshold says -- the
    procedure is a ladder, and it ends at the first rung you cannot reach.

    pvalues: a list, in whatever order the caller wants its answers back in.
    Returns one dict per input, IN INPUT ORDER, carrying:
        index      position in the input list
        rank       0-based position after sorting ascending (ties keep input order)
        p_value    the p-value as given
        threshold  alpha / (k - rank), the bar this hypothesis had to clear
        significant  whether it cleared it AND no smaller p-value had already failed
        k, alpha   the family size and family-wise alpha the correction used
    With k == 1 every threshold is alpha and the answer is p < alpha, so passing a single
    p-value through this function changes nothing.
    """
    ps = [float(p) for p in pvalues]
    k = len(ps)
    if k == 0:
        return []
    if not 0.0 < float(alpha) < 1.0:
        raise ValueError("alpha must be in (0,1)")
    alpha = float(alpha)
    order = sorted(range(k), key=lambda i: (ps[i], i))
    out = [None] * k
    still_rejecting = True
    for rank, i in enumerate(order):
        threshold = alpha / float(k - rank)
        if still_rejecting and ps[i] < threshold:
            significant = True
        else:
            still_rejecting = False
            significant = False
        out[i] = {
            "index": i,
            "rank": rank,
            "p_value": ps[i],
            "threshold": threshold,
            "significant": significant,
            "k": k,
            "alpha": alpha,
        }
    return out


# --------------------------------------------------------------------------
# GATE 2 helper — truncation gradient
# --------------------------------------------------------------------------
def pearson_r(xs, ys):
    """How tightly two lists move together, from -1 to +1.

    Returns None when there is nothing to measure: fewer than 3 points, or one of the
    lists never changes.
    """
    n = len(xs)
    if n < 3 or n != len(ys):
        return None
    mx, my = _mean(xs), _mean(ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


# What counts as "flat". The number that decides the branch is the late-vs-early
# MAGNITUDE, never the correlation: when the cohort means are nearly equal, a
# correlation has no scale to it and is mostly noise, so it cannot carry a decision.
GRADIENT_FLAT_BAND = 0.02       # |late-vs-early| below this reads as flat


def truncation_gradient(cohort_means, flat_band=GRADIENT_FLAT_BAND):
    """Does the metric behave like a counter that has not finished counting yet?

    A 28-day metric measured too early MUST read lower for users who were exposed
    later, because they have had fewer days to accumulate anything. So look at the
    average by exposure date and see whether it slopes down. If it does not, but the
    calendar says it must, the column itself is suspect -- and that is a more useful
    finding than "immature", because waiting does not fix it.

    cohort_means: list of (cohort_key, mean) in exposure-date order, pooled ACROSS
    ARMS on purpose. A trend over time that ignores which arm a user was in contains
    no treatment-vs-control comparison, so it is safe to compute and report even when
    the conclusion gates are suppressed.

    early_mean / late_mean are absolute metric LEVELS, and they are returned on
    purpose. The caller must keep them in the JSON payload and out of any prose.
    That split looks inconsistent, so here is why it is not:
      * Suppression exists to stop CONCLUSIONS ABOUT THE TREATMENT EFFECT reaching a
        reader. A pooled cohort mean compares no arm with any other, so it is a
        data-quality reading, not a conclusion. It is not the thing being suppressed.
      * The JSON is there to be audited, not sent to the PM. Remove the levels and
        nobody can re-check why this was called flat instead of truncated.
      * Prose is where a bare level does the damage, because a reader treats any
        number near an experiment as "the result".
    So: levels stay in the payload, never in the rendered report. Do not "tidy" them
    away.

    Returns the trend evidence only. The caller reads it against the timeline and
    decides which of the two stories it tells.
    """
    pairs = [(k, float(v)) for k, v in cohort_means if v is not None]
    n = len(pairs)
    out = {
        "n_cohorts": n,
        "first_cohort": pairs[0][0] if pairs else None,
        "last_cohort": pairs[-1][0] if pairs else None,
        "early_mean": None,
        "late_mean": None,
        "late_vs_early_delta": None,
        "late_vs_early_rel": None,
        "corr": None,
        "corr_p_value": None,
        "corr_agrees_with_magnitude": None,
        "flat_band": flat_band,
        "decided_by": "late_vs_early_rel magnitude vs flat_band (r is context only)",
        "direction": "insufficient_cohorts",
    }
    # Fewer than 3 cohorts: refuse to name a direction. The <3 bar is chosen here, not
    # copied from somewhere else.
    #   n == 2: a straight line goes exactly through any two points, so the correlation
    #           is +/-1 whatever the data and tells you nothing. Each "half" is also a
    #           single cohort, and a trend drawn from two points is not a trend.
    #   n == 3: still one cohort per half, but the magnitude -- the number that actually
    #           decides -- is now comparing two different cohorts, and the branch never
    #           depends on the correlation. So 3 is the first size where the decider
    #           means something.
    # Code that specifically leans on the correlation may reasonably want n >= 4 before
    # trusting its p-value (at n == 3 there is only one degree of freedom). That is a
    # stricter bar on the supporting statistic, not on this refusal; both can be true.
    if n < 3:
        return out
    means = [v for _k, v in pairs]
    half = n // 2
    early = _mean(means[:half])
    late = _mean(means[n - half:])
    out["early_mean"] = early
    out["late_mean"] = late
    out["late_vs_early_delta"] = late - early
    out["late_vs_early_rel"] = (late - early) / early if early else None
    r = pearson_r(list(range(n)), means)
    out["corr"] = r
    if r is not None and abs(r) < 1.0:
        t = r * math.sqrt((n - 2) / (1.0 - r * r))
        out["corr_p_value"] = 2.0 * t_sf(t, n - 2)
    elif r is not None:
        out["corr_p_value"] = 0.0
    rel = out["late_vs_early_rel"]
    if rel is None:
        out["direction"] = "undefined"
    elif rel <= -flat_band:
        out["direction"] = "late_lower"
    elif rel >= flat_band:
        out["direction"] = "late_higher"
    else:
        out["direction"] = "flat"
    if r is not None and rel is not None and out["direction"] != "flat":
        out["corr_agrees_with_magnitude"] = bool((r < 0) == (rel < 0))
    return out


# --------------------------------------------------------------------------
# power / duration planning
# --------------------------------------------------------------------------
def sample_size_per_arm(baseline_mean, baseline_sd, mde_rel, alpha=0.05, power=0.80):
    """How many users per arm are needed to see an effect of size mde_rel.

    Two arms, two-sided test. The MDE arrives as a fraction of the baseline mean, so it
    is turned into an absolute effect first. Note the square in the denominator: the
    smaller the effect you want to detect, the faster the cost grows -- halve the MDE
    and n goes up fourfold.

    n = 2 * (z_{alpha/2} + z_{power})^2 * sd^2 / (mde_rel * mean)^2
    """
    baseline_mean = float(baseline_mean)
    baseline_sd = float(baseline_sd)
    mde_rel = float(mde_rel)
    if baseline_sd < 0:
        raise ValueError("baseline_sd must be >= 0")
    delta = mde_rel * baseline_mean
    if delta == 0:
        raise ValueError("absolute effect size (mde_rel * baseline_mean) is zero")
    z_a = norm_ppf(1.0 - alpha / 2.0)
    z_b = norm_ppf(power)
    n = 2.0 * (z_a + z_b) ** 2 * baseline_sd ** 2 / (delta ** 2)
    return int(math.ceil(n))


def duration_days(n_per_arm, daily_users_per_arm, metric_window_days):
    """Calendar cost: sign users up, then wait for the metric window to close.

    The window is added once at the end rather than per user, because the last person
    enrolled is the one who sets the finish line.

    exposure_days   = ceil(n_per_arm / daily_users_per_arm)
    maturation_days = metric_window_days
    total_days      = exposure_days + maturation_days
    total_weeks     = ceil(total_days / 7)   (whole weeks, rounded up)
    """
    n_per_arm = float(n_per_arm)
    daily = float(daily_users_per_arm)
    window = int(metric_window_days or 0)
    if daily <= 0:
        raise ValueError("daily_users_per_arm must be positive")
    if n_per_arm < 0:
        raise ValueError("n_per_arm must be >= 0")
    exposure_days = int(math.ceil(n_per_arm / daily))
    total = exposure_days + window
    return {
        "exposure_days": exposure_days,
        "maturation_days": window,
        "total_days": total,
        "total_weeks": int(math.ceil(total / 7.0)),
        "total_weeks_exact": round(total / 7.0, 2),
    }


_WINDOW_RE = re.compile(r"_(\d+)d$")


def parse_metric_window(metric_name):
    """Pull the N out of a metric named like 'completed_orders_28d' -> 28.

    Returns None when the name carries no window.

    The pattern only matches at the very END of the name, as the contract requires, so
    'completed_orders_28d (mean per user)' returns None. Trimming that trailing bracket
    is the brief parser's job (run_readout.parse_metric_field), not this function's.
    """
    if not metric_name:
        return None
    m = _WINDOW_RE.search(str(metric_name).strip())
    return int(m.group(1)) if m else None


# --------------------------------------------------------------------------
if __name__ == "__main__":  # quick check that the hand-written distributions still agree
                            # with textbook values. Run this file directly to see it.
    checks = [
        ("chi2_sf(3.841,1)", chi2_sf(3.841, 1), 0.05),
        ("chi2_sf(6.635,1)", chi2_sf(6.635, 1), 0.01),
        ("chi2_sf(5.991,2)", chi2_sf(5.991, 2), 0.05),
        ("chi2_sf(11.345,3)", chi2_sf(11.345, 3), 0.01),
        ("t_sf(1.96,1e6)", t_sf(1.96, 1e6), 0.025),
        ("t_sf(2.776,4)", t_sf(2.776, 4), 0.025),
        ("t_sf(12.706,1)", t_sf(12.706, 1), 0.025),
        ("t_sf(1.6449,1e9)", t_sf(1.6449, 1e9), 0.05),
        ("t_sf(0,10)", t_sf(0, 10), 0.5),
    ]
    ok = True
    for name, got, want in checks:
        good = abs(got - want) < 5e-4
        ok = ok and good
        print("%-22s got=%.6f want=%.6f %s" % (name, got, want, "OK" if good else "BAD"))
    holm = holm_bonferroni([0.01, 0.03, 0.04])
    holm_ok = [h["significant"] for h in holm] == [True, False, False]
    ok = ok and holm_ok
    print("holm([.01,.03,.04])   thresholds=%s significant=%s %s"
          % (["%.5f" % h["threshold"] for h in holm],
             [h["significant"] for h in holm], "OK" if holm_ok else "BAD"))
    print("norm_ppf(0.975)=%.6f (1.959964)" % norm_ppf(0.975))
    print("norm_ppf(0.80) =%.6f (0.841621)" % norm_ppf(0.80))
    print("t_ppf(0.975,4) =%.6f (2.776445)" % t_ppf(0.975, 4))
    print("ALL OK" if ok else "FAILURES PRESENT")
