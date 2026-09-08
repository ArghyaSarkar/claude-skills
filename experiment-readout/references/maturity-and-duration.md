# Maturity and duration

Cite as `references/maturity-and-duration.md § <section>`. Plain English explains; blocks
labelled **RULE —** and **DEFINITION —** are exact and are quoted as written, never
paraphrased.

Two separate questions live here. Answer both; they fail independently.

| Question | Driven by | Script |
|---|---|---|
| **How many weeks does this MDE require?** | MDE → sample size → enrolment days + window | `scripts/power.py` |
| **Have those weeks actually elapsed in this data?** | exposure dates vs the metric window | GATE 2 in `scripts/run_readout.py` |

A design can pass the first and fail the second (enough users, read too early), or pass the
second and fail the first (waited long enough, never enough users). Never let one answer the
other.

## Q1 — MDE → sample size → weeks

The chain runs from "how small a change do we care about" to "how many weeks does that cost".
Each step feeds the next, and every step should appear in the answer, because the PM needs to
see which one is expensive.

**DEFINITION —** Chain, in order:

1. **MDE → absolute effect.** MDE is relative to the control mean unless the brief says
   otherwise: `delta = mde_rel * baseline_mean`.
2. **Absolute effect → n per arm.**
   `n = 2 * (z_{alpha/2} + z_{power})^2 * sd^2 / delta^2`
   with alpha = 0.05 two-sided (z = 1.959964) and power = 0.80 (z = 0.841621).
   Baseline mean and sd come from the **control arm**. Smaller MDE and higher variance both
   raise n quadratically: halving the MDE quadruples n.
3. **n per arm → enrolment days.** `exposure_days = ceil(n_per_arm / daily_users_per_arm)`,
   where the daily rate is observed (users per arm per distinct exposure day) or supplied.
4. **Enrolment days → total days.** `total_days = exposure_days + W`, `total_weeks =
   ceil(total_days / 7)`. The window is added once, not per user: the last-enrolled user
   sets the finish line.

Caveats to state alongside the number:

- An sd estimated from an **immature** metric column is too small, so the n it produces is a
  **floor**, not the requirement. Re-estimate from a mature cohort when you can.
- A rerun's traffic may not match the daily rate you observed here. Say which rate you used.
- `n` is per arm. Total users = n × number of arms.
- Fixed horizon: plan the duration, then read once at the end. Looking early and often
  inflates the false-positive rate, so if interim looks are genuinely required that is a
  sequential design and needs different thresholds.
- Round up to whole weeks. Behaviour differs by day of week, so a 10-day read gives different
  cohorts a different mix of weekdays and weekends.

## Q2 — is the window closed in the data you were handed?

**DEFINITION — A metric with an N-day window is not observable until N days after exposure.**
For a user exposed on day D, `completed_orders_28d` is only a complete measurement on D+28.
Before that the column holds a partial count that looks like a smaller number — and partial
counts are not equally partial across cohorts.

**DEFINITION —** Checks, in order:

1. **Window.** Parse W from the metric name (`_(\d+)d$`). No suffix → the window is unknown,
   maturity is not machine-checkable, and you must ask the metric owner rather than assume.
2. **Exposure span.** `exposure_span_days = (max - min exposure date) + 1`. This is how long
   enrolment ran — not how long the experiment has been observable.
3. **As-of date.** Resolved by the order in § As-of resolution below, never guessed silently.
   The provenance is reported with the date, every time.
4. **Maturity cutoff.** `cutoff = asof - W`. Anyone exposed after the cutoff cannot be
   mature. `mature_share = share of users exposed on or before the cutoff`.
5. **Full maturity date.** `last_exposure + W` — the earliest date the whole cohort is
   readable.
6. **Required days, end to end.** `exposure_span_days + W` (`required_days` in the payload),
   i.e. the calendar cost of enrolling everyone *and* waiting out the window.

Anything short of everyone being mature fails, but for one of two reasons, and the report has
to name the right one.

