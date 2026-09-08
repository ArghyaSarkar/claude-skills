#!/usr/bin/env python3
"""Deterministic, seeded fixture generator for the experiment-readout test suite.

Run:  /usr/bin/python3 tests/fixtures/generate_fixtures.py

Targets CONTRACT.md v1.3 (frozen contract + AMENDMENTS 1, 2, 3).

Every CSV/YAML in this directory is produced by this script from a single fixed
seed, so the ground truth is reproducible and reviewable.  Nothing here reads
the implementation under test.

GROUND-TRUTH CONSTRUCTION
-------------------------
Per-user metric values are drawn as exp(N(0, sigma)) (strictly positive), then
*multiplicatively rescaled* so the arm mean is EXACTLY the target we chose.
Rescaling is multiplicative rather than additive so values stay positive and
the arm sd scales with the mean (realistic for counts and rates).

Because the arm means are exact by construction, the true difference and the
true relative lift of every fixture are known to ~1e-9, not merely estimated.
After generation we recompute the means from the *rounded, written* CSV rows in
file order and record them in manifest.json.  Tests read manifest.json, never
the implementation's output, for their expected values.

Exposure dates are dealt out by cycling day-by-day *within each arm*, so the
observed arm split is driven purely by the row counts we chose and never by
date sampling noise.  min(exposure_date) == date_start and
max(exposure_date) == date_end exactly.

TRUNCATION GRADIENT (v1.2)
--------------------------
A genuinely truncated N-day metric must show LATE cohorts lower, because they
have had less follow-up time.  Two fixtures cover the two readings:
  truncation_gradient  -- an engineered declining gradient: positive evidence of
                          truncation, establishable from the data alone.
  flat_but_impossible  -- flat cohort means while the timeline still makes
                          maturity impossible: a DATA INTEGRITY concern, because
                          the values do not show the follow-up dependence they
                          must have.  This is the real arena dataset's shape
                          (measured corr = -0.031, late-vs-early -0.44%).

SUPPRESSION DESIGN (v1.1)
-------------------------
Under AMENDMENT 1 both CONCLUSION gates -- guardrail (3) and lift (4) -- are
NOT_RUN whenever any VALIDITY gate (0/1/2) failed.  So every invalid fixture is
built to carry BOTH a large real lift AND a real guardrail breach, each with a
deliberately non-round, fixture-unique magnitude, so that a leak of either is
unambiguous under a whole-payload numeric scan.

A/B/n (v1.4)
-----------
A spec may carry `arms=[dict(name=..., n=..., rel_lift=..., cancel_delta=...)]`
instead of n_t/n_c, which builds three or more arms.  Two-arm specs are
normalised into exactly that shape with the arms in the order (treatment,
control), so the random draws happen in the same order they always did and every
pre-existing fixture is byte-for-byte what it was.  Multi-arm fixtures are
APPENDED to the end of FIXTURES for the same reason: the generator draws from one
shared stream, so inserting a fixture in the middle would rewrite every fixture
after it.

SEED is fixed at 20260821.  Changing it changes every expected value in the
suite, so don't.
"""

import csv
import json
import math
import os
import random
from datetime import date, timedelta

SEED = 20260821
HERE = os.path.dirname(os.path.abspath(__file__))

# Lognormal shape parameters.  sigma is the sd of log(value); the resulting
# relative sd of the arm is sqrt(exp(sigma**2) - 1).
SIGMA_PRIMARY = 0.40      # -> relative sd ~0.4165 on the primary metric
SIGMA_GUARDRAIL = 0.50    # -> relative sd ~0.5330 on cancel_rate

CONTROL_PRIMARY_MEAN = 2.0      # mean completed_orders_28d per user, control
CONTROL_GUARDRAIL_MEAN = 0.05   # mean cancel_rate per user, control

PRIMARY_COL = "completed_orders_28d"
HEADER = ["user_id", "arm", "exposure_date_ist", PRIMARY_COL, "cancel_rate"]

VALIDITY_GATES = ["design_integrity", "srm", "maturity"]


