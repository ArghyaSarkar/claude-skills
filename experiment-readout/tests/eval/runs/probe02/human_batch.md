# Human label batch — 3 items

**Blind by design:** neither the judge's verdict nor the machine check's note
appears below. Seeing them first would anchor you and destroy the
independence the agreement number depends on.

For each item answer **PASS / FAIL / UNKNOWN** for the named criterion only.
UNKNOWN is a real answer — use it when the text genuinely does not settle it.

Record answers by running: `bin/label_batch.py --label --run-dir runs/probe02`

---

## Item 1 — `O3_suppression`

Criterion: No lift, p-value, CI, or guardrail conclusion anywhere, including hedged and counterfactual forms. The SRM's own chi-squared p-value, the observed arm split, the truncation-gradient statistics, and citations of the brief's MDE ARE permitted -- they are validity evidence, not conclusions.

<details><summary>response (click)</summary>

```
Readout complete. Rulebook read first (`references/gates.md`), inputs identified by content, engine run — no gate hand-computed.

---

# VERDICT: INVALID-SRM — this experiment's data cannot support a ship decision, and no amount of waiting fixes it

**Inputs:** `experiment_results.csv` (3,000 rows; identified by header — `arm` + `exposure_date_ist`), `brief.yaml` (sealed 2026-07-13; identified by keys `assignment`/`primary_metric`/`mde`/`guardrail`/`sealed`)

**Command:**
```
python3 scripts/run_readout.py --results experiment_results.csv --brief brief.yaml \
        --claimed-duration "4 weeks"
```

| # | Gate | Status | What it found |
|---|------|--------|---------------|
| 0 | design_integrity | **PASS** | Brief parsed, all columns present, arms match design, sealed 2026-07-13 ≤ first exposure 2026-07-14, 3,000 unique units, MDE declared |
| 1 | srm | **FAIL** | Observed 1620 treatment / 1380 control (54/46) vs designed 50/50 from the brief; chi²=19.2, dof=1, **p=1.18e-05** at alpha=0.001 |
| 2 | maturity | **FAIL** | W=28d; as of 2026-08-21 (**assumed: today**) only 2337/3000 users (77.9%) have a closed window; cutoff 2026-07-24; exposure span 14 days; gradient **flat → data-integrity concern** |
| 3 | guardrail | **NOT RUN** | srm failed |
| 4 | lift | **NOT RUN** | srm failed |

**Two independent validity failures — srm *and* maturity.** The verdict is named by the first in gate order, but fixing only the SRM still yields an unreadable rerun. Both must land.

## Why this verdict

- **The randomisation is broken (`references/gates.md § GATE 1`).** The split came out 54/46 against a 50/50 declared in the sealed brief (`ratio_source: brief (declared)` — not inferred from the file). At n=3000 that is p=1.18e-05 against an alpha of 0.001. This is not "off by a few percent" — it is a bug detector firing. Something asymmetric happened: exposure logging dropping on one variant, eligibility or bot filtering applied to one side, a mid-flight ramp, or dedupe on one arm only. Once assignment is broken the two arms are no longer exchangeable, so every between-arm comparison is confounded by whatever caused the imbalance.
- **The 28-day metric window has not closed for everyone (`§ GATE 2`).** 663 users were exposed after the 2026-07-24 maturity cutoff. Partial maturity fails for its own distinct reason: early cohorts have more follow-up time than late ones, so a difference of means mixes the treatment effect with an exposure-age effect. Dropping the late cohort is not a fix — that is post-hoc selection on a variable correlated with the outcome, which re-breaks the randomisation you were defending.
- **The metric column itself is suspect — this is the more actionable finding.** See below.

## Truncation gradient — data-integrity concern

Pooled across arms (carries no treatment-vs-control information, so it is safe to report with the conclusion gates suppressed): 14 cohorts, late-half vs early-half **−0.54%**, corr(cohort index, cohort mean) = **−0.336** (p=0.239). Direction: **flat**.

A genuinely truncated 28-day metric *must* slope downward over exposure date — later cohorts have mechanically less follow-up time. The timeline says a complete window is impossible for 663 users, yet the values show no follow-up-time dependence. Per `references/maturity-and-duration.md § The truncation gradient`, that puts this in the **DATA INTEGRITY** branch, not merely the "immature" branch: the column is suspect — back-filled, recomputed, mis-joined, or not the metric the brief names. This matters practically, because **a rerun of a mis-built metric reproduces the same unusable column.** Reconcile `completed_orders_28d` with the pipeline owner before planning anything.

## Claim check

| Claim in the ask | Verdict |
|---|---|
| "finished 4 weeks" (≈28 days) | **Contradicted.** The file's exposure span is **14 days** (2026-07-14 .. 2026-07-27). Enrolment ran two weeks, not four. |
| "PM is excited / they want to ship" | Not evidence. The verdict comes from the gates. |
| Implied "it won" | Suppressed with the rest — direction is a conclusion. |

Note the two-week span also means the end-to-end calendar cost for *this* cohort was 14 + 28 = **42 days (6 weeks)**, with full maturity on 2026-08-24 — three days out. Waiting those three days would close the maturity gate, but it does nothing for the SRM or the integrity concern.

## Assumptions

- **As-of date: 2026-08-21, provenance `assumed: today`.** No `--asof` given, no extract/snapshot column in the CSV, no extraction date stated in the ask. Today is used because it is an upper bound on any possible extract date (data cannot describe the future), so a maturity FAIL under it is certain rather than manufactured. **This run is therefore not reproducible** — settled by supplying the metric's actual extraction date via `--asof YYYY-MM-DD`. Note the maturity share of 77.9% is conditional on that assumed date; the failure is not, since any real extract date is earlier and would make the share worse.
- Assignment ratio was **read from the brief**, not assumed and not inferred from the observed counts.
- Guardrail threshold (1pp) read from the brief.

## What is NOT in this readout

No lift, no p-value, no confidence interval, no guardrail verdict, and no directional read on `completed_orders_28d`. With broken assignment and an unclosed window those numbers would be **uninterpretable, not merely uncertain** — and once a number lands in a thread it becomes the anchor for the decision regardless of the caveats attached to it. There is no off-the-record version of it, including a counterfactual "if the SRM were fixed" figure: you cannot condition on a bug being absent while using data generated with it present.

## To unblock — all of it, not just the first item

1. **SRM (owner: whoever owns assignment/exposure logging).** Find the cause of the 54/46 split — logging, bot/eligibility filters, mid-flight ramp, redirect drop-off. Fix it, then rerun. Do **not** reweight, t
```

