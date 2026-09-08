#!/usr/bin/env python3
"""Read out an experiment through five checks, in a fixed order.

usage: python3 run_readout.py --results R.csv --brief B.yaml [--asof YYYY-MM-DD] [--json]

The checks are called gates, and they come in two kinds.

Gates 0-2 are VALIDITY gates. They ask whether the data can answer the question at all:
was the design written down first, did the arms come out the size the design asked for,
and has the metric finished counting? All three always evaluate and are always reported,
so a second defect is never hidden behind the first. The verdict is named by the FIRST
failing validity gate.

Gates 3-4 are CONCLUSION gates. They are the ones that produce a number. If any validity
gate failed, both are NOT_RUN and no lift / p-value / CI / guardrail number appears
anywhere in the output.

Exit 0 means the run produced a verdict, including the INVALID ones — a failed gate is a
finding, not a crash. Exit 1 means the input itself could not be used.
"""

import argparse
import csv
import datetime
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gates import (  # noqa: E402
    holm_bonferroni,
    parse_metric_window,
    srm_chisq,
    truncation_gradient,
    welch_ttest,
)

SRM_ALPHA = 0.001
SIG_ALPHA = 0.05
POWER = 0.80
GUARDRAIL_DEFAULT_THRESHOLD = 0.01

GATE_ORDER = ["design_integrity", "srm", "maturity", "guardrail", "lift"]
BLOCKING_GATES = ["design_integrity", "srm", "maturity"]
VERDICT_FOR_BLOCKING_FAIL = {
    "design_integrity": "INVALID-DESIGN",
    "srm": "INVALID-SRM",
    "maturity": "INVALID-IMMATURE",
}

ARM_COL_CANDIDATES = ["arm", "variant", "group", "bucket", "treatment_group", "cell"]
DATE_COL_PATTERNS = [
    r"^exposure_date",
    r"exposure.*date",
    r"date.*exposure",
    r"^assignment_date",
    r"^enroll.*date",
    r"^first_seen",
    r"^date$",
]
ASOF_COL_PATTERNS = [r"^as_?of", r"observed.*date", r"snapshot.*date", r"extract.*date"]
CONTROL_NAMES = ("control", "ctrl", "holdout", "baseline", "a", "off")


# ==========================================================================
# Reading the brief — the sealed design.
#
# The brief is a small YAML file, and this environment has no YAML library, so what
# follows reads the one shape we actually need: flat `key: value` lines. Anything more
# complicated is skipped and recorded as a problem, never guessed at.
# ==========================================================================
def _strip_value(raw):
    v = raw.strip()
    if v.startswith("#"):
        return ""
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1]
    return v.strip()


def read_yaml_flat(path):
    """Read the flat `key: value` lines out of a YAML file. Returns (values, problems)."""
    out, errors = {}, []
    try:
        with open(path, "r") as fh:
            lines = fh.read().splitlines()
    except Exception as exc:  # unreadable / missing
        return out, ["cannot read brief: %s" % exc]
    for ln in lines:
        s = ln.strip()
        if not s or s.startswith("#") or s in ("---", "..."):
            continue
        if s.startswith("- "):
            errors.append("list item ignored: %s" % s)
            continue
        if ":" not in s:
            errors.append("unparseable line ignored: %s" % s)
            continue
        key, _, val = s.partition(":")
        key = key.strip().lstrip("-").strip().lower()
        if not key:
            continue
        out[key] = _strip_value(val)
    return out, errors


def _first_number(text):
    m = re.search(r"-?\d+(?:\.\d+)?", text or "")
    return float(m.group(0)) if m else None


def parse_rate(text, default_relative=True):
    """Turn a rate written in words into a number, and say whether it is relative.

    '3%' -> (0.03, relative)    '1pp' -> (0.01, absolute)
    '0.03' -> (0.03, relative)  '3'   -> (0.03, relative)

    'pp' means percentage points, which is a step of that size rather than a fraction of
    something else, so it comes back absolute. Everything else follows default_relative.
    """
    if text is None:
        return None, None
    t = str(text).strip().lower()
    num = _first_number(t)
    if num is None:
        return None, None
    is_relative = default_relative
    if "pp" in t or "percentage point" in t or "absolute" in t or "abs " in t:
        value = num / 100.0
        is_relative = False
    elif "%" in t or "percent" in t:
        value = num / 100.0
    elif abs(num) < 1.0:
        value = num
    else:
        value = num / 100.0
    if "relative" in t:
        is_relative = True
    return value, is_relative


def parse_guardrail_threshold(text):
    """Pull the guardrail's threshold out of the way the brief words it.

    'cancel_rate (must not worsen by >1pp)' -> 0.01

    The search wants a number with a unit attached (pp, %, bps), and looks inside the
    brackets first. That anchoring matters: without it, a guardrail named `cancel_rate_7d`
    would hand back 7 as its threshold.
    """
    t = str(text or "").lower()
    m_par = re.search(r"\(([^)]*)\)", t)
    scope = m_par.group(1) if m_par else t
    m = re.search(r"(\d+(?:\.\d+)?)\s*(pp\b|percentage points?|%|percent|bps)", scope)
    if m:
        num = float(m.group(1))
        return (num / 10000.0 if m.group(2) == "bps" else num / 100.0), "brief (declared)"
    m = re.search(r"[><=]+\s*(\d+(?:\.\d+)?)", scope)
    if m:
        num = float(m.group(1))
        if num < 1:
            return num, "brief (declared)"
        return num / 100.0, ("ASSUMED reading of '>%g' as %g percentage points — the brief gives "
                             "no unit; confirm with the brief author" % (num, num))
    return None, None


def parse_assignment(text, observed_arms, declared_arms=None):
    """Work out what share of users each arm was designed to get.

    '50/50 user-level' -> ({treatment: 0.5, control: 0.5}, unit, notes, source)

    Which share belongs to which arm: if the assignment text (or a brief `arms:` key)
    names the arms, that order wins. Otherwise the first share maps to the treatment arm
    and the last to the control arm.

    DO NOT "IMPROVE" THIS INTO INFERRING SHARES FROM THE OBSERVED COUNTS.
    The expected ratio comes only from the brief, or from a loudly-labelled equal-split
    default. Deriving the expected ratio from the observed arm counts drives the SRM
    chi-squared statistic to ~0 by construction: the gate could then never fail, and would
    print a reassuring "srm PASS" on data with a broken split. Arm LABELS may come from the
    data (they are names, not proportions); SHARES may not.
    """
    notes = []
    unit = None
    t = (text or "").strip()
    low = t.lower()
    for u in ("user-level", "user level", "session-level", "session level",
              "device-level", "cookie-level", "account-level"):
        if u in low:
            unit = u.replace(" level", "-level")
            break
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", low.split("user")[0] or low)]
    if not nums:
        nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", low)]
    nums = [n for n in nums if n > 0]

    if declared_arms:
        arms = list(declared_arms)
        unknown = [a for a in observed_arms if a not in arms]
        if unknown:
            notes.append("arm label(s) %s in the data are not declared in the brief (%s)"
                         % (unknown, arms))
    else:
        arms = order_arms(observed_arms)
        named = [(low.find(str(a).lower()), a) for a in observed_arms
                 if str(a).lower() and low.find(str(a).lower()) >= 0]
        if len(named) == len(observed_arms) and len(named) > 1:
            arms = [a for _, a in sorted(named)]
            notes.append("arm order taken from the assignment text: %s" % ", ".join(map(str, arms)))
    if not nums:
        if not arms:
            return (None, unit, ["no assignment ratio in brief and no arms in data"],
                    "unavailable")
        share = 1.0 / len(arms)
        return ({a: share for a in arms}, unit,
                ["assignment ratio absent from brief — ASSUMED equal split across %d arms "
                 "(arm names taken from the data; shares are NOT inferred from observed counts)"
                 % len(arms)],
                "ASSUMED equal split (the brief declares no ratio)")
    total = sum(nums)
    shares = [n / total for n in nums]
    if arms and len(shares) != len(arms):
        notes.append("brief declares %d arms, data has %d (%s)"
                     % (len(shares), len(arms), ", ".join(arms)))
        if len(shares) < len(arms):
            arms = arms[: len(shares)]
        else:
            shares = shares[: len(arms)] if arms else shares
    if not arms:
        arms = ["treatment", "control"][: len(shares)]
    ratio = {}
    for i, a in enumerate(arms):
        ratio[a] = shares[i] if i < len(shares) else 0.0
    if len(set(round(s, 6) for s in shares)) > 1:
        notes.append("unequal designed ratio — first share mapped to '%s', last to '%s'; "
                     "confirm arm order with the brief author" % (arms[0], arms[-1]))
    return ratio, unit, notes, "brief (declared)"


def order_arms(arms):
    """Put the treatment arms first, in alphabetical order, and the control arm last."""
    arms = list(arms)
    treat = sorted(a for a in arms if str(a).strip().lower() not in CONTROL_NAMES)
    ctrl = sorted(a for a in arms if str(a).strip().lower() in CONTROL_NAMES)
    return treat + ctrl


def parse_metric_field(text):
    """Split a metric field into the column name and the note written beside it.

    'completed_orders_28d (mean per user)' -> ('completed_orders_28d', 'mean per user')
    """
    if not text:
        return None, None
    t = str(text).strip()
    head = t.split("(")[0].strip()
    note = None
    m = re.search(r"\(([^)]*)\)", t)
    if m:
        note = m.group(1).strip()
    col = head.split()[0].strip().strip(",;") if head else None
    return col, note


def parse_date(text):
    if not text:
        return None
    t = str(text).strip()
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", t)
    if not m:
        return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def parse_brief(path, observed_arms=None):
    """Read the brief into one tidy dict describing the design.

    A missing or unreadable brief is a finding, not a crash, so this never raises. It puts
    what went wrong in `errors`, leaves `present` False, and lets GATE 0 turn that into the
    verdict.
    """
    d = {
        "path": path,
        "present": False,
        "raw": {},
        "errors": [],
        "notes": [],
        "experiment": None,
        "primary_metric": None,
        "primary_metric_note": None,
        "metric_window_days": None,
        "mde": None,
        "mde_is_relative": True,
        "mde_raw": None,
        "assignment_raw": None,
        "assignment_unit": None,
        "designed_ratio": None,
        "guardrail_metric": None,
        "guardrail_threshold": None,
        "guardrail_worse_direction": "increase",
        "guardrail_raw": None,
        "sealed": None,
    }
    if not path or not os.path.exists(path):
        d["errors"].append("brief file not found: %s" % (path or "<none>"))
        return d
    raw, errs = read_yaml_flat(path)
    d["raw"] = raw
    d["errors"].extend(errs)
    if not raw:
        d["errors"].append("brief is empty or unparseable")
        return d
    d["present"] = True

    d["experiment"] = raw.get("experiment") or raw.get("name") or raw.get("experiment_name")

    pm_raw = raw.get("primary_metric") or raw.get("metric") or raw.get("primary")
    col, note = parse_metric_field(pm_raw)
    d["primary_metric"] = col
    d["primary_metric_note"] = note
    d["metric_window_days"] = parse_metric_window(col or pm_raw)

    d["mde_raw"] = raw.get("mde") or raw.get("minimum_detectable_effect") or raw.get("mde_rel")
    mde, rel = parse_rate(d["mde_raw"], default_relative=True)
    d["mde"] = mde
    if rel is not None:
        d["mde_is_relative"] = rel

    d["assignment_raw"] = raw.get("assignment") or raw.get("split") or raw.get("allocation")
    declared = raw.get("arms") or raw.get("variants")
    declared_arms = [a.strip() for a in re.split(r"[,/|]", declared) if a.strip()] if declared else None
    d["declared_arms"] = declared_arms
    ratio, unit, notes, ratio_source = parse_assignment(d["assignment_raw"],
                                                        observed_arms or [],
                                                        declared_arms=declared_arms)
    d["ratio_source"] = ratio_source
    d["designed_ratio"] = ratio
    d["assignment_unit"] = unit
    d["notes"].extend(notes)

    g_raw = raw.get("guardrail") or raw.get("guardrails") or raw.get("guardrail_metric")
    d["guardrail_raw"] = g_raw
    gcol, _gnote = parse_metric_field(g_raw)
    d["guardrail_metric"] = gcol
    d["guardrail_threshold_source"] = None
    if g_raw:
        gt, gsrc = parse_guardrail_threshold(g_raw)
        if gt is None:
            gt, gsrc = GUARDRAIL_DEFAULT_THRESHOLD, ("ASSUMED %gpp default — no threshold could "
                                                     "be read from the brief text"
                                                     % (GUARDRAIL_DEFAULT_THRESHOLD * 100))
        d["guardrail_threshold"] = abs(gt)
        d["guardrail_threshold_source"] = gsrc
        low = str(g_raw).lower()
        if re.search(r"not\s+(drop|decrease|fall|reduce|go below|dip)", low) or "at least" in low:
            d["guardrail_worse_direction"] = "decrease"
    d["sealed"] = parse_date(raw.get("sealed") or raw.get("sealed_at") or raw.get("sealed_date"))
    return d


