#!/usr/bin/env python3
"""How many users, and how many weeks, would it take to detect the brief's MDE?

This is the planning script. run_readout.py reads an experiment that already ran;
this one sizes the experiment you would need.

usage: python3 power.py --results R.csv --brief B.yaml [--mde 0.03] [--daily N] [--json]

The baseline average and spread are measured from the CONTROL arm of the results file,
because control is the "nothing changed" group. How fast users arrive is read off the
exposure dates. The total duration is sign-up days PLUS the metric's own window, since
a 28-day metric cannot be read until 28 days after a user was exposed.
"""

import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gates import duration_days, sample_size_per_arm  # noqa: E402
from run_readout import (  # noqa: E402
    SIG_ALPHA,
    POWER,
    _pick_control,
    _to_float,
    load_results,
    parse_brief,
    parse_date,
    parse_rate,
)


def estimate(results_path, brief_path, mde_override=None, daily_override=None,
             alpha=SIG_ALPHA, power=POWER):
    res = load_results(results_path)
    arms = []
    if res["arm_col"]:
        for r in res["rows"]:
            a = (r.get(res["arm_col"]) or "").strip()
            if a and a not in arms:
                arms.append(a)
    brief = parse_brief(brief_path, observed_arms=arms)

    pm = brief["primary_metric"]
    if not pm or pm not in res["columns"]:
        raise ValueError("primary metric %r is not a usable column in %s (columns: %s)"
                         % (pm, os.path.basename(results_path), res["columns"]))
    if not res["arm_col"]:
        raise ValueError("no arm column in %s" % os.path.basename(results_path))

    ctrl = _pick_control({a: 1 for a in arms}, brief["designed_ratio"] or {})
    by_arm = {}
    dates_by_arm = {}
    for r in res["rows"]:
        a = (r.get(res["arm_col"]) or "").strip()
        v = _to_float(r.get(pm))
        if not a or v is None:
            continue
        by_arm.setdefault(a, []).append(v)
        d = parse_date(r.get(res["date_col"])) if res["date_col"] else None
        if d:
            dates_by_arm.setdefault(a, set()).add(d)

    vals = by_arm.get(ctrl) or []
    if len(vals) < 2:
        raise ValueError("control arm %r has fewer than 2 usable observations" % ctrl)
    mean = sum(vals) / float(len(vals))
    var = sum((x - mean) ** 2 for x in vals) / float(len(vals) - 1)
    sd = math.sqrt(var)

    mde = mde_override if mde_override is not None else brief["mde"]
    if mde is None:
        raise ValueError("no MDE in the brief and no --mde given — cannot size the test")

    window = brief["metric_window_days"]
    if daily_override:
        daily = float(daily_override)
        daily_src = "--daily flag"
    else:
        # No --daily given, so measure the arrival rate from this file: for each arm,
        # users divided by the number of distinct days it saw exposures.
        per_arm_rates = []
        for a, ds in dates_by_arm.items():
            if ds:
                per_arm_rates.append(len(by_arm.get(a, [])) / float(len(ds)))
        daily = sum(per_arm_rates) / len(per_arm_rates) if per_arm_rates else 0.0
        daily_src = "observed: mean over arms of users / distinct exposure days"
    if daily <= 0:
        raise ValueError("could not derive observed daily users per arm — pass --daily")

    # n first, then how long it takes to enrol that many, then the window wait.
    n = sample_size_per_arm(mean, sd, mde, alpha=alpha, power=power)
    dur = duration_days(n, daily, window or 0)
    observed_n = {a: len(v) for a, v in by_arm.items()}

    return {
        "experiment": brief["experiment"] or os.path.basename(results_path),
        "primary_metric": pm,
        "metric_window_days": window,
        "control_arm": ctrl,
        "baseline_mean": mean,
        "baseline_sd": sd,
        "baseline_cv": (sd / mean) if mean else None,
        "mde_rel": mde,
        "mde_absolute": mde * mean,
        "alpha": alpha,
        "power": power,
        "n_per_arm_required": n,
        "n_total_required": n * max(2, len(observed_n) or 2),
        "observed_n_per_arm": observed_n,
        "daily_users_per_arm": daily,
        "daily_users_source": daily_src,
        "exposure_days": dur["exposure_days"],
        "maturation_days": dur["maturation_days"],
        "total_days": dur["total_days"],
        "total_weeks": dur["total_weeks"],
        "shortfall_per_arm": {a: max(0, n - c) for a, c in observed_n.items()},
        "notes": [
            "n per arm = 2*(z_a/2 + z_b)^2 * sd^2 / (mde_rel*mean)^2 — two-sample, two-sided.",
            "sd is estimated from the control arm of THIS data; a rerun's sd may differ.",
            "total_days = exposure_days + maturation_days; an N-day metric is unreadable "
            "until N days after the last exposure.",
        ] + ([
            "if the maturity gate failed on this file, these baseline values come from an "
            "incomplete %d-day window: sd is understated, so treat the required n as a FLOOR "
            "and re-estimate from a mature cohort." % window
        ] if window else []),
    }