# --------------------------------------------------------------------------
# Fixture specification table.
#
#   rel_lift      : TRUE relative lift on the primary metric (treatment/control - 1)
#   cancel_delta  : TRUE absolute difference on cancel_rate (treatment - control)
#   asof          : the --asof value tests pass. AMENDMENT 2 removed
#                   max(exposure_date) as the default and replaced it with the
#                   SYSTEM DATE, which makes any un-pinned verdict TIME
#                   DEPENDENT. So every fixture pins an explicit asof and no
#                   fixture may leave it None -- enforced by a guard in main().
#   bad_guardrail_cells: replace this many cancel_rate values with the
#                   unparseable sentinel "n/a", split across arms. AMENDMENT 3A:
#                   a bad cell in a SECONDARY column is dropped and surfaced,
#                   but once dropped rows EXCEED 2% of the file gate 0 FAILS.
#   cohort_gradient: if set, scale the primary metric by a factor declining
#                   linearly from 1.0 (earliest cohort) to this value (latest),
#                   IDENTICALLY in both arms, so a truncation gradient is
#                   imposed while the relative lift is preserved.
#   date_mode     : "cycle"            -> deal days across [date_start, date_end]
#                   "single"           -> every user exposed on date_start
#                   "single_plus_late" -> all on date_start except n_late users
#                                         on date_start + 1 day (off-by-one probe)
#   expect_*      : intended ground truth per CONTRACT.md v1.1
#   expect_validity_status : per-gate status to assert; None = do not assert
#                            (used where the contract is genuinely ambiguous)
# --------------------------------------------------------------------------
FIXTURES = [

    # ------------------------------------------------------------------
    # ALL VALIDITY GATES PASS -> conclusion gates run
    # ------------------------------------------------------------------
    dict(
        name="ship_clean",
        n_t=3000, n_c=3000, rel_lift=0.0800, cancel_delta=0.0000,
        date_start="2026-07-14", date_end="2026-07-27", sealed="2026-07-13",
        asof="2026-08-24",           # 2026-07-27 + 28d -> every user mature
        expect_verdict="SHIP", expect_stopped_at=None,
        expect_validity_status=dict(design_integrity="PASS", srm="PASS", maturity="PASS"),
        expect_all_validity_failures=[],
        note="Exact 50/50, every user mature at the supplied asof, guardrail "
             "flat, +8.00% lift with p~1.5e-12 and rel CI [+5.79%, +10.21%] "
             "entirely above the 3% MDE. Also reused by the --asof CLI test: the "
             "SAME CSV run WITHOUT --asof must flip maturity PASS -> FAIL.",
    ),
    dict(
        name="srm_mild",
        n_t=3050, n_c=2950, rel_lift=0.0800, cancel_delta=0.0000,
        date_start="2026-07-14", date_end="2026-07-27", sealed="2026-07-13",
        asof="2026-08-24",
        expect_verdict="SHIP", expect_stopped_at=None,
        expect_validity_status=dict(design_integrity="PASS", srm="PASS", maturity="PASS"),
        expect_all_validity_failures=[],
        note="Mild 3050/2950 imbalance. chi2 = 2*50^2/3000 = 1.66667, "
             "p = erfc(sqrt(0.833333)) = 0.19670, which must NOT trip "
             "alpha=0.001. Proves the SRM gate is not hair-triggered.",
    ),
    dict(
        name="maturity_exact_boundary",
        n_t=1500, n_c=1500, rel_lift=0.0800, cancel_delta=0.0000,
        date_start="2026-07-27", date_end="2026-07-27", date_mode="single",
        sealed="2026-07-13", asof="2026-08-24",
        expect_verdict="SHIP", expect_stopped_at=None,
        expect_validity_status=dict(design_integrity="PASS", srm="PASS", maturity="PASS"),
        expect_all_validity_failures=[],
        note="OFF-BY-ONE PROBE, pass side. Every user exposed on 2026-07-27 and "
             "asof = 2026-08-24 = exposure + exactly 28 days. The contract rule "
             "is 'mature iff exposure + W <= asof', so mature_share must be "
             "exactly 1.0 and maturity must PASS. An implementation using '<' "
             "instead of '<=' fails here. exposure_span_days = 0.",
    ),
    dict(
        name="guardrail_breach",
        n_t=3000, n_c=3000, rel_lift=0.0800, cancel_delta=0.0150,
        date_start="2026-07-14", date_end="2026-07-27", sealed="2026-07-13",
        asof="2026-08-24",
        expect_verdict="NO-SHIP", expect_stopped_at=None,
        expect_validity_status=dict(design_integrity="PASS", srm="PASS", maturity="PASS"),
        expect_all_validity_failures=[],
        expect_guardrail_status="FAIL",
        note="Validity is clean, so the conclusion gates run. Primary metric is "
             "up +8.00% and significant, but cancel_rate is worse by exactly "
             "+1.50pp, which exceeds the +1pp breach threshold. Guardrail BREACH "
             "forces NO-SHIP despite a great primary result.",
    ),
    dict(
        name="guardrail_at_risk",
        n_t=3000, n_c=3000, rel_lift=0.0800, cancel_delta=0.0095,
        date_start="2026-07-14", date_end="2026-07-27", sealed="2026-07-13",
        asof="2026-08-24",
        expect_verdict="SHIP", expect_stopped_at=None,
        expect_validity_status=dict(design_integrity="PASS", srm="PASS", maturity="PASS"),
        expect_all_validity_failures=[],
        expect_guardrail_status="WARN",
        note="cancel_rate diff = +0.95pp, so <= 1pp and NOT a breach, but the 95% "
             "CI upper is +1.104pp which exceeds 1pp -> AT_RISK (status WARN). "
             "The contract says only BREACH forces NO-SHIP, so with a +8.00% "
             "significant lift the verdict must still be SHIP.",
    ),
    dict(
        name="sig_below_mde",
        n_t=6000, n_c=6000, rel_lift=0.0240, cancel_delta=0.0000,
        date_start="2026-07-14", date_end="2026-07-27", sealed="2026-07-13",
        asof="2026-08-24",
        expect_verdict="NO-SHIP", expect_stopped_at=None,
        expect_validity_status=dict(design_integrity="PASS", srm="PASS", maturity="PASS"),
        expect_all_validity_failures=[],
        note="n=6000/arm. diff = +0.048, se ~ 0.0152, t ~ 3.11, p ~ 0.00190 "
             "(< 0.05) -- but rel_lift = +2.40% < the 3% MDE. Statistically "
             "significant yet practically below the MDE -> NO-SHIP.",
    ),
    dict(
        name="mde_ruled_out",
        n_t=6000, n_c=6000, rel_lift=0.0020, cancel_delta=0.0000,
        date_start="2026-07-14", date_end="2026-07-27", sealed="2026-07-13",
        asof="2026-08-24",
        expect_verdict="NO-SHIP", expect_stopped_at=None,
        expect_validity_status=dict(design_integrity="PASS", srm="PASS", maturity="PASS"),
        expect_all_validity_failures=[],
        note="n=6000/arm. diff = +0.004, se ~ 0.0152, t ~ 0.26, p ~ 0.795 (NOT "
             "significant) and rel_ci_high = +1.705% which is BELOW the 3% MDE. "
             "The MDE is ruled out, so this is NO-SHIP, not INCONCLUSIVE. This is "
             "the fixture that separates 'no effect worth having' from "
             "'we could not tell'.",
    ),
    dict(
        name="inconclusive",
        n_t=150, n_c=150, rel_lift=0.0200, cancel_delta=0.0000,
        date_start="2026-07-14", date_end="2026-07-27", sealed="2026-07-13",
        asof="2026-08-24",
        expect_verdict="INCONCLUSIVE", expect_stopped_at=None,
        expect_validity_status=dict(design_integrity="PASS", srm="PASS", maturity="PASS"),
        expect_all_validity_failures=[],
        note="Underpowered: n=150/arm. diff = +0.04, se ~ 0.0964, t ~ 0.43, "
             "p ~ 0.669 (NOT significant) and rel_ci_high = +11.18%, well ABOVE "
             "the 3% MDE, so the MDE is NOT ruled out -> INCONCLUSIVE.",
    ),

    # ------------------------------------------------------------------
    # VALIDITY FAILURES -> both conclusion gates NOT_RUN, everything suppressed
    # Each carries a fixture-unique juicy lift AND a juicy guardrail breach.
    # ------------------------------------------------------------------
    dict(
        name="srm_broken",
        n_t=3600, n_c=2400, rel_lift=0.1173, cancel_delta=0.0231,
        date_start="2026-07-14", date_end="2026-07-27", sealed="2026-07-13",
        asof="2026-08-24",
        expect_verdict="INVALID-SRM", expect_stopped_at="srm",
        expect_validity_status=dict(design_integrity="PASS", srm="FAIL", maturity="PASS"),
        expect_all_validity_failures=["srm"],
        note="Badly broken 3600/2400 split: chi2 = 2*600^2/3000 = 240.0, "
             "p = 3.93e-54, far below alpha=0.001. Design and maturity are both "
             "clean (asof supplied), so this isolates gate 1 and proves the other "
             "validity gates still report PASS rather than NOT_RUN. Carries a "
             "+11.73% real lift AND a +2.31pp real guardrail breach, both of "
             "which must be completely absent from the output.",
    ),
    dict(
        name="immature",
        n_t=3000, n_c=3000, rel_lift=0.0917, cancel_delta=0.0187,
        date_start="2026-07-14", date_end="2026-07-27", sealed="2026-07-13",
        asof="2026-07-27",           # PINNED (v1.2): 0% mature
        expect_verdict="INVALID-IMMATURE", expect_stopped_at="maturity",
        expect_validity_status=dict(design_integrity="PASS", srm="PASS", maturity="FAIL"),
        expect_all_validity_failures=["maturity"],
        note="Exact 50/50 and otherwise clean, but the 14-day exposure window "
             "ends 2026-07-27 and the metric window is 28d, so under the ASSUMED "
             "asof = max(exposure_date) no user can be mature: mature_share = "
             "0.0, cutoff = 2026-06-29. This is real-data trap #2 from "
             "SCENARIO.md. Carries a +9.17% lift and a +1.87pp guardrail breach, "
             "both of which must be suppressed.",
    ),
    dict(
        name="partial_maturity",
        n_t=3000, n_c=3000, rel_lift=0.0631, cancel_delta=0.0164,
        date_start="2026-06-01", date_end="2026-07-27", sealed="2026-05-30",
        asof="2026-07-27",           # PINNED (v1.2): ~51% mature
        expect_verdict="INVALID-IMMATURE", expect_stopped_at="maturity",
        expect_validity_status=dict(design_integrity="PASS", srm="PASS", maturity="FAIL"),
        expect_all_validity_failures=["maturity"],
        note="PARTIAL MATURITY BOUNDARY. 57-day exposure span (2026-06-01 .. "
             "2026-07-27); under the assumed asof = 2026-07-27 the cutoff is "
             "2026-06-29, so roughly half the users are mature (0 < "
             "mature_share < 1). AMENDMENT 1 keeps this a FAIL -> "
             "INVALID-IMMATURE, for the differential-follow-up reason. Carries a "
             "+6.31% lift and a +1.64pp guardrail breach, both suppressed.",
    ),
    dict(
        name="maturity_off_by_one",
        n_t=1500, n_c=1500, rel_lift=0.1051, cancel_delta=0.0218,
        date_start="2026-07-27", date_end="2026-07-28",
        date_mode="single_plus_late", n_late=1,
        sealed="2026-07-13", asof="2026-08-24",
        expect_verdict="INVALID-IMMATURE", expect_stopped_at="maturity",
        expect_validity_status=dict(design_integrity="PASS", srm="PASS", maturity="FAIL"),
        expect_all_validity_failures=["maturity"],
        note="OFF-BY-ONE PROBE, fail side. Identical to maturity_exact_boundary "
             "except that EXACTLY ONE treatment user is exposed on 2026-07-28, "
             "one day too late for the 28-day window at asof = 2026-08-24. "
             "mature_share = 2999/3000 = 0.999667 < 1.0, so maturity must FAIL. "
             "An implementation that rounds, or that uses a tolerance, or that "
             "tests 'most users mature', passes when it must not. Carries a "
             "+10.51% lift and a +2.18pp guardrail breach, both suppressed.",
    ),
    dict(
        name="claim_vs_data_span",
        n_t=3000, n_c=3000, rel_lift=0.0709, cancel_delta=0.0176,
        date_start="2026-07-14", date_end="2026-07-27", sealed="2026-07-13",
        asof="2026-07-27",           # PINNED (v1.2)
        expect_verdict="INVALID-IMMATURE", expect_stopped_at="maturity",
        expect_validity_status=dict(design_integrity="PASS", srm="PASS", maturity="FAIL"),
        expect_all_validity_failures=["maturity"],
        note="Real-data trap #1 in isolation. The exposure span is 14 calendar "
             "days (2026-07-14 .. 2026-07-27) while the ask claims the experiment "
             "'finished 4 weeks'. The split is clean, so maturity is the only "
             "failure, and the gate's reported exposure_span_days is what exposes "
             "the claim-vs-data mismatch. Carries a +7.09% lift and a +1.76pp "
             "guardrail breach, both suppressed.",
    ),
    dict(
        name="precedence_all_bad",
        n_t=3600, n_c=2400, rel_lift=0.1409, cancel_delta=0.0258,
        date_start="2026-07-14", date_end="2026-07-27", sealed="2026-07-13",
        asof="2026-07-27",           # PINNED (v1.2)
        expect_verdict="INVALID-SRM", expect_stopped_at="srm",
        expect_validity_status=dict(design_integrity="PASS", srm="FAIL", maturity="FAIL"),
        expect_all_validity_failures=["srm", "maturity"],
        note="PRECEDENCE + NO-HIDING. Simultaneously SRM-broken (3600/2400, "
             "chi2 = 240.0) AND immature (28d metric, assumed asof) AND "
             "guardrail-breaching (+2.58pp). Because SRM is gate 1 the verdict "
             "MUST be INVALID-SRM and stopped_at MUST be 'srm' -- but under "
             "AMENDMENT 1 the maturity gate must STILL report a real FAIL, not "
             "NOT_RUN, and all_validity_failures must be exactly "
             "['srm', 'maturity']. Carries a +14.09% lift, suppressed.",
    ),
    dict(
        name="trap_real_data",
        n_t=3300, n_c=2700, rel_lift=0.0842, cancel_delta=0.0137,
        date_start="2026-07-14", date_end="2026-07-27", sealed="2026-07-13",
        asof="2026-07-27", brief_metric_suffix=" (mean per user)",   # PINNED (v1.2)
        expect_verdict="INVALID-SRM", expect_stopped_at="srm",
        expect_validity_status=dict(design_integrity="PASS", srm="FAIL", maturity="FAIL"),
        expect_all_validity_failures=["srm", "maturity"],
        note="Both real-data traps from SCENARIO.md at once, using the VERBATIM "
             "brief text 'completed_orders_28d (mean per user)' so the metric-name "
             "parser has to cope with the parenthetical: (1) 14-day exposure span "
             "vs a claimed '4 weeks' with a 28d metric that cannot be mature; "
             "(2) a broken 3300/2700 split (chi2 = 2*300^2/3000 = 60.0, "
             "p = 9.49e-15). Carries a +8.42% lift and a +1.37pp guardrail "
             "breach, both suppressed.",
    ),
    dict(
        name="real_dataset_shape",
        n_t=6492, n_c=5508, rel_lift=0.0764, cancel_delta=0.0193,
        date_start="2026-07-14", date_end="2026-07-27", sealed="2026-07-13",
        asof="2026-08-21",           # PINNED (v1.2): reproduces the arena reading, ~79% mature
        expect_verdict="INVALID-SRM", expect_stopped_at="srm",
        expect_validity_status=dict(design_integrity="PASS", srm="FAIL", maturity="FAIL"),
        expect_all_validity_failures=["srm", "maturity"],
        expect_truncation_reading="integrity",
        expect_gradient_label="flat",
        note="Reproduces the SHAPE of the real arena practice dataset without "
             "depending on the file: n=12000 split 6492/5508 = 54.1/45.9, so "
             "chi2 = 2*492^2/6000 = 80.688 and p = 2.66e-19 (the contract quotes "
             "chi2 ~ 80.7, p ~ 3e-19); 14-day exposure span 2026-07-14 .. "
             "2026-07-27 against a 28-day metric window. Both defects present at "
             "once: verdict INVALID-SRM, maturity ALSO FAIL, both conclusion "
             "gates NOT_RUN. Carries a +7.64% lift and a +1.93pp guardrail "
             "breach, both suppressed.",
    ),
    dict(
        name="truncation_gradient",
        n_t=3000, n_c=3000, rel_lift=0.0873, cancel_delta=0.0221,
        date_start="2026-07-14", date_end="2026-07-27", sealed="2026-07-13",
        asof="2026-07-27", cohort_gradient=0.55,
        expect_verdict="INVALID-IMMATURE", expect_stopped_at="maturity",
        expect_validity_status=dict(design_integrity="PASS", srm="PASS", maturity="FAIL"),
        expect_all_validity_failures=["maturity"],
        expect_truncation_reading="truncation",
        expect_gradient_label="late_lower",
        note="TRUNCATION GRADIENT, present. The primary metric is scaled by a "
             "factor declining linearly from 1.00 for the 2026-07-14 cohort to "
             "0.55 for the 2026-07-27 cohort, identically in both arms. That is "
             "exactly what a genuinely truncated 28-day metric looks like: late "
             "cohorts had less follow-up time, so they are systematically lower. "
             "The correlation of cohort index with cohort mean is strongly "
             "negative and the late-half mean is far below the early-half mean, "
             "so AMENDMENT 2 requires this to be reported as positive evidence "
             "of truncation, establishable from the data with no as-of date at "
             "all. Verdict INVALID-IMMATURE. Carries a +8.73% lift and a "
             "+2.21pp guardrail breach, both suppressed.",
    ),
    dict(
        name="flat_but_impossible",
        n_t=3000, n_c=3000, rel_lift=0.0785, cancel_delta=0.0205,
        date_start="2026-07-14", date_end="2026-07-27", sealed="2026-07-13",
        asof="2026-08-21", sigma_primary=0.10,
        expect_verdict="INVALID-IMMATURE", expect_stopped_at="maturity",
        expect_validity_status=dict(design_integrity="PASS", srm="PASS", maturity="FAIL"),
        expect_all_validity_failures=["maturity"],
        expect_truncation_reading="integrity",
        expect_gradient_label="flat",
        note="TRUNCATION GRADIENT, absent -- the DATA INTEGRITY reading. Values "
             "are drawn i.i.d. of exposure date, so cohort means are FLAT "
             "(correlation ~0), yet at asof 2026-08-21 the cutoff is 2026-07-24 "
             "and the last three cohorts cannot possibly have a complete 28-day "
             "window (~79% mature). A truncated metric MUST show the "
             "follow-up-time dependence and this one does not, so AMENDMENT 2 "
             "requires the stronger finding: a data-integrity concern, not "
             "ordinary truncation. This is the real arena dataset's shape "
             "(measured corr = -0.031, late-vs-early -0.44%). Carries a +7.85% "
             "lift and a +2.05pp guardrail breach, both suppressed.",
    ),
    dict(
        name="monotone_but_tiny",
        n_t=3000, n_c=3000, rel_lift=0.0968, cancel_delta=0.0234,
        date_start="2026-07-14", date_end="2026-07-27", sealed="2026-07-13",
        asof="2026-08-21", cohort_gradient=0.994, sigma_primary=0.02,
        expect_verdict="INVALID-IMMATURE", expect_stopped_at="maturity",
        expect_validity_status=dict(design_integrity="PASS", srm="PASS", maturity="FAIL"),
        expect_all_validity_failures=["maturity"],
        expect_truncation_reading="integrity",
        expect_gradient_label="flat",
        note="AMENDMENT 3C DISCRIMINATOR: r and the MAGNITUDE disagree. The "
             "primary metric carries a PERFECTLY MONOTONE but trivially small "
             "decline (multiplier 1.000 -> 0.994 across the 14 cohorts) on a "
             "very low dispersion (sigma 0.02), so the Pearson r of cohort "
             "index against cohort mean is strongly negative while the "
             "late-half vs early-half magnitude is only about -0.3%. An "
             "implementation keying the flat/late_lower call off r calls this "
             "late_lower; the contract now requires the MAGNITUDE to decide, so "
             "it must be called FLAT -- and because the timeline still makes "
             "maturity impossible for the late cohorts, flat means the DATA "
             "INTEGRITY branch. This is the fixture that proves the strongest "
             "finding in the readout no longer rests on an unstable statistic. "
             "Carries a +9.68% lift and a +2.34pp guardrail breach, suppressed.",
    ),
    dict(
        name="dropped_at_2pct",
        n_t=500, n_c=500, rel_lift=0.0800, cancel_delta=0.0000,
        date_start="2026-07-27", date_end="2026-07-27", date_mode="single",
        sealed="2026-07-13", asof="2026-08-24", bad_guardrail_cells=20,
        expect_verdict="SHIP", expect_stopped_at=None,
        expect_validity_status=dict(design_integrity="WARN", srm="PASS", maturity="PASS"),
        expect_all_validity_failures=[],
        note="AMENDMENT 3A BOUNDARY, inclusive side. Exactly 20 of 1000 rows "
             "(2.000%) have an unparseable 'n/a' in the SECONDARY column "
             "cancel_rate. 2% does not EXCEED 2%, so gate 0 must WARN and the "
             "readout must proceed: dropped rows are surfaced (rows_total 1000, "
             "rows_usable 980, the column named) but do not block. Guardrail is "
             "flat and the lift is +8.00%, so the verdict is SHIP.",
    ),
    dict(
        name="dropped_over_2pct",
        n_t=500, n_c=500, rel_lift=0.1122, cancel_delta=0.0246,
        date_start="2026-07-27", date_end="2026-07-27", date_mode="single",
        sealed="2026-07-13", asof="2026-08-24", bad_guardrail_cells=21,
        expect_verdict="INVALID-DESIGN", expect_stopped_at="design_integrity",
        expect_validity_status=dict(design_integrity="FAIL", srm="PASS", maturity="PASS"),
        expect_all_validity_failures=["design_integrity"],
        note="AMENDMENT 3A BOUNDARY, exclusive side. 21 of 1000 rows (2.100%) "
             "unparseable in cancel_rate -- ONE row more than dropped_at_2pct. "
             "That EXCEEDS 2%, so this is a data-quality problem rather than a "
             "rounding nuisance: gate 0 must FAIL -> INVALID-DESIGN. srm and "
             "maturity still have their inputs so they must still PASS. Carries "
             "a +11.22% lift and a +2.46pp guardrail breach, both suppressed.",
    ),
    dict(
        name="missing_metric_col",
        n_t=1000, n_c=1000, rel_lift=0.0000, cancel_delta=0.0152,
        date_start="2026-07-14", date_end="2026-07-27", sealed="2026-07-13",
        asof="2026-08-24", drop_primary_col=True,
        expect_verdict="INVALID-DESIGN", expect_stopped_at="design_integrity",
        expect_validity_status=dict(design_integrity="FAIL", srm="PASS", maturity="PASS"),
        expect_all_validity_failures=["design_integrity"],
        note="The brief names primary_metric completed_orders_28d but the CSV has "
             "no such column, so gate 0 FAILs. The brief IS present and parseable "
             "and the arm/date columns exist, so srm and maturity can and (under "
             "AMENDMENT 1) must still evaluate and PASS. Carries a +1.52pp real "
             "guardrail breach, which must be suppressed.",
    ),
    dict(
        name="missing_brief",
        n_t=1000, n_c=1000, rel_lift=0.1338, cancel_delta=0.0209,
        date_start="2026-07-14", date_end="2026-07-27", sealed="2026-07-13",
        asof="2026-08-24", write_brief=False,
        expect_verdict="INVALID-DESIGN", expect_stopped_at="design_integrity",
        # AMENDMENT 3B resolves what was ambiguous here. With no brief there is
        # no designed ratio and no primary-metric name, so srm and maturity have
        # no inputs -- that is NOT_ASSESSABLE ("we could not check"), which is a
        # DIFFERENT thing from NOT_RUN ("we chose not to conclude").
        expect_validity_status=dict(design_integrity="FAIL",
                                    srm="NOT_ASSESSABLE",
                                    maturity="NOT_ASSESSABLE"),
        expect_all_validity_failures=["design_integrity"],
        expect_validity_not_assessable=["srm", "maturity"],
        expect_first_validity_failure="design_integrity",
        note="No brief.yaml is written at all; the tests pass a path that does "
             "not exist. Gate 0 must FAIL -> INVALID-DESIGN, with exit code 0, "
             "because 'brief present' is a GATE, and a gate failure is a result "
             "rather than an input error. The CSV still carries a +13.38% lift "
             "and a +2.09pp guardrail breach, so suppression is testable.",
    ),
    dict(
        name="sealed_after_exposure",
        n_t=1000, n_c=1000, rel_lift=0.1256, cancel_delta=0.0243,
        date_start="2026-07-14", date_end="2026-07-27",
        sealed="2026-07-20",         # AFTER the first exposure 2026-07-14
        asof="2026-08-24",
        expect_verdict="INVALID-DESIGN", expect_stopped_at="design_integrity",
        expect_validity_status=dict(design_integrity="FAIL", srm="PASS", maturity="PASS"),
        expect_all_validity_failures=["design_integrity"],
        note="sealed = 2026-07-20 is AFTER the first exposure 2026-07-14, so the "
             "design was not sealed before the data existed -- the classic "
             "post-hoc-design tell. Gate 0 requires sealed <= first exposure, so "
             "it FAILs. Everything else is clean. Carries a +12.56% lift and a "
             "+2.43pp guardrail breach, both suppressed.",
    ),

    # ------------------------------------------------------------------
    # A/B/n (v1.4). Three arms, appended LAST so the shared random stream
    # leaves every fixture above untouched. sigma_primary is raised to 0.66
    # so that at 1000 users per arm a ~4% lift is genuinely uncertain --
    # which is the whole point of the second treatment arm.
    # ------------------------------------------------------------------
    dict(
        name="multiarm_one_winner",
        arms=[dict(name="treatment_a", n=1000, rel_lift=0.1700, cancel_delta=0.0),
              dict(name="treatment_b", n=1000, rel_lift=0.0380, cancel_delta=0.0),
              dict(name="control", n=1000, rel_lift=0.0, cancel_delta=0.0)],
        n_t=1000, n_c=1000, rel_lift=0.1700, cancel_delta=0.0,
        sigma_primary=0.66,
        date_start="2026-07-14", date_end="2026-07-27", sealed="2026-07-13",
        asof="2026-08-24",
        expect_verdict="SHIP", expect_stopped_at=None,
        expect_validity_status=dict(design_integrity="PASS", srm="PASS", maturity="PASS"),
        expect_all_validity_failures=[],
        expect_winning_arms=["treatment_a"],
        expect_significant_after_holm=dict(treatment_a=True, treatment_b=False),
        expect_t_band=dict(treatment_a=(4.0, 6.5), treatment_b=(0.6, 1.6)),
        note="THE A/B/n DEFECT FIXTURE. treatment_a is a large, unmistakable "
             "winner; treatment_b is up about 4%, which CLEARS the 3% MDE on the "
             "point estimate while being nowhere near significant. An engine "
             "that compares one treatment arm against control and drops the rest "
             "reports the +17% and never mentions treatment_b at all -- and a "
             "reader ships on a number without knowing a second arm existed. "
             "Verdict SHIP, and the verdict must NAME treatment_a.",
    ),
    dict(
        name="multiarm_none_survive_holm",
        arms=[dict(name="treatment_a", n=1000, rel_lift=0.0707, cancel_delta=0.0),
              dict(name="treatment_b", n=1000, rel_lift=0.0270, cancel_delta=0.0),
              dict(name="control", n=1000, rel_lift=0.0, cancel_delta=0.0)],
        n_t=1000, n_c=1000, rel_lift=0.0707, cancel_delta=0.0,
        sigma_primary=0.66,
        date_start="2026-07-14", date_end="2026-07-27", sealed="2026-07-13",
        asof="2026-08-24",
        expect_verdict="INCONCLUSIVE", expect_stopped_at=None,
        expect_validity_status=dict(design_integrity="PASS", srm="PASS", maturity="PASS"),
        expect_all_validity_failures=[],
        expect_winning_arms=[],
        expect_significant_after_holm=dict(treatment_a=False, treatment_b=False),
        expect_t_band=dict(treatment_a=(2.02, 2.20), treatment_b=(0.2, 1.5)),
        note="THE MULTIPLICITY FIXTURE. treatment_a lands at p between 0.025 and "
             "0.05: significant on its own, NOT significant once the family of "
             "two hypotheses is corrected, because the smallest of two p-values "
             "is held to alpha/2. treatment_b then inherits the stop and is "
             "retained too. Its point estimate clears the 3% MDE, so this is "
             "exactly the run that gets cherry-picked later. Nothing is ruled "
             "out either, so the verdict is INCONCLUSIVE, not NO-SHIP.",
    ),
    dict(
        name="multiarm_guardrail_breach",
        arms=[dict(name="treatment_a", n=1000, rel_lift=0.1700, cancel_delta=0.0),
              dict(name="treatment_b", n=1000, rel_lift=0.0380, cancel_delta=0.0150),
              dict(name="control", n=1000, rel_lift=0.0, cancel_delta=0.0)],
        n_t=1000, n_c=1000, rel_lift=0.1700, cancel_delta=0.0150,
        sigma_primary=0.66,
        date_start="2026-07-14", date_end="2026-07-27", sealed="2026-07-13",
        asof="2026-08-24",
        expect_verdict="SHIP", expect_stopped_at=None,
        expect_validity_status=dict(design_integrity="PASS", srm="PASS", maturity="PASS"),
        expect_all_validity_failures=[],
        expect_guardrail_status="FAIL",
        expect_winning_arms=["treatment_a"],
        expect_significant_after_holm=dict(treatment_a=True, treatment_b=False),
        expect_t_band=dict(treatment_a=(4.0, 6.5), treatment_b=(0.6, 1.6)),
        note="A breach in an arm nobody would ship. treatment_b worsens "
             "cancel_rate by +1.50pp, past the +1pp threshold; treatment_a is "
             "clean on the guardrail and wins on the primary metric. The breach "
             "bars treatment_b and says nothing about treatment_a, so the "
             "verdict is SHIP naming treatment_a -- with treatment_b's breach "
             "stated in the same breath. Reading one arm's guardrail onto "
             "another arm is the same mixing-of-arms error as reading one arm's "
             "lift as the experiment's.",
    ),
]