# ==========================================================================
# Reading the results file
# ==========================================================================
def _match_col(columns, patterns):
    """Return the first column whose name matches one of these name patterns."""
    low = {c.lower().strip(): c for c in columns}
    for p in patterns:
        for lc, orig in low.items():
            if re.search(p, lc):
                return orig
    return None


def load_results(path):
    """Read the results CSV, and work out which columns hold what.

    Columns are found by what they are named, not by position, so a file with the right
    contents under different headers still works. Raises if the file cannot be opened.
    """
    with open(path, "r", newline="") as fh:
        reader = csv.DictReader(fh)
        columns = list(reader.fieldnames or [])
        rows = [r for r in reader]
    out = {"path": path, "columns": columns, "rows": rows, "n_rows": len(rows)}
    low = {c.lower().strip(): c for c in columns}
    out["arm_col"] = next((low[c] for c in ARM_COL_CANDIDATES if c in low), None)
    out["date_col"] = _match_col(columns, DATE_COL_PATTERNS)
    out["asof_col"] = _match_col(columns, ASOF_COL_PATTERNS)
    return out


class InputDataError(Exception):
    """The input file cannot be read at all. Not a gate failure — this one exits 1."""


_MISSING_TOKENS = ("", "na", "n/a", "null", "none", "nan", "-", "?")


DROP_ESCALATION_SHARE = 0.02     # more than 2% of rows dropped from a metric column -> GATE 0 FAIL


def check_primary_numeric(res, primary_col):
    """Refuse the whole run if the PRIMARY metric column holds something unreadable.

    The two metric columns are treated differently on purpose (contract v1.3 A).

    PRIMARY metric column: an unparseable value is malformed INPUT -> exit 1. You cannot
    read out a primary metric you cannot parse, and silently dropping rows from the very
    column the verdict rests on would bias the estimate invisibly.
    SECONDARY (guardrail) column: drop the row and surface it as a GATE 0 WARN, escalating
    to FAIL past DROP_ESCALATION_SHARE — a guardrail is a constraint, not the estimand, so
    one bad cell must not block the readout, but 2%+ is a data-quality problem.
    Blank / NA / null / none / nan / - / ? are recognised MISSING markers in either column:
    dropped and counted, never an exit-1 error.
    """
    for col in [c for c in [primary_col] if c and c in res["columns"]]:
        # start=2 so the number reported matches the line number in the file: line 1 is
        # the header, and file lines are counted from 1.
        for i, r in enumerate(res["rows"], start=2):
            raw = r.get(col)
            if raw is None:
                continue
            s_ = str(raw).strip()
            if s_.lower() in _MISSING_TOKENS:
                continue
            if _to_float(s_) is None:
                raise InputDataError(
                    "%s line %d: column %r contains %r, which is not a number and not a "
                    "recognised missing-value marker. Fix the extract and re-run."
                    % (os.path.basename(res["path"]), i, col, raw))


