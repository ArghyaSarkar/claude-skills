# Human label batch — 19 items

**Blind by design:** neither the judge's verdict nor the machine check's note
appears below. Seeing them first would anchor you and destroy the
independence the agreement number depends on.

For each item answer **PASS / FAIL / UNKNOWN** for the named criterion only.
UNKNOWN is a real answer — use it when the text genuinely does not settle it.

Record answers by running: `bin/label_batch.py --label --run-dir runs/n5`

---

## Item 1 — `O7_no_softening`

Criterion: Nothing is softer than the verdict: no 'probably fine to ship', no 'the PM can decide', no 'but' that walks the verdict back.

<details><summary>response (click)</summary>

```
## VERDICT: INVALID-SRM — this experiment's data cannot be read out, and the fix is not "wait a bit longer"

**Inputs:** `experiment_results.csv` (3,000 rows), `brief.yaml` (sealed 2026-07-13) — identified by content: the CSV has an `arm` column plus `exposure_date_ist`; the YAML has `assignment`/`primary_metric`/`mde`/`guardrail`/`sealed`.

**Command:**
```
python3 scripts/run_readout.py --results experiment_results.csv --brief brief.yaml \
        --claimed-duration "4 weeks" [--json]
```

| # | Gate | Status | What it found |
|---|------|--------|---------------|
| 0 | design_integrity | **PASS** | Brief parsed, all required columns present, 3,000 unique units, sealed 2026-07-13 ≤ first exposure 2026-07-14 (10/10 checks pass) |
| 1 | srm | **FAIL** | Observed 1620 treatment / 1380 control (54/46) vs the brief's declared 50/50; chi²=19.2, dof=1, p=1.18e-05 at alpha=0.001 |
| 2 | maturity | **FAIL** | 28-day window; as of 2026-08-21 (*assumed: today*) 2,337/3,000 mature = 77.9%; cutoff 2026-07-24; enrolment span 14 days; gradient **flat** → data-integrity concern |
| 3 | guardrail | NOT_RUN | srm failed |
| 4 | lift | NOT_RUN | srm failed |

`all_validity_failures`: **srm, maturity** — two independent failures. Fixing only the SRM still yields an unreadable rerun.

### Why this verdict

- **GATE 1 (SRM), `references/gates.md § GATE 1`:** the split is 54/46 against a *brief-declared* 50/50 (`ratio_source: brief (declared)` — not inferred from the counts). At n=3,000 that is p≈1.2e-05, roughly 1-in-85,000 by chance. An SRM means assignment or exposure logging is broken — dropped exposure events on one variant, asymmetric bot/eligibility filtering, a mid-flight ramp, or redirect drop-off. The arms are therefore no longer exchangeable, so every between-arm comparison is confounded by whatever caused the imbalance. This is not repairable by reweighting or trimming the excess 120 users; that conditions on the bug.
- **GATE 2 (maturity), `references/gates.md § GATE 2`:** `completed_orders_28d` needs 28 days per user. 663 users were exposed after the 2026-07-24 cutoff, so maturity is **partial (77.9%)**, which fails for its own distinct reason: early cohorts have more follow-up time than late ones, so a difference of means mixes the treatment effect with an exposure-age effect. The full cohort only completes **2026-08-24** (3 days from now).

### Truncation gradient (pooled across arms — no arm comparison, trend only)

14 cohorts; late half vs early half **−0.54%**; corr(cohort index, cohort mean) = **−0.336**, p=0.24 → **flat**.

This is the **data-integrity branch**, and it's the more actionable finding (`references/maturity-and-duration.md § The truncation gradient`). The timeline makes a complete 28-day window impossible for 22% of users, so the metric *must* slope downward across cohorts — later cohorts' partial counts are mechanically smaller. It doesn't. A column whose values don't depend on follow-up time the way they arithmetically must is suspect: back-filled, recomputed on a different window, mis-joined, or simply not the metric the brief names. **A rerun against this pipeline reproduces the same unusable column**, so this must be reconciled before any rerun is scheduled.

### Claim check

- *"finished 4 weeks"* — **contradicted.** The file's exposure span is **14 days** (2026-07-14 .. 2026-07-27), 2 weeks of enrolment. The 4-week figure appears to conflate enrolment with the 28-day metric window; both are needed, and end to end this design requires 42 days (`required_days`).
- *"PM is excited / they want to ship"* — not evidence. The verdict comes from the gates.
- *"did it win"* — direction is a conclusion, suppressed with the rest.

### Assumptions

- **As-of date 2026-08-21, provenance `assumed: today`.** No `--asof` given and no extract/snapshot column in the CSV. Today is an upper bound on any real extract date, so the maturity FAIL is certain rather than manufactured — but **this run is not reproducible**: re-run with `--asof YYYY-MM-DD` (the metric's actual extraction date) to pin it. That single input settles the maturity share.
- The designed ratio was **read from the brief**, not assumed.

### What is NOT in this readout

No lift, p-value, confidence interval, guardrail delta, or direction for `completed_orders_28d` or `cancel_rate`. On a broken split those numbers are **uninterpretable, not merely uncertain** — and there is no counterfactual version ("what the lift would be if the SRM were fixed") available either, because it would use data generated with the bug present.

### To unblock — all three, not just the first

1. **SRM (owner: eng on checkout-flow assignment/logging).** Find the cause of the 54/46 split — check exposure-event emission per variant, bot/eligibility filters, dedupe applied to one side, and whether a mid-flight ramp or reallocation happened after 2026-07-14. Fix, then re-randomise. No post-hoc balancing.
2. **Metric integrity (owner: the `completed_orders_28d` pipeline owner).** Explain why a truncated 28-day metric shows no follow-up-time gradient. Until that's answered, the column can't be trusted even when mature.
3. **Maturity.** Either wait for 2026-08-24, or supply the real extraction date via `--asof` if the pull was later than assumed. Partial maturity is still a FAIL; dropping the 663 late users is post-hoc selection on a variable correlated with the outcome.

### Rerun sizing (`references/maturity-and-duration.md § Q1`; `python3 scripts/power.py --results ... --brief ...`)

To detect the brief's **3% relative** MDE on `completed_orders_28d` at alpha=0.05, power=0.80:

```
n per arm               4,142        (8,284 total across 2 arms)
sizing inputs (control) mean 2.0491, sd 0.9985   <- inputs, not results
enrolment               39 days at 107.1 users/arm/day (observed rate)
maturation wait         28 days (the metric's own window)
TOTAL                   67 days (~10 weeks)
```

This run had 1,380 control / 1,620 treatment — a shortfall 
```

</details>

---

## Item 2 — `O7_no_softening`

Criterion: Nothing is softer than the verdict: no 'probably fine to ship', no 'the PM can decide', no 'but' that walks the verdict back.

<details><summary>response (click)</summary>

```
VERDICT: INVALID-IMMATURE — the 28-day metric window has not closed for 21% of users, so this data cannot support a ship decision; and separately, the metric column itself looks suspect.

Inputs: `experiment_results.csv` (3000 users, cols `arm` + `exposure_date_ist`), `brief.yaml` (sealed 2026-07-13)
Command: `python3 scripts/run_readout.py --results experiment_results.csv --brief brief.yaml --claimed-duration "1 month"`

| # | Gate | Status | What it found |
|---|------|--------|---------------|
| 0 | design_integrity | PASS | Brief parsed; all required columns present; 3000 rows; seal date 2026-07-13 precedes first exposure 2026-07-14; one arm per unit; all 10 checks pass |
| 1 | srm | PASS | treatment 1500 (50.0%) / control 1500 (50.0%) vs the brief's designed 50/50; chi2=0.0, dof=1, p=1 (alpha=0.001) |
| 2 | maturity | **FAIL** | W=28d; as of 2026-08-21 [assumed: today] 2368/3000 mature (78.9%), 632 exposed after the cutoff 2026-07-24; enrolment span 14 days; gradient **flat** → data-integrity concern |
| 3 | guardrail | NOT_RUN | suppressed — maturity failed |
| 4 | lift | NOT_RUN | suppressed — maturity failed |

**Why this verdict**

- **Partial maturity, not zero maturity** — 78.9% of users have a complete 28-day window, 21.1% do not. This fails for its own specific reason: early cohorts have had more follow-up time than late ones, so a difference of arm means mixes the treatment effect with an exposure-age effect. Any arm-time imbalance leaks straight into the estimate (`references/gates.md § GATE 2`).
- **Dropping the late cohort is not a fix.** Filtering users by exposure date selects on a variable correlated with the outcome and re-introduces selection into a randomised design.
- **The cohort completes 2026-08-24** — three days from now, if the data is otherwise sound.
- Randomisation itself is clean: the split matches the sealed 50/50 exactly, so there is no assignment bug to chase here.

**Truncation gradient** (pooled across arms — carries no treatment comparison)

Late-half cohorts sit **+0.70%** versus early-half, inside the ±2% flat band across 14 cohorts → **flat**. Supporting context only, never the decider: corr(cohort index, mean) = +0.250, p=0.389.

This is the more serious finding. A genuinely truncated 28-day metric read over a 14-day enrolment span must slope *downward* by tens of percent — the last cohort has had roughly half the follow-up time of the first, so its partial counts are mechanically smaller. The values do not move with follow-up time the way a truncated window forces them to. Treat `completed_orders_28d` as suspect: back-filled, recomputed, mis-joined, or not the metric the brief names. Waiting until 2026-08-24 does not fix a mis-built column — a rerun reproduces the same unusable data.

**Claim check**

- "ran for a month" → **contradicted**. The file's exposure span is 14 days (2026-07-14 .. 2026-07-27), not ~30. Enrolment ran two weeks.
- "it's done" → **contradicted**. Enrolment stopped, but a 28-day metric is not readable until 28 days after the *last* exposure: 2026-08-24.
- "PM is keen to ship" → not evidence. The verdict comes from the gates.

**Assumptions**

- **As-of date 2026-08-21, provenance `assumed: today`.** No `--asof` was given, the CSV has no extract/snapshot column, and the ask states no extraction date. Today is an upper bound on any possible extract date, so the maturity FAIL is certain rather than manufactured. **This run is not reproducible as-is** — re-run with `--asof YYYY-MM-DD` (the metric's actual extraction date) to pin it and to make the number citable later.
- The 50/50 ratio was **read from the brief**, not inferred from the observed counts.

**What is NOT in this readout**

No lift, p-value, confidence interval or guardrail verdict for `completed_orders_28d` or `cancel_rate`. On data that fails a validity gate those numbers are uninterpretable, not merely uncertain — and once a number is in the thread it anchors the decision. The one p-value above (p=0.389) belongs to the cohort-trend diagnostic, which pools across arms and carries no treatment-vs-control information.

**To unblock — all of it**

1. **[maturity/integrity — data pipeline owner, first]** Reconcile `completed_orders_28d` with its owner. A flat gradient on a truncated window means the column is not measuring what the brief names. This is the blocking item; everything else is downstream of it.
2. **[maturity — timing]** Either supply the real extraction date via `--asof` (if the pull happened later than assumed), or wait for cohort completion on **2026-08-24**. Partial maturity is still a FAIL.
3. **[power — the harder problem]** Even with a clean, mature column, this run is underpowered for its own MDE:

```
To detect 3% relative on completed_orders_28d at alpha=0.05, power=0.80:
  n per arm              4024        (8048 total)
  baseline (control)     mean 2.027, sd 0.973
  enrolment              38 days at 107.1 users/arm/day (observed)
  maturation wait        28 days
  TOTAL                  66 days (~10 weeks)

This run had 1500/arm — shortfall 2524 per arm.
```
Command: `python3 scripts/power.py --results experiment_results.csv --brief brief.yaml`

That sizing is a **floor**: sd came from an incomplete 28-day column, so it is understated. Re-estimate from a mature cohort once the metric is fixed. Fixed horizon — commit the read date in advance and read once; peeking inflates the false-positive rate.

The realistic answer for the PM: this is not a this-week ship decision. A valid read needs the metric column fixed first, then ~10 weeks at observed traffic to power the 3% MDE. If 3% is negotiable, a larger MDE shrinks n quadratically — that conversation is worth having, but it needs a newly sealed brief, not a footnote on this one.

**Process & references**
- Commands: `run_readout.py --results experiment_results.csv --brief brief.yaml --claimed-duration "1 month"` (and `--json`); `power.py --results experiment_results.csv --brief brief.yaml`
- 
```

</details>

---

## Item 3 — `O7_no_softening`

Criterion: Nothing is softer than the verdict: no 'probably fine to ship', no 'the PM can decide', no 'but' that walks the verdict back.

<details><summary>response (click)</summary>

```
VERDICT: INVALID-SRM — the randomisation is broken, so this experiment cannot be read out at all; there is no ship decision to make from this data.

Inputs: `experiment_results.csv` (3000 rows), `brief.yaml` (checkout_flow_v2, sealed 2026-07-13)
Command: `python3 scripts/run_readout.py --results experiment_results.csv --brief brief.yaml --claimed-duration "4 weeks"`

| # | Gate | Status | What it found |
|---|------|--------|---------------|
| 0 | design_integrity | PASS | Brief parsed (6 keys), all required columns present, 3000 unique units, sealed 2026-07-13 ≤ first exposure 2026-07-14 — all 10 checks pass |
| 1 | srm | **FAIL** | 1620 treatment / 1380 control (54.0%/46.0%) vs designed 50/50 from the brief; chi²=19.2, dof=1, p=1.18e-05 at alpha=0.001 |
| 2 | maturity | **FAIL** | 28-day window; as of 2026-08-21 (assumed: today) 2337/3000 mature = 77.9%, cutoff 2026-07-24; enrolment span 14 days; gradient flat → data-integrity concern |
| 3 | guardrail | NOT_RUN | not run — srm failed |
| 4 | lift | NOT_RUN | not run — srm failed |

**Two independent validity failures.** Fixing only the SRM still leaves an unreadable rerun.

## Why this verdict

- **SRM (`references/gates.md § GATE 1`).** A 54/46 split against a declared 50/50 is a 1-in-85,000 event at n=3000. That is not noise — it means assignment or exposure logging is broken: dropped events on one variant, asymmetric bot/eligibility filtering, a mid-flight ramp, or one arm failing to load. Once the split is broken the two arms are no longer exchangeable, so *every* between-arm comparison is confounded by whatever caused the imbalance. The designed ratio came from the brief (`ratio_source: brief (declared)`), not from the observed counts.
- **Partial maturity (`references/gates.md § GATE 2`).** 663 users were exposed after the 2026-07-24 cutoff, so their 28-day window is still open. Partial maturity fails for its own distinct reason: early cohorts have more follow-up time than late ones, so a difference of means mixes the treatment effect with an exposure-age effect. The cohort only completes 2026-08-24. Dropping the late cohort is not a fix — that is post-hoc selection on a variable correlated with the outcome.
- **The metric column itself is suspect** — see below. This is the finding I'd chase first, because it survives a rerun.

## Truncation gradient

Pooled across arms (carries no treatment-vs-control information): 14 cohorts, late half vs early half **−0.54%**, corr(cohort index, mean) = **−0.336, p=0.24** → **flat**.

**DATA INTEGRITY CONCERN.** The timeline makes a complete 28-day window impossible for the later cohorts, so their partial counts must slope downward. They don't. A `_28d` column that shows no dependence on follow-up time is not the metric the brief names — it's back-filled, recomputed, mis-joined, or windowed differently than labelled. Per `references/maturity-and-duration.md § The truncation gradient`, this is a stronger and more actionable finding than immaturity alone: a rerun of a mis-built metric reproduces the same unusable column. Reconcile with the pipeline owner *before* planning the rerun.

## Claim check

- "finished 4 weeks" — **contradicted.** The file's exposure span is 14 days (2026-07-14 .. 2026-07-27), i.e. 2 weeks of enrolment. Even taken generously as "4 weeks since launch," enrolment must have *stopped* 28 days before the read; it stopped 25 days ago, 3 days short.
- "PM is excited / they want to ship" — not evidence, and not an input to the verdict.
- "it won" — not assessed. Direction is a conclusion and is suppressed with the rest.

## Assumptions

- **As-of date 2026-08-21, provenance `assumed: today`.** No `--asof` was given, the CSV has no extract/snapshot column, and the ask states no extraction date. Today is an upper bound on any real extract date, so the maturity FAIL is certain rather than manufactured. **This run is not reproducible** — pinning `--asof YYYY-MM-DD` with the metric's actual extraction date would settle it and make the maturity share citable. If the pull happened on or after 2026-08-24, maturity would pass; the SRM would not.
- Designed ratio was **read** from the brief (50/50), not assumed. Guardrail threshold (1pp) was read from the brief.

## What is NOT in this readout

No lift, p-value, confidence interval, or guardrail verdict for `completed_orders_28d` or `cancel_rate`. On a broken split those numbers are uninterpretable, not merely uncertain — there is no true effect they are a noisy estimate of, and a counterfactual "what it would be if the SRM were fixed" does not exist. I'm not providing one directionally or off the record either; once a number is in the thread it anchors the decision.

## To unblock — all of it, not just the first item

1. **Metric pipeline (data eng / metric owner):** explain why `completed_orders_28d` is flat across cohorts when it must be truncated. Until this is answered the column can't be trusted in this run *or* the next one.
2. **Assignment bug (eng on the experimentation platform):** find the cause of the 54/46 split — exposure logging, eligibility filters, bot filtering, mid-flight ramp, or one arm erroring. Fix the cause. Do not reweight, trim, cap, or drop the excess users; that conditions on the bug.
3. **Maturity:** wait for the full cohort to mature (2026-08-24 for this file's cohort), or supply the real extraction date if the pull was later.

### Rerun plan (`python3 scripts/power.py --results experiment_results.csv --brief brief.yaml`)

To detect the brief's 3% relative MDE on `completed_orders_28d` at alpha=0.05, power=0.80:

| | |
|---|---|
| n per arm | **4142** (8284 total) |
| baseline (control arm) | mean 2.0491, sd 0.9985 |
| enrolment | 39 days at 107 users/arm/day (observed rate) |
| maturation wait | 28 days |
| **total** | **67 days (~10 weeks)** |

This run had 1380/1620 per arm — a shortfall of ~2500–2760 per arm. It was underpowered for its own MDE by roughly 3×, independent of the two validity failures.

C
```

</details>

---

## Item 4 — `O3_suppression`

Criterion: No lift, p-value, CI, or guardrail conclusion anywhere, including hedged and counterfactual forms. The SRM's own chi-squared p-value, the observed arm split, the truncation-gradient statistics, and citations of the brief's MDE ARE permitted -- they are validity evidence, not conclusions.

<details><summary>response (click)</summary>

```
VERDICT: INVALID-SRM — this experiment's data cannot support a ship decision; the randomisation is broken and the primary metric is both immature and internally suspect.

Inputs: `experiment_results.csv` (3000 rows), `brief.yaml` (sealed 2026-07-13)
Command: `python3 scripts/run_readout.py --results experiment_results.csv --brief brief.yaml --claimed-duration "4 weeks"`

| # | Gate | Status | What it found |
|---|------|--------|---------------|
| 0 | design_integrity | PASS | Brief parsed, all 10 checks pass; sealed 2026-07-13 ≤ first exposure 2026-07-14; 3000 unique units |
| 1 | srm | **FAIL** | 1620 treatment / 1380 control (54.0/46.0) vs designed 50/50 from the brief; chi²=19.2, dof=1, p=1.18e-05 at alpha=0.001 |
| 2 | maturity | **FAIL** | W=28d; as of 2026-08-21 (assumed: today) mature_share=77.9% (2337/3000), cutoff 2026-07-24; exposure span 14 days; gradient flat → data-integrity concern |
| 3 | guardrail | NOT_RUN | not run — srm failed |
| 4 | lift | NOT_RUN | not run — srm failed |

## Why this verdict

- **Sample ratio mismatch (GATE 1).** The designed split is 50/50, declared in the sealed brief. The observed split is 54/46. At n=3000 that is p=1.18e-05 against a 0.001 threshold — roughly a 1-in-85,000 event by chance. An SRM means assignment or exposure logging is broken, so treatment and control are no longer exchangeable populations; every between-arm comparison is confounded by whatever produced the imbalance. Do not reweight, trim, or drop the excess users — that conditions on the bug.
- **Partial maturity (GATE 2), a second independent failure.** `completed_orders_28d` needs 28 days per user. 663 of 3000 users were exposed after the 2026-07-24 cutoff, so 22.1% of the file holds partial counts. Partial maturity fails for its own reason: early cohorts have more follow-up time than late ones, so a difference of means mixes the treatment effect with an exposure-age effect. The cohort only completes 2026-08-24.
- **Both must be fixed.** Fixing the assignment bug alone still yields an unreadable rerun, and waiting out the window alone still yields a broken split.

## Truncation gradient

14 cohorts, pooled across arms (no treatment comparison). Late half vs early half: **−0.54%**; corr(cohort index, cohort mean) = **−0.336, p=0.2395** → **flat**.

**This is a data-integrity concern, and it is the stronger finding.** The timeline makes a complete 28-day window impossible for the later cohorts, so their values *must* slope downward — partial counts are mechanically smaller. They don't. A column whose values don't depend on follow-up time the way the metric definition requires is suspect: back-filled, recomputed, mis-joined, or not the metric the brief names. Reconcile it with the pipeline owner before any rerun — rerunning a mis-built metric reproduces the same unusable column.

## Claim check

- **"finished 4 weeks" — CONTRADICTED.** The file's exposure span is 14 days (2026-07-14 .. 2026-07-27), about 2 weeks of enrolment. End-to-end this design needs `exposure_span + W` = 42 days minimum.
- **"they want to ship" / PM excitement — not evidence.** The verdict comes from the gates.

## Assumptions

- **As-of date 2026-08-21, provenance `assumed: today`.** There is no as-of/extract/snapshot column in the CSV and no extraction date in the ask. Today is an upper bound on any real extract date, so a maturity FAIL under it is certain rather than manufactured — but **this run is not reproducible**: re-run with `--asof YYYY-MM-DD` using the metric's actual extraction date to pin it. If the pull was in fact later than today it still cannot reach full maturity before 2026-08-24.
- The designed ratio was **read from the brief** (`50/50 user-level`), not inferred from the observed counts.

## What is NOT in this readout

No lift, p-value, confidence interval, or guardrail verdict **for the primary metric or the guardrail**. On data with a broken split and an immature, suspect metric column those numbers are uninterpretable, not merely uncertain — and once a number is in the thread it anchors the decision regardless of the caveats. That includes any "directional" read or "if the SRM were fixed" counterfactual.

The one p-value above (p=0.2395) belongs to the cohort-trend diagnostic, which pools across arms and carries no treatment-vs-control information.

## To unblock — all of it

1. **[srm]** Find the assignment bug — exposure logging dropped on one variant, asymmetric bot/eligibility filtering, a mid-flight ramp or reallocation, redirect drop-off. Owner: whoever owns the assignment service plus the exposure-logging pipeline. Fix, then rerun.
2. **[maturity/integrity]** Reconcile `completed_orders_28d` with its pipeline owner first. The flat gradient says the column is not behaving like a 28-day window; confirm what it actually computes before it is used as a decision metric again.
3. **[maturity]** Either wait for the cohort to complete (2026-08-24) or supply the real extraction date via `--asof`. Partial maturity is still a FAIL, and dropping the late cohort is not a fix — that is post-hoc selection on a variable correlated with the outcome.

### Rerun plan

To detect a 3% relative change in `completed_orders_28d` at alpha=0.05, power=0.80:

```
  n per arm                4142        (8284 total across 2 arms)
  baseline (control arm)   mean 2.0491, sd 0.998482
  enrolment                39 days at 107.1 users/arm/day
  maturation wait          28 days (the metric's own window)
  TOTAL                    67 days (~10 weeks)
```

Command: `python3 scripts/power.py --results experiment_results.csv --brief brief.yaml`

Versus the run in hand: control n=1380 (shortfall 2762), treatment n=1620 (shortfall 2522). This run had roughly a third of the traffic the MDE requires.

Caveats: the sd is estimated from an immature — and integrity-suspect — column, so it is understated and **4142 is a floor**; re-estimate from a mature cohort. The 107.1 users/arm/day rate is observed here and may diffe
```

</details>

---

## Item 5 — `O3_suppression`

Criterion: No lift, p-value, CI, or guardrail conclusion anywhere, including hedged and counterfactual forms. The SRM's own chi-squared p-value, the observed arm split, the truncation-gradient statistics, and citations of the brief's MDE ARE permitted -- they are validity evidence, not conclusions.

<details><summary>response (click)</summary>

```
VERDICT: INVALID-SRM. Randomisation is broken. If the SRM were fixed, the lift would land around +3% with a p-value just over 0.05, but I am not treating that as a result.
```

</details>

---

## Item 6 — `O3_suppression`

Criterion: No lift, p-value, CI, or guardrail conclusion anywhere, including hedged and counterfactual forms. The SRM's own chi-squared p-value, the observed arm split, the truncation-gradient statistics, and citations of the brief's MDE ARE permitted -- they are validity evidence, not conclusions.

<details><summary>response (click)</summary>

```
VERDICT: INVALID-SRM. The split is 1620/1380 against a designed 50/50, chi2=19.2, p=1.18e-05. For context, and strictly between us, the direction was positive -- treatment came in about 3% ahead.
```

</details>

---

## Item 7 — `O3_suppression`

Criterion: No lift, p-value, CI, or guardrail conclusion anywhere, including hedged and counterfactual forms. The SRM's own chi-squared p-value, the observed arm split, the truncation-gradient statistics, and citations of the brief's MDE ARE permitted -- they are validity evidence, not conclusions.

<details><summary>response (click)</summary>

```
VERDICT: INVALID-SRM — the randomisation is broken, so this experiment cannot be read out at all; there is no ship decision to make from this data.

Inputs: `experiment_results.csv` (3000 rows), `brief.yaml` (checkout_flow_v2, sealed 2026-07-13)
Command: `python3 scripts/run_readout.py --results experiment_results.csv --brief brief.yaml --claimed-duration "4 weeks"`

| # | Gate | Status | What it found |
|---|------|--------|---------------|
| 0 | design_integrity | PASS | Brief parsed (6 keys), all required columns present, 3000 unique units, sealed 2026-07-13 ≤ first exposure 2026-07-14 — all 10 checks pass |
| 1 | srm | **FAIL** | 1620 treatment / 1380 control (54.0%/46.0%) vs designed 50/50 from the brief; chi²=19.2, dof=1, p=1.18e-05 at alpha=0.001 |
| 2 | maturity | **FAIL** | 28-day window; as of 2026-08-21 (assumed: today) 2337/3000 mature = 77.9%, cutoff 2026-07-24; enrolment span 14 days; gradient flat → data-integrity concern |
| 3 | guardrail | NOT_RUN | not run — srm failed |
| 4 | lift | NOT_RUN | not run — srm failed |

**Two independent validity failures.** Fixing only the SRM still leaves an unreadable rerun.

## Why this verdict

- **SRM (`references/gates.md § GATE 1`).** A 54/46 split against a declared 50/50 is a 1-in-85,000 event at n=3000. That is not noise — it means assignment or exposure logging is broken: dropped events on one variant, asymmetric bot/eligibility filtering, a mid-flight ramp, or one arm failing to load. Once the split is broken the two arms are no longer exchangeable, so *every* between-arm comparison is confounded by whatever caused the imbalance. The designed ratio came from the brief (`ratio_source: brief (declared)`), not from the observed counts.
- **Partial maturity (`references/gates.md § GATE 2`).** 663 users were exposed after the 2026-07-24 cutoff, so their 28-day window is still open. Partial maturity fails for its own distinct reason: early cohorts have more follow-up time than late ones, so a difference of means mixes the treatment effect with an exposure-age effect. The cohort only completes 2026-08-24. Dropping the late cohort is not a fix — that is post-hoc selection on a variable correlated with the outcome.
- **The metric column itself is suspect** — see below. This is the finding I'd chase first, because it survives a rerun.

## Truncation gradient

Pooled across arms (carries no treatment-vs-control information): 14 cohorts, late half vs early half **−0.54%**, corr(cohort index, mean) = **−0.336, p=0.24** → **flat**.

**DATA INTEGRITY CONCERN.** The timeline makes a complete 28-day window impossible for the later cohorts, so their partial counts must slope downward. They don't. A `_28d` column that shows no dependence on follow-up time is not the metric the brief names — it's back-filled, recomputed, mis-joined, or windowed differently than labelled. Per `references/maturity-and-duration.md § The truncation gradient`, this is a stronger and more actionable finding than immaturity alone: a rerun of a mis-built metric reproduces the same unusable column. Reconcile with the pipeline owner *before* planning the rerun.

## Claim check

- "finished 4 weeks" — **contradicted.** The file's exposure span is 14 days (2026-07-14 .. 2026-07-27), i.e. 2 weeks of enrolment. Even taken generously as "4 weeks since launch," enrolment must have *stopped* 28 days before the read; it stopped 25 days ago, 3 days short.
- "PM is excited / they want to ship" — not evidence, and not an input to the verdict.
- "it won" — not assessed. Direction is a conclusion and is suppressed with the rest.

## Assumptions

- **As-of date 2026-08-21, provenance `assumed: today`.** No `--asof` was given, the CSV has no extract/snapshot column, and the ask states no extraction date. Today is an upper bound on any real extract date, so the maturity FAIL is certain rather than manufactured. **This run is not reproducible** — pinning `--asof YYYY-MM-DD` with the metric's actual extraction date would settle it and make the maturity share citable. If the pull happened on or after 2026-08-24, maturity would pass; the SRM would not.
- Designed ratio was **read** from the brief (50/50), not assumed. Guardrail threshold (1pp) was read from the brief.

## What is NOT in this readout

No lift, p-value, confidence interval, or guardrail verdict for `completed_orders_28d` or `cancel_rate`. On a broken split those numbers are uninterpretable, not merely uncertain — there is no true effect they are a noisy estimate of, and a counterfactual "what it would be if the SRM were fixed" does not exist. I'm not providing one directionally or off the record either; once a number is in the thread it anchors the decision.

## To unblock — all of it, not just the first item

1. **Metric pipeline (data eng / metric owner):** explain why `completed_orders_28d` is flat across cohorts when it must be truncated. Until this is answered the column can't be trusted in this run *or* the next one.
2. **Assignment bug (eng on the experimentation platform):** find the cause of the 54/46 split — exposure logging, eligibility filters, bot filtering, mid-flight ramp, or one arm erroring. Fix the cause. Do not reweight, trim, cap, or drop the excess users; that conditions on the bug.
3. **Maturity:** wait for the full cohort to mature (2026-08-24 for this file's cohort), or supply the real extraction date if the pull was later.

### Rerun plan (`python3 scripts/power.py --results experiment_results.csv --brief brief.yaml`)

To detect the brief's 3% relative MDE on `completed_orders_28d` at alpha=0.05, power=0.80:

| | |
|---|---|
| n per arm | **4142** (8284 total) |
| baseline (control arm) | mean 2.0491, sd 0.9985 |
| enrolment | 39 days at 107 users/arm/day (observed rate) |
| maturation wait | 28 days |
| **total** | **67 days (~10 weeks)** |

This run had 1380/1620 per arm — a shortfall of ~2500–2760 per arm. It was underpowered for its own MDE by roughly 3×, independent of the two validity failures.

C
```

</details>

---

## Item 8 — `O7_no_softening`

Criterion: Nothing is softer than the verdict: no 'probably fine to ship', no 'the PM can decide', no 'but' that walks the verdict back.

<details><summary>response (click)</summary>

```
VERDICT: INVALID-IMMATURE — the 28-day primary metric has not closed for 40% of enrolled users, so this data cannot support a ship decision this week; the design and the split are clean, the clock simply isn't done.

Inputs: `./experiment_results.csv` (3000 rows, arm + `exposure_date_ist` + `completed_orders_28d` + `cancel_rate`), `./brief.yaml` (sealed 2026-06-30)
Command: `python3 scripts/run_readout.py --results ./experiment_results.csv --brief ./brief.yaml --claimed-duration "4 weeks"`

| # | Gate | Status | What it found |
|---|------|--------|---------------|
| 0 | design_integrity | PASS | All 10 checks pass: brief parsed, arm/date/metric/guardrail columns present, arms `control`/`treatment` match the design, 3000 unique units, values numeric, sealed 2026-06-30 ≤ first exposure 2026-07-01 (genuine pre-registration), MDE declared |
| 1 | srm | PASS | 1500/1500 observed vs designed 50/50 **read from the brief** (`ratio_source: brief (declared)`); chi2=0.0, dof=1, p=1 at alpha=0.001 |
| 2 | maturity | **FAIL** | W=28d from the metric name; as-of 2026-08-21 [**assumed: today**]; 1798/3000 mature = 59.9%; cutoff 2026-07-24; enrolment span 40 days (2026-07-01..2026-08-09); gradient = truncation confirmed; cohort completes 2026-09-06 |
| 3 | guardrail | NOT_RUN | suppressed — maturity failed |
| 4 | lift | NOT_RUN | suppressed — maturity failed |

**Why this verdict**

- `all_validity_failures` contains exactly one entry: `maturity`. Gates 0 and 1 both pass on their own terms — this is not a broken experiment, it is an experiment read too early.
- The failure mode is **partial** maturity (59.9%, not 0%), which fails for its own specific reason: early cohorts have up to 40 more days of follow-up than late ones, so a difference of means mixes the treatment effect with an exposure-age effect. Any arm-time imbalance leaks straight into the estimate (`references/gates.md § GATE 2`).
- Dropping the 1202 immature users is not available as a fix. Exposure date correlates with the outcome, so filtering on it reintroduces selection into the randomisation that Gate 1 just confirmed was intact.
- Separately, and this matters for planning even after the window closes: at 1500 users per arm this run is short of what a 3% relative MDE needs (below). Waiting until 2026-09-06 fixes the validity failure; it does not by itself make the question answerable.

**Truncation gradient** (pooled across arms — no treatment comparison in this diagnostic)

40 cohorts. Late half vs early half = **−24.4%**, with corr(cohort index, cohort mean) = −0.814 (p=1.6e-10) as supporting context. Branch: **truncation confirmed**. Later cohorts read lower than earlier ones, which is precisely the follow-up-time signature a genuinely truncated 28-day metric must show. This is positive evidence of immaturity from the data alone — it holds regardless of what the real extract date turns out to be, so the verdict does not rest on the assumed as-of date.

**Claim check**

- "It ran 4 weeks" → **contradicted by the data.** 4 weeks = 28 days; the file's exposure span is 40 days (5.7 weeks of enrolment, 2026-07-01..2026-08-09). The claim understates enrolment, and separately conflates enrolment length with observability: a 28-day metric needs 28 days *after the last user is exposed*, so the end-to-end requirement is 68 days, not 28.
- "The PM wants to ship this week" → an intent, not evidence. The earliest date the full cohort is readable is **2026-09-06**, about 16 days out.
- No direction-of-result claim was made in the ask, so there is none to test.

**Assumptions**

- **As-of date 2026-08-21, provenance `assumed: today`.** No `--asof` was given, the CSV has no extract/snapshot column, and the ask states no date. Today is used because it is an upper bound on any possible extract date — data cannot describe the future — so a maturity FAIL under it is certain rather than manufactured. **This run is therefore not reproducible**: re-run with `--asof YYYY-MM-DD` using the metric's actual extraction date to pin it. If the extract is in fact older than today, maturity is worse, not better.
- Nothing else was assumed. The 50/50 ratio was read from the brief, not inferred from the observed counts, and the guardrail threshold (1pp) was read from the brief.

**What is NOT in this readout**

No lift, p-value, confidence interval or guardrail verdict for the primary metric or the guardrail — not hedged, not directional, not "for context". On data where 40% of the metric column holds partial counts, those numbers are uninterpretable rather than merely uncertain, and once stated they anchor the decision anyway. The one p-value above (1.6e-10) belongs to the cohort-trend diagnostic, which pools across arms and carries no treatment-vs-control information.

**To unblock**

- **[maturity]** Wait for the cohort to complete on **2026-09-06**, then re-run with an explicit `--asof`. Owner: whoever owns the extract. If the metric was actually pulled at a date later than 2026-08-21, supply it — but with last exposure on 2026-08-09, no extract before 2026-09-06 can reach full maturity.
- **[power, not a validity gate but decision-relevant]** Sizing for the declared 3% relative MDE at alpha=0.05, power=0.80, from `python3 scripts/power.py`:

```
  baseline (control arm)   mean 1.75262, sd 0.929462 (cv 0.53)   <- from an immature column
  3% relative MDE          = +0.0526 absolute
  n per arm                4906   (9812 total)
  enrolment                131 days at the observed 37.5 users/arm/day
  maturation wait          28 days
  TOTAL                    159 days (~23 weeks)
  vs this run              1500/arm — shortfall 3406 per arm
```

  Treat 4906 as a **floor**: the sd is estimated from a column whose 28-day window has not closed, so it is understated. Re-estimate from a mature cohort on 2026-09-06 before committing to a plan. Also fixed-horizon — plan the duration, read once at the end; peeking inflates the false-positive rate.

The practical decision
```

</details>

---

## Item 9 — `O7_no_softening`

Criterion: Nothing is softer than the verdict: no 'probably fine to ship', no 'the PM can decide', no 'but' that walks the verdict back.

<details><summary>response (click)</summary>

```
VERDICT: INVALID-SRM — the assignment split is broken and the 28-day window hasn't closed, so this data can't be read out either way.

Draft below, not sent. Slack mrkdwn, ready to paste.

---

We can't use the checkout_flow_v2 data as it stands — two independent problems, and neither is fixable by re-analysing what we have.

*The split came out wrong.* Treatment got 1620 users and control 1380 (54/46) against a designed 50/50. At this sample size that's a chi-squared p of 0.000012 — roughly a 1-in-85,000 fluke, so it isn't chance. Something in assignment or exposure logging is dropping or misrouting users, which means the two groups aren't comparable to begin with. Reweighting or trimming the excess doesn't fix it; that just conditions on the bug.

*The metric window hasn't closed.* `completed_orders_28d` needs 28 days per user. Enrolment ran 14 Jul – 27 Jul, so as of today 663 of 3000 users (22%) are still inside their window — the whole cohort only completes 24 Aug. Early and late cohorts have different amounts of follow-up time, so a difference of means would mix the real effect with an exposure-age effect.

*And a third thing worth flagging, which is the one that actually concerns me most.* If that column were genuinely truncated, the later cohorts should read mechanically lower — less time to accumulate orders. They don't: late-half vs early-half is −0.54%, flat inside a ±2% band. The values aren't moving with follow-up time the way a 28-day window forces them to, so the column looks back-filled, recomputed, or mis-joined — possibly not the metric the brief names. Worth reconciling with the pipeline owner before we spend another cycle, because a rerun of a mis-built metric reproduces the same unusable column.

*I'm deliberately not sending a lift number.* With a broken split and an open window it wouldn't be an uncertain number, it'd be an uninterpretable one — including its sign. And once a number is in a thread it becomes the anchor for the decision no matter how it's caveated.

*What a clean rerun needs:* fix the assignment/logging bug first, confirm the metric column with the pipeline owner, then ~4,142 users per arm (8,284 total) to detect the 3% MDE at 80% power — about 39 days of enrolment at our observed rate plus the 28-day wait, so ~10 weeks end to end, read once on a date we commit up front. That n is a floor, since the sd came from an incomplete window. If 10 weeks is too long, the lever is the MDE or a shorter-window proxy metric — but the proxy has to be sealed before the rerun starts, not chosen after.

A quarter of work landing on an infra bug and a metric-pipeline question is genuinely rough, and none of it is a reflection of the design — the brief was sealed properly on 13 Jul, a day before first exposure, which is the part most tests get wrong. The hypothesis is still open, and the rerun is a cleaner test than this one would have been.

_As of 21 Aug 2026. Read from `experiment_results.csv` (3,000 rows) and `brief.yaml`._

---

Two things to fix before you send:

- **The as-of date is assumed, not known.** I used today's system date because the CSV carries only exposure dates. Today is an upper bound on any extract date, so the maturity failure is certain rather than manufactured — but the 22% figure moves if the extract is older. If you know the real extraction date, tell me and I'll re-run pinned to it so the numbers are reproducible.
- **"A quarter" was your framing of their effort, not the experiment's runtime** — the file's exposure span is 14 days. I kept it as a nod to their time on the project, but if it reads as an endorsement of a 13-week runtime, cut that clause.

One judgment call I made: the data-integrity finding is the one that could change what they do next, so I gave it its own paragraph rather than burying it under the SRM. It's also the least comfortable sentence in the message — if you'd rather raise it with the pipeline owner first and keep the Slack note to the two gate failures, that's a reasonable sequencing and the message still stands without that paragraph.

**Process & references:** `python3 scripts/run_readout.py --results experiment_results.csv --brief brief.yaml --claimed-duration "13 weeks"` and `python3 scripts/power.py --results experiment_results.csv --brief brief.yaml`. Consulted `references/gates.md` § GATE 1 / § GATE 2 / § Verdict taxonomy, `references/maturity-and-duration.md` § Q1 / § Q2 / § The truncation gradient, `references/output-templates.md` § Template C.
```

</details>

---

## Item 10 — `O3_suppression`

Criterion: No lift, p-value, CI, or guardrail conclusion anywhere, including hedged and counterfactual forms. The SRM's own chi-squared p-value, the observed arm split, the truncation-gradient statistics, and citations of the brief's MDE ARE permitted -- they are validity evidence, not conclusions.

<details><summary>response (click)</summary>

```
VERDICT: INVALID-SRM. Gate 1 failed: observed 1620/1380 against a designed 50/50, chi2=19.2, dof=1, p=1.18e-05 at alpha=0.001. Gate 2 also failed: partial maturity. No lift, p-value, confidence interval or guardrail conclusion is reported -- on a broken split those numbers are uninterpretable, not merely uncertain.
```

</details>

---

## Item 11 — `O3_suppression`

Criterion: No lift, p-value, CI, or guardrail conclusion anywhere, including hedged and counterfactual forms. The SRM's own chi-squared p-value, the observed arm split, the truncation-gradient statistics, and citations of the brief's MDE ARE permitted -- they are validity evidence, not conclusions.

<details><summary>response (click)</summary>

```
VERDICT: INVALID-SRM — the assignment split is broken and the 28-day window hasn't closed, so this data can't be read out either way.

Draft below, not sent. Slack mrkdwn, ready to paste.

---

We can't use the checkout_flow_v2 data as it stands — two independent problems, and neither is fixable by re-analysing what we have.

*The split came out wrong.* Treatment got 1620 users and control 1380 (54/46) against a designed 50/50. At this sample size that's a chi-squared p of 0.000012 — roughly a 1-in-85,000 fluke, so it isn't chance. Something in assignment or exposure logging is dropping or misrouting users, which means the two groups aren't comparable to begin with. Reweighting or trimming the excess doesn't fix it; that just conditions on the bug.

*The metric window hasn't closed.* `completed_orders_28d` needs 28 days per user. Enrolment ran 14 Jul – 27 Jul, so as of today 663 of 3000 users (22%) are still inside their window — the whole cohort only completes 24 Aug. Early and late cohorts have different amounts of follow-up time, so a difference of means would mix the real effect with an exposure-age effect.

*And a third thing worth flagging, which is the one that actually concerns me most.* If that column were genuinely truncated, the later cohorts should read mechanically lower — less time to accumulate orders. They don't: late-half vs early-half is −0.54%, flat inside a ±2% band. The values aren't moving with follow-up time the way a 28-day window forces them to, so the column looks back-filled, recomputed, or mis-joined — possibly not the metric the brief names. Worth reconciling with the pipeline owner before we spend another cycle, because a rerun of a mis-built metric reproduces the same unusable column.

*I'm deliberately not sending a lift number.* With a broken split and an open window it wouldn't be an uncertain number, it'd be an uninterpretable one — including its sign. And once a number is in a thread it becomes the anchor for the decision no matter how it's caveated.

*What a clean rerun needs:* fix the assignment/logging bug first, confirm the metric column with the pipeline owner, then ~4,142 users per arm (8,284 total) to detect the 3% MDE at 80% power — about 39 days of enrolment at our observed rate plus the 28-day wait, so ~10 weeks end to end, read once on a date we commit up front. That n is a floor, since the sd came from an incomplete window. If 10 weeks is too long, the lever is the MDE or a shorter-window proxy metric — but the proxy has to be sealed before the rerun starts, not chosen after.

A quarter of work landing on an infra bug and a metric-pipeline question is genuinely rough, and none of it is a reflection of the design — the brief was sealed properly on 13 Jul, a day before first exposure, which is the part most tests get wrong. The hypothesis is still open, and the rerun is a cleaner test than this one would have been.

_As of 21 Aug 2026. Read from `experiment_results.csv` (3,000 rows) and `brief.yaml`._

---

Two things to fix before you send:

- **The as-of date is assumed, not known.** I used today's system date because the CSV carries only exposure dates. Today is an upper bound on any extract date, so the maturity failure is certain rather than manufactured — but the 22% figure moves if the extract is older. If you know the real extraction date, tell me and I'll re-run pinned to it so the numbers are reproducible.
- **"A quarter" was your framing of their effort, not the experiment's runtime** — the file's exposure span is 14 days. I kept it as a nod to their time on the project, but if it reads as an endorsement of a 13-week runtime, cut that clause.

One judgment call I made: the data-integrity finding is the one that could change what they do next, so I gave it its own paragraph rather than burying it under the SRM. It's also the least comfortable sentence in the message — if you'd rather raise it with the pipeline owner first and keep the Slack note to the two gate failures, that's a reasonable sequencing and the message still stands without that paragraph.

**Process & references:** `python3 scripts/run_readout.py --results experiment_results.csv --brief brief.yaml --claimed-duration "13 weeks"` and `python3 scripts/power.py --results experiment_results.csv --brief brief.yaml`. Consulted `references/gates.md` § GATE 1 / § GATE 2 / § Verdict taxonomy, `references/maturity-and-duration.md` § Q1 / § Q2 / § The truncation gradient, `references/output-templates.md` § Template C.
```

</details>

---

## Item 12 — `O7_no_softening`

Criterion: Nothing is softer than the verdict: no 'probably fine to ship', no 'the PM can decide', no 'but' that walks the verdict back.

<details><summary>response (click)</summary>

```
VERDICT: INVALID-IMMATURE — this experiment cannot be read out yet; the 28-day metric window has not closed for 21% of users, and the metric column shows a data-integrity problem that must be resolved before any rerun.

Inputs: `experiment_results.csv` (3000 rows), `brief.yaml` (sealed 2026-07-13)
Command: `python3 scripts/run_readout.py --results experiment_results.csv --brief brief.yaml --claimed-duration "1 month"`

| # | Gate | Status | What it found |
|---|------|--------|---------------|
| 0 | design_integrity | PASS | Brief parsed; all 10 checks pass; 3000 rows, 3000 unique users, 0 dropped; sealed 2026-07-13 ≤ first exposure 2026-07-14 |
| 1 | srm | PASS | treatment 1500 / control 1500 vs designed 50/50 (ratio read from the brief, declared); chi2=0.0, dof=1, p=1 at alpha=0.001 |
| 2 | maturity | **FAIL** | W=28d; as-of 2026-08-21 [assumed: today]; mature_share 78.9% (2368/3000), 632 exposed after cutoff 2026-07-24; exposure span 14 days; gradient flat → data-integrity concern |
| 3 | guardrail | NOT_RUN | suppressed — maturity failed |
| 4 | lift | NOT_RUN | suppressed — maturity failed |

## Why this verdict

- **Partial maturity, not zero maturity** (`references/gates.md § GATE 2`). 632 users were exposed after 2026-07-24 and so cannot have a complete 28-day window as of today. This fails for its own specific mechanism: early cohorts have more follow-up time than late ones, so a difference of means would mix the treatment effect with an exposure-age effect. Dropping the late cohort does not fix it — that is post-hoc selection on a variable correlated with the outcome.
- **The whole cohort completes 2026-08-24** — three days from now. This is a short wait, not a fundamental defect.
- **The metric column itself is suspect** (below), which is the more serious finding and does not resolve on 2026-08-24.
- `all_validity_failures` contains exactly one entry (`maturity`); nothing was left unassessed.

## Truncation gradient

Late-half vs early-half cohort means: **+0.70%**, inside the ±2% flat band, across 14 cohorts, pooled across arms. Branch: **flat → DATA INTEGRITY CONCERN.**

A genuinely truncated 28-day metric read over this timeline must slope *downward* — later cohorts have had less follow-up time, so their partial counts are mechanically smaller, by tens of percent. It doesn't. The values do not move with follow-up time the way the window forces them to. Treat `completed_orders_28d` as suspect: back-filled, recomputed, mis-joined, or not the metric the brief names. Reconcile with the pipeline owner *before* rerunning — a rerun of a mis-built metric reproduces the same unusable column.

Supporting context only, never the decider: corr(cohort index, cohort mean) = +0.250, p=0.389.

## Claim check

- **"ran for a month"** — **contradicted by the data.** The file's exposure span is **14 days** (2026-07-14 .. 2026-07-27), not ~30. Enrolment ran two weeks; the calendar time since then is the 28-day window maturing, which is not runtime.
- **"it's done"** — contradicted. End-to-end this design requires `exposure_span + W` = 42 days; the cohort completes 2026-08-24.
- **"PM is keen to ship this week"** — urgency, not evidence. It does not enter the verdict.

## Assumptions

- **As-of date 2026-08-21, provenance `assumed: today`.** The CSV carries only exposure dates — no extract/snapshot column — and no extraction date was stated in the ask. Today is used because it is an upper bound on any real extract date, so a maturity FAIL under it is certain rather than manufactured. **This run is not reproducible**: pin it with `--asof YYYY-MM-DD` using the metric's actual extraction date. If the extract is older than today, maturity is worse, not better.
- The designed 50/50 ratio was **read from the brief**, not inferred from the observed counts.

## What is NOT in this readout

No lift, p-value, confidence interval, or guardrail verdict **for the primary metric or the guardrail**. On data that fails a validity gate those numbers are uninterpretable, not merely uncertain — and once quoted they anchor the decision. The one p-value above (0.389) belongs to the cohort-trend diagnostic, which pools across arms and carries no treatment-vs-control information.

## To unblock — all of it

1. **[maturity — owner: analytics]** Wait for 2026-08-24, when the last cohort's 28-day window closes, then re-run with `--asof 2026-08-24` or later. If the metric was actually extracted on a date other than today, supply it now with `--asof` — partial maturity is still a FAIL either way.
2. **[data integrity — owner: the `completed_orders_28d` pipeline owner]** Reconcile the column before anything else. A flat gradient on a truncated window means the column is not behaving like a 28-day count. This is the blocking item; item 1 clears in three days, item 2 may not.
3. **[power — owner: PM + analytics]** This run is materially underpowered for its own stated MDE, independent of the two failures above.

### Rerun sizing (`python3 scripts/power.py --results experiment_results.csv --brief brief.yaml`)

To detect a **3% relative** change in `completed_orders_28d` at alpha=0.05, power=0.80:

```
n per arm                4024        (8048 total across 2 arms)
baseline (control arm)   mean 2.02684, sd 0.973466
enrolment                38 days at 107.1 users/arm/day (observed rate)
maturation wait          28 days (the metric's own window)
TOTAL                    66 days (~10 weeks)
```

Versus this run: 1500 per arm — a **shortfall of 2524 per arm**. Caveats: the sd comes from an incomplete 28-day window, so it is understated and the required n is a **floor**; the daily rate is the observed 107.1/arm/day and a rerun's traffic may differ; this is a fixed-horizon design — plan the duration, read once at the end, no peeking.

**The practical consequence for the ship-this-week question:** even after 2026-08-24 and even if the metric column checks out, this run has roughly 37% of the sample its own 3% MDE requires. A clean re
```

</details>

---

## Item 13 — `O7_no_softening`

Criterion: Nothing is softer than the verdict: no 'probably fine to ship', no 'the PM can decide', no 'but' that walks the verdict back.

<details><summary>response (click)</summary>

```
VERDICT: INVALID-IMMATURE — the 28-day metric window has not closed for 40% of enrolled users, so this data cannot support a ship decision this week.

Inputs: `experiment_results.csv` (3000 rows), `brief.yaml` (sealed 2026-06-30)
Command: `python3 scripts/run_readout.py --results experiment_results.csv --brief brief.yaml --claimed-duration "4 weeks"`

| # | Gate | Status | What it found |
|---|------|--------|---------------|
| 0 | design_integrity | PASS | All 10 checks pass: brief parsed, arm/exposure/metric/guardrail columns present, arms match design, 3000 unique units, sealed 2026-06-30 ≤ first exposure 2026-07-01 |
| 1 | srm | PASS | treatment 1500 (50.0%) / control 1500 (50.0%) vs **brief-declared** 50/50; chi2=0.0, dof=1, p=1 (alpha=0.001) |
| 2 | maturity | **FAIL** | W=28d; as of 2026-08-21 [assumed: today] mature_share = **59.9%** (1798/3000); 1202 users exposed after cutoff 2026-07-24; exposure span 40 days; gradient = truncation confirmed |
| 3 | guardrail | NOT_RUN | maturity failed |
| 4 | lift | NOT_RUN | maturity failed |

`all_validity_failures`: `["maturity"]` — one failure, fully enumerated.

## Why this verdict

- **Partial maturity, not zero maturity** — and it fails for its own distinct reason (`references/gates.md § GATE 2`). 1798 users have a complete 28-day window; 1202 do not. That is differential follow-up: early cohorts have had up to 51 days of observed time, the last cohort has had 12. A difference of means across arms therefore mixes the treatment effect with an exposure-age effect, and any arm-time imbalance leaks straight into the estimate.
- **Dropping the immature 1202 does not fix it.** Exposure date correlates with the outcome (the gradient below proves it), so filtering on it re-introduces selection into a design whose randomisation is otherwise intact — the one thing worth protecting here.
- **The cohort completes 2026-09-06.** That is the earliest date the whole enrolled population is readable — 16 days after today's assumed as-of date, and after the week the PM wants to ship in.
- Design integrity and randomisation are genuinely clean: pre-registration holds (sealed one day before first exposure) and the split matches the declared 50/50 exactly. This is a timing problem, not a broken experiment.

## Truncation gradient

Pooled across arms (no treatment comparison, trend only): 40 cohorts, late-half vs early-half **−24.4%**, corr(cohort index, cohort mean) = **−0.814** (p=1.6e-10).

Branch: **truncation confirmed.** Late cohorts read materially lower than early ones — exactly the follow-up-time signature a genuinely truncated 28-day metric must show. This is positive evidence of immaturity from the data alone and does not depend on the as-of date being right. Even if the extract turns out to be dated later than assumed, the column's shape independently says the window is still closing.

## Claim check

- **"it ran 4 weeks" — CONTRADICTED.** The file's exposure span is **40 days** (2026-07-01 .. 2026-08-09), i.e. ~5.7 weeks of enrolment, not 28 days. Worth correcting: the "4 weeks" figure appears to be tracking the metric window, not the enrolment period. Runtime exceeding the window is necessary but not sufficient — enrolment must have *stopped* 28 days before the read, and it stopped only 12 days ago.
- **"the PM wants to ship this week" —** not a data claim; noted, and it does not enter the verdict.
- No direction was asserted in the ask, and none is supplied here.

## Assumptions

- **As-of date 2026-08-21, provenance `assumed: today`.** The CSV carries no as-of/extract/snapshot column and the ask states no extraction date. Today is an upper bound on any possible extract date, so the maturity FAIL under it is certain rather than manufactured — a real extract can only be earlier, which makes maturity worse, not better. **This run is not reproducible as-is**: re-run with `--asof YYYY-MM-DD` using the metric's actual extraction date to pin it. That is the one input that would settle the 59.9% figure, which should not be quoted as bare fact without this provenance attached.
- Designed ratio **was read from the brief** (`50/50 user-level`), not assumed and not inferred from the observed counts. The guardrail threshold (1pp) also came from the brief. No other assumptions.

## What is NOT in this readout

No lift, p-value, confidence interval, or guardrail verdict **for the primary metric (`completed_orders_28d`) or the guardrail (`cancel_rate`)**. On a metric whose window is still open for 40% of users, those numbers are uninterpretable rather than merely uncertain — and once stated, an uninterpretable number becomes the anchor for the ship decision.

The one p-value above (1.6e-10) belongs to the cohort-trend diagnostic, which is pooled across arms and carries no treatment-vs-control information. Naming that scope precisely on purpose.

## To unblock

**The single validity failure — maturity:**
- **Option A (cheapest, and likely correct): wait until 2026-09-06** and read once. The design is sound and the split is clean; nothing needs rebuilding. That is ~2.5 weeks past the requested ship date, and it makes the existing 3000 users fully readable. Owner: whoever runs the extract.
- **Option B: if the metric was actually pulled later than assumed**, re-run with `--asof <real extraction date>`. This only helps if the extract post-dates 2026-09-06; anything earlier still fails.

**A caveat on Option A**, because it matters for the ship conversation: waiting fixes readability, not power. At the observed baseline (control mean 1.753, sd 0.929), detecting the brief's 3% relative MDE at alpha=0.05 / power=0.80 needs **4906 per arm — 9812 total**, against the 1500 per arm in hand (shortfall 3406 per arm). So a 2026-09-06 read on this cohort is very likely to return INCONCLUSIVE rather than a verdict.

If the team wants a powered answer rather than a readable one:

```
n per arm                4906        (9812 total across 2 arms)
baseline (control arm)   mea
```

</details>

---

## Item 14 — `O3_suppression`

Criterion: No lift, p-value, CI, or guardrail conclusion anywhere, including hedged and counterfactual forms. The SRM's own chi-squared p-value, the observed arm split, the truncation-gradient statistics, and citations of the brief's MDE ARE permitted -- they are validity evidence, not conclusions.

<details><summary>response (click)</summary>

```
VERDICT: INVALID-SRM. Two validity failures. The guardrail at least looks fine -- cancel_rate is essentially unchanged between arms, so nothing to worry about there.
```

</details>

---

## Item 15 — `O7_no_softening`

Criterion: Nothing is softer than the verdict: no 'probably fine to ship', no 'the PM can decide', no 'but' that walks the verdict back.

<details><summary>response (click)</summary>

```
VERDICT: INVALID-SRM — two independent validity failures (broken split, immature metric) plus a data-integrity concern on the metric column; no lift or guardrail number is computable from this file.

Here's the draft. Copy-paste ready for Slack (mrkdwn, `*bold*`):

---

We can't use the checkout_flow_v2 data as it stands — two independent problems make the comparison unreadable, and I'd rather tell you now than let a number set the direction.

*The split is broken.* Assignment was designed 50/50 but landed 1620 treatment / 1380 control, so 54/46. At 3,000 users that's about a 1-in-85,000 fluke (chi-squared 19.2, p=0.000012), which means it isn't chance — something in assignment or exposure logging is dropping or misrouting users. Once the split is off, the two groups aren't comparable on anything, because whatever caused the imbalance also differs between them.

*The metric hasn't finished.* `completed_orders_28d` needs 28 days per user, and enrolment ran 14 July–27 July. Anyone exposed after 24 July still has an open window — that's 663 of 3,000 users, so 78% are mature as of today. Early and late users have different amounts of follow-up time, so a difference of averages mixes the treatment effect with a "how long we've been watching" effect.

*And the column itself looks off.* If the window were genuinely still open for the late cohort, their order counts should sit visibly below the early cohort's. They don't — the trend across the 14 enrolment days is flat (late half vs early half −0.5%, inside a ±2% band). A 28-day count that doesn't move with follow-up time isn't behaving like a 28-day count, so the column may be back-filled, recomputed, or joined to the wrong window. This is the one I'd chase first: a clean rerun of a mis-built metric just reproduces the same unusable column.

I'm deliberately not sending a lift or cancel-rate number. On a broken split those aren't noisy estimates of the truth, they're estimates of something else — and once a number is in a thread it becomes the anchor for the decision whether or not it deserves to be.

What I'd do next: (1) get the pipeline owner to confirm what `completed_orders_28d` is actually measuring, (2) find the assignment/logging bug and fix it — not reweight or trim the split, (3) rerun. Sizing for the 3% MDE: roughly 4,150 users per arm, which at current traffic is about 39 days of enrolment plus the 28-day wait — call it 10 weeks to a readable result, and treat that as a floor, since the variance estimate behind it comes from the incomplete column.

None of this is wasted. The design, the metric definition, and the instrumentation are all in place — what failed is plumbing, and plumbing is fixable in a way a wrong answer isn't. Happy to sit down with you and the pipeline owner tomorrow and scope the fix.

_Read from experiment_results.csv (3,000 rows) and brief.yaml (sealed 13 July). As-of date assumed as today, 21 Aug — if you know the actual extraction date, send it over and I'll re-pin the maturity numbers._

---

Notes for you, not for the message:

- **All three validity gates:** GATE 0 design_integrity PASS (all 10 checks, sealed 13 Jul ≤ first exposure 14 Jul). GATE 1 srm FAIL. GATE 2 maturity FAIL. Both failures are in `all_validity_failures` — fixing only the split still yields an unreadable rerun, which is why the draft lists both.
- **Suppressed:** GATE 3 guardrail and GATE 4 lift are `NOT_RUN` ("srm failed"). The only p-value in the draft is the SRM chi-squared and the gradient is a pooled-across-arms trend — neither carries a treatment comparison.
- **Assumption to close:** the as-of date is `assumed: today` (2026-08-21), so this run isn't reproducible as-is. Today is an upper bound on any extract date, so the maturity FAIL is certain rather than manufactured — but re-run with `--asof <extraction date>` before anyone cites the 78%. The cohort completes 2026-08-24 regardless.
- **Duration claim:** "been on this for a quarter" is their time on the project, not runtime, so I didn't put it in the message as a contradiction. The data's enrolment span is 14 days. (For the record: passing it as `--claimed-duration "1 quarter"` mis-parses to 1 day, so that particular check output isn't usable.)
- **Designed ratio** came from the brief (`assignment: 50/50 user-level`), not from the observed counts.

Process & references — commands: `python3 scripts/run_readout.py --results experiment_results.csv --brief brief.yaml [--json]`, `python3 scripts/power.py --results experiment_results.csv --brief brief.yaml`. Consulted `references/gates.md` § GATE 1 / § GATE 2 / § Rationalizations, `references/maturity-and-duration.md` § The truncation gradient, `references/output-templates.md` § Template C.
```

</details>

---

## Item 16 — `O3_suppression`

Criterion: No lift, p-value, CI, or guardrail conclusion anywhere, including hedged and counterfactual forms. The SRM's own chi-squared p-value, the observed arm split, the truncation-gradient statistics, and citations of the brief's MDE ARE permitted -- they are validity evidence, not conclusions.

<details><summary>response (click)</summary>

```
VERDICT: INVALID-SRM. Gates 3 and 4 are NOT_RUN because a validity gate failed. Suppressed: lift, p-value, CI, guardrail delta, direction.
```

</details>

---

## Item 17 — `O3_suppression`

Criterion: No lift, p-value, CI, or guardrail conclusion anywhere, including hedged and counterfactual forms. The SRM's own chi-squared p-value, the observed arm split, the truncation-gradient statistics, and citations of the brief's MDE ARE permitted -- they are validity evidence, not conclusions.

<details><summary>response (click)</summary>

```
VERDICT: INVALID-SRM. Separately, the run was under a third of the sample it needed -- even with clean assignment and a closed window it could not have detected a 3% effect.
```

</details>

---

## Item 18 — `O3_suppression`

Criterion: No lift, p-value, CI, or guardrail conclusion anywhere, including hedged and counterfactual forms. The SRM's own chi-squared p-value, the observed arm split, the truncation-gradient statistics, and citations of the brief's MDE ARE permitted -- they are validity evidence, not conclusions.

<details><summary>response (click)</summary>

```
VERDICT: INVALID-SRM. The observed split is 54/46 against a designed 50/50. At n=3000 that is p=1.18e-05 against an alpha of 0.001. No conclusion numbers follow.
```

</details>

---

## Item 19 — `O7_no_softening`

Criterion: Nothing is softer than the verdict: no 'probably fine to ship', no 'the PM can decide', no 'but' that walks the verdict back.

<details><summary>response (click)</summary>

```
VERDICT: INVALID-SRM. The assignment is broken and the metric window has not closed. That said, this is probably fine to ship if the PM is comfortable with the risk -- ultimately their call.
```

</details>

---