# --------------------------------------------------------------------------

def arm_specs(spec):
    """The arms of a fixture, always as a list of dicts, control LAST.

    A two-arm spec (n_t / n_c) is normalised into the same shape, in the order the
    draws have always happened, so nothing about an existing fixture moves.
    """
    if spec.get("arms"):
        return [dict(a) for a in spec["arms"]]
    return [dict(name="treatment", n=spec["n_t"], rel_lift=spec["rel_lift"],
                 cancel_delta=spec["cancel_delta"]),
            dict(name="control", n=spec["n_c"], rel_lift=0.0, cancel_delta=0.0)]


def arm_prefix(name):
    """A user_id prefix unique per arm: treatment -> t, treatment_a -> ta."""
    return "".join(part[0] for part in str(name).split("_") if part)


def welch_t(a, b):
    """The Welch t statistic and a normal-approximation p, for GENERATOR GUARDS only.

    The generator must not import the implementation, and a t-distribution tail needs an
    incomplete beta that would be a second copy of code under test. With thousands of
    users per arm the t distribution is indistinguishable from a normal one, so erfc is
    close enough to assert that a fixture landed in the band it was designed for. Tests
    use the independent reference in tests/unit/_ref.py for exact p-values, never this.
    """
    na, nb = len(a), len(b)
    ma, mb = sum(a) / na, sum(b) / nb
    va = sum((x - ma) ** 2 for x in a) / (na - 1)
    vb = sum((x - mb) ** 2 for x in b) / (nb - 1)
    se = math.sqrt(va / na + vb / nb)
    t = (ma - mb) / se if se else 0.0
    return t, math.erfc(abs(t) / math.sqrt(2.0))