def _to_float(v):
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    if s == "" or s.lower() in ("na", "n/a", "null", "none", "nan"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ==========================================================================
# GATE 0 — design integrity (a validity gate)
#
# One question: did somebody write down what they were going to measure before they
# measured it, and does the results file match what they wrote? Each check is recorded
# separately, so the report can name the one that failed instead of just saying "GATE 0".
# ==========================================================================
def gate_design_integrity(res, brief):
    """Run every design check and return them all, plus one overall status."""
    checks = []
    failures = []

    def add(name, status, detail):
        checks.append({"name": name, "status": status, "detail": detail})
        if status == "FAIL":
            failures.append("%s: %s" % (name, detail))

    if brief["present"]:
        add("brief_present", "PASS", "parsed %d keys from %s"
            % (len(brief["raw"]), os.path.basename(brief["path"] or "")))
    else:
        add("brief_present", "FAIL",
            "; ".join(brief["errors"]) or "no readable brief — the sealed design is unknown")

    if res["n_rows"] == 0:
        add("results_non_empty", "FAIL", "results file has no data rows")
    else:
        add("results_non_empty", "PASS", "%d rows" % res["n_rows"])

    required = []
    if res["arm_col"]:
        add("arm_column", "PASS", "using '%s'" % res["arm_col"])
    else:
        add("arm_column", "FAIL", "no arm/variant column found in %s" % res["columns"])
    if res["date_col"]:
        add("exposure_date_column", "PASS", "using '%s'" % res["date_col"])
    else:
        add("exposure_date_column", "FAIL", "no exposure-date column found in %s" % res["columns"])

    pm = brief["primary_metric"]
    if not pm:
        add("primary_metric_declared", "FAIL", "brief does not declare a primary_metric")
    elif pm not in res["columns"]:
        add("primary_metric_column", "FAIL",
            "brief primary_metric '%s' is not a column in the results (%s)" % (pm, res["columns"]))
    else:
        add("primary_metric_column", "PASS", "'%s' present" % pm)
        required.append(pm)

    gm = brief["guardrail_metric"]
    if not gm:
        add("guardrail_declared", "WARN", "brief declares no guardrail metric")
    elif gm not in res["columns"]:
        add("guardrail_column", "WARN",
            "guardrail metric '%s' is not a column in the results — guardrail cannot be checked" % gm)
    else:
        add("guardrail_column", "PASS", "'%s' present" % gm)
        required.append(gm)

    # Do the arm names in the data match the arms the design declared?
    arms_observed = {}
    if res["arm_col"]:
        for r in res["rows"]:
            a = (r.get(res["arm_col"]) or "").strip()
            arms_observed[a] = arms_observed.get(a, 0) + 1
    ratio = brief["designed_ratio"] or {}
    blank_arms = arms_observed.pop("", 0)
    if blank_arms:
        add("arm_labels_populated", "FAIL", "%d rows have a blank arm label" % blank_arms)
    unknown = [a for a in arms_observed if a not in ratio]
    if ratio and unknown:
        add("arm_labels_known", "FAIL",
            "arm label(s) %s appear in the data but not in the designed assignment %s"
            % (unknown, sorted(ratio)))
    elif ratio:
        missing = [a for a in ratio if a not in arms_observed]
        if missing:
            add("arm_labels_known", "FAIL",
                "designed arm(s) %s have zero users in the data" % missing)
        else:
            add("arm_labels_known", "PASS", "arms %s match the design" % sorted(arms_observed))
    else:
        add("arm_labels_known", "WARN", "no designed assignment to compare arm labels against")

    # Are the metric values numbers? Counted per column, so the report can name which
    # column the unusable rows came from.
    rows_usable = 0
    dropped = 0
    dropped_by_col = {}
    if required and res["n_rows"]:
        for r in res["rows"]:
            bad = [c for c in required if _to_float(r.get(c)) is None]
            if bad:
                dropped += 1
                for c in bad:
                    dropped_by_col[c] = dropped_by_col.get(c, 0) + 1
            else:
                rows_usable += 1
        share = dropped / float(res["n_rows"])
        cols_txt = ", ".join("%s: %d" % (c, n) for c, n in sorted(dropped_by_col.items()))
        if rows_usable == 0:
            add("metric_values_numeric", "FAIL",
                "no row has usable numeric values for %s" % required)
        elif share > DROP_ESCALATION_SHARE:
            add("metric_values_numeric", "FAIL",
                "%d of %d rows (%.2f%%) dropped for missing/unparseable values (%s) — above the "
                "%.0f%% ceiling. A file that cannot parse %.0f%%+ of a metric column is a "
                "data-quality problem, not a rounding nuisance: fix the extract."
                % (dropped, res["n_rows"], 100.0 * share, cols_txt,
                   100.0 * DROP_ESCALATION_SHARE, 100.0 * DROP_ESCALATION_SHARE))
        elif dropped:
            add("metric_values_numeric", "WARN",
                "%d of %d rows (%.2f%%) dropped for missing/unparseable values (%s); %d rows "
                "usable. Within the %.0f%% ceiling, so the readout proceeds on the usable rows."
                % (dropped, res["n_rows"], 100.0 * share, cols_txt, rows_usable,
                   100.0 * DROP_ESCALATION_SHARE))
        else:
            add("metric_values_numeric", "PASS", "%d rows numeric" % rows_usable)

    # Pre-registration: the design must have been sealed on or before the first exposure.
    # A design sealed later was written around the result it was meant to test.
    dates = []
    if res["date_col"]:
        for r in res["rows"]:
            d = parse_date(r.get(res["date_col"]))
            if d:
                dates.append(d)
    first_exposure = min(dates) if dates else None
    last_exposure = max(dates) if dates else None
    if res["date_col"] and not dates:
        add("exposure_dates_parseable", "FAIL",
            "no parseable YYYY-MM-DD values in '%s'" % res["date_col"])
    if brief["sealed"] is None:
        add("sealed_before_exposure", "WARN",
            "brief has no sealed date — pre-registration cannot be verified")
    elif first_exposure is None:
        add("sealed_before_exposure", "WARN", "no exposure dates to compare the sealed date against")
    elif brief["sealed"] <= first_exposure:
        add("sealed_before_exposure", "PASS",
            "sealed %s <= first exposure %s" % (brief["sealed"], first_exposure))
    else:
        add("sealed_before_exposure", "FAIL",
            "brief sealed %s AFTER first exposure %s — the design was not pre-registered"
            % (brief["sealed"], first_exposure))

    # One unit, one arm. A user who shows up in both arms means the assignment did not
    # hold, and every comparison after that is between overlapping groups.
    id_col = next((c for c in res["columns"] if c.lower().strip() in ("user_id", "id", "unit_id")),
                  None)
    if id_col and res["n_rows"]:
        seen = set()
        dupes = 0
        cross_arm = set()
        arm_of = {}
        for r in res["rows"]:
            u = (r.get(id_col) or "").strip()
            a = (r.get(res["arm_col"]) or "").strip() if res["arm_col"] else ""
            if u in seen:
                dupes += 1
                if arm_of.get(u) and a and arm_of[u] != a:
                    cross_arm.add(u)
            seen.add(u)
            arm_of.setdefault(u, a)
        if cross_arm:
            add("unit_assignment_unique", "FAIL",
                "%d unit(s) appear in more than one arm — assignment is not unit-stable"
                % len(cross_arm))
        elif dupes:
            add("unit_assignment_unique", "WARN", "%d duplicate unit rows" % dupes)
        else:
            add("unit_assignment_unique", "PASS", "%d unique units" % len(seen))

    if str(brief.get("guardrail_threshold_source") or "").startswith("ASSUMED"):
        add("guardrail_threshold_source", "WARN", brief["guardrail_threshold_source"])
    if brief["present"] and str(brief.get("ratio_source", "")).startswith("ASSUMED"):
        add("assignment_ratio_source", "WARN",
            "brief declares no assignment ratio — %s. Shares are never inferred from the "
            "observed counts (that would make an SRM undetectable by construction)."
            % brief.get("ratio_source"))
    if brief["present"] and brief["mde"] is None:
        add("mde_declared", "WARN",
            "brief declares no MDE — practical significance cannot be judged")
    for n in brief["notes"]:
        checks.append({"name": "assignment_note", "status": "WARN", "detail": n})

    status = "FAIL" if failures else ("WARN" if any(c["status"] == "WARN" for c in checks) else "PASS")
    warns = [c["name"] for c in checks if c["status"] == "WARN"]
    if failures:
        headline = "%d check(s) failed: %s" % (
            len(failures), "; ".join(f.split(":")[0] for f in failures))
    elif warns:
        headline = "required checks pass, %d rows; warnings: %s" % (res["n_rows"], ", ".join(warns))
    else:
        headline = "brief parsed, required columns present, %d rows" % res["n_rows"]
    return {
        "status": status,
        "headline": headline,
        "blocking": True,
        "experiment": brief["experiment"],
        "brief_path": brief["path"],
        "results_path": res["path"],
        "primary_metric": brief["primary_metric"],
        "guardrail_metric": brief["guardrail_metric"],
        "mde": brief["mde"],
        "mde_is_relative": brief["mde_is_relative"],
        "designed_ratio": brief["designed_ratio"],
        "designed_ratio_source": brief.get("ratio_source"),
        "assignment_unit": brief["assignment_unit"],
        "sealed_date": brief["sealed"].isoformat() if brief["sealed"] else None,
        "first_exposure_date": first_exposure.isoformat() if first_exposure else None,
        "last_exposure_date": last_exposure.isoformat() if last_exposure else None,
        "arms_observed": arms_observed,
        "rows_total": res["n_rows"],
        "rows_usable": rows_usable,
        "rows_dropped": dropped,
        "rows_dropped_by_column": dropped_by_col,
        "drop_escalation_share": DROP_ESCALATION_SHARE,
        "checks": checks,
        "failures": failures,
    }


# ==========================================================================
# GATE 1 — SRM, sample ratio mismatch (a validity gate)
#
# Arms filled by a coin flip come out close to the size the design asked for. A gap far
# larger than chance allows is a bug rather than bad luck: exposure events went missing on
# one side, or a filter fired on one side only, or the split was moved mid-flight. What
# makes it fatal is that the arms are then no longer two samples of the same population,
# so whatever caused the imbalance is mixed into every comparison you could draw.
# ==========================================================================
def gate_srm(counts, ratio, alpha=SRM_ALPHA, ratio_source="brief (declared)"):
    """Test the arm sizes we observed against the ratio the design asked for.

    The expected ratio MUST come from the brief (or a labelled equal-split default).
    Never from the observed counts — see parse_assignment's warning.
    """
    if not counts or not ratio:
        return {"status": "FAIL", "blocking": True, "alpha": alpha,
                "detail": "cannot test the split without both observed counts and a designed ratio"}
    r = srm_chisq(counts, ratio, alpha=alpha)
    total = float(sum(counts.values())) or 1.0
    observed_share = {k: v / total for k, v in counts.items()}
    status = "FAIL" if r["srm_detected"] else "PASS"

    detail = "%s vs designed %s; chi2=%s dof=%d p=%s (alpha=%s)" % (
        ", ".join("%s %d (%.1f%%)" % (k, int(r["observed"].get(k, 0)),
                                     100.0 * observed_share.get(k, 0.0)) for k in ratio),
        ", ".join("%s %.4g%%" % (k, 100.0 * ratio[k] / sum(ratio.values())) for k in ratio),
        "inf" if r["chi2"] is None or math.isinf(r["chi2"]) else round(r["chi2"], 4),
        r["dof"],
        "n/a" if r["p_value"] is None else "%.3g" % r["p_value"],
        alpha,
    )
    obs_txt = "/".join(str(int(r["observed"].get(k, 0))) for k in ratio)
    des_txt = "/".join(("%.4g" % (100.0 * ratio[k] / sum(ratio.values()))) for k in ratio)
    headline = "split %s vs designed %s, chi2=%s dof=%d p=%s%s" % (
        obs_txt, des_txt,
        "inf" if r["chi2"] is None or math.isinf(r["chi2"]) else "%.4g" % r["chi2"],
        r["dof"], "n/a" if r["p_value"] is None else "%.3g" % r["p_value"],
        " — SAMPLE RATIO MISMATCH" if status == "FAIL" else " — matches the design")
    if status == "FAIL":
        detail += " — SAMPLE RATIO MISMATCH: the randomisation is not trustworthy"
    if str(ratio_source).startswith("ASSUMED"):
        detail += (" NOTE: the expected ratio was %s, not read from the brief — an SRM result "
                   "under an assumed ratio is weaker evidence than one under a declared ratio."
                   % ratio_source)
    return {
        "status": status,
        "headline": headline,
        "blocking": True,
        "alpha": alpha,
        "designed_ratio": ratio,
        "ratio_source": ratio_source,
        "observed": {k: int(v) for k, v in r["observed"].items()},
        "expected": {k: round(v, 2) for k, v in r["expected"].items()},
        "observed_share": {k: round(v, 6) for k, v in observed_share.items()},
        "chi2": r["chi2"],
        "dof": r["dof"],
        "p_value": r["p_value"],
        "srm_detected": r["srm_detected"],
        "detail": detail,
    }


# ==========================================================================
# GATE 2 — maturity (a validity gate)
#
# A metric named `..._28d` is a promise to count 28 days of behaviour per user. Until
# those 28 days have passed, the cell holds a partial count that happens to look like a
# small number. This gate asks whether the counting has actually finished — for every
# user, not on average.
# ==========================================================================
def parse_duration_claim(text):
    """Turn a duration written in words into a number of days.

    '4 weeks' -> 28, '10 days' -> 10, '2 mo' -> 60. None when it cannot be read.
    """
    if text in (None, ""):
        return None
    t = str(text).strip().lower()
    m = re.search(r"(\d+(?:\.\d+)?)\s*(weeks?|wks?|w|days?|d|months?|mos?|mo)\b", t)
    if m:
        n = float(m.group(1))
        u = m.group(2)
        mult = 7 if u.startswith(("week", "wk", "w")) else (30 if u.startswith(("month", "mo")) else 1)
        return int(round(n * mult))
    if re.search(r"\b(a|one)\s+(week|fortnight|month)\b", t):
        return {"week": 7, "fortnight": 14, "month": 30}[
            re.search(r"\b(week|fortnight|month)\b", t).group(1)]
    n = _first_number(t)
    return int(round(n)) if n is not None else None


def gate_maturity(exposures, window_days, asof, asof_source, metric_name,
                  asof_provenance="assumed: today", claimed_duration_days=None,
                  claimed_duration_raw=None, metric_by_date=None):
    """VALIDITY gate. FAIL when mature_share < 1.0; WARN when it would otherwise PASS on
    an as-of date that was assumed rather than supplied.

    Deciding whether the window has closed needs a second date: the day the metric was
    pulled. A results file that carries only exposure dates cannot supply it, so the
    caller RESOLVES it in this order (v1.2): explicit --asof ("given"), an
    as-of/extract/snapshot column in the CSV ("from data"), a date stated in the ask
    ("from request"), else today's system date ("assumed: today").

    Today is the most generous defensible default: data cannot describe the future, so
    today is an UPPER bound on any possible extract date. A gate should fail only when
    failure is unavoidable even under the most generous assumption — then the failure is
    certain rather than an artefact of a pessimistic default. max(exposure_date) is a LOWER
    bound and made mature_share == 1.0 arithmetically impossible for any window W > 0, so
    the gate could never pass and carried no information.

    Also runs the TRUNCATION GRADIENT check, which needs no as-of date at all — so it is
    the one piece of evidence here that cannot be argued out of by disputing the date.
    """
    n = len(exposures)
    if n == 0:
        return {"status": "FAIL", "blocking": True, "metric": metric_name,
                "detail": "no parseable exposure dates — maturity cannot be established"}
    first, last = min(exposures), max(exposures)
    span = (last - first).days + 1
    is_assumed = str(asof_provenance).startswith("assumed")
    base = {
        "status": "PASS",
        "blocking": True,
        "metric": metric_name,
        "metric_window_days": window_days,
        "maturation_days": window_days,
        "asof": asof.isoformat() if asof else None,
        "asof_provenance": asof_provenance,
        "asof_source": asof_source,
        "asof_is_assumed": is_assumed,
        "asof_settled_by": ("the metric's actual extraction date — re-run with "
                            "--asof YYYY-MM-DD to replace this assumption and to make the "
                            "run reproducible" if is_assumed else None),
        "first_exposure": first.isoformat(),
        "last_exposure": last.isoformat(),
        "exposure_span_days": span,
        "exposure_span_weeks": round(span / 7.0, 1),
        "total_users": n,
        "claimed_duration_raw": claimed_duration_raw,
        "claimed_duration_days": claimed_duration_days,
    }

    # --- The duration the ask asserts, against the exposure span actually in the data.
    if claimed_duration_days is None:
        base["claim_check"] = ("no duration claim was passed in; check this span against any "
                               "duration the request asserts, and pass it via "
                               "--claimed-duration '<N weeks>' so the check is recorded")
        base["claim_matches_data"] = None
    else:
        matches = abs(claimed_duration_days - span) <= 1
        base["claim_matches_data"] = matches
        if matches:
            base["claim_check"] = ("claimed %d day(s) is consistent with the %d-day exposure span "
                                   "in the data" % (claimed_duration_days, span))
        else:
            base["claim_check"] = (
                "CLAIM-VS-DATA MISMATCH: the ask claims %s (~%d days) of runtime, but the data's "
                "exposure span is %d days (%s..%s). Check the claim against the data, do not "
                "inherit it." % (claimed_duration_raw or "%d days" % claimed_duration_days,
                                 claimed_duration_days, span, base["first_exposure"],
                                 base["last_exposure"]))
        if window_days and claimed_duration_days < window_days:
            base["claim_check"] += (" Note: even the claimed %d days is shorter than the metric's "
                                    "%d-day window." % (claimed_duration_days, window_days))

    # --- The truncation gradient: evidence from the data alone, no as-of date needed.
    # Pooled across arms on purpose. A trend that ignores which arm a user was in carries
    # no treatment-vs-control comparison, so it stays reportable even when the conclusion
    # gates are suppressed.
    grad = None
    if metric_by_date:
        cohort_means = [(d.isoformat(), sum(v) / float(len(v)))
                        for d, v in sorted(metric_by_date.items()) if v]
        grad = truncation_gradient(cohort_means)
        grad["pooled_across_arms"] = True
        base["truncation_gradient"] = grad

    if window_days is None:
        base["status"] = "WARN"
        base["mature_share"] = None
        base["required_days"] = None
        base["detail"] = ("metric %r has no _<N>d window suffix — the observation window is "
                          "unknown, so maturity is not machine-checkable; confirm the window "
                          "with the metric owner before concluding anything." % metric_name)
        base["headline"] = "window unknown for metric %r — maturity unverified" % metric_name
        return base

    cutoff = asof - datetime.timedelta(days=window_days)   # exposures after this cannot be mature
    full_maturity_date = last + datetime.timedelta(days=window_days)
    mature = sum(1 for d in exposures if (asof - d).days >= window_days)
    share = mature / float(n)
    days_elapsed = (asof - last).days
    required_days = span + window_days
    base.update({
        "mature_users": mature,
        "immature_users": n - mature,
        "mature_share": share,
        "maturity_cutoff_date": cutoff.isoformat(),
        "full_maturity_date": full_maturity_date.isoformat(),
        "required_days": required_days,
        "required_weeks": int(math.ceil(required_days / 7.0)),
        "days_since_last_exposure": days_elapsed,
        "days_short": max(0, window_days - days_elapsed),
        "observed_days_from_first_exposure": (asof - first).days + 1,
    })

    prefix = "As of %s [%s] " % (base["asof"], asof_provenance)

    # --- Read the gradient against the timeline, and pick the story it tells.
    #
    # d_ decides the branch; r_ and p_ may only choose WORDING (AMENDMENT 3 C). weak_monotone
    # marks the case where the cohort means DO slide downwards but by far too little for the
    # window: there, "the values do not move" and "no downward slope appears" are both FALSE
    # sentences, and a qualifying clause does not unsay a false sentence.
    d_ = grad["direction"] if grad else None
    r_ = grad.get("corr") if grad else None
    p_ = grad.get("corr_p_value") if grad else None
    weak_monotone = (d_ == "flat" and r_ is not None and r_ <= -0.5
                     and p_ is not None and p_ < 0.05)
    gnote = ""
    base["data_integrity_concern"] = False
    if grad and share < 1.0:
        if d_ == "late_lower":
            gnote = ("TRUNCATION CONFIRMED: late cohorts read lower than early ones — the "
                     "follow-up-time signature a genuinely truncated %d-day metric must show. "
                     "Positive evidence of immaturity from the data alone, independent of the "
                     "as-of date." % window_days)
        elif d_ in ("insufficient_cohorts", "undefined"):
            gnote = ("NOT ASSESSABLE: %s — too little cohort variation to read a trend."
                     % d_.replace("_", " "))
        else:
            base["data_integrity_concern"] = True
            if d_ != "flat":
                core = ("the trend slopes the WRONG WAY — the late cohorts, with LESS follow-up "
                        "time, read HIGHER")
            elif weak_monotone:
                core = ("the cohort means DO decline monotonically, but by far less than a "
                        "%d-day truncation forces: the late-vs-early gap sits inside the flat "
                        "band, so the dependence on follow-up time is far weaker than the window "
                        "requires — too little movement, not none" % window_days)
            else:
                core = ("the trend is flat — the values do not move with follow-up time the way "
                        "a truncated window forces them to")
            gnote = ("DATA INTEGRITY CONCERN: the timeline makes a complete %d-day window "
                     "impossible for the later cohorts, yet %s. Treat the column as suspect "
                     "(back-filled, recomputed, mis-joined, or not the metric the brief names) "
                     "and reconcile it with the pipeline owner before any rerun. A stronger "
                     "finding than immaturity alone." % (window_days, core))
        base["truncation_gradient"]["reading"] = gnote.strip()
    elif grad and is_assumed:
        # Maturity here rests on an assumed as-of date, so the gradient stops being
        # "not required" and becomes the only corroboration the data itself can offer.
        if d_ == "late_lower":
            base["truncation_gradient"]["reading"] = (
                "AGAINST THE ASSUMED AS-OF DATE: the late cohorts read LOWER — the "
                "follow-up-time signature of a read taken before the %d-day window closed. "
                "That points at an extract earlier than %s, which would leave the late "
                "cohorts truncated. Supply --asof <extraction date>."
                % (int(window_days), base["full_maturity_date"]))
        elif d_ in ("insufficient_cohorts", "undefined"):
            base["truncation_gradient"]["reading"] = (
                "not assessable — %s, so the data offers no corroboration for the assumed "
                "as-of date either way." % d_.replace("_", " "))
        elif weak_monotone:
            base["truncation_gradient"]["reading"] = (
                "CONSISTENT WITH the assumed as-of date, and no more than that: the cohort "
                "means DO decline, but by far less than a %d-day truncation forces — nothing "
                "like the slope a file extracted before %s would show. Consistent with a "
                "late-enough extract, never proof of one."
                % (int(window_days), base["full_maturity_date"]))
        else:
            base["truncation_gradient"]["reading"] = (
                "CONSISTENT WITH the assumed as-of date, and no more than that: a file "
                "extracted before %s would show the late cohorts lower, and no downward "
                "slope appears. Consistent with a late-enough extract, never proof of one."
                % base["full_maturity_date"])
    elif grad:
        base["truncation_gradient"]["reading"] = (
            "not required — every cohort has a complete %d-day window, so no follow-up-time "
            "gradient is expected; any slope here is seasonality or novelty, not truncation."
            % int(window_days))

    if share <= 0.0:
        base["status"] = "FAIL"
        base["headline"] = ("0%% of %d users have a complete %d-day window as of %s (%s) — "
                            "the metric is not yet observable"
                            % (n, window_days, base["asof"], asof_provenance))
        base["detail"] = (
            prefix + "no user has a complete %d-day window: the maturity cutoff is %s, before the "
            "first exposure %s. The cohort completes on %s. End-to-end this metric needs %d days "
            "(~%d weeks) from first exposure.%s"
            % (window_days, base["maturity_cutoff_date"], base["first_exposure"],
               base["full_maturity_date"], required_days, base["required_weeks"], ""))
    elif share < 1.0:
        base["status"] = "FAIL"
        base["headline"] = ("%.1f%% of %d users have a complete %d-day window as of %s (%s) — "
                            "partial maturity"
                            % (100.0 * share, n, window_days, base["asof"], asof_provenance))
        base["detail"] = (
            prefix + "%d of %d users are mature; %d were exposed after the cutoff %s. PARTIAL "
            "maturity fails for its own reason: early and late cohorts have different follow-up "
            "time, so a difference of means mixes the treatment effect with an exposure-age "
            "effect. Cohort completes on %s.%s"
            % (mature, n, n - mature, base["maturity_cutoff_date"],
               base["full_maturity_date"], ""))
    elif is_assumed:
        # The mirror image of the bug AMENDMENT 2 fixed, and the worse half of it: a false
        # FAIL is loud, a false PASS is silent. The metric values were computed at an
        # unknown extraction time and frozen in the file, and calendar time passing does
        # not mature data already written to disk. So an assumed as-of date can establish
        # that maturity was POSSIBLE by now, never that it happened -- which is a WARN, not
        # a PASS. WARN does not block: the conclusion gates still run and the verdict still
        # stands, with the caveat carried next to it.
        base["status"] = "WARN"
        base["maturity_unconfirmed"] = True
        base["headline"] = (
            "enough calendar time has elapsed for all %d users to be mature IF the metric was "
            "extracted on or after %s; the file carries no extraction date, so supply "
            "--asof <extraction date> to confirm"
            % (n, base["full_maturity_date"]))
        base["detail"] = (
            prefix + "the metric values were frozen at an unknown extraction time, and calendar "
            "time passing does not mature data already on disk (maturity cutoff %s; exposure "
            "%s..%s). The gradient below corroborates the assumption but cannot settle it."
            % (base["maturity_cutoff_date"], base["first_exposure"], base["last_exposure"]))
    else:
        base["headline"] = ("all %d users have a complete %d-day window as of %s (%s)"
                            % (n, window_days, base["asof"], asof_provenance))
        base["detail"] = (
            prefix + "all %d users are mature (maturity cutoff %s; exposure %s..%s)."
            % (n, base["maturity_cutoff_date"], base["first_exposure"], base["last_exposure"]))
    return base



# ==========================================================================
# GATE 3 — guardrail (a conclusion gate)
#
# The guardrail is the thing you promised not to break while chasing the primary metric.
# It never has to improve; it must only not get worse than the brief allows.
# ==========================================================================
def _guardrail_one(treat_vals, ctrl_vals, metric, threshold, worse_direction, alpha=SIG_ALPHA,
                   threshold_source=None):
    """Compare ONE treatment arm's guardrail against the threshold the brief committed to.

    BREACH is a point difference already worse than the threshold, and it forces NO-SHIP
    however good the primary metric looks. AT_RISK is a point difference inside the
    threshold whose 95% CI upper bound crosses it; that is a WARN, and it has to appear in
    the verdict reasoning rather than being filed away.

    `cancel_rate` is a per-user rate, so each user contributes their own number and this is
    a difference of means (Welch), not a pooled proportion test.
    """
    if not metric:
        return {"status": "WARN", "blocking": False, "metric": None, "assessment": None,
                "detail": "no guardrail metric declared in the brief — nothing to check"}
    if threshold is None:
        threshold = GUARDRAIL_DEFAULT_THRESHOLD
    if len(treat_vals) < 2 or len(ctrl_vals) < 2:
        return {"status": "WARN", "blocking": False, "metric": metric, "assessment": None,
                "threshold": threshold,
                "detail": "not enough guardrail observations to test (need >=2 per arm)"}
    w = welch_ttest(treat_vals, ctrl_vals, alpha=alpha)
    if worse_direction == "decrease":
        worse_point = -w["diff"]
        worse_ci = -w["ci_low"]
    else:
        worse_point = w["diff"]
        worse_ci = w["ci_high"]
    if worse_point > threshold:
        assessment, status = "BREACH", "FAIL"
    elif worse_ci > threshold:
        assessment, status = "AT_RISK", "WARN"
    else:
        assessment, status = "OK", "PASS"
    detail = ("%s: treatment %.6g vs control %.6g, diff %+.6g (95%% CI %+.6g..%+.6g) "
              "against a %s-of-%.4g threshold -> %s"
              % (metric, w["mean_a"], w["mean_b"], w["diff"], w["ci_low"], w["ci_high"],
                 "worsen-by" if worse_direction == "increase" else "drop-by", threshold,
                 assessment))
    if str(threshold_source or "").startswith("ASSUMED"):
        detail += " NOTE: threshold %s" % threshold_source
    return {
        "status": status,
        "headline": "%s diff %+.4g vs %+.4g threshold -> %s" % (metric, w["diff"], threshold,
                                                                assessment),
        "blocking": False,
        "metric": metric,
        "assessment": assessment,
        "threshold": threshold,
        "threshold_source": threshold_source,
        "worse_direction": worse_direction,
        "mean_treatment": w["mean_a"],
        "mean_control": w["mean_b"],
        "diff": w["diff"],
        "ci_low": w["ci_low"],
        "ci_high": w["ci_high"],
        "p_value": w["p_value"],
        "forces_no_ship": assessment == "BREACH",
        "detail": detail,
    }


def gate_guardrail(by_arm, control_arm, treatment_arms, metric, threshold, worse_direction,
                   alpha=SIG_ALPHA, threshold_source=None):
    """Run the guardrail comparison for EVERY treatment arm against control.

    A guardrail is a promise about what the change must not break, and each arm is a
    different change. So each arm is measured against control on its own, and every
    comparison is reported: an arm that breaks the promise is a finding whether or not it
    is the arm anyone wants to ship.

    With one treatment arm the family result IS that arm's comparison, key for key, so the
    A/B output is exactly what it was before A/B/n was handled.
    """
    ctrl_vals = by_arm.get(control_arm, [])
    arms = [a for a in (treatment_arms or []) if a != control_arm]
    if not metric or not arms:
        one = _guardrail_one([], ctrl_vals, metric, threshold, worse_direction, alpha=alpha,
                             threshold_source=threshold_source)
        one["comparisons"] = []
        one["family_size"] = 0
        one["breaching_arms"] = []
        one["at_risk_arms"] = []
        return one

    comparisons = []
    for arm in arms:
        c = _guardrail_one(by_arm.get(arm, []), ctrl_vals, metric, threshold, worse_direction,
                           alpha=alpha, threshold_source=threshold_source)
        c["arm"] = arm
        c["control_arm"] = control_arm
        comparisons.append(c)

    breaching = [c["arm"] for c in comparisons if c.get("assessment") == "BREACH"]
    at_risk = [c["arm"] for c in comparisons if c.get("assessment") == "AT_RISK"]

    if len(comparisons) == 1:
        out = dict(comparisons[0])
    else:
        if breaching:
            status, assessment = "FAIL", "BREACH"
        elif at_risk:
            status, assessment = "WARN", "AT_RISK"
        elif any(c.get("assessment") is None for c in comparisons):
            status, assessment = "WARN", None
        else:
            status, assessment = "PASS", "OK"
        per_arm = "; ".join(
            "%s %s" % (c["arm"],
                       ("diff %+.4g -> %s" % (c["diff"], c["assessment"]))
                       if c.get("assessment") else "not testable")
            for c in comparisons)
        detail = ("%s vs a %s-of-%.4g threshold, one comparison per treatment arm: %s"
                  % (metric, "worsen-by" if worse_direction == "increase" else "drop-by",
                     comparisons[0].get("threshold", threshold), per_arm))
        if str(threshold_source or "").startswith("ASSUMED"):
            detail += " NOTE: threshold %s" % threshold_source
        out = {
            "status": status,
            "headline": "%s: %s" % (metric, per_arm),
            "blocking": False,
            "metric": metric,
            "assessment": assessment,
            "threshold": comparisons[0].get("threshold", threshold),
            "threshold_source": threshold_source,
            "worse_direction": worse_direction,
            "forces_no_ship": bool(breaching),
            "detail": detail,
        }
    out["comparisons"] = comparisons
    out["family_size"] = len(comparisons)
    out["breaching_arms"] = breaching
    out["at_risk_arms"] = at_risk
    return out


# ==========================================================================
# GATE 4 — lift (a conclusion gate)
#
# Only now, and only if everything above passed: how much better or worse did treatment do
# than control?
# ==========================================================================
def gate_lift(by_arm, control_arm, metric, mde, mde_is_relative=True, alpha=SIG_ALPHA):
    """Compare each treatment arm against control on the primary metric.

    Every comparison is reported. With more than one treatment arm, the best-looking one is
    never quietly promoted to be the answer — and every arm is corrected for the fact that
    asking k questions gives you k chances to be wrong (see `holm_bonferroni`).

    With one treatment arm the family result IS that arm's comparison, key for key, and the
    Holm threshold is plain alpha, so the A/B output is exactly what it was before A/B/n was
    handled.
    """
    comparisons = []
    ctrl = by_arm.get(control_arm, [])
    for arm in order_arms([a for a in by_arm if a != control_arm]):
        vals = by_arm[arm]
        if len(vals) < 2 or len(ctrl) < 2:
            comparisons.append({"arm": arm, "status": "WARN",
                                "detail": "not enough observations to test this arm"})
            continue
        w = welch_ttest(vals, ctrl, alpha=alpha)
        c = {"arm": arm, "control_arm": control_arm, "status": "PASS"}
        c.update(w)
        c["significant"] = w["p_value"] < alpha
        c["ci_excludes_zero"] = (w["ci_low"] > 0) or (w["ci_high"] < 0)
        c["mde"] = mde
        c["mde_is_relative"] = mde_is_relative
        if mde is not None:
            eff = w["rel_diff"] if mde_is_relative else w["diff"]
            up = w["rel_ci_high"] if mde_is_relative else w["ci_high"]
            c["meets_mde"] = (eff is not None and eff >= mde)
            c["mde_ruled_out"] = (up is not None and up < mde)
        else:
            c["meets_mde"] = None
            c["mde_ruled_out"] = None
        comparisons.append(c)

    # --- multiplicity. k treatment arms are k hypotheses about the same control, so the
    # chance that at least one of them comes back a false positive is 1-(1-alpha)^k, not
    # alpha. Holm-Bonferroni puts it back. At k == 1 the threshold IS alpha, so nothing
    # about a two-arm readout moves.
    testable = [c for c in comparisons if c.get("status") == "PASS"]
    holm = holm_bonferroni([c["p_value"] for c in testable], alpha=alpha)
    for c, h in zip(testable, holm):
        c["significant_uncorrected"] = c["significant"]
        c["holm_rank"] = h["rank"]
        c["holm_threshold"] = h["threshold"]
        c["significant"] = h["significant"]
        c["wins_on_primary"] = bool(
            c["significant"] and c["ci_excludes_zero"]
            and (c["meets_mde"] if mde is not None
                 else (c["rel_diff"] is not None and c["rel_diff"] > 0)))

    out = {
        "status": "PASS",
        "blocking": False,
        "metric": metric,
        "alpha": alpha,
        "mde": mde,
        "mde_is_relative": mde_is_relative,
        "control_arm": control_arm,
        "control_n": len(ctrl),
        "control_mean": (sum(ctrl) / float(len(ctrl))) if ctrl else None,
        "treatment_arms": [c["arm"] for c in comparisons],
        "family_size": len(comparisons),
        "multiplicity": {
            "method": "holm-bonferroni",
            "family_size": len(testable),
            "alpha": alpha,
            "thresholds": {c["arm"]: c["holm_threshold"] for c in testable},
            "note": ("one treatment arm, so the Holm threshold is plain alpha and the "
                     "correction changes nothing" if len(testable) <= 1 else
                     "%d hypotheses; the i-th smallest p-value is held to alpha/(k-i) and "
                     "testing stops at the first arm that fails" % len(testable)),
        },
        "arms_winning_on_primary": [c["arm"] for c in testable if c["wins_on_primary"]],
        "comparisons": comparisons,
    }
    primary = next((c for c in comparisons if c.get("status") == "PASS"), None)
    if not primary:
        out["status"] = "WARN"
    if primary and len(comparisons) > 1:
        # More than one treatment arm: NOTHING is promoted to the top level. A single
        # `rel_diff` / `p_value` up here would be one arm's answer wearing the whole
        # experiment's clothes, which is the defect this branch exists to prevent. The
        # per-arm answers live in `comparisons`, all of them, always.
        wins = out["arms_winning_on_primary"]
        per_arm = "; ".join(
            ("%s %s p=%.4g vs Holm threshold %.4g -> %s"
             % (c["arm"], _pct(c["rel_diff"]), c["p_value"], c["holm_threshold"],
                "significant" if c["significant"] else "not significant"))
            if c.get("status") == "PASS" else "%s not testable" % c["arm"]
            for c in comparisons)
        out["headline"] = (
            "%d treatment arms vs %s, Holm-Bonferroni at alpha=%s; %s"
            % (len(comparisons), control_arm, alpha,
               ("significant and clears the MDE: %s" % ", ".join(wins)) if wins
               else "no arm is significant after correction and clears the MDE"))
        out["detail"] = "%s: %s" % (metric, per_arm)
    elif primary:
        for k in ("arm", "n_a", "n_b", "mean_a", "mean_b", "diff", "se", "t", "dof", "p_value",
                  "ci_low", "ci_high", "rel_diff", "rel_ci_low", "rel_ci_high", "significant",
                  "ci_excludes_zero", "meets_mde", "mde_ruled_out"):
            out[k] = primary[k]
        out["treatment_arm"] = primary["arm"]
        out["headline"] = ("rel lift %s (95%% CI %s..%s), p=%.4g vs alpha=%s, MDE=%s -> %s"
                           % (_pct(primary["rel_diff"]), _pct(primary["rel_ci_low"]),
                              _pct(primary["rel_ci_high"]), primary["p_value"], alpha,
                              "n/a" if mde is None else "%.4g%%" % (100.0 * mde),
                              "clears the MDE" if primary.get("meets_mde") else
                              "does not clear the MDE"))
        out["detail"] = (
            "%s: treatment %.6g vs control %.6g, abs diff %+.6g, rel lift %s "
            "(95%% CI %s..%s), p=%.4g, Welch dof=%.1f"
            % (metric, primary["mean_a"], primary["mean_b"], primary["diff"],
               _pct(primary["rel_diff"]), _pct(primary["rel_ci_low"]), _pct(primary["rel_ci_high"]),
               primary["p_value"], primary["dof"])
        )
    else:
        out["detail"] = "no arm pair had enough observations to test"
    return out


def _pct(v):
    """Show a proportion as a signed percentage: 0.0764 -> '+7.64%'. None -> 'n/a'."""
    return "n/a" if v is None else "%+.2f%%" % (100.0 * v)


# ==========================================================================
# The verdict
#
# Exactly one token comes out of here, and it comes from the gate results rather than from
# anyone's reading of them.
# ==========================================================================
def _guardrail_by_arm(guard):
    """{arm: its guardrail comparison}, for looking a single arm's promise up by name."""
    out = {}
    for c in (guard or {}).get("comparisons") or []:
        if c.get("arm"):
            out[c["arm"]] = c
    return out


def ship_eligible_arms(lift, guard):
    """The arms this readout would let anyone ship, named.

    An arm qualifies on two separate counts, and it needs both: it beat control on the
    primary metric after the multiplicity correction and by enough to matter, and it did
    not break the guardrail promise. A breach in a DIFFERENT arm bars that other arm; it
    says nothing about this one, because the arms are different changes measured
    separately.
    """
    if not isinstance(lift, dict) or lift.get("status") != "PASS":
        return []
    gmap = _guardrail_by_arm(guard)
    single_breach = (guard or {}).get("assessment") == "BREACH" and not gmap
    out = []
    for c in lift.get("comparisons") or []:
        if c.get("status") != "PASS" or not c.get("wins_on_primary"):
            continue
        g = gmap.get(c["arm"])
        breached = (g or {}).get("assessment") == "BREACH" or (single_breach and not g)
        if not breached:
            out.append(c["arm"])
    return out


def _decide_verdict_family(lift, guard):
    """The verdict when the design ran more than one treatment arm.

    Same two questions as the A/B rule — is the gap real, is a gap that size worth
    shipping — asked of every arm and answered for the family. The winner is NAMED,
    because 'ship it' is not an instruction anybody can follow when there were three
    versions of 'it'.
    """
    testable = [c for c in (lift.get("comparisons") or []) if c.get("status") == "PASS"]
    untestable = [c["arm"] for c in (lift.get("comparisons") or []) if c.get("status") != "PASS"]
    mde = lift.get("mde")
    mde_txt = "n/a" if mde is None else "%.4g%%" % (100.0 * mde)
    gmap = _guardrail_by_arm(guard)
    breaching = (guard or {}).get("breaching_arms") or []
    at_risk = (guard or {}).get("at_risk_arms") or []

    def arm_phrase(c):
        g = gmap.get(c["arm"])
        return ("%s %s (p=%.4g vs Holm threshold %.4g, %s; %s the %s MDE%s)"
                % (c["arm"], _pct(c["rel_diff"]), c["p_value"], c["holm_threshold"],
                   "significant" if c["significant"] else "not significant",
                   "clears" if c.get("meets_mde") else "does not clear", mde_txt,
                   "" if not g or g.get("assessment") in (None, "OK")
                   else ", guardrail %s" % g["assessment"]))

    if not testable:
        return "INCONCLUSIVE", ("lift could not be estimated for any treatment arm: %s"
                                % lift.get("detail"))

    winners = ship_eligible_arms(lift, guard)
    body = "; ".join(arm_phrase(c) for c in testable)
    tail = ""
    if breaching:
        tail += ("; guardrail %s BREACHED in %s, which bars %s from shipping"
                 % ((guard or {}).get("metric"), ", ".join(breaching),
                    "that arm" if len(breaching) == 1 else "those arms"))
    if at_risk:
        tail += ("; guardrail %s is AT_RISK in %s"
                 % ((guard or {}).get("metric"), ", ".join(at_risk)))
    if untestable:
        tail += "; not testable: %s" % ", ".join(untestable)
    correction = (" Holm-Bonferroni over %d testable treatment arm%s; the threshold%s %s."
                  % (len(testable), "" if len(testable) == 1 else "s",
                     " was" if len(testable) == 1 else "s were",
                     ", ".join("%s %.4g" % (c["arm"], c["holm_threshold"]) for c in testable)))

    if winners:
        return "SHIP", ("ship %s: %s%s.%s"
                        % (" or ".join(winners), body, tail, correction))
    if all((c["significant"] and not c.get("meets_mde")) or c.get("mde_ruled_out")
           for c in testable):
        return "NO-SHIP", ("no arm is both real and big enough: %s%s.%s"
                           % (body, tail, correction))
    if breaching and len(breaching) == len(testable):
        return "NO-SHIP", ("every treatment arm breaches the guardrail: %s%s.%s"
                           % (body, tail, correction))
    return "INCONCLUSIVE", ("no arm wins and at least one is unanswered rather than ruled "
                            "out: %s%s.%s" % (body, tail, correction))


def decide_verdict(gates, stopped_at, all_validity_failures=None):
    """Name the verdict from the gates, and return the reason alongside it.

    If any validity gate failed, the verdict is named by the FIRST failure in gate order,
    and the reason lists every failure — so it is visible that fixing only the first one
    leaves a rerun nobody can read. Otherwise a guardrail BREACH decides it, and after that
    the two questions in order: is the gap real, and is a gap that size worth shipping.
    """
    all_validity_failures = all_validity_failures or ([stopped_at] if stopped_at else [])
    if stopped_at:
        v = VERDICT_FOR_BLOCKING_FAIL[stopped_at]
        parts = []
        for name in all_validity_failures:
            g = gates.get(name, {})
            why = (g.get("headline") or "; ".join(g.get("failures") or []) or "failed")
            parts.append("%s: %s" % (name, why))
        extra = ""
        if len(all_validity_failures) > 1:
            extra = (" %d independent validity failures; all must be fixed."
                     % len(all_validity_failures))
        return v, "%s — verdict named by the first failing validity gate '%s'.%s %s" % (
            v, stopped_at, extra, " | ".join(parts))

    guard = gates.get("guardrail", {})
    lift_gate = gates.get("lift", {})
    if isinstance(lift_gate, dict) and lift_gate.get("family_size", 1) > 1:
        # A/B/n. The guardrail is checked per arm inside this branch, because a breach in
        # one arm is a fact about that arm and not about the others.
        return _decide_verdict_family(lift_gate, guard)

    if guard.get("assessment") == "BREACH":
        return "NO-SHIP", ("guardrail breach: %s — a guardrail breach forces NO-SHIP regardless "
                           "of the primary metric" % guard.get("detail"))

    lift = gates.get("lift", {})
    if lift.get("status") != "PASS":
        return "INCONCLUSIVE", "lift could not be estimated: %s" % lift.get("detail")

    p = lift["p_value"]
    mde = lift.get("mde")
    rel = lift.get("rel_diff")
    sig = p < lift.get("alpha", SIG_ALPHA)
    excl0 = lift.get("ci_excludes_zero")
    eff = rel if lift.get("mde_is_relative", True) else lift.get("diff")
    upper = lift.get("rel_ci_high") if lift.get("mde_is_relative", True) else lift.get("ci_high")
    mde_txt = "n/a" if mde is None else "%.4g%%" % (100.0 * mde)

    if sig and mde is not None and eff is not None and eff >= mde and excl0:
        v = "SHIP"
        reason = ("significant (p=%.4g < %s) and the effect %s clears the %s MDE with a CI that "
                  "excludes zero" % (p, lift.get("alpha"), _pct(rel), mde_txt))
    elif sig and mde is not None and eff is not None and eff < mde:
        v = "NO-SHIP"
        reason = ("statistically significant (p=%.4g) but the effect %s is below the %s MDE — "
                  "real but not worth shipping on" % (p, _pct(rel), mde_txt))
    elif sig and mde is None:
        v = "SHIP" if excl0 and (rel is None or rel > 0) else "NO-SHIP"
        reason = ("significant (p=%.4g) but the brief declares no MDE, so practical significance "
                  "is unverified" % p)
    elif not sig and mde is not None and upper is not None and upper < mde:
        v = "NO-SHIP"
        reason = ("not significant (p=%.4g) and the CI upper bound %s rules out the %s MDE — the "
                  "effect we cared about is not there" % (p, _pct(lift.get("rel_ci_high")), mde_txt))
    else:
        v = "INCONCLUSIVE"
        reason = ("not significant (p=%.4g) and the CI still spans the %s MDE (upper %s) — "
                  "underpowered, the question is unanswered" % (p, mde_txt, _pct(lift.get("rel_ci_high"))))
    if guard.get("assessment") == "AT_RISK":
        reason += "; guardrail %s is AT_RISK (CI upper %+.6g exceeds the %.4g threshold)" % (
            guard.get("metric"), guard.get("ci_high"), guard.get("threshold"))
    return v, reason


# ==========================================================================
# The orchestrator — runs the gates in order and assembles the result
# ==========================================================================
def evaluate(results_path, brief_path, asof_override=None, claimed_duration=None,
             asof_from_request=None, today=None):
    """Run every gate in order and return the payload that both outputs are built from.

    The keys of that payload are a public contract: other tools read them by name. Do not
    rename one to make it read better.
    """
    res = load_results(results_path)
    arms_observed = []
    if res["arm_col"]:
        seen = []
        for r in res["rows"]:
            a = (r.get(res["arm_col"]) or "").strip()
            if a and a not in seen:
                seen.append(a)
        arms_observed = seen
    brief = parse_brief(brief_path, observed_arms=arms_observed)

    check_primary_numeric(res, brief["primary_metric"])

    gates = {}
    # GATE 0. A validity gate.
    gates["design_integrity"] = gate_design_integrity(res, brief)

    # Walk the rows once and collect everything gates 1-4 need. Cheaper than four passes,
    # and it keeps the per-arm bookkeeping in one place.
    exposures = []
    counts = {}
    prim = {}
    prim_by_date = {}
    guard = {}
    pm, gm = brief["primary_metric"], brief["guardrail_metric"]
    if res["arm_col"] and res["date_col"]:
        for r in res["rows"]:
            arm = (r.get(res["arm_col"]) or "").strip()
            if not arm:
                continue
            # Arm counts and exposure dates do not depend on whether the metric columns
            # are readable: SRM is about the assignment, maturity is about the dates. So
            # collect them for every row, because gates 1 and 2 still have to run when
            # GATE 0 failed on a metric column.
            counts[arm] = counts.get(arm, 0) + 1
            d = parse_date(r.get(res["date_col"]))
            if d is not None:
                exposures.append(d)
            pv = _to_float(r.get(pm)) if pm else None
            gv = _to_float(r.get(gm)) if gm else None
            if pv is not None:
                prim.setdefault(arm, []).append(pv)
                if d is not None:
                    prim_by_date.setdefault(d, []).append(pv)
            if gv is not None:
                guard.setdefault(arm, []).append(gv)

    # --- Resolve the as-of date (v1.2). First hit wins, and the provenance travels with
    # the date so a reader always knows where it came from.
    #
    # max(exposure_date) is NOT one of the options. It is a lower bound, and it made
    # mature_share == 1.0 impossible for any window W > 0. Today is an upper bound instead
    # (data cannot describe the future), so it is the most generous defensible assumption —
    # a FAIL under it is certain, not an artefact.
    asof, asof_source, asof_provenance = None, None, None
    if asof_override:
        asof = asof_override
        asof_provenance = "given"
        asof_source = "given explicitly via --asof"
    if asof is None and res.get("asof_col"):
        col_dates = [parse_date(r.get(res["asof_col"])) for r in res["rows"]]
        col_dates = [d for d in col_dates if d]
        if col_dates:
            asof = max(col_dates)
            asof_provenance = "from data"
            asof_source = "from data: max(%s) in the results file" % res["asof_col"]
    if asof is None and asof_from_request:
        asof = asof_from_request
        asof_provenance = "from request"
        asof_source = "from request: a date stated in the ask"
    if asof is None:
        asof = today or datetime.date.today()
        asof_provenance = "assumed: today"
        asof_source = ("assumed: today (the system date). An upper bound on any possible extract "
                       "date, so the most generous defensible value. NOT REPRODUCIBLE — pass "
                       "--asof YYYY-MM-DD to pin it.")
    # GATE 1. A validity gate. Always evaluated (Amendment 1), even if GATE 0 failed, so a
    # second defect is never hidden behind the first.
    if not counts or not (brief["designed_ratio"] or {}):
        gates["srm"] = {
            "status": "NOT_ASSESSABLE", "blocking": True,
            "headline": "not assessable — no designed ratio to test the observed split against",
            "reason": "missing input: %s (GATE 0 could not supply it)"
                      % ("observed arm counts" if not counts
                         else "a designed assignment ratio from the brief")}
    else:
        gates["srm"] = gate_srm(counts, brief["designed_ratio"] or {},
                                ratio_source=brief.get("ratio_source") or "brief (declared)")

    # GATE 2. A validity gate. Always evaluated (Amendment 1), even if GATE 0 or GATE 1
    # failed.
    if not exposures or not pm:
        gates["maturity"] = {
            "status": "NOT_ASSESSABLE", "blocking": True,
            "headline": "not assessable — %s" % ("no primary metric declared, so there is no "
                                                 "observation window to check" if not pm
                                                 else "no parseable exposure dates"),
            "reason": "missing input: %s (GATE 0 could not supply it)"
                      % ("a primary metric name in the brief" if not pm
                         else "parseable exposure dates in the results file")}
    else:
        gates["maturity"] = gate_maturity(
            exposures, brief["metric_window_days"], asof, asof_source, pm,
            asof_provenance=asof_provenance,
            claimed_duration_days=parse_duration_claim(claimed_duration),
            claimed_duration_raw=claimed_duration,
            metric_by_date=prim_by_date)

    all_validity_failures = [g for g in BLOCKING_GATES if gates[g].get("status") == "FAIL"]
    # NOT_ASSESSABLE is neither a failure nor a suppression: the check could not be performed
    # at all, because GATE 0 could not supply its inputs. It gets its own list so that a check
    # nobody ran is never silently dropped from the account, and never reads as a clean PASS.
    validity_not_assessable = [g for g in BLOCKING_GATES
                               if gates[g].get("status") == "NOT_ASSESSABLE"]
    # A WARN is a third thing again: the check ran, but its result is conditional on
    # something that was assumed. It does not make the data unreadable, so it must not
    # block gates 3-4 -- and it must not be left to sit in the gate table where a reader
    # can take the verdict without it.
    validity_warnings = [g for g in BLOCKING_GATES if gates[g].get("status") == "WARN"]
    stopped_at = all_validity_failures[0] if all_validity_failures else None

    # GATES 3 and 4 — the conclusion gates. Both suppressed if ANY validity gate failed.
    if stopped_at:
        gates["guardrail"] = {"status": "NOT_RUN", "reason": "%s failed" % stopped_at}
        gates["lift"] = {"status": "NOT_RUN", "reason": "%s failed" % stopped_at}
    else:
        ctrl_arm = _pick_control(counts, brief["designed_ratio"] or {})
        # Every arm the data actually contains, not just the first one that is not the
        # control. An arm dropped here is an arm nobody reads about.
        t_arms = [a for a in order_arms(list(counts)) if a != ctrl_arm]
        gates["guardrail"] = gate_guardrail(guard, ctrl_arm, t_arms,
                                            gm, brief["guardrail_threshold"],
                                            brief["guardrail_worse_direction"],
                                            threshold_source=brief.get(
                                                "guardrail_threshold_source"))
        gates["lift"] = gate_lift(prim, ctrl_arm, pm, brief["mde"], brief["mde_is_relative"])

    verdict, reason = decide_verdict(gates, stopped_at, all_validity_failures)
    return {
        "experiment": brief["experiment"] or os.path.basename(results_path),
        "asof": asof.isoformat() if asof else None,
        "asof_provenance": asof_provenance,
        "asof_source": asof_source,
        "reproducible": asof_provenance != "assumed: today",
        "verdict": verdict,
        "verdict_reason": reason,
        "winning_arms": ship_eligible_arms(gates.get("lift"), gates.get("guardrail")),
        "arms": arms_observed,
        "gates": {k: gates[k] for k in GATE_ORDER},
        "stopped_at": stopped_at,
        "all_validity_failures": all_validity_failures,
        "validity_not_assessable": validity_not_assessable,
        "validity_warnings": validity_warnings,
    }


def _pick_control(counts, ratio):
    """Decide which arm is the control: a control-like name if there is one, else last."""
    for a in list(counts) + list(ratio):
        if str(a).strip().lower() in CONTROL_NAMES:
            return a
    ordered = order_arms(list(counts) or list(ratio))
    return ordered[-1] if ordered else None


# ==========================================================================
# The human-readable report
# ==========================================================================
_ICON = {"PASS": "PASS", "FAIL": "FAIL", "WARN": "WARN", "NOT_RUN": "NOT RUN",
         "NOT_ASSESSABLE": "NO INPUT"}
GATE_LABEL = {
    "design_integrity": "GATE 0 design_integrity",
    "srm": "GATE 1 srm",
    "maturity": "GATE 2 maturity",
    "guardrail": "GATE 3 guardrail",
    "lift": "GATE 4 lift",
}


def _gate_summary(name, g):
    """The one line of detail printed beside a gate in the gate table."""
    if g["status"] == "NOT_RUN":
        return "suppressed — %s" % g.get("reason", "")
    if g["status"] == "NOT_ASSESSABLE":
        return "not assessable — %s" % g.get("reason", "")
    if name == "design_integrity":
        bad = [c["name"] for c in g.get("checks", []) if c["status"] == "FAIL"]
        warn = [c["name"] for c in g.get("checks", []) if c["status"] == "WARN"]
        if bad:
            return "; ".join(g.get("failures", []))[:300]
        return "brief parsed, columns present, %d rows%s" % (
            g.get("rows_total", 0), (", warnings: %s" % ", ".join(warn)) if warn else "")
    if name == "srm":
        return g.get("detail", "")
    if name == "maturity":
        return g.get("detail", "")
    if name == "guardrail":
        return g.get("detail", "")
    if name == "lift":
        return g.get("detail", "")
    return ""


def _wrap(text, width=96, indent="", first_indent=None):
    """Break text into lines of at most `width`, indenting the continuation lines."""
    import textwrap
    first = first_indent if first_indent is not None else indent
    return textwrap.wrap(str(text), width=width, initial_indent=first,
                         subsequent_indent=indent) or [first]


def render_report(payload):
    """Turn the payload into the text report. One fact, one place.

    FORMATTING LAW: every number reaching prose carries an EXPLICIT format spec
    (%d / %.4g / %+.2f%% / _pct). Never "%s" on a numeric field -- that is the path by
    which an unformatted repr like 2.0938572760580003 lands in a sentence, which a
    formatted-string scan cannot see and a reader mistakes for precision.

    The layout follows from the same rule. WHY carries the headlines. The gate rows are the
    detail layer. The sections after them carry only what the gate rows have not already
    said. Repeating a line word for word reads as padding, not as thoroughness.
    """
    lines = []
    gate0 = payload["gates"]["design_integrity"]
    maturity = payload["gates"]["maturity"]
    fails = payload.get("all_validity_failures") or []

    # Line 1 is the verdict token. Printing it first means that pasting this output
    # verbatim satisfies the "line 1 is the verdict" rule by construction, rather than
    # leaving it to the agent's discipline. The experiment and as-of header is metadata,
    # so it sits underneath.
    lines.append("VERDICT: %s" % payload["verdict"])
    lines.append("readout: %s · as of %s [%s]"
                 % (payload["experiment"], payload["asof"] or "n/a",
                    payload.get("asof_provenance") or "n/a"))
    if not payload.get("reproducible", True):
        lines.append("NOT REPRODUCIBLE: the as-of date was assumed; pass --asof to pin it")
    lines.append("")

    # ---- WHY: exactly ONE form of this reaches the reader.
    #
    # The per-gate block when a validity gate failed, because it is easier to read;
    # otherwise the single verdict_reason string. verdict_reason always stays in the JSON
    # payload as the machine-readable summary, but it must never print alongside the
    # per-gate block. These two branches are mutually exclusive by construction -- do not
    # add a third statement between them, which is how they came apart once already.
    if fails:
        lines.append("WHY: %d validity failure(s); verdict named by the first in gate order."
                     % len(fails))
        for name in fails:
            gate = payload["gates"][name]
            head = "  - %-18s " % (name + ":")
            lines.extend(_wrap(gate.get("headline") or "failed", 96,
                               indent=" " * len(head), first_indent=head))
        if len(fails) > 1:
            lines.append("  Fixing only the first does not make this experiment readable.")
    else:
        lines.extend(_wrap(payload["verdict_reason"], 96, indent="     ", first_indent="WHY: "))

    # ---- Checks that ran but only conditionally. They print HERE, next to the verdict,
    # because a WARN does not block the conclusion gates: the verdict was reached under the
    # assumption, so a reader must not be able to take one without the other.
    for name in payload.get("validity_warnings") or []:
        head = "  CAVEAT %-13s " % (name + ":")
        lines.extend(_wrap(payload["gates"][name].get("headline") or "unconfirmed", 96,
                           indent=" " * len(head), first_indent=head))

    # ---- Checks nobody could run, counted separately from checks that failed.
    not_assessable = payload.get("validity_not_assessable") or []
    if not_assessable:
        lines.append("NOT ASSESSABLE (checked nothing — not a pass): %s"
                     % ", ".join(not_assessable))
        for name in not_assessable:
            gate = payload["gates"][name]
            head = "  - %-18s " % (name + ":")
            lines.extend(_wrap(gate.get("reason") or "no inputs", 96,
                               indent=" " * len(head), first_indent=head))
    lines.append("")

    # ---- The gate table. This is the detail layer, and it is stated once.
    lines.append("GATES (validity 0-2 always evaluated; "
                 "conclusion gates 3-4 suppressed if any fails)")
    for name in GATE_ORDER:
        gate = payload["gates"][name]
        head = "  [%-8s] %-24s " % (_ICON.get(gate["status"], gate["status"]), GATE_LABEL[name])
        lines.extend(_wrap(_gate_summary(name, gate), 96,
                           indent=" " * len(head), first_indent=head))
    lines.append("")

    # ---- GATE 0's own checks: itemise only what is not PASS, and name the passes on one
    # line, so the failures are not buried in a list of things that went fine.
    checks = gate0.get("checks") or []
    if checks:
        notable = [c for c in checks if c["status"] != "PASS"]
        passed = [c["name"] for c in checks if c["status"] == "PASS"]
        lines.append("GATE 0 checks")
        for c in notable:
            head = "  %-5s %-26s " % (c["status"], c["name"])
            lines.extend(_wrap(c["detail"], 96, indent=" " * len(head), first_indent=head))
        if passed and notable:
            lines.extend(_wrap("PASS (%d): %s" % (len(passed), ", ".join(passed)), 96,
                               indent="        ", first_indent="  "))
        elif passed:
            lines.append("  all %d checks pass" % len(passed))
        lines.append("")

    # ---- The exposure window. A plain fact about the data, so it prints every time.
    if isinstance(maturity, dict) and maturity.get("exposure_span_days") is not None:
        lines.append("EXPOSURE WINDOW & DURATION CLAIM")
        lines.append("  observed: %s .. %s = %d day(s), %.1f week(s) of enrolment"
                     % (maturity.get("first_exposure"),
                        maturity.get("last_exposure"),
                        maturity["exposure_span_days"],
                        maturity.get("exposure_span_weeks") or 0.0))
        if maturity.get("metric_window_days"):
            lines.append("  the %d-day metric window then runs from each user's exposure; "
                         "cohort completes %s"
                         % (int(maturity["metric_window_days"]),
                            maturity.get("full_maturity_date")))
        if maturity.get("claimed_duration_days") is not None:
            lines.append("  claimed:  %s = %d day(s) -> %s"
                         % (maturity.get("claimed_duration_raw"),
                            maturity["claimed_duration_days"],
                            "CONSISTENT with the data" if maturity.get("claim_matches_data")
                            else "CONTRADICTED by the data"))
        lines.extend(_wrap(maturity.get("claim_check") or "", 96, indent="  "))
        lines.append("")

    # ---- Assumptions, each with the input that would settle it.
    assumptions = []
    src = gate0.get("designed_ratio_source")
    if src and str(src).startswith("ASSUMED"):
        assumptions.append(
            "Assignment ratio: %s. Shares are never inferred from the observed counts (that "
            "would make an SRM undetectable by construction) — get the sealed design." % src)
    if isinstance(maturity, dict) and maturity.get("asof_is_assumed"):
        # The generosity of the default cuts one way only. Under an upper bound a FAIL is
        # certain; a pass is not, because the bound is on when the metric COULD have been
        # extracted, not on when it was. Say whichever of the two this run earned.
        assumptions.append(
            ("As-of date %s [%s]: today is an upper bound on any extract date (data cannot "
             "describe the future), so it shows only that maturity was POSSIBLE by now — not "
             "that the frozen values were extracted that late. Settled by %s."
             if maturity.get("maturity_unconfirmed") else
             "As-of date %s [%s]: today is an upper bound on any extract date (data cannot "
             "describe the future), so a maturity FAIL under it is certain, not an artefact. "
             "Settled by %s.")
            % (maturity.get("asof"), maturity.get("asof_provenance"),
               maturity.get("asof_settled_by")))
    if assumptions:
        lines.append("ASSUMPTIONS (state these in any report)")
        for a in assumptions:
            lines.extend(_wrap(a, 96, indent="    ", first_indent="  - "))
        lines.append("")

    # ---- The truncation gradient: the trend and the reading of it, with none of the
    # arithmetic restated. Trend, never level. The absolute cohort means stay in the JSON —
    # it is an audit artefact, and without them nobody can re-check why this was called flat
    # — but they never appear in prose, because a reader pattern-matches any number near an
    # experiment to "the result". A pooled mean carries no arm comparison, so it is a
    # data-quality diagnostic, not a conclusion about the treatment effect.
    grad = maturity.get("truncation_gradient") if isinstance(maturity, dict) else None
    if grad:
        band = grad.get("flat_band") or 0.0
        lines.append("TRUNCATION GRADIENT (pooled across arms — no arm comparison; trend only)")
        lines.append("  late-half vs early-half = %s  (flat band +/-%.1f%%, %d cohorts)  ->  %s"
                     % ("n/a" if grad.get("late_vs_early_rel") is None
                        else "%+.2f%%" % (100.0 * grad["late_vs_early_rel"]),
                        100.0 * band, grad.get("n_cohorts") or 0, grad.get("direction")))
        lines.append("  context only, never decides: corr(index, mean)=%s (p=%s)"
                     % ("n/a" if grad.get("corr") is None else "%+.3f" % grad["corr"],
                        "n/a" if grad.get("corr_p_value") is None
                        else "%.4g" % grad["corr_p_value"]))
        if grad.get("reading"):
            lines.extend(_wrap(grad["reading"], 96, indent="  "))
        lines.append("")

    # ---- What was suppressed, and what would unblock it.
    if payload["stopped_at"]:
        lines.append("SUPPRESSED — conclusion gates not run")
        lines.extend(_wrap("No lift, p-value, confidence interval, guardrail verdict or "
                           "'directional' number FOR THE PRIMARY METRIC OR THE GUARDRAIL appears "
                           "above, and none may be added: on invalid data they are "
                           "uninterpretable, not merely uncertain.", 96, indent="  "))
        if (maturity.get("truncation_gradient") or {}).get("corr_p_value") is not None:
            lines.extend(_wrap("The one p-value above belongs to the cohort-trend diagnostic, "
                               "which pools across arms and carries no treatment comparison.",
                               96, indent="  "))
        lines.append("")
        lines.append("TO UNBLOCK — every item, not just the first")
        for name in fails:
            if name == "design_integrity":
                for f in gate0.get("failures", []):
                    lines.extend(_wrap(f, 96, indent="    ", first_indent="  - [design] "))
            elif name == "srm":
                lines.extend(_wrap("Find the assignment bug (logging, bot filtering, eligibility, "
                                   "mid-flight ramp), fix it, re-run. Do not reweight, trim or "
                                   "'repair' the split after the fact.", 96,
                                   indent="    ", first_indent="  - [srm] "))
            elif name == "maturity":
                lines.extend(_wrap("Wait for the cohort to complete (%s), or supply the real "
                                   "extraction date with --asof if the metric was pulled later. "
                                   "Partial maturity is still a FAIL."
                                   % maturity.get("full_maturity_date"), 96,
                                   indent="    ", first_indent="  - [maturity] "))
                if maturity.get("data_integrity_concern"):
                    lines.extend(_wrap("Reconcile the metric column with its pipeline owner "
                                       "first — a rerun of a mis-built metric reproduces the "
                                       "same unusable column.", 96, indent="    ",
                                       first_indent="  - [maturity/integrity] "))
        lines.append("")
    elif payload["gates"]["lift"].get("family_size", 1) > 1:
        lines.extend(_render_multiarm(payload))
    else:
        lift = payload["gates"]["lift"]
        lines.append("PRIMARY METRIC — %s" % lift.get("metric"))
        lines.append("  control   n=%d mean=%.6g" % (int(lift["n_b"]), lift["mean_b"]))
        lines.append("  treatment n=%d mean=%.6g" % (int(lift["n_a"]), lift["mean_a"]))
        lines.append("  abs diff  %+.6g  (95%% CI %+.6g .. %+.6g)"
                     % (lift["diff"], lift["ci_low"], lift["ci_high"]))
        lines.append("  rel lift  %s  (95%% CI %s .. %s)"
                     % (_pct(lift.get("rel_diff")), _pct(lift.get("rel_ci_low")),
                        _pct(lift.get("rel_ci_high"))))
        lines.append("  p-value   %.4g (two-sided Welch, alpha=%s)"
                     % (lift["p_value"], lift["alpha"]))
        lines.append("  vs MDE    MDE=%s, effect %s the bar"
                     % ("n/a" if lift.get("mde") is None else "%.4g%%" % (100 * lift["mde"]),
                        "clears" if lift.get("meets_mde") else "does not clear"))
        lines.append("")
    return "\n".join(lines)


def _render_multiarm(payload):
    """The primary-metric and guardrail blocks when the design ran more than two arms.

    One row per treatment arm, always, in a fixed alphabetical order that owes nothing to
    which arm did best. The A/B layout above is untouched: a two-arm readout renders
    exactly the document it rendered before A/B/n was handled.

    FORMATTING LAW applies here too — every number is formatted with an explicit spec and
    only then padded into its column.
    """
    lift = payload["gates"]["lift"]
    guard = payload["gates"]["guardrail"]
    testable = [c for c in lift.get("comparisons") or [] if c.get("status") == "PASS"]
    lines = []

    arm_w = max([11] + [len(str(c["arm"])) for c in lift.get("comparisons") or []])
    row = "  %-" + str(arm_w) + "s %6s %10s %12s %9s %11s %9s  %s"

    lines.append("PRIMARY METRIC — %s   (%d treatment arms vs %s; every arm is reported)"
                 % (lift.get("metric"), lift.get("family_size") or 0, lift.get("control_arm")))
    lines.append("  %-*s n=%d mean=%.6g" % (arm_w, lift.get("control_arm"),
                                            int(lift.get("control_n") or 0),
                                            lift.get("control_mean") or 0.0))
    lines.append(row % ("arm", "n", "mean", "abs diff", "rel lift", "p-value", "Holm thr",
                        "after Holm"))
    for c in lift.get("comparisons") or []:
        if c.get("status") != "PASS":
            lines.append("  %-*s %s" % (arm_w, c["arm"],
                                        c.get("detail") or "not testable"))
            continue
        lines.append(row % (c["arm"], "%d" % int(c["n_a"]), "%.6g" % c["mean_a"],
                            "%+.6g" % c["diff"], _pct(c["rel_diff"]),
                            "%.4g" % c["p_value"], "%.4g" % c["holm_threshold"],
                            "significant" if c["significant"] else "not significant"))
        lines.append("  %-*s 95%% CI abs %+.6g .. %+.6g   rel %s .. %s"
                     % (arm_w, "", c["ci_low"], c["ci_high"],
                        _pct(c["rel_ci_low"]), _pct(c["rel_ci_high"])))
    mult = lift.get("multiplicity") or {}
    k = mult.get("family_size") or 0
    if k:
            lines.extend(_wrap("%d testable treatment arm%s is %d hypothes%s about one control, so "
                           "the alpha=%s bar was corrected by Holm-Bonferroni: the smallest "
                           "p-value faced the strictest threshold and testing stopped at the "
                           "first arm that failed. Threshold%s %s."
                           % (k, "" if k == 1 else "s", k, "is" if k == 1 else "es",
                              mult.get("alpha"), ":" if k == 1 else "s:",
                              ", ".join("%s %.4g" % (a, t)
                                        for a, t in (mult.get("thresholds") or {}).items())),
                           96, indent="                ",
                           first_indent="  MULTIPLICITY  "))
    if testable and lift.get("mde") is not None:
        clears = [c["arm"] for c in testable if c.get("meets_mde")]
        misses = [c["arm"] for c in testable if not c.get("meets_mde")]
        lines.extend(_wrap("MDE=%.4g%%. Point estimate clears it: %s. Does not: %s. Clearing "
                           "the MDE is not the same question as being significant, and an arm "
                           "can do either without the other."
                           % (100.0 * lift["mde"], ", ".join(clears) or "none",
                              ", ".join(misses) or "none"), 96,
                           indent="                ", first_indent="  vs MDE        "))
    lines.append("")

    gcomps = guard.get("comparisons") or []
    if gcomps:
        lines.append("GUARDRAIL — %s   (one comparison per treatment arm)"
                     % guard.get("metric"))
        for c in gcomps:
            if c.get("assessment") is None:
                lines.append("  %-*s %s" % (arm_w, c["arm"], c.get("detail") or "not testable"))
                continue
            lines.append("  %-*s diff %+.6g  (95%% CI %+.6g .. %+.6g)  vs %s-of-%.4g  ->  %s"
                         % (arm_w, c["arm"], c["diff"], c["ci_low"], c["ci_high"],
                            "worsen-by" if guard.get("worse_direction") == "increase"
                            else "drop-by", c["threshold"], c["assessment"]))
        lines.append("")
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Gated experiment readout",
        epilog="REPRODUCIBILITY: with no --asof and no as-of column in the CSV, the as-of date "
               "falls back to today's system date, so the maturity gate (and therefore the "
               "verdict) can change from one day to the next. Any run that must be reproducible "
               "-- fixtures, tests, anything you will cite later -- MUST pass an explicit --asof. "
               "The resolved date and its provenance are always recorded in the payload "
               "(asof, asof_provenance, reproducible).")
    ap.add_argument("--results", required=True, help="experiment_results.csv")
    ap.add_argument("--brief", required=False, default=None, help="brief.yaml (sealed design)")
    ap.add_argument("--asof", default=None,
                    help="metric extraction date YYYY-MM-DD (provenance 'given'). Pass this for "
                         "any reproducible run: without it the fallback is today's system date.")
    ap.add_argument("--asof-from-request", dest="asof_from_request", default=None,
                    help="a date stated in the ask, YYYY-MM-DD (provenance 'from request'); used "
                         "only when --asof is absent and the CSV has no as-of column")
    ap.add_argument("--today", default=None,
                    help="TEST-ONLY: override the system date behind the 'assumed: today' "
                         "fallback (YYYY-MM-DD), so a fixture's verdict does not drift as days "
                         "pass. NEVER use it on real data: moving the clock forward to make the "
                         "maturity gate pass falsifies the readout. A real extraction date "
                         "belongs in --asof.")
    ap.add_argument("--claimed-duration", dest="claimed_duration", default=None,
                    help="duration asserted in the ask, e.g. '4 weeks' — checked against the data")
    ap.add_argument("--json", action="store_true", help="print only the JSON payload")
    args = ap.parse_args(argv)

    if not os.path.exists(args.results):
        sys.stderr.write("input error: results file not found: %s\n" % args.results)
        return 1
    asof = None
    if args.asof:
        asof = parse_date(args.asof)
        if asof is None:
            sys.stderr.write("input error: --asof must be YYYY-MM-DD, got %r\n" % args.asof)
            return 1
    asof_req = None
    if args.asof_from_request:
        asof_req = parse_date(args.asof_from_request)
        if asof_req is None:
            sys.stderr.write("input error: --asof-from-request must be YYYY-MM-DD, got %r\n"
                             % args.asof_from_request)
            return 1
    today = None
    if args.today:
        today = parse_date(args.today)
        if today is None:
            sys.stderr.write("input error: --today must be YYYY-MM-DD, got %r\n" % args.today)
            return 1
    try:
        payload = evaluate(args.results, args.brief, asof_override=asof,
                           claimed_duration=args.claimed_duration,
                           asof_from_request=asof_req, today=today)
    except InputDataError as exc:
        sys.stderr.write("input error: %s\n" % exc)
        return 1
    except Exception as exc:  # runtime error -> exit 1, never a traceback
        sys.stderr.write("runtime error: %s: %s\n" % (type(exc).__name__, exc))
        return 1

    if args.json:
        sys.stdout.write(json.dumps(payload, indent=2, sort_keys=False, default=str) + "\n")
    else:
        sys.stdout.write(render_report(payload) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
