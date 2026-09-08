"""Roll observed signals up to the arena's 12-point scale.

COMPARABILITY IS THE CONSTRAINT
-------------------------------
The arena scores Triggering 0-4, Process 0-4, Output 0-4. This module must land
on the same 12 points or the number it prints is not comparable, which was the
whole point of building it. So:

  * Nothing outside the arena's three axes enters the 12 points. The
    false-positive rate on near-miss prompts is a real defect signal and it is
    reported prominently -- but as a DIAGNOSTIC, because the arena does not
    measure it and folding it in would silently shift the scale.
  * UNKNOWN cells are excluded from the denominator rather than counted as
    failures, and the count of excluded cells is printed next to every score. A
    score computed from three of six sub-checks is reported as such.
  * Every cell records whether it was decided by MACHINE, JUDGE or HUMAN.

AXIS SHAPES
-----------
Triggering: banded from the measured fire rate. Near-binary in the arena (4 / 2 /
0), but a skill that fires 6 times in 10 is a real risk in a one-shot arena run,
so the bands distinguish it from one that fires 10 in 10 without inventing
precision the rubric does not have.

Process: exactly 4 binary signals, 1 point each. This mirrors the arena's "one
point per step-quality signal" literally.

Output: 7 binary sub-criteria normalised to 4 points. The arena does not specify
a decomposition for Output, so the harness uses the finest-grained one that the
research supports and rescales.
"""

import json

PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"
MACHINE, JUDGE, HUMAN = "machine", "judge", "human"

PROCESS_SIGNALS = ["P1_gate_order", "P2_scripts_invoked",
                   "P3_references_cited", "P4_no_improvisation"]
OUTPUT_CRITERIA = ["O1_verdict", "O2_enumeration", "O3_suppression", "O4_format",
                   "O5_asof_calibration", "O6_claim_vs_data", "O7_no_softening",
                   "O8_truncation_gradient"]


# ---------------------------------------------------------------------------
def triggering_score(fire_rate_unprompted, explicit_invocation_fires):
    """Arena bands, with the middle of the range made visible.

    Arena rubric: 4 = fired on its own; 2 = only via /skill; 0 = never.
    """
    if fire_rate_unprompted is None:
        return None, "not measured"
    r = fire_rate_unprompted
    if r >= 0.8:
        return 4, "fires unprompted reliably (%.0f%%)" % (r * 100)
    if r >= 0.5:
        return 3, ("fires unprompted but UNRELIABLY (%.0f%%) -- the arena is a "
                   "single shot, so this is closer to a coin-flip than to a 4"
                   % (r * 100))
    if r > 0.0:
        return 2, ("fires unprompted only rarely (%.0f%%); scored as the arena's "
                   "explicit-invocation band" % (r * 100))
    if explicit_invocation_fires:
        return 2, "never fired unprompted; fires only when invoked explicitly"
    return 0, "never fired, even when invoked explicitly"


def _tally(cells, keys):
    passed = sum(1 for k in keys if cells.get(k, {}).get("verdict") == PASS)
    failed = sum(1 for k in keys if cells.get(k, {}).get("verdict") == FAIL)
    unknown = [k for k in keys if cells.get(k, {}).get("verdict") in (UNKNOWN, None)]
    graded = passed + failed
    return passed, failed, graded, unknown


def process_score(cells):
    passed, failed, graded, unknown = _tally(cells, PROCESS_SIGNALS)
    if graded == 0:
        return None, "no process signal was observable", unknown
    # 1 point per signal; ungraded signals are excluded and the score is
    # rescaled over what was actually observable, so a partial run is not
    # silently penalised.
    score = 4.0 * passed / graded
    return round(score, 2), "%d/%d observable signals passed" % (passed, graded), unknown


def output_score(cells):
    passed, failed, graded, unknown = _tally(cells, OUTPUT_CRITERIA)
    if graded == 0:
        return None, "no output criterion was gradeable", unknown
    score = 4.0 * passed / graded
    return round(score, 2), "%d/%d graded criteria passed" % (passed, graded), unknown


def build(case_id, cells, trig=None, diagnostics=None):
    p, pnote, punk = process_score(cells)
    o, onote, ounk = output_score(cells)
    t, tnote = (trig if trig else (None, "not measured in this run"))
    parts = [x for x in (t, p, o) if x is not None]
    total = round(sum(parts), 2) if parts else None
    return {
        "case_id": case_id,
        "axes": {
            "triggering": {"score": t, "max": 4, "note": tnote},
            "process": {"score": p, "max": 4, "note": pnote, "ungraded": punk},
            "output": {"score": o, "max": 4, "note": onote, "ungraded": ounk},
        },
        "total": total,
        "max": 12,
        "complete": len(parts) == 3,
        "cells": cells,
        "diagnostics": diagnostics or {},
    }