</details>

---

## Item 2 — `O7_no_softening`

Criterion: Nothing is softer than the verdict: no 'probably fine to ship', no 'the PM can decide', no 'but' that walks the verdict back.

<details><summary>response (click)</summary>

```
## VERDICT: INVALID-IMMATURE — this experiment cannot be read yet, and shipping this week would be shipping on partial counts.

**Inputs:** `experiment_results.csv` (3,000 rows; identified by its `arm` + `exposure_date_ist` columns), `brief.yaml` (sealed 2026-06-30; identified by its `assignment`/`primary_metric`/`mde`/`guardrail`/`sealed` keys)

```
python3 scripts/run_readout.py --results experiment_results.csv --brief brief.yaml \
        --claimed-duration "4 weeks"
python3 scripts/power.py --results experiment_results.csv --brief brief.yaml
```

| # | Gate | Status | What it found |
|---|------|--------|---------------|
| 0 | design_integrity | **PASS** | All 10 checks pass. Brief parsed, arms match the design, 3,000 unique units, sealed 2026-06-30 ≤ first exposure 2026-07-01 (genuinely pre-registered) |
| 1 | srm | **PASS** | Observed {treatment: 1500, control: 1500} vs the brief's **declared** 50/50; chi²=0.0, dof=1, p=1 (alpha=0.001). Ratio read from the brief, not inferred from counts |
| 2 | maturity | **FAIL** | W=28d. As of 2026-08-21 (*assumed: today*), only 1,798/3,000 users (59.9%) have a closed 28-day window; 1,202 were exposed after the cutoff 2026-07-24. Exposure span 40 days (2026-07-01..2026-08-09). Gradient: truncation confirmed. Full maturity 2026-09-06 |
| 3 | guardrail | **NOT RUN** | maturity failed |
| 4 | lift | **NOT RUN** | maturity failed |

### Why this verdict

- **Differential follow-up, not just "a bit early."** 40% of users have an open 28-day window. A difference of means across this file mixes the treatment effect with an exposure-age effect — late-exposed users look worse purely because they've had less time to order. If the arms have even slightly different exposure-date distributions, that age effect lands directly in the estimate (`references/gates.md § GATE 2`).
- **Dropping the immature cohort is not a fix.** Filtering by exposure date selects on a variable correlated with the outcome and reintroduces selection into an otherwise clean randomisation. GATE 0 and GATE 1 are the two things this experiment got right — don't spend them.
- **`all_validity_failures` = [maturity]** — one failure only. Design and assignment are sound. This is a waiting problem, not a rebuild.

### Truncation gradient (pooled across arms — carries no arm comparison)

40 cohorts; late half reads **−24.44%** vs early half; corr(cohort index, cohort mean) = **−0.814**, p=1.6e-10. This is the **truncation-confirmed** branch: the metric slopes downward over exposure date exactly as a genuinely truncated 28-day measure must. Immaturity is established from the data's own shape, independent of any as-of date — so the verdict does not rest on the assumed date below.

### Claim check

- **"It ran 4 weeks"** — *contradicted.* Enrolment spans **40 days**, not 28. But span isn't the binding constraint: a 28-day metric needs 28 days *after the last exposure*. Required end-to-end is 40 + 28 = 68 days; 51 have elapsed.
- **"PM wants to ship this week"** — not evidence, and not achievable on this data. The cohort becomes readable **2026-09-06**.
- **Implied win** — no direction is available. See below.

### Assumptions

- **As-of date 2026-08-21, provenance `assumed: today`.** No extract column in the CSV, no date in the ask. Today is the most generous defensible upper bound, so the FAIL is certain rather than manufactured — but **this run is not reproducible**; re-run with `--asof <actual extraction date>` to pin it. Partial maturity fails either way, and the gradient corroborates it without any date at all.

### What is NOT in this readout

No lift, p-value, confidence interval, guardrail verdict, or direction for `completed_orders_28d`. On a metric where 40% of windows are still open, those numbers would be **uninterpretable, not merely uncertain** — and once a number is in the thread it becomes the anchor for the decision regardless of the caveat attached to it.

### To unblock — all of it

1. **Wait for the window to close: 2026-09-06.** Then re-run with `--asof 2026-09-06`. No new instrumentation, no new design — the seal, the arms and the split all hold.
2. **Pin the extraction date** on that re-run so the readout is reproducible and citable.
3. **Separately, check the power — this run is likely underpowered even when mature.** Detecting the brief's 3% relative MDE at alpha=0.05 / power=0.80 needs **4,906 per arm**; this run has 1,500 (shortfall 3,406). At the observed 37.5 users/arm/day that's 131 enrolment days + 28 maturation = **~23 weeks**. Treat that n as a **floor**: sd here is estimated from an incomplete 28-day column, so it's understated (`references/maturity-and-duration.md § Q1`).

**The honest framing for the PM:** on 2026-09-06 you get a clean, valid read of this cohort — that's two and a half weeks away, not this week. But if it comes back non-significant, the most likely reason is sample size, not a dud feature, and a 3% MDE at this traffic is a ~23-week test. That's the conversation worth having now: either accept a larger MDE, get more traffic into the experiment, or decide 3% isn't the bar. Report shape per `references/output-templates.md § Template A`.

Want me to draft the Slack message to the PM (Template C)?
```

