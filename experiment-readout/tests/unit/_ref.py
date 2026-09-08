"""Independent reference implementations of the distribution functions.

These exist so the suite can check the skill's hand-rolled `chi2_sf` / `t_sf`
against a SECOND, independently-derived method rather than against the skill's
own output.  They are the classic Numerical Recipes continued-fraction
algorithms for the regularized incomplete gamma and incomplete beta functions,
written from the recurrences -- not copied from, or calling into, the
implementation under test.

The reference itself is validated in test_distributions.py against
  * exact closed forms  (chi2 dof=1 -> erfc, chi2 dof=2 -> exp,
                         t dof=1 -> atan, t dof=2 -> algebraic), and
  * published critical-value tables,
so it is not taken on trust either.

stdlib only.
"""

import math

_EPS = 3.0e-16
_FPMIN = 1.0e-300
_MAXIT = 500


# ---------------------------------------------------------------- gamma ----

def _gser(a, x):
    """Regularized LOWER incomplete gamma P(a, x) by series. Good for x < a+1."""
    ap = a
    s = 1.0 / a
    d = s
    for _ in range(_MAXIT):
        ap += 1.0
        d *= x / ap
        s += d
        if abs(d) < abs(s) * _EPS:
            break
    return s * math.exp(-x + a * math.log(x) - math.lgamma(a))


def _gcf(a, x):
    """Regularized UPPER incomplete gamma Q(a, x) by the modified Lentz
    continued fraction. Good for x >= a+1."""
    b = x + 1.0 - a
    c = 1.0 / _FPMIN
    d = 1.0 / b
    h = d
    for i in range(1, _MAXIT + 1):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < _FPMIN:
            d = _FPMIN
        c = b + an / c
        if abs(c) < _FPMIN:
            c = _FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < _EPS:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def gammaq(a, x):
    """Regularized upper incomplete gamma Q(a, x) = 1 - P(a, x)."""
    if x <= 0.0:
        return 1.0
    if x < a + 1.0:
        return 1.0 - _gser(a, x)
    return _gcf(a, x)


def chi2_sf(x, dof):
    """Upper tail of the chi-squared distribution: P(X > x)."""
    if x <= 0.0:
        return 1.0
    return gammaq(dof / 2.0, x / 2.0)


# ----------------------------------------------------------------- beta ----

def _betacf(a, b, x):
    """Continued fraction for the incomplete beta function (Lentz)."""
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < _FPMIN:
        d = _FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, _MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < _FPMIN:
            d = _FPMIN
        c = 1.0 + aa / c
        if abs(c) < _FPMIN:
            c = _FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < _FPMIN:
            d = _FPMIN
        c = 1.0 + aa / c
        if abs(c) < _FPMIN:
            c = _FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < _EPS:
            break
    return h


def betainc(a, b, x):
    """Regularized incomplete beta I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    bt = math.exp(lbeta + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def t_sf(t, dof):
    """Upper tail of Student's t: P(T > t). Handles negative t and float dof."""
    if dof <= 0:
        raise ValueError("dof must be > 0")
    x = dof / (dof + t * t)
    half = 0.5 * betainc(dof / 2.0, 0.5, x)
    return half if t >= 0.0 else 1.0 - half


def t_sf_abs(t, dof):
    """Upper tail at |t| -- the one-sided p the contract's t_sf describes."""
    return t_sf(abs(t), dof)


def t_two_sided_p(t, dof):
    return 2.0 * t_sf_abs(t, dof)


def t_ppf(p, dof):
    """Inverse: value t such that P(T > t) == p, by bisection on t_sf."""
    if not (0.0 < p < 1.0):
        raise ValueError("p must be in (0,1)")
    lo, hi = -1.0e6, 1.0e6
    for _ in range(300):
        mid = 0.5 * (lo + hi)
        if t_sf(mid, dof) > p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def t_crit_two_sided(alpha, dof):
    """Two-sided critical value: t such that P(|T| > t) == alpha."""
    return t_ppf(alpha / 2.0, dof)


# ------------------------------------------------------- welch reference ----

def welch(a, b, alpha=0.05):
    """Independent Welch two-sample t-test, used as the oracle for the
    implementation's welch_ttest. a = treatment, b = control."""
    na, nb = len(a), len(b)
    ma = sum(a) / na
    mb = sum(b) / nb
    va = sum((x - ma) ** 2 for x in a) / (na - 1)
    vb = sum((x - mb) ** 2 for x in b) / (nb - 1)
    sa, sb = va / na, vb / nb
    se = math.sqrt(sa + sb)
    diff = ma - mb
    t = diff / se
    dof = (sa + sb) ** 2 / (sa * sa / (na - 1) + sb * sb / (nb - 1))
    p = t_two_sided_p(t, dof)
    tc = t_crit_two_sided(alpha, dof)
    return {
        "n_a": na, "n_b": nb, "mean_a": ma, "mean_b": mb,
        "diff": diff, "se": se, "t": t, "dof": dof, "p_value": p,
        "ci_low": diff - tc * se, "ci_high": diff + tc * se,
        "rel_diff": diff / mb,
        "rel_ci_low": (diff - tc * se) / mb,
        "rel_ci_high": (diff + tc * se) / mb,
    }


# --------------------------------------------------------- normal quantile --

# Published two-sided/one-sided standard-normal quantiles used by the
# sample-size formula in the contract.
Z_ALPHA_HALF_05 = 1.9599639845400545   # z_{0.975}
Z_POWER_80 = 0.8416212335729143        # z_{0.80}


def sample_size_per_arm(mean, sd, mde_rel, z_a=Z_ALPHA_HALF_05, z_b=Z_POWER_80):
    """n = 2*(z_a2 + z_b)^2 * sd^2 / (mde_rel*mean)^2, as an exact float
    (callers apply their own ceil)."""
    delta = mde_rel * mean
    return 2.0 * (z_a + z_b) ** 2 * sd * sd / (delta * delta)