def gen_values(rng, n, mean_target, sigma, ndp):
    """Draw n strictly-positive values, rescale so the mean is exactly
    mean_target, then round to ndp decimals."""
    raw = [math.exp(rng.gauss(0.0, sigma)) for _ in range(n)]
    m = sum(raw) / n
    scale = mean_target / m
    return [round(v * scale, ndp) for v in raw]


def dates_cycle(n, date_start, date_end):
    """Cycle day-by-day so min == date_start and max == date_end exactly."""
    d0 = date.fromisoformat(date_start)
    d1 = date.fromisoformat(date_end)
    ndays = (d1 - d0).days + 1
    if n < ndays:
        raise ValueError("n=%d < ndays=%d; span would not be covered" % (n, ndays))
    return [(d0 + timedelta(days=i % ndays)).isoformat() for i in range(n)]


def assign_dates(spec, arms):
    """{arm name: its users' exposure dates}, per the fixture's date_mode."""
    mode = spec.get("date_mode", "cycle")
    start = spec["date_start"]
    first_treatment = next(a["name"] for a in arms if a["name"] != "control")
    out = {}
    for a in arms:
        n = a["n"]
        if mode == "cycle":
            out[a["name"]] = dates_cycle(n, start, spec["date_end"])
        elif mode == "single":
            out[a["name"]] = [start] * n
        elif mode == "single_plus_late":
            if a["name"] == first_treatment:
                n_late = spec["n_late"]
                late = (date.fromisoformat(start) + timedelta(days=1)).isoformat()
                out[a["name"]] = [start] * (n - n_late) + [late] * n_late
            else:
                out[a["name"]] = [start] * n
        else:
            raise ValueError("unknown date_mode %r" % mode)
    return out


