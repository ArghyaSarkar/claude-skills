"""Aggregate repeated runs of the same case into per-criterion pass rates.

WHY RATES AND NOT MEANS
A mean of 11.66/12 across two runs hides whether a criterion passed twice or
passed once and failed once. Those are very different facts about a skill: the
first is a working rule, the second is a coin flip that happened to land well.
The arena draws ONE sample, so what matters is the per-trial rate of each
criterion, with the counts visible.

DISTINGUISHING "UNLUCKY RUN" FROM "RULE NOT BINDING"
A criterion that fails sometimes is either a mostly-working rule with drift, or a
rule that is not actually constraining the model. The separation used here:

  rate == 1.0                 BINDING      -- no counter-example in n runs
  0.80 <= rate < 1.0          DRIFT        -- holds usually; a real but occasional
                                             escape. Worth hardening.
  0.20 <= rate < 0.80         NOT BINDING  -- the instruction is not controlling
                                             behaviour. This is a SKILL defect,
                                             not an unlucky sample.
  0 < rate < 0.20             INEFFECTIVE  -- the rule is essentially absent
  rate == 0.0                 FAILING      -- consistently wrong; at least it is
                                             deterministic and easy to fix

The bands are judgement, not statistics: at n=5 the 95% CI on any interior rate
is enormous. They are there to route attention, and the counts are always printed
next to them so a reader can apply their own scepticism. With n=5, a single
failure (rate 0.80) is the smallest observable departure from binding.

stdlib only.
"""

from collections import OrderedDict

PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"


def classify(rate, n_graded, n_runs=None):
    """Coverage is reported before the rate, because a rate computed on a
    minority of runs is not a rate. O3_suppression routinely goes UNKNOWN when a
    hedge needs adjudication, so it can show "100%" on a 2-of-5 denominator --
    which would read as a binding rule when it is really thin evidence."""
    if n_graded == 0:
        return "UNGRADED"
    if n_runs and n_graded * 2 < n_runs:
        return "LOW COVERAGE (%d/%d graded)" % (n_graded, n_runs)
    if rate >= 1.0:
        return "BINDING"
    if rate >= 0.80:
        return "DRIFT"
    if rate >= 0.20:
        return "NOT BINDING"
    if rate > 0.0:
        return "INEFFECTIVE"
    return "FAILING"


def per_criterion(cards):
    """cards: list of scorecards for the SAME case. -> OrderedDict criterion -> stats"""
    out = OrderedDict()
    keys = []
    for c in cards:
        for k in c["cells"]:
            if k not in keys:
                keys.append(k)
    for k in sorted(keys):
        p = f = u = 0
        for c in cards:
            v = (c["cells"].get(k) or {}).get("verdict")
            if v == PASS:
                p += 1
            elif v == FAIL:
                f += 1
            else:
                u += 1
        graded = p + f
        rate = (p / float(graded)) if graded else 0.0
        out[k] = {"pass": p, "fail": f, "unknown": u, "n": len(cards),
                  "graded": graded, "rate": rate,
                  "verdict": classify(rate, graded, len(cards))}
    return out


def render(by_case, threshold_note=True):
    L = []
    W = 92
    L.append("")
    L.append("=" * W)
    L.append("PER-CRITERION PASS RATES ACROSS REPEATED RUNS")
    L.append("counts are shown because a rate without a denominator is not a finding")
    L.append("=" * W)
    flagged = []
    for case_id in sorted(by_case):
        stats = by_case[case_id]
        n = max((s["n"] for s in stats.values()), default=0)
        L.append("")
        L.append("%s   (n=%d runs)" % (case_id, n))
        L.append("  %-24s %-7s %-9s %-6s %s" % ("criterion", "pass/n", "graded", "rate", "reading"))
        L.append("  " + "-" * (W - 2))
        for k, s in stats.items():
            rate = ("  -  " if not s["graded"] else "%4.0f%%" % (100 * s["rate"]))
            L.append("  %-24s %d/%-5d %-9s %-6s %s"
                     % (k, s["pass"], s["n"],
                        "%d/%d" % (s["graded"], s["n"]),
                        rate, s["verdict"]))
            if s["verdict"] in ("NOT BINDING", "INEFFECTIVE", "FAILING") and s["graded"]:
                flagged.append((case_id, k, s))
    if flagged:
        L.append("")
        L.append("!! FLAGGED -- variance suggests the RULE is not binding, not an unlucky run")
        L.append("-" * W)
        for case_id, k, s in flagged:
            L.append("  %-24s %-24s %d pass / %d fail  -> %s"
                     % (case_id, k, s["pass"], s["fail"], s["verdict"]))
        L.append("")
        L.append("  A rule that holds in 3 of 5 runs is not controlling the model --")
        L.append("  but check the DETECTOR before blaming the skill. These checks are")
        L.append("  regexes over free prose, and more runs means more phrasings to")
        L.append("  mishandle. Read the matched span in the cell note first; three")
        L.append("  false positives were found this way (DECISIONS.md D7).")
    else:
        L.append("")
        L.append("No criterion fell below the DRIFT band. Every graded rule held in")
        L.append("at least 80% of runs.")
    if threshold_note:
        L.append("")
        L.append("Reliability note: the arena draws ONE sample, so the per-trial rate above")
        L.append("is the arena-relevant number. A criterion at 80% has a 0.8 chance of")
        L.append("holding on the single graded question; across 5 independent criteria at")
        L.append("80% each, the chance all hold is 0.8^5 = 33%.")
    L.append("=" * W)
    return "\n".join(L)
