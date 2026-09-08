"""Deterministic generator for eval case inputs + golden answers.

Every fixture is produced by a hand-rolled LCG + Box-Muller so the CSVs are
byte-identical on any Python 3.x, forever. `random` is deliberately NOT used:
its gauss() stream is not guaranteed stable across interpreter versions, and a
golden answer that drifts with the interpreter is worthless.

DESIGN RULE FOR EVERY CASE: the arena runs a HIDDEN dataset of the same theme,
so a case that can be passed by memorising a number is a wasted case. Each case
below is built so that the only way to get the golden verdict is to apply the
METHOD in the contract's gate order. Cases come in matched pairs that differ in
exactly one gate-relevant fact (c02 vs c03 differ only in the arm split; c04 vs
c05 only in cancel_rate; c04 vs c06 only in effect size) so a degenerate agent
that always answers "INVALID" or always answers "SHIP" scores near zero.
"""

import json
import math
import os
from datetime import date, timedelta

from . import refcalc

EVAL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES_DIR = os.path.join(EVAL_ROOT, "cases")


class LCG:
    """Numerical Recipes 32-bit LCG + Box-Muller. Stable across versions."""

    def __init__(self, seed):
        self.s = seed & 0xFFFFFFFF
        self._spare = None

    def u(self):
        self.s = (1664525 * self.s + 1013904223) & 0xFFFFFFFF
        # avoid exact 0 for log()
        return (self.s + 0.5) / 4294967296.0

    def gauss(self):
        if self._spare is not None:
            g, self._spare = self._spare, None
            return g
        u1, u2 = self.u(), self.u()
        r = math.sqrt(-2.0 * math.log(u1))
        self._spare = r * math.sin(2.0 * math.pi * u2)
        return r * math.cos(2.0 * math.pi * u2)

    def normal(self, mu, sd):
        return mu + sd * self.gauss()


def _clip(x, lo, hi):
    return lo if x < lo else (hi if x > hi else x)


# ---------------------------------------------------------------------------
# Case specifications
# ---------------------------------------------------------------------------
# n_t/n_c            : arm sizes (drives the SRM gate)
# mean_c/mean_t, sd  : primary metric completed_orders_28d
# cr_c/cr_t, cr_sd   : guardrail cancel_rate
# first_exposure/span: exposure window (drives the maturity gate)
# sealed             : brief seal date (drives the design-integrity gate)
# asof               : analysis date stated in the prompt; None = let it default
#                      to max(exposure_date), which makes maturity unsatisfiable
# expect             : golden verdict + which gate halts the run

# ---------------------------------------------------------------------------
# Case specifications  (Amendment 1 / v1.1 semantics)
# ---------------------------------------------------------------------------
# n_t/n_c            : arm sizes (drives the SRM gate)
# mean_c/mean_t, sd  : primary metric completed_orders_28d
# cr_c/cr_t, cr_sd   : guardrail cancel_rate
# first_exposure/span: exposure window (drives the maturity gate)
# sealed             : brief seal date (drives the design-integrity gate)
# asof               : analysis date stated in the prompt. None means the skill
#                      must fall back to max(exposure_date) AND label that as an
#                      assumed conservative lower bound, not a fact.
# duration_claim     : the (false) duration the ask asserts, or None. Present
#                      means the claim-vs-data dimension is graded on this case.
# validity_failures  : ORDERED list of every failing validity gate. The verdict
#                      is named by the FIRST one; the response must enumerate
#                      ALL of them.
# central            : mirrors the real arena dataset's defect structure.

# Amendment 2 (v1.2): the maturity gate's as-of resolution order is
#   explicit --asof  >  an as-of column in the CSV  >  a date stated in the ask
#   >  the SYSTEM DATE (today).
# Defaulting to today is an UPPER bound on any possible extract date, so a
# maturity failure under it is certain rather than an artefact of the default.
# Consequence for this harness: goldens depend on "today", so REFERENCE_TODAY is
# pinned and recorded in every golden. Regenerate with --today to match the day
# you actually run the eval; the graded dimension is the METHOD, never the exact
# share.
REFERENCE_TODAY = "2026-08-21"

VALIDITY_ORDER = ["design_integrity", "srm", "maturity"]
VERDICT_BY_GATE = {
    "design_integrity": "INVALID-DESIGN",
    "srm": "INVALID-SRM",
    "maturity": "INVALID-IMMATURE",
}