# ---------------------------------------------------------------------------
def render(cards, trig_summary=None, baseline=None):
    L = []
    W = 78
    L.append("=" * W)
    L.append("EXPERIMENT-READOUT SKILL -- EVAL SCORECARD")
    L.append("scale: 12 points (Triggering 4 + Process 4 + Output 4), arena-comparable")
    L.append("=" * W)

    if trig_summary:
        L.append("")
        L.append("TRIGGERING (machine-measured from the tool trace)")
        L.append("-" * W)
        for k in ("should_fire", "should_not_fire"):
            s = trig_summary.get(k)
            if not s:
                continue
            L.append("  %-15s fired %2d/%-2d  rate %5.1f%%   %s"
                     % (k, s["fired"], s["n"], 100.0 * s["rate"],
                        "(target: high)" if k == "should_fire" else "(target: LOW -- false positives)"))
        for k in ("train", "test"):
            s = trig_summary.get("split_" + k)
            if s:
                L.append("    %-13s should-fire rate %5.1f%%  (held-out score is the "
                         "honest one)" % (k, 100.0 * s))
        if trig_summary.get("per_prompt"):
            L.append("")
            L.append("  per-prompt detail:")
            for r in trig_summary["per_prompt"]:
                mark = "FIRE" if r["fired"] else "----"
                flag = ""
                if r["expected"] == "fire" and not r["fired"]:
                    flag = "  <-- MISS"
                if r["expected"] == "no_fire" and r["fired"]:
                    flag = "  <-- FALSE POSITIVE"
                L.append("    [%s] %-4s conf=%-6s %-52s%s"
                         % (mark, r["id"], r.get("confidence", "?"),
                            r["prompt"][:52], flag))

    L.append("")
    L.append("PER-CASE SCORES")
    L.append("-" * W)
    L.append("  %-24s %5s %5s %5s %6s  %s"
             % ("case", "trig", "proc", "out", "total", "note"))
    tot, n = 0.0, 0
    for c in cards:
        a = c["axes"]
        f = lambda x: ("  -  " if x["score"] is None else "%5.2f" % x["score"])
        note = "" if c["complete"] else "PARTIAL"
        L.append("  %-24s %s %s %s %6s  %s"
                 % (c["case_id"], f(a["triggering"]), f(a["process"]),
                    f(a["output"]),
                    ("  -  " if c["total"] is None else "%5.2f" % c["total"]), note))
        if c["total"] is not None:
            tot += c["total"]; n += 1
    L.append("-" * W)
    if n:
        L.append("  MEAN TOTAL over %d scored case(s): %.2f / 12" % (n, tot / n))
    else:
        L.append("  MEAN TOTAL: not computable -- no case had all three axes measured")

    # ungraded cells, stated plainly
    L.append("")
    L.append("UNGRADED CELLS (excluded from the denominator, not counted as failures)")
    L.append("-" * W)
    any_unk = False
    for c in cards:
        u = (c["axes"]["process"].get("ungraded") or []) + \
            (c["axes"]["output"].get("ungraded") or [])
        if u:
            any_unk = True
            L.append("  %-24s %s" % (c["case_id"], ", ".join(u)))
    if not any_unk:
        L.append("  none")

    if baseline:
        L.append("")
        L.append("BASELINE ARM (skill unavailable) -- RED phase")
        L.append("-" * W)
        for k, v in sorted(baseline.get("failure_rates", {}).items()):
            L.append("  %-28s %s" % (k, v))
        if baseline.get("rationalizations"):
            L.append("")
            L.append("  verbatim rationalizations captured without the skill:")
            for q in baseline["rationalizations"][:12]:
                L.append("    \"%s\"" % q[:150])
        if baseline.get("did_not_fail"):
            L.append("")
            L.append("  !! BASELINE DID NOT FAIL on: %s"
                     % ", ".join(baseline["did_not_fail"]))
            L.append("     For those cases the skill is not demonstrably necessary. "
                     "That is a real finding, not a harness bug.")

    L.append("")
    L.append("DIAGNOSTICS (real defects, deliberately OUTSIDE the 12 points)")
    L.append("-" * W)
    fp = (trig_summary or {}).get("should_not_fire", {}).get("rate")
    if fp is not None:
        L.append("  false-positive firing rate: %.1f%%  %s"
                 % (100.0 * fp,
                    "(over-broad description)" if fp > 0.2 else "(acceptable)"))
    for c in cards:
        for k, v in (c.get("diagnostics") or {}).items():
            L.append("  %-24s %s: %s" % (c["case_id"], k, v))
    L.append("")
    L.append("=" * W)
    return "\n".join(L)