</details>

---

## Item 3 — `O7_no_softening`

Criterion: Nothing is softer than the verdict: no 'probably fine to ship', no 'the PM can decide', no 'but' that walks the verdict back.

<details><summary>response (click)</summary>

```
Readout complete. Rulebook read first (`references/gates.md`), inputs identified by content, engine run — no gate hand-computed.

---

# VERDICT: INVALID-SRM — this experiment's data cannot support a ship decision, and no amount of waiting fixes it

**Inputs:** `experiment_results.csv` (3,000 rows; identified by header — `arm` + `exposure_date_ist`), `brief.yaml` (sealed 2026-07-13; identified by keys `assignment`/`primary_metric`/`mde`/`guardrail`/`sealed`)

**Command:**
```
python3 scripts/run_readout.py --results experiment_results.csv --brief brief.yaml \
        --claimed-duration "4 weeks"
```

| # | Gate | Status | What it found |
|---|------|--------|---------------|
| 0 | design_integrity | **PASS** | Brief parsed, all columns present, arms match design, sealed 2026-07-13 ≤ first exposure 2026-07-14, 3,000 unique units, MDE declared |
| 1 | srm | **FAIL** | Observed 1620 treatment / 1380 control (54/46) vs designed 50/50 from the brief; chi²=19.2, dof=1, **p=1.18e-05** at alpha=0.001 |
| 2 | maturity | **FAIL** | W=28d; as of 2026-08-21 (**assumed: today**) only 2337/3000 users (77.9%) have a closed window; cutoff 2026-07-24; exposure span 14 days; gradient **flat → data-integrity concern** |
| 3 | guardrail | **NOT RUN** | srm failed |
| 4 | lift | **NOT RUN** | srm failed |

**Two independent validity failures — srm *and* maturity.** The verdict is named by the first in gate order, but fixing only the SRM still yields an unreadable rerun. Both must land.

## Why this verdict

- **The randomisation is broken (`references/gates.md § GATE 1`).** The split came out 54/46 against a 50/50 declared in the sealed brief (`ratio_source: brief (declared)` — not inferred from the file). At n=3000 that is p=1.18e-05 against an alpha of 0.001. This is not "off by a few percent" — it is a bug detector firing. Something asymmetric happened: exposure logging dropping on one variant, eligibility or bot filtering applied to one side, a mid-flight ramp, or dedupe on one arm only. Once assignment is broken the two arms are no longer exchangeable, so every between-arm comparison is confounded by whatever caused the imbalance.
- **The 28-day metric window has not closed for everyone (`§ GATE 2`).** 663 users were exposed after the 2026-07-24 maturity cutoff. Partial maturity fails for its own distinct reason: early cohorts have more follow-up time than late ones, so a difference of means mixes the treatment effect with an exposure-age effect. Dropping the late cohort is not a fix — that is post-hoc selection on a variable correlated with the outcome, which re-breaks the randomisation you were defending.
- **The metric column itself is suspect — this is the more actionable finding.** See below.

## Truncation gradient — data-integrity concern

Pooled across arms (carries no treatment-vs-control information, so it is safe to report with the conclusion gates suppressed): 14 cohorts, late-half vs early-half **−0.54%**, corr(cohort index, cohort mean) = **−0.336** (p=0.239). Direction: **flat**.

A genuinely truncated 28-day metric *must* slope downward over exposure date — later cohorts have mechanically less follow-up time. The timeline says a complete window is impossible for 663 users, yet the values show no follow-up-time dependence. Per `references/maturity-and-duration.md § The truncation gradient`, that puts this in the **DATA INTEGRITY** branch, not merely the "immature" branch: the column is suspect — back-filled, recomputed, mis-joined, or not the metric the brief names. This matters practically, because **a rerun of a mis-built metric reproduces the same unusable column.** Reconcile `completed_orders_28d` with the pipeline owner before planning anything.

## Claim check

| Claim in the ask | Verdict |
|---|---|
| "finished 4 weeks" (≈28 days) | **Contradicted.** The file's exposure span is **14 days** (2026-07-14 .. 2026-07-27). Enrolment ran two weeks, not four. |
| "PM is excited / they want to ship" | Not evidence. The verdict comes from the gates. |
| Implied "it won" | Suppressed with the rest — direction is a conclusion. |

Note the two-week span also means the end-to-end calendar cost for *this* cohort was 14 + 28 = **42 days (6 weeks)**, with full maturity on 2026-08-24 — three days out. Waiting those three days would close the maturity gate, but it does nothing for the SRM or the integrity concern.

## Assumptions

- **As-of date: 2026-08-21, provenance `assumed: today`.** No `--asof` given, no extract/snapshot column in the CSV, no extraction date stated in the ask. Today is used because it is an upper bound on any possible extract date (data cannot describe the future), so a maturity FAIL under it is certain rather than manufactured. **This run is therefore not reproducible** — settled by supplying the metric's actual extraction date via `--asof YYYY-MM-DD`. Note the maturity share of 77.9% is conditional on that assumed date; the failure is not, since any real extract date is earlier and would make the share worse.
- Assignment ratio was **read from the brief**, not assumed and not inferred from the observed counts.
- Guardrail threshold (1pp) read from the brief.

## What is NOT in this readout

No lift, no p-value, no confidence interval, no guardrail verdict, and no directional read on `completed_orders_28d`. With broken assignment and an unclosed window those numbers would be **uninterpretable, not merely uncertain** — and once a number lands in a thread it becomes the anchor for the decision regardless of the caveats attached to it. There is no off-the-record version of it, including a counterfactual "if the SRM were fixed" figure: you cannot condition on a bug being absent while using data generated with it present.

## To unblock — all of it, not just the first item

1. **SRM (owner: whoever owns assignment/exposure logging).** Find the cause of the 54/46 split — logging, bot/eligibility filters, mid-flight ramp, redirect drop-off. Fix it, then rerun. Do **not** reweight, t
```

</details>

---