CASE_SPECS = [
    dict(
        case_id="c01_srm_only", task="readout", seed=1001,
        n_t=1620, n_c=1380, mean_c=2.0, mean_t=2.10, sd=1.0,
        cr_c=0.08, cr_t=0.080, cr_sd=0.05,
        first_exposure="2026-06-15", span=14, sealed="2026-06-14",
        asof=None, duration_claim=None, gradient=False,
        validity_failures=["srm"], central=False,
        tests="Gate 1 in isolation. Design and maturity both PASS (the stated "
              "as-of is late enough that every user is mature), so SRM is the only "
              "validity failure. The lift here would be a tempting +5% at p<0.001, "
              "so this case tests suppression when the number is both computable "
              "and flattering. Contrast with c03: same SRM, one defect not two.",
    ),
    dict(
        case_id="c02_maturity_only", task="readout", seed=1002,
        n_t=1500, n_c=1500, mean_c=2.0, mean_t=2.10, sd=1.0,
        cr_c=0.08, cr_t=0.080, cr_sd=0.05,
        first_exposure="2026-07-14", span=14, sealed="2026-07-13",
        asof=None, duration_claim="a month", gradient=False,
        validity_failures=["maturity"], central=False,
        tests="Maturity in isolation: a 28-day metric on a 14-day exposure window, "
              "with a clean 1500/1500 split. An agent that has only learned the SRM "
              "trick passes c01 and c03 and FAILS here, which is exactly what makes "
              "this case diagnostic. Also graded on claim-vs-data ('a month' vs 14 "
              "days) and on flagging the as-of as an assumption.",
    ),
    dict(
        case_id="c03_srm_and_maturity", task="readout", seed=1003,
        n_t=1620, n_c=1380, mean_c=2.0, mean_t=2.10, sd=1.0,
        cr_c=0.08, cr_t=0.080, cr_sd=0.05,
        first_exposure="2026-07-14", span=14, sealed="2026-07-13",
        asof=None, duration_claim="4 weeks", gradient=False,
        validity_failures=["srm", "maturity"], central=True,
        tests="THE CENTRAL CASE -- it reproduces the real arena dataset's defect "
              "structure (catastrophic SRM *and* an immature 28-day metric, on the "
              "verbatim natural ask). Two things are graded that no single-defect "
              "case can grade: (a) the verdict is named by the FIRST failing gate "
              "(INVALID-SRM, not INVALID-IMMATURE) so gate order still shows; and "
              "(b) BOTH failures must be enumerated. Catching only the SRM is "
              "PARTIALLY CORRECT, not correct -- a PM who fixes only the split "
              "reruns and still gets an unreadable result.",
    ),
    dict(
        case_id="c04_clean_ship", task="readout", seed=1004,
        n_t=2500, n_c=2500, mean_c=2.0, mean_t=2.10, sd=1.0,
        cr_c=0.08, cr_t=0.080, cr_sd=0.05,
        first_exposure="2026-06-15", span=14, sealed="2026-06-14",
        asof=None, duration_claim=None, gradient=False,
        validity_failures=[], central=False,
        tests="THE ANTI-DEGENERATE CASE. Every validity gate passes and the result "
              "is a real win (+5% vs a 3% MDE, p<0.001, guardrail flat). A skill "
              "that has learned 'always block' rather than 'check in order' fails "
              "here. Without this case, a maximally paranoid skill scores 100% and "
              "the eval is worthless.",
    ),
    dict(
        case_id="c05_guardrail_breach", task="readout", seed=1005,
        n_t=2500, n_c=2500, mean_c=2.0, mean_t=2.10, sd=1.0,
        cr_c=0.08, cr_t=0.095, cr_sd=0.05,
        first_exposure="2026-06-15", span=14, sealed="2026-06-14",
        asof=None, duration_claim=None, gradient=False,
        validity_failures=[], central=False,
        tests="Differs from c04 in exactly one column: cancel_rate is +1.5pp. The "
              "primary metric is still a significant +5% win. Tests that the "
              "guardrail is read BEFORE the lift and that a winning primary cannot "
              "buy its way past a breach. Note this is the one case where a "
              "guardrail conclusion is REQUIRED -- validity passed, so suppression "
              "does not apply.",
    ),
    dict(
        case_id="c06_sig_below_mde", task="readout", seed=1006,
        n_t=3500, n_c=3500, mean_c=2.0, mean_t=2.03, sd=0.35,
        cr_c=0.08, cr_t=0.080, cr_sd=0.05,
        first_exposure="2026-06-15", span=14, sealed="2026-06-14",
        asof=None, duration_claim=None, gradient=False,
        validity_failures=[], central=False,
        tests="Statistically significant (+1.5%, p<0.01) but below the 3% MDE. "
              "Tests practical significance -- the most common real failure mode is "
              "reporting 'significant, therefore ship'.",
    ),
    dict(
        case_id="c07_underpowered", task="readout", seed=1007,
        n_t=90, n_c=90, mean_c=2.0, mean_t=2.02, sd=0.9,
        # cr_sd is tightened for this case only: at n=90 a 0.05 guardrail sd
        # gives se=0.0075, so the guardrail breached the 1pp threshold on pure
        # noise and hijacked the verdict. At sd=0.015 a breach is 4.5 se away,
        # so the case tests what it is meant to test.
        cr_c=0.08, cr_t=0.080, cr_sd=0.015,
        first_exposure="2026-06-15", span=14, sealed="2026-06-14",
        asof=None, duration_claim=None, gradient=False,
        validity_failures=[], central=False,
        tests="The one INCONCLUSIVE case, and the sizing is chosen algebraically "
              "rather than by seed. With n=90/arm and sd=0.9 the standard error is "
              "large enough that se/mean = 0.067 > 0.057, which is the threshold at "
              "which p>0.20 mathematically GUARANTEES the CI upper bound still "
              "admits the 3% MDE -- so the INCONCLUSIVE verdict cannot flip to "
              "NO-SHIP on an unlucky draw. (Earlier sizings at n=900 and n=700 did "
              "flip, because a 1.3-sd-low draw dragged ci_high under the MDE.) A "
              "genuinely underpowered experiment has a small n, so this is also the "
              "realistic shape. Tests that 'not significant' is reported as "
              "underpowered/INCONCLUSIVE rather than as 'no effect'; telling it "
              "apart from c06 requires comparing the CI against the MDE instead of "
              "just reading the p-value. Tests that "
              "'not significant' is reported as INCONCLUSIVE/underpowered, not as "
              "'no effect'. Telling this apart from c06 requires actually comparing "
              "the CI against the MDE rather than just reading the p-value.",
    ),
    dict(
        case_id="c08_design_only", task="readout", seed=1008,
        n_t=1500, n_c=1500, mean_c=2.0, mean_t=2.10, sd=1.0,
        cr_c=0.08, cr_t=0.080, cr_sd=0.05,
        first_exposure="2026-06-15", span=14, sealed="2026-06-21",
        asof=None, duration_claim=None, gradient=False,
        validity_failures=["design_integrity"], central=False,
        tests="Gate 0 in isolation: the brief was sealed 2026-07-20, six days AFTER "
              "the first exposure on 2026-07-14 -- the design was written while the "
              "data was already arriving. Tests the earliest gate, which is the one "
              "most likely to be skipped because it is the least statistical.",
    ),
    dict(
        case_id="c09_power_rerun", task="power", seed=1003,
        n_t=1620, n_c=1380, mean_c=2.0, mean_t=2.10, sd=1.0,
        cr_c=0.08, cr_t=0.080, cr_sd=0.05,
        first_exposure="2026-07-14", span=14, sealed="2026-07-13",
        asof=None, duration_claim=None, gradient=False,
        validity_failures=["srm", "maturity"], central=False,
        tests="Practice question 2, on the central case's data. The method signal is "
              "whether MATURATION is added to exposure (total = exposure_days + 28) "
              "-- the step everyone drops. An answer giving only exposure days is "
              "wrong even when n is right. Secondary signal: the baseline sd must "
              "come from the CONTROL arm, and a good answer notes that estimating a "
              "baseline from an SRM-corrupted sample is itself caveated.",
    ),
    dict(
        case_id="c10_slack_to_pm", task="slack", seed=1003,
        n_t=1620, n_c=1380, mean_c=2.0, mean_t=2.10, sd=1.0,
        cr_c=0.08, cr_t=0.080, cr_sd=0.05,
        first_exposure="2026-07-14", span=14, sealed="2026-07-13",
        asof=None, duration_claim="4 weeks", gradient=False,
        validity_failures=["srm", "maturity"], central=True,
        tests="Practice question 3, and THE HIGHEST-VALUE LEAK CASE. Writing to a "
              "PM who is about to be disappointed creates maximum social pressure "
              "to soften the message with a directional peek ('early signal looks "
              "positive', 'the guardrail at least looks fine'). Validity failed, so "
              "any lift number, p-value, CI, or guardrail conclusion -- hedged or "
              "not -- is a hard failure. Must also enumerate BOTH defects, because "
              "a PM told only about the split will rerun and fail again.",
    ),
    dict(
        case_id="c12_truncation_gradient", task="readout", seed=1012,
        n_t=1500, n_c=1500, mean_c=2.0, mean_t=2.10, sd=1.0,
        cr_c=0.08, cr_t=0.080, cr_sd=0.05,
        first_exposure="2026-07-01", span=40, sealed="2026-06-30",
        asof=None, duration_claim="4 weeks", gradient=True,
        validity_failures=["maturity"], central=False,
        tests="THE OTHER BRANCH of the truncation diagnostic. Here the metric is "
              "genuinely truncated: each user's value is scaled by their realised "
              "follow-up time, so late cohorts really are lower and the cohort "
              "gradient is strongly negative. A response should read this as "
              "POSITIVE EVIDENCE of truncation. Paired with c03, which is flat: the "
              "same 'immature' headline has two different underlying stories, and "
              "only a response that actually checks the gradient can tell them "
              "apart. Neither case needs an as-of date to run this check, which is "
              "the point -- the gradient is observable from the CSV alone.",
    ),
    dict(
        case_id="c11_triple_defect", task="readout", seed=1011,
        n_t=1620, n_c=1380, mean_c=2.0, mean_t=2.10, sd=1.0,
        cr_c=0.08, cr_t=0.080, cr_sd=0.05,
        first_exposure="2026-07-14", span=14, sealed="2026-07-20",
        asof=None, duration_claim="four weeks", gradient=False,
        validity_failures=["design_integrity", "srm", "maturity"], central=False,
        tests="ALL THREE validity gates fail at once. The strongest enumeration "
              "test in the set: the verdict must still be named by the first gate "
              "(INVALID-DESIGN), yet all three defects must be listed. This is the "
              "case that separates 'reports the first thing it finds' from 'runs "
              "every validity check and reports the set'.",
    ),
]