def render(p):
    L = []
    L.append("SAMPLE SIZE & DURATION — %s" % p["experiment"])
    L.append("")
    L.append("INPUTS (from the brief + the control arm of this data)")
    L.append("  primary metric        %s (%s-day window)" % (p["primary_metric"],
                                                             p["metric_window_days"]))
    L.append("  baseline mean (ctrl)  %.6g" % p["baseline_mean"])
    L.append("  baseline sd   (ctrl)  %.6g%s" % (p["baseline_sd"],
             ("  (cv %.2f)" % p["baseline_cv"]) if p["baseline_cv"] else ""))
    L.append("  MDE                   %.4g%% relative = %+.6g absolute"
             % (100 * p["mde_rel"], p["mde_absolute"]))
    L.append("  alpha / power         %s (two-sided) / %s" % (p["alpha"], p["power"]))
    L.append("  observed daily users  %.1f per arm  [%s]" % (p["daily_users_per_arm"],
                                                             p["daily_users_source"]))
    L.append("")
    L.append("REQUIRED")
    L.append("  n per arm             %d" % p["n_per_arm_required"])
    L.append("  n total               %d" % p["n_total_required"])
    L.append("  enrolment (exposure)  %d days" % p["exposure_days"])
    L.append("  maturation wait       %d days (the %s-day metric window)"
             % (p["maturation_days"], p["metric_window_days"]))
    L.append("  TOTAL                 %d days (~%d weeks)" % (p["total_days"], p["total_weeks"]))
    L.append("")
    L.append("VS WHAT THIS RUN HAD")
    for a, c in sorted(p["observed_n_per_arm"].items()):
        L.append("  %-12s n=%d   shortfall %d" % (a, c, p["shortfall_per_arm"][a]))
    L.append("")
    for n in p["notes"]:
        L.append("  note: %s" % n)
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Sample size and duration for a brief's MDE")
    ap.add_argument("--results", required=True)
    ap.add_argument("--brief", default=None)
    ap.add_argument("--mde", default=None, help="override, e.g. 3%% or 0.03")
    ap.add_argument("--daily", default=None, type=float,
                    help="override daily users per arm")
    ap.add_argument("--alpha", default=SIG_ALPHA, type=float)
    ap.add_argument("--power", default=POWER, type=float)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if not os.path.exists(args.results):
        sys.stderr.write("input error: results file not found: %s\n" % args.results)
        return 1
    mde = None
    if args.mde:
        mde, _ = parse_rate(args.mde, default_relative=True)
        if mde is None:
            sys.stderr.write("input error: cannot parse --mde %r\n" % args.mde)
            return 1
    try:
        p = estimate(args.results, args.brief, mde_override=mde, daily_override=args.daily,
                     alpha=args.alpha, power=args.power)
    except Exception as exc:
        sys.stderr.write("input error: %s\n" % exc)
        return 1
    sys.stdout.write((json.dumps(p, indent=2, default=str) if args.json else render(p)) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