def apply_cohort_gradient(values, dates, all_dates, final_mult):
    """Scale each user's primary value by a factor declining linearly from 1.0
    for the earliest cohort to final_mult for the latest.

    Applied IDENTICALLY in both arms, and both arms have identical exposure-date
    distributions, so the weighted average multiplier is the same in each arm
    and the RELATIVE lift survives untouched while an absolute truncation
    gradient is imposed.
    """
    d = len(all_dates)
    idx = {v: i for i, v in enumerate(all_dates)}
    out = []
    for v, dt in zip(values, dates):
        f = 1.0 if d <= 1 else 1.0 + (final_mult - 1.0) * (idx[dt] / float(d - 1))
        out.append(round(v * f, 4))
    return out


def cohort_stats(rows, date_idx, primary_idx):
    """Ground truth for the truncation-gradient check: the primary metric's
    POOLED mean by exposure date, the Pearson correlation of cohort index with
    cohort mean, and the late-half vs early-half delta.

    Pooled across arms deliberately: a PER-ARM cohort breakdown would itself
    leak the lift, so the diagnostic the contract asks for has to be arm-blind.
    """
    by = {}
    for r in rows:
        by.setdefault(r[date_idx], []).append(float(r[primary_idx]))
    dates = sorted(by)
    means = [sum(by[d]) / len(by[d]) for d in dates]
    n = len(dates)
    if n < 2:
        return dict(n_cohorts=n, cohort_dates=dates, cohort_means=means,
                    truncation_corr=None, late_vs_early_delta=None,
                    late_vs_early_rel=None, early_half_mean=None,
                    late_half_mean=None)
    idx = list(range(n))
    mi = sum(idx) / float(n)
    mm = sum(means) / float(n)
    num = sum((idx[k] - mi) * (means[k] - mm) for k in range(n))
    si = math.sqrt(sum((idx[k] - mi) ** 2 for k in range(n)))
    sm = math.sqrt(sum((means[k] - mm) ** 2 for k in range(n)))
    corr = (num / (si * sm)) if si > 0 and sm > 0 else 0.0
    half = n // 2
    early = means[:half]
    late = means[half:]
    em = sum(early) / len(early)
    lm = sum(late) / len(late)
    return dict(n_cohorts=n, cohort_dates=dates, cohort_means=means,
                truncation_corr=corr, early_half_mean=em, late_half_mean=lm,
                late_vs_early_delta=lm - em, late_vs_early_rel=(lm - em) / em)