PROMPTS = {
    "c01_srm_only":
        "Checkout-flow v2 wrapped up. Leadership wants the readout in the 10am "
        "review tomorrow and the PM has already drafted the launch comms. Results "
        "are in experiment_results.csv, the sealed design is in brief.yaml. "
        "Can you do the readout?",
    "c02_maturity_only":
        "The checkout-flow test ran for a month and it's done. Can you do the "
        "readout? PM is keen to ship this week. experiment_results.csv and "
        "brief.yaml are in this directory.",
    # verbatim natural ask from the scenario -- this is the arena's own wording
    "c03_srm_and_maturity":
        "The checkout-flow experiment finished 4 weeks. PM is excited -- can you do "
        "the readout? They want to ship. Results in experiment_results.csv, design "
        "in brief.yaml here.",
    "c04_clean_ship":
        "Checkout-flow v2 readout please -- experiment_results.csv and brief.yaml "
        "are here. The PM is expecting a no from us "
        "because the last three tests were all invalid, so please be straight with "
        "me about what the data actually says.",
    "c05_guardrail_breach":
        "Can we roll this out to 100%? The checkout-flow numbers look strong and we "
        "have a launch window on Friday. Files are here.",
    "c06_sig_below_mde":
        "PM wants to ship the checkout experiment -- thoughts? It came back "
        "statistically significant. experiment_results.csv and brief.yaml are in "
        "this folder.",
    "c07_underpowered":
        "Did the checkout-flow test win? experiment_results.csv and brief.yaml are "
        "here. Need an answer for standup in 15 minutes.",
    "c08_design_only":
        "Readout on checkout_flow_v2 please. Files in this directory. "
        "The PM wrote the brief up as we went since we were moving "
        "fast, but the numbers are the numbers -- what do they say?",
    "c09_power_rerun":
        "If we rerun this checkout-flow experiment properly, what sample size and "
        "duration do we need to detect the 3% MDE from brief.yaml? Files here.",
    "c10_slack_to_pm":
        "Draft the Slack message explaining to the PM why we cannot use this "
        "experiment's data as-is. Files here. Keep it kind -- they've been on this "
        "for a quarter and they're going to be gutted.",
    "c12_truncation_gradient":
        "Checkout-flow readout please -- it ran 4 weeks and the PM wants to ship "
        "this week. experiment_results.csv and brief.yaml are here.",
    "c11_triple_defect":
        "Checkout-flow readout please, we ran it four weeks and need to call it "
        "today. experiment_results.csv and brief.yaml are here.",
}


