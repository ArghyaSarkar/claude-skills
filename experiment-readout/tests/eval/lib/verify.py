"""Verify each generated golden is internally consistent with the contract
(v1.1 / Amendment 1) AND decided by a WIDE margin.

Margin discipline is the whole point. lib/refcalc.py is a normal approximation;
if a case's verdict hinged on p = 0.049 vs 0.051, a disagreement between refcalc
and the skill's exact gates.py would be meaningless noise and the harness would
emit false failures. So every case must clear these margins:

  MARGIN_SIG    p < 0.005     when the golden needs "significant"
  MARGIN_NULL   p > 0.20      when the golden needs "not significant"
  MDE ratio     rel_lift >= 1.5x the MDE, or <= 0.6x it
  GUARD_MARGIN  guardrail diff at least 0.3pp clear of the 1pp threshold
  SRM           p < 1e-4 for a breach, p > 0.05 for a clean split

A case that cannot clear its margin is a BROKEN CASE, not a failing skill, and
bin/gen_cases.py exits non-zero so it can never be silently used.
"""

MDE = 0.03
MARGIN_SIG = 0.005
MARGIN_NULL = 0.20
GUARD_THRESHOLD = 0.01
GUARD_MARGIN = 0.003
VALIDITY_ORDER = ["design_integrity", "srm", "maturity"]


def verify_all(goldens):
    problems, notes = [], []
    for g in goldens:
        p, n = _verify_one(g)
        problems.extend(p)
        notes.extend(n)
    return (len(problems) == 0), problems, notes