def write_brief(path, name, sealed, metric_suffix="", arms=None):
    """The sealed design.

    With more than two arms the brief NAMES them and gives the share each was designed to
    get, because the SRM gate may only read shares from the brief -- never from the counts
    it is meant to be testing.
    """
    names = [a["name"] for a in (arms or [])]
    with open(path, "w") as fh:
        fh.write("experiment: %s\n" % name)
        if len(names) > 2:
            share = int(round(100.0 / len(names)))
            fh.write("assignment: %s user-level\n"
                     % "/".join([str(share)] * len(names)))
            fh.write("arms: %s\n" % "/".join(names))
        else:
            fh.write("assignment: 50/50 user-level\n")
        fh.write("primary_metric: %s%s\n" % (PRIMARY_COL, metric_suffix))
        fh.write("mde: 3%\n")
        fh.write("guardrail: cancel_rate (must not worsen by >1pp)\n")
        fh.write("sealed: %s\n" % sealed)


def build(spec, rng):
    arms = arm_specs(spec)
    names = [a["name"] for a in arms]
    assert len(set(names)) == len(names), ("duplicate arm name", spec["name"])
    drop_primary = spec.get("drop_primary_col", False)
    sigma_p = spec.get("sigma_primary", SIGMA_PRIMARY)

    # Draw order is primary for every arm, then guardrail for every arm, arms in the
    # order arm_specs returns them. That is the order the two-arm generator has always
    # drawn in, so every pre-existing fixture is unchanged.
    primary = {a["name"]: gen_values(rng, a["n"],
                                     CONTROL_PRIMARY_MEAN * (1.0 + a["rel_lift"]),
                                     sigma_p, 4)
               for a in arms}
    guardrail = {a["name"]: gen_values(rng, a["n"],
                                       CONTROL_GUARDRAIL_MEAN + a["cancel_delta"],
                                       SIGMA_GUARDRAIL, 6)
                 for a in arms}
    for vals in guardrail.values():
        for v in vals:
            if not (0.0 <= v <= 1.0):
                raise ValueError("cancel_rate %r outside [0,1] in %s" % (v, spec["name"]))

    dates = assign_dates(spec, arms)

    grad = spec.get("cohort_gradient")
    if grad is not None:
        allds = sorted(set(d for ds in dates.values() for d in ds))
        for name in names:
            primary[name] = apply_cohort_gradient(primary[name], dates[name], allds, grad)

    rows = []
    for a in arms:
        name = a["name"]
        pfx = arm_prefix(name)
        for i in range(a["n"]):
            rows.append(["%s%06d" % (pfx, i), name, dates[name][i],
                         primary[name][i], guardrail[name][i]])
    rng.shuffle(rows)

    # AMENDMENT 3A: unparseable cells in the SECONDARY (guardrail) column.
    # Injected after the shuffle at deterministic positions, split across arms
    # so neither arm is emptied.
    n_bad = spec.get("bad_guardrail_cells", 0)
    bad_rows = 0
    if n_bad:
        want = {"treatment": (n_bad + 1) // 2, "control": n_bad // 2}
        for r in rows:
            if want.get(r[1], 0) > 0:
                r[4] = "n/a"
                want[r[1]] -= 1
                bad_rows += 1
            if not any(want.values()):
                break
        assert bad_rows == n_bad, (spec["name"], bad_rows, n_bad)

    header = list(HEADER)
    if drop_primary:
        header = [h for h in HEADER if h != PRIMARY_COL]
        rows = [[r[0], r[1], r[2], r[4]] for r in rows]

    results_name = "%s_results.csv" % spec["name"]
    with open(os.path.join(HERE, results_name), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for r in rows:
            w.writerow(r)

    brief_name = "%s_brief.yaml" % spec["name"]
    brief_path = os.path.join(HERE, brief_name)
    if spec.get("write_brief", True):
        write_brief(brief_path, spec["name"], spec["sealed"],
                    spec.get("brief_metric_suffix", ""), arms=arms)
    elif os.path.exists(brief_path):
        os.remove(brief_path)

    # --- recompute ground truth from the WRITTEN, ROUNDED rows, in file order --
    pi = header.index(PRIMARY_COL) if not drop_primary else None
    gi = header.index("cancel_rate")
    di = header.index("exposure_date_ist")
    counts = {n: 0 for n in names}
    pvals = {n: [] for n in names}
    gvals = {n: [] for n in names}
    all_dates = []
    for r in rows:
        arm = r[1]
        counts[arm] += 1
        if pi is not None:
            pvals[arm].append(float(r[pi]))
        try:
            gvals[arm].append(float(r[gi]))
        except (TypeError, ValueError):
            pass                      # the injected "n/a" sentinel
        all_dates.append(r[di])

    mean_p = {a: ((sum(pvals[a]) / counts[a]) if pi is not None else None) for a in counts}
    mean_g = {a: ((sum(gvals[a]) / len(gvals[a])) if gvals[a] else None) for a in counts}

    min_date, max_date = min(all_dates), max(all_dates)
    W = 28
    asof_used = spec["asof"] or max_date
    cutoff = (date.fromisoformat(asof_used) - timedelta(days=W)).isoformat()
    mature = sum(1 for d in all_dates if d <= cutoff)

    n = sum(counts.values())
    expected_each = n / float(len(names))
    chi2 = sum((counts[a] - expected_each) ** 2 / expected_each for a in names)

    treatment_arms = [x for x in names if x != "control"]
    entry = dict(
        name=spec["name"],
        results=results_name,
        brief=brief_name,
        brief_exists=spec.get("write_brief", True),
        asof=spec["asof"],
        asof_used=asof_used,
        asof_provenance=("given" if spec["asof"] else "assumed"),
        metric_window_days=W,
        maturity_cutoff_date=cutoff,
        mature_count=mature,
        mature_share=mature / float(n),
        min_exposure_date=min_date,
        max_exposure_date=max_date,
        exposure_span_days_exclusive=(date.fromisoformat(max_date)
                                      - date.fromisoformat(min_date)).days,
        sealed=spec["sealed"],
        primary_metric=PRIMARY_COL + spec.get("brief_metric_suffix", ""),
        primary_col_present=not drop_primary,
        arm_names=names,
        treatment_arms=treatment_arms,
        n_treatment_arms=len(treatment_arms),
        counts=counts,
        srm_chi2=chi2,
        mean_primary=mean_p,
        mean_guardrail=mean_g,
        intended_rel_lift=({a["name"]: a["rel_lift"] for a in arms}
                           if spec.get("arms") else spec["rel_lift"]),
        intended_cancel_delta=({a["name"]: a["cancel_delta"] for a in arms}
                               if spec.get("arms") else spec["cancel_delta"]),
        expect_verdict=spec["expect_verdict"],
        expect_stopped_at=spec["expect_stopped_at"],
        expect_validity_status=spec["expect_validity_status"],
        expect_all_validity_failures=spec["expect_all_validity_failures"],
        expect_first_validity_failure=spec.get(
            "expect_first_validity_failure", spec["expect_stopped_at"]),
        expect_guardrail_status=spec.get("expect_guardrail_status"),
        expect_winning_arms=spec.get("expect_winning_arms"),
        expect_significant_after_holm=spec.get("expect_significant_after_holm"),
        rows_total=len(rows),
        rows_dropped=bad_rows,
        rows_usable=len(rows) - bad_rows,
        dropped_share=bad_rows / float(len(rows)),
        expect_validity_not_assessable=spec.get(
            "expect_validity_not_assessable", []),
        expect_gradient_label=spec.get("expect_gradient_label"),
        cohort_gradient=spec.get("cohort_gradient"),
        sigma_primary=sigma_p,
        expect_truncation_reading=spec.get("expect_truncation_reading"),
        expect_t_band=spec.get("expect_t_band"),
        invalid=spec["expect_stopped_at"] is not None,
        note=" ".join(spec["note"].split()),
    )
    # Per-arm truth. The scalar treatment-vs-control fields below stay exactly where they
    # were for two-arm fixtures, because the whole suite reads them by those names.
    if pi is not None:
        entry["diff_primary_by_arm"] = {a: mean_p[a] - mean_p["control"]
                                        for a in treatment_arms}
        entry["rel_diff_primary_by_arm"] = {a: entry["diff_primary_by_arm"][a]
                                            / mean_p["control"] for a in treatment_arms}
        entry["welch_t_primary_by_arm"] = {}
        entry["p_normal_approx_primary_by_arm"] = {}
        for a in treatment_arms:
            t, p = welch_t(pvals[a], pvals["control"])
            entry["welch_t_primary_by_arm"][a] = t
            entry["p_normal_approx_primary_by_arm"][a] = p
    entry["diff_guardrail_by_arm"] = {a: (mean_g[a] - mean_g["control"])
                                      for a in treatment_arms
                                      if mean_g[a] is not None
                                      and mean_g["control"] is not None}
    if len(treatment_arms) == 1:
        t0 = treatment_arms[0]
        if pi is not None:
            entry["diff_primary"] = entry["diff_primary_by_arm"][t0]
            entry["rel_diff_primary"] = entry["rel_diff_primary_by_arm"][t0]
        entry["diff_guardrail"] = mean_g[t0] - mean_g["control"]
    if pi is not None:
        entry["gradient"] = cohort_stats(rows, di, pi)
    return entry


def write_extras():
    """Fixtures that are not (results, brief) pairs from the table.

    malformed_results.csv holds a non-numeric value in the primary-metric
    column. It is built to be VALID in every other respect -- exact 3/3 split,
    every exposure on 2026-07-27, sealed 2026-07-13 -- and the tests run it with
    --asof 2026-08-24 so all three validity gates PASS and the lift genuinely
    has to parse the value. Without that, maturity would fail first and the bad
    cell would never be touched, so the test would prove nothing.
    """
    with open(os.path.join(HERE, "malformed_results.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(HEADER)
        w.writerow(["t000001", "treatment", "2026-07-27", "2.1", "0.05"])
        w.writerow(["t000002", "treatment", "2026-07-27", "2.3", "0.05"])
        w.writerow(["t000003", "treatment", "2026-07-27", "2.2", "0.05"])
        w.writerow(["c000001", "control", "2026-07-27", "2.0", "0.05"])
        w.writerow(["c000002", "control", "2026-07-27", "NOT_A_NUMBER", "0.05"])
        w.writerow(["c000003", "control", "2026-07-27", "1.9", "0.05"])
    write_brief(os.path.join(HERE, "malformed_brief.yaml"), "malformed", "2026-07-13")

    # Same shape, but the unparseable value is in the GUARDRAIL column.
    with open(os.path.join(HERE, "malformed_guardrail_results.csv"), "w",
              newline="") as fh:
        w = csv.writer(fh)
        w.writerow(HEADER)
        w.writerow(["t000001", "treatment", "2026-07-27", "2.1", "0.05"])
        w.writerow(["t000002", "treatment", "2026-07-27", "2.3", "n/a"])
        w.writerow(["t000003", "treatment", "2026-07-27", "2.2", "0.05"])
        w.writerow(["c000001", "control", "2026-07-27", "2.0", "0.05"])
        w.writerow(["c000002", "control", "2026-07-27", "2.05", "0.05"])
        w.writerow(["c000003", "control", "2026-07-27", "1.9", "0.05"])

    # A results file with no `arm` column at all: a REQUIRED column is absent,
    # which the contract makes gate 0's business (INVALID-DESIGN, exit 0).
    with open(os.path.join(HERE, "no_arm_col_results.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["user_id", "exposure_date_ist", PRIMARY_COL, "cancel_rate"])
        for i in range(6):
            w.writerow(["u%06d" % i, "2026-07-27", "2.0", "0.05"])


def main():
    rng = random.Random(SEED)
    manifest = {
        "contract_version": "v1.1 (frozen contract + AMENDMENT 1)",
        "seed": SEED,
        "primary_col": PRIMARY_COL,
        "validity_gates": VALIDITY_GATES,
        "conclusion_gates": ["guardrail", "lift"],
        "control_primary_mean": CONTROL_PRIMARY_MEAN,
        "control_guardrail_mean": CONTROL_GUARDRAIL_MEAN,
        "sigma_primary": SIGMA_PRIMARY,
        "sigma_guardrail": SIGMA_GUARDRAIL,
        "fixtures": {},
    }
    for spec in FIXTURES:
        manifest["fixtures"][spec["name"]] = build(spec, rng)

    # Guard (AMENDMENT 3A): the boundary fixtures must genuinely straddle 2%.
    at = manifest["fixtures"]["dropped_at_2pct"]
    over = manifest["fixtures"]["dropped_over_2pct"]
    assert at["dropped_share"] == 0.02, at["dropped_share"]
    assert over["dropped_share"] > 0.02, over["dropped_share"]
    assert over["rows_dropped"] == at["rows_dropped"] + 1, "boundary must be 1 row wide"

    # Guard (AMENDMENT 2): an un-pinned asof falls back to the system date, so
    # the verdict would silently change as days pass. Refuse to generate.
    for name, e in manifest["fixtures"].items():
        assert e["asof"], ("fixture %r has no explicit asof; under v1.2 that "
                           "makes its verdict time-dependent" % name)

    # Guard: every INVALID fixture must carry a genuinely juicy, unique lift and
    # a genuine guardrail breach, or the suppression test proves nothing.
    seen = {}
    for name, e in manifest["fixtures"].items():
        if not e["invalid"]:
            continue
        if e["primary_col_present"]:
            for arm, rel in e["rel_diff_primary_by_arm"].items():
                assert abs(rel) > 0.05, (name, arm, "lift too small to notice")
                key = round(rel, 6)
                assert key not in seen, ("duplicate rel lift", name, seen.get(key))
                seen[key] = name
        assert max(e["diff_guardrail_by_arm"].values()) > 0.01, (
            name, "guardrail is not a real breach")

    # Guard (v1.4): the A/B/n fixtures only teach what they are for if they landed in the
    # band they were designed for. The bands are stated in t units against the normal
    # approximation, well clear of every boundary they straddle, so a fixture that drifts
    # is caught here rather than in a test that reads as "the maths changed".
    for name, e in manifest["fixtures"].items():
        band = e.get("expect_t_band")
        if not band:
            continue
        for arm, (lo, hi) in band.items():
            t = e["welch_t_primary_by_arm"][arm]
            assert lo <= t <= hi, (name, arm, "welch t %.4f outside the designed band "
                                              "[%.2f, %.2f]" % (t, lo, hi))
    write_extras()

    with open(os.path.join(HERE, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")

    print("wrote %d fixtures + manifest.json to %s" % (len(FIXTURES), HERE))
    print("%-25s %-13s %-8s %-11s %-9s %s"
          % ("fixture", "split", "chi2", "rel_lift", "g_delta", "verdict"))
    for name in sorted(manifest["fixtures"]):
        e = manifest["fixtures"][name]
        split = "/".join("%d" % e["counts"][a] for a in e["arm_names"])
        rel = e.get("rel_diff_primary_by_arm") or {}
        gd = e.get("diff_guardrail_by_arm") or {}
        print("%-25s %-13s %-8.3f %-11s %+9.5f %s"
              % (name, split, e["srm_chi2"],
                 ",".join("%+.5f" % v for v in rel.values()) or "n/a",
                 max(gd.values()) if gd else 0.0, e["expect_verdict"]))


if __name__ == "__main__":
    main()