**DEFINITION —** `mature_share < 1.0` is a FAIL either way:

| mature_share | Why it fails |
|---|---|
| 0 | Nothing is measured yet. Every value in the metric column is a partial count. |
| between 0 and 1 | Differential follow-up. Early cohorts have more observed time than late ones, so a difference of means mixes the treatment effect with an exposure-age effect. Dropping the late cohort does not fix it — that is post-hoc selection on a variable correlated with the outcome. |

## As-of resolution — and why the default is *today*

A results file that carries only exposure dates cannot tell you when the metric was
extracted. So look for that date in a fixed order, and always say which source won.

**DEFINITION —** Resolve in this order, first hit wins:

| Order | Source | Provenance |
|---|---|---|
| 1 | explicit `--asof` | `given` |
| 2 | an as-of / extract / snapshot column in the CSV | `from data` |
| 3 | a date stated in the ask (pass it as `--asof-from-request`) | `from request` |
| 4 | today's system date | `assumed: today` |

**Why today, and not the last exposure date.** Pick the *most generous defensible* value, so
that a failure is certain rather than manufactured.

- Today is an **upper bound** on any possible extract date: data cannot describe the future,
  so no real extract can be later than now. Under the most generous assumption available, a
  maturity FAIL is unavoidable — it is a fact about the data, not an artefact of the default.
- `max(exposure_date)` is a **lower bound**, and a fatal one: the last-exposed user is by
  definition 0 days old, so `mature_share == 1.0` is arithmetically impossible for any window
  W > 0. A gate that can never pass carries no information and trains you to treat
  INVALID-IMMATURE as the house answer. Never reintroduce it as a default.
- The direction of the fix is which bound to default to, not how strict the gate is. The gate
  is unchanged: `mature_share < 1.0` fails.
- The generosity runs one way only: it licenses a certain FAIL, never a clean PASS. See
  `gates.md § GATE 2`, **RULE — An assumed as-of date can never produce a PASS**.

**RULE — Determinism.** The `assumed: today` fallback makes the verdict time-dependent — the
same file can read PASS tomorrow and FAIL next month. Any run that must be reproducible (a
fixture, a test, a number you will cite later, anything a reader may re-run) **must** pass an
explicit `--asof`. The payload always records `asof`, `asof_provenance` and `reproducible`, so
the assumption stays auditable after the fact.

## The truncation gradient — maturity evidence with no as-of date at all

The as-of date is an input you may not have. The data's own shape is not.

**DEFINITION — A genuinely truncated N-day metric must slope downward over exposure date.**
Later cohorts have had less follow-up time, so their partial counts are mechanically smaller.
So compute the primary metric's mean per exposure date and measure the trend:

- `late_vs_early_rel` — mean of the late half of cohorts vs the early half, relative. **This is
  the decider.** It is a percentage change between two averages: stable, scale-aware, and it
  answers the question actually being asked ("how much lower are the late cohorts?").
- `corr` + `corr_p_value` — Pearson correlation of cohort index with cohort mean. **Supporting
  context only, never the decider.** Over near-equal cohort means r is scale-free and
  noise-dominated: an r of −0.03 on a flat series is an artefact, and even an r of −1.0 can
  accompany a decline too small to matter. Reporting r as the headline evidence for flatness is
  a statistical error, and letting it drive the branch would rest the DATA INTEGRITY finding —
  the strongest claim in the readout — on noise.
- **Fewer than 3 cohorts: refuse.** At n = 2, Pearson r is ±1 by construction for any two
  points, and each "half" is a single cohort — a late-vs-early trend from two points is not a
  trend. n = 3 is the first size at which the magnitude compares distinct cohorts, and the
  branch never depends on r. Anything below that reports `insufficient_cohorts`, not a
  direction. (A stricter bar on r itself — n >= 4, since dof = n − 2 = 1 at n = 3 — is
  reasonable and compatible: it constrains the context statistic, not the refusal.)