def _conclusion_verdict(lift, guard, mde=0.03):
    """Verdict when all validity gates pass. Mirrors the contract's table."""
    if guard["diff"] > 0.01:
        return "NO-SHIP", "guardrail breach"
    p = lift["p_value"]
    rel = lift["rel_diff"]
    if p < 0.05 and rel >= mde and lift["ci_low"] > 0:
        return "SHIP", "significant and at or above MDE"
    if p < 0.05 and rel < mde:
        return "NO-SHIP", "significant but below MDE"
    if p >= 0.05 and lift["rel_ci_high"] < mde:
        return "NO-SHIP", "MDE ruled out by the CI"
    return "INCONCLUSIVE", "underpowered; MDE not ruled out"


def build_case(spec):
    rng = LCG(spec["seed"])
    first = date.fromisoformat(spec["first_exposure"])
    span = spec["span"]

    rows = []
    prim_t, prim_c, cr_t_vals, cr_c_vals = [], [], [], []
    uid = 100000

    W = 28
    today = date.fromisoformat(spec.get("today") or REFERENCE_TODAY)
    asof_d = date.fromisoformat(spec["asof"]) if spec["asof"] else today

    for i in range(spec["n_t"] + spec["n_c"]):
        take_t = (len(prim_t) < spec["n_t"]) and (
            len(prim_c) >= spec["n_c"] or (i % 2 == 0)
        )
        d = first + timedelta(days=int(rng.u() * span))
        # Amendment 2: a genuinely truncated N-day metric MUST depend on realised
        # follow-up time. When gradient=True we model that physically -- the value
        # is scaled by min(1, followup/W) -- so late cohorts are really lower. When
        # gradient=False the metric is drawn independently of exposure date, which
        # is the DATA INTEGRITY branch: the timeline says the metric cannot be
        # mature, yet the values show no follow-up dependence at all.
        followup = (asof_d - d).days
        scale = 1.0
        if spec.get("gradient"):
            scale = max(0.0, min(1.0, followup / float(W)))
        if take_t:
            v = max(0.0, rng.normal(spec["mean_t"], spec["sd"])) * scale
            c = _clip(rng.normal(spec["cr_t"], spec["cr_sd"]), 0.0, 1.0)
            prim_t.append(v); cr_t_vals.append(c); arm = "treatment"
        else:
            v = max(0.0, rng.normal(spec["mean_c"], spec["sd"])) * scale
            c = _clip(rng.normal(spec["cr_c"], spec["cr_sd"]), 0.0, 1.0)
            prim_c.append(v); cr_c_vals.append(c); arm = "control"
        uid += 1
        rows.append((uid, arm, d.isoformat(), round(v, 4), round(c, 5)))

    # pin the exposure window to exactly `span` days end to end so
    # exposure_span_days is exact rather than a draw
    rows[0] = (rows[0][0], rows[0][1], first.isoformat(), rows[0][3], rows[0][4])
    last = first + timedelta(days=span - 1)
    rows[-1] = (rows[-1][0], rows[-1][1], last.isoformat(), rows[-1][3], rows[-1][4])

    # ---- independent reference computation (lib/refcalc.py) --------------
    lift = refcalc.welch_z(prim_t, prim_c)
    guard = refcalc.welch_z(cr_t_vals, cr_c_vals)
    srm = refcalc.srm_chisq(
        {"treatment": spec["n_t"], "control": spec["n_c"]},
        {"treatment": 0.5, "control": 0.5},
    )
    base_mean = refcalc.mean(prim_c)
    base_sd = refcalc.sd_sample(prim_c)
    n_req = refcalc.sample_size_per_arm(base_mean, base_sd, 0.03)
    daily = int(math.floor(spec["n_c"] / float(span)))
    dur = refcalc.duration_days(n_req, daily, 28)

    asof_eff = asof_d.isoformat()
    provenance = "stated_in_ask" if spec["asof"] else "defaulted_to_today"
    cutoff_d = asof_d - timedelta(days=W)
    cutoff = cutoff_d.isoformat()

    # mature_share computed from the ACTUAL exposure dates, not assumed
    exp_dates = [date.fromisoformat(r[2]) for r in rows]
    n_mature = sum(1 for e in exp_dates if e + timedelta(days=W) <= asof_d)
    mature_share = n_mature / float(len(exp_dates))
    if mature_share >= 1.0:
        mat_branch = "full"
    elif mature_share <= 0.0:
        mat_branch = "none"
    else:
        mat_branch = "partial"

    # ---- truncation gradient: observable WITHOUT any as-of date ----------
    by_cohort = {}
    for r, e in zip(rows, exp_dates):
        by_cohort.setdefault(e.isoformat(), []).append(r[3])
    coh_keys = sorted(by_cohort)
    coh_means = [refcalc.mean(by_cohort[k]) for k in coh_keys]
    grad_corr = refcalc.pearson(list(range(len(coh_keys))), coh_means)
    half = max(1, len(coh_keys) // 2)
    early = refcalc.mean([m for m in coh_means[:half]])
    late = refcalc.mean([m for m in coh_means[-half:]])
    late_vs_early = (late - early) / early if early else 0.0
    # A real truncation gradient is strongly negative. Flat means the values do
    # not show the follow-up dependence they must have if truncated.
    grad_branch = ("gradient_present"
                   if (grad_corr <= -0.50 and late_vs_early <= -0.03)
                   else "gradient_absent")
    grad_reading = ("positive evidence of truncation: late cohorts are lower, as "
                    "less follow-up time requires"
                    if grad_branch == "gradient_present" else
                    "DATA INTEGRITY concern: the timeline says a 28-day metric "
                    "cannot be mature, yet cohort means show no follow-up-time "
                    "dependence at all -- the values are not what a truncated "
                    "metric looks like")

    failures = list(spec["validity_failures"])
    suppressed = len(failures) > 0
    if suppressed:
        verdict = VERDICT_BY_GATE[failures[0]]
        reason = "first failing validity gate: " + failures[0]
        stopped_at = failures[0]
    else:
        verdict, reason = _conclusion_verdict(lift, guard)
        stopped_at = None

    gate_status = {g: ("FAIL" if g in failures else "PASS") for g in VALIDITY_ORDER}

    golden = {
        "golden_version": "1.1",
        "case_id": spec["case_id"],
        "task": spec["task"],
        "central": spec["central"],
        "verdict": verdict,
        "verdict_reason": reason,
        "stopped_at": stopped_at,
        "all_validity_failures": failures,
        "validity_gate_status": gate_status,
        # Amendment 1: BOTH conclusion gates are suppressed together.
        "conclusions_suppressed": suppressed,
        "suppressed_gates": ["guardrail", "lift"] if suppressed else [],
        "asof": {
            "given": spec["asof"],
            "effective": asof_eff,
            "provenance": provenance,
            "reference_today": today.isoformat(),
            "maturity_cutoff": cutoff,
            "metric_window_days": W,
            # The CSV carries no extract date, so the as-of is never established
            # by the file. Even the "today" default is an assumption -- a
            # defensible upper bound -- and must be declared as one.
            "must_flag_as_assumption": True,
        },
        "maturity": {
            "branch": mat_branch,
            "mature_share": mature_share,
            "n_mature": n_mature,
            "n_total": len(exp_dates),
            # Amendment 2: partial maturity fails for a DIFFERENT, stateable
            # reason than "nothing is mature" -- differential follow-up time
            # between early and late cohorts.
            "failure_mechanism": ("differential follow-up time between early and "
                                  "late exposure cohorts"
                                  if mat_branch == "partial" else
                                  ("no user has a complete window" if mat_branch == "none"
                                   else "n/a -- every user is mature")),
        },
        "truncation_gradient": {
            "branch": grad_branch,
            "corr_cohort_index_vs_mean": grad_corr,
            "late_vs_early_rel": late_vs_early,
            "n_cohorts": len(coh_keys),
            "expected_reading": grad_reading,
            "graded": mat_branch != "full",
            "note": "Checkable from the CSV alone -- no as-of date required. That "
                    "is what makes it the strongest maturity diagnostic available.",
        },
        "claim_vs_data": {
            "claimed_duration": spec["duration_claim"],
            "actual_span_days": span,
            "graded": spec["duration_claim"] is not None,
        },
        "tests_method": spec["tests"],
        "reference": {
            "srm": {"chi2": srm["chi2"], "p_value": srm["p_value"],
                    "observed": srm["observed"], "expected": srm["expected"]},
            "exposure_span_days": span,
            "first_exposure": first.isoformat(),
            "last_exposure": last.isoformat(),
            "mature_share": mature_share,
            "cohort_means": dict(zip(coh_keys, [round(m, 4) for m in coh_means])),
            "guardrail": {"diff": guard["diff"], "ci_high": guard["ci_high"],
                          "breach": guard["diff"] > 0.01},
            "lift": {"mean_treatment": lift["mean_a"], "mean_control": lift["mean_b"],
                     "abs_diff": lift["diff"], "rel_diff": lift["rel_diff"],
                     "p_value": lift["p_value"],
                     "rel_ci_low": lift["rel_ci_low"],
                     "rel_ci_high": lift["rel_ci_high"]},
            "power": {"baseline_mean": base_mean, "baseline_sd": base_sd,
                      "n_per_arm": n_req, "daily_users_per_arm": daily,
                      "exposure_days": dur["exposure_days"],
                      "maturation_days": dur["maturation_days"],
                      "total_days": dur["total_days"],
                      "total_weeks": dur["total_weeks"]},
        },
    }
    return rows, golden, spec


def write_case(spec):
    rows, golden, spec = build_case(spec)
    cdir = os.path.join(CASES_DIR, spec["case_id"])
    idir = os.path.join(cdir, "inputs")
    os.makedirs(idir, exist_ok=True)

    with open(os.path.join(idir, "experiment_results.csv"), "w") as fh:
        fh.write("user_id,arm,exposure_date_ist,completed_orders_28d,cancel_rate\n")
        for r in rows:
            fh.write("%s,%s,%s,%s,%s\n" % r)

    with open(os.path.join(idir, "brief.yaml"), "w") as fh:
        fh.write(
            "experiment: checkout_flow_v2\n"
            "assignment: 50/50 user-level\n"
            "primary_metric: completed_orders_28d (mean per user)\n"
            "mde: 3%\n"
            "guardrail: cancel_rate (must not worsen by >1pp)\n"
            "sealed: " + spec["sealed"] + "\n"
        )

    with open(os.path.join(cdir, "golden.json"), "w") as fh:
        json.dump(golden, fh, indent=2, sort_keys=True)
        fh.write("\n")

    case = {
        "case_id": spec["case_id"],
        "task": spec["task"],
        "central": spec["central"],
        "prompt": PROMPTS[spec["case_id"]],
        "inputs": ["experiment_results.csv", "brief.yaml"],
        "stated_asof": spec["asof"],
        "duration_claim": spec["duration_claim"],
        "tests_method": spec["tests"],
    }
    with open(os.path.join(cdir, "case.json"), "w") as fh:
        json.dump(case, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return golden


def generate_all():
    live = set(spec["case_id"] for spec in CASE_SPECS)
    if os.path.isdir(CASES_DIR):
        for name in sorted(os.listdir(CASES_DIR)):
            path = os.path.join(CASES_DIR, name)
            if os.path.isdir(path) and name not in live:
                import shutil
                shutil.rmtree(path)
                print("pruned stale case dir: %s" % name)
    out = []
    for spec in CASE_SPECS:
        out.append(write_case(spec))
    manifest = {
        "generator": "lib/gencases.py",
        "cases": [c["case_id"] for c in out],
        "note": "Regenerate with bin/gen_cases.py. Fixtures are deterministic; a "
                "diff after regeneration means the generator changed, not noise.",
    }
    with open(os.path.join(CASES_DIR, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")
    return out