def _verify_one(g):
    cid = g["case_id"]
    ref = g["reference"]
    bad, ok = [], []

    def B(m):
        bad.append("%-22s BROKEN: %s" % (cid, m))

    def O(m):
        ok.append("%-22s ok    : %s" % (cid, m))

    fails = g["all_validity_failures"]

    # ---- ordering + verdict naming (Amendment 1) -----------------------
    if fails != [x for x in VALIDITY_ORDER if x in fails]:
        B("all_validity_failures %s is not in gate order %s" % (fails, VALIDITY_ORDER))
    expected_verdict = {
        "design_integrity": "INVALID-DESIGN",
        "srm": "INVALID-SRM",
        "maturity": "INVALID-IMMATURE",
    }
    if fails:
        if g["verdict"] != expected_verdict[fails[0]]:
            B("verdict %s is not named by the first failing gate %s"
              % (g["verdict"], fails[0]))
        else:
            O("verdict named by first failing gate (%s -> %s); %d failure(s) to "
              "enumerate: %s" % (fails[0], g["verdict"], len(fails), ", ".join(fails)))
        if not g["conclusions_suppressed"]:
            B("validity failed but conclusions_suppressed is False")
        if g["suppressed_gates"] != ["guardrail", "lift"]:
            B("Amendment 1 requires BOTH guardrail and lift suppressed, got %s"
              % g["suppressed_gates"])
    else:
        if g["conclusions_suppressed"]:
            B("no validity failure but conclusions_suppressed is True")
        O("all validity gates pass; conclusions are required, not suppressed")

    # ---- SRM margin ----------------------------------------------------
    sp = ref["srm"]["p_value"]
    if "srm" in fails:
        if not sp < 1e-4:
            B("SRM p=%.3g not decisively below alpha=0.001" % sp)
        else:
            O("SRM breach decisive (chi2=%.1f, p=%.1e)" % (ref["srm"]["chi2"], sp))
    else:
        if not sp > 0.05:
            B("SRM p=%.3g too close to alpha for a case requiring SRM to PASS" % sp)
        else:
            O("SRM clean (p=%.2f)" % sp)

    # ---- maturity ------------------------------------------------------
    if "maturity" in fails:
        if ref["mature_share"] >= 1.0:
            B("maturity listed as failing but mature_share=%s" % ref["mature_share"])
        else:
            O("maturity fails (mature_share=%.1f, span=%dd, window=%dd, asof %s '%s')"
              % (ref["mature_share"], ref["exposure_span_days"],
                 g["asof"]["metric_window_days"], g["asof"]["effective"],
                 g["asof"]["provenance"]))
    else:
        if ref["mature_share"] < 1.0:
            B("maturity expected to PASS but mature_share=%s -- the case must state "
              "an as-of at least %dd after the last exposure"
              % (ref["mature_share"], g["asof"]["metric_window_days"]))
        else:
            O("maturity passes via stated asof=%s" % g["asof"]["given"])

    # ---- as-of epistemics (Amendment 2) --------------------------------
    if not g["asof"]["must_flag_as_assumption"]:
        B("every as-of is an assumption under Amendment 2 -- even the today default")

    # ---- maturity branch consistency -----------------------------------
    m = g["maturity"]
    share = m["mature_share"]
    expected_branch = ("full" if share >= 1.0 else
                       ("none" if share <= 0.0 else "partial"))
    if m["branch"] != expected_branch:
        B("maturity branch %s disagrees with mature_share %.3f" % (m["branch"], share))
    elif m["branch"] == "partial":
        if "differential follow-up" not in m["failure_mechanism"]:
            B("partial maturity must name differential follow-up as the mechanism")
        else:
            O("maturity PARTIAL (%.1f%% of %d mature) -- fails on differential "
              "follow-up, not on 'nothing is mature'" % (100 * share, m["n_total"]))
    elif m["branch"] == "full":
        O("maturity full under the %s as-of %s"
          % (g["asof"]["provenance"], g["asof"]["effective"]))

    # ---- truncation gradient -------------------------------------------
    tg = g["truncation_gradient"]
    if tg["graded"]:
        strong = tg["corr_cohort_index_vs_mean"] <= -0.50 and tg["late_vs_early_rel"] <= -0.03
        if strong != (tg["branch"] == "gradient_present"):
            B("gradient branch %s disagrees with corr=%+.2f / late_vs_early=%+.3f"
              % (tg["branch"], tg["corr_cohort_index_vs_mean"], tg["late_vs_early_rel"]))
        elif tg["branch"] == "gradient_present":
            O("truncation gradient PRESENT (corr=%+.2f, late %+.1f%% vs early) -> "
              "positive evidence of truncation"
              % (tg["corr_cohort_index_vs_mean"], 100 * tg["late_vs_early_rel"]))
        else:
            O("truncation gradient ABSENT (corr=%+.2f, late %+.1f%%) -> data-integrity "
              "reading: values show no follow-up dependence they must have"
              % (tg["corr_cohort_index_vs_mean"], 100 * tg["late_vs_early_rel"]))
        # guard the separation: a case must not sit near the boundary
        if -0.60 < tg["corr_cohort_index_vs_mean"] < -0.40:
            B("gradient correlation %+.2f sits on the classifier boundary; the case "
              "would flip branch on noise" % tg["corr_cohort_index_vs_mean"])

    # ---- conclusion gates, only where they are reached -----------------
    if not fails and g["task"] == "readout":
        gd = ref["guardrail"]["diff"]
        p = ref["lift"]["p_value"]
        rel = ref["lift"]["rel_diff"]
        v = g["verdict"]
        if v == "NO-SHIP" and ref["guardrail"]["breach"]:
            if gd < GUARD_THRESHOLD + GUARD_MARGIN:
                B("guardrail diff %+.4f within %.3f of the threshold" % (gd, GUARD_MARGIN))
            else:
                O("guardrail BREACH decisive (diff=%+.4f vs 1pp) -> NO-SHIP" % gd)
        elif gd > GUARD_THRESHOLD - GUARD_MARGIN:
            B("guardrail diff %+.4f too near the threshold for a non-breach case" % gd)

        if v == "SHIP":
            if p >= MARGIN_SIG:
                B("SHIP needs decisive significance, p=%.3g" % p)
            elif rel < MDE * 1.5:
                B("SHIP rel_lift %.3f not comfortably above the MDE" % rel)
            elif ref["lift"]["rel_ci_low"] <= 0:
                B("SHIP needs a CI excluding 0, rel_ci_low=%.4f" % ref["lift"]["rel_ci_low"])
            else:
                O("SHIP margins good (rel=%+.1f%%, p=%.1e, rel_ci_low=%+.2f%%)"
                  % (rel * 100, p, ref["lift"]["rel_ci_low"] * 100))
        elif v == "NO-SHIP" and not ref["guardrail"]["breach"]:
            # Two distinct routes reach NO-SHIP here and they need different
            # margins: (a) significant but below the MDE, (b) not significant but
            # the CI already rules the MDE out. Conflating them produced a false
            # BROKEN report on the first run of this verifier.
            if p < 0.05:
                if p >= MARGIN_SIG:
                    B("sig-below-MDE case needs p<%.3f, got %.3g" % (MARGIN_SIG, p))
                elif rel > MDE * 0.6:
                    B("rel_lift %.3f too close to the MDE to be clearly below it" % rel)
                else:
                    O("sig-below-MDE margins good (rel=%+.1f%% vs MDE %.0f%%, p=%.1e)"
                      % (rel * 100, MDE * 100, p))
            else:
                ch = ref["lift"]["rel_ci_high"]
                if ch >= MDE:
                    B("MDE-ruled-out route needs rel_ci_high < MDE, got %+.3f" % ch)
                elif ch > MDE * 0.85:
                    B("rel_ci_high %+.3f too close to the MDE to be clearly ruled out" % ch)
                else:
                    O("MDE-ruled-out margins good (p=%.2f, rel_ci_high=%+.1f%% < MDE)"
                      % (p, ch * 100))
        elif v == "INCONCLUSIVE":
            if p <= MARGIN_NULL:
                B("INCONCLUSIVE needs a decisively null p, got %.3g" % p)
            elif ref["lift"]["rel_ci_high"] <= MDE * 1.3:
                B("CI upper %+.3f does not admit the MDE with margin -> the contract "
                  "would call this NO-SHIP, not INCONCLUSIVE" % ref["lift"]["rel_ci_high"])
            else:
                O("INCONCLUSIVE margins good (p=%.2f, rel_ci_high=%+.1f%% admits MDE)"
                  % (p, ref["lift"]["rel_ci_high"] * 100))

    if g["task"] == "power":
        pw = ref["power"]
        if pw["maturation_days"] != 28:
            B("power golden must carry a 28d maturation tail")
        else:
            O("power golden: n/arm=%d, exposure=%dd + maturation=%dd = %dd (%.1f wk)"
              % (pw["n_per_arm"], pw["exposure_days"], pw["maturation_days"],
                 pw["total_days"], pw["total_weeks"]))

    if g["claim_vs_data"]["graded"]:
        O("claim-vs-data graded: ask claims '%s', data spans %dd"
          % (g["claim_vs_data"]["claimed_duration"], g["claim_vs_data"]["actual_span_days"]))
    return bad, ok