- Branch rule: `late_vs_early_rel <= −2%` -> late_lower; `>= +2%` -> late_higher; otherwise flat.
  A truncated N-day metric read over a span comparable to its window moves by tens of percent,
  so a ±2% band is generous: anything inside it is flat for practical purposes.
- When the magnitude is inside the band but r is strongly negative and significant, the reading
  must be rewritten, not annotated: say "the cohort means DO decline monotonically, but by far
  less than an N-day truncation forces — too little movement, not none." Writing "the values do
  not move with follow-up time" and then appending a nuance is wrong, because **a qualifying
  clause does not unsay a false sentence** (see `output-templates.md § RULE — Universal rules`). The
  branch is still decided by magnitude; the correlation only selects the wording.
- Pooled **across arms** by design: a pooled time trend carries no treatment-vs-control
  information, so this diagnostic is safe to compute and report even when the conclusion gates
  are suppressed. Never split it by arm — that is a lift by the back door.
- Report the **trend**, not the level: quote the relative late-vs-early change and the
  correlation, never the absolute cohort means. A level reads as a conclusion number even when
  it is not one.

Two readings come out of this, and the second one is the more valuable finding. If the values
do not depend on follow-up time when the calendar says they must, the column itself is the
problem — and unlike immaturity, waiting does not fix it.

**DEFINITION —**

| Gradient | Timeline says maturity is impossible | Read it as |
|---|---|---|
| late cohorts lower | yes | **Truncation confirmed** from the data alone. Immature at high confidence, no as-of date needed. |
| flat, or late cohorts *higher* | yes | **DATA INTEGRITY CONCERN.** The values do not show the follow-up-time dependence they must have. The column is suspect: back-filled, recomputed, mis-joined, or not the metric the brief names. Say so plainly — it is a stronger and more actionable finding than "immature", and a rerun of a mis-built metric reproduces the same unusable column. |
| any | no (all cohorts mature, on an as-of date that was SUPPLIED) | Not required. Report it as context only; a slope in mature data is seasonality or novelty, not truncation. |
| no downward slope | no — but only under an ASSUMED as-of date | **Corroborating, never conclusive.** A file extracted before the window closed would show the late cohorts lower, and none of that appears — CONSISTENT WITH a late-enough extract, not proof of one. |
| late cohorts lower | no — but only under an ASSUMED as-of date | Evidence AGAINST the assumed date: the truncation signature is present, which points at an extract taken before the window closed. Ask for the extraction date. |
| fewer than 3 cohorts | any | Not assessable. Say that, do not infer from two points. |

**RULE — Report the numbers the data gives and the branch they put you in. Never assume a
branch.**

## The claim-vs-data check

When the ask asserts a duration ("it finished 4 weeks", "it's been running a month"), that is
a claim about the data, so test it.

**DEFINITION —**

1. Convert the claim to days (4 weeks = 28).
2. Compare with `exposure_span_days` from the data.
3. If they disagree, say so plainly and use the data: *"the ask says 4 weeks; the file's
   exposure span is N days (first .. last)."* Do not restate the claim as fact, and do not
   quietly substitute the data without flagging the mismatch — the requester's mental model is
   part of what needs correcting.
4. Then check the claim against the window too. Runtime longer than the window is necessary
   but not sufficient: enrolment must have *stopped* at least W days before the read.

A duration claim and an as-of assumption can both be wrong in the same readout. They are
separate problems, so state each separately.

## What a rerun plan must contain

- n per arm and total, with the MDE and baseline it came from.
- Enrolment days at the assumed daily rate, plus the W-day maturation wait, plus the total in
  weeks.
- The fix for every validity failure found in the last run — for instance the assignment bug
  behind an SRM. Running a broken design for longer leaves it broken.
- The read date, committed in advance, and a note that the read happens once.
- What would change the plan: a different MDE, a wider guardrail, or a shorter-window proxy
  metric sealed *before* the rerun starts.
