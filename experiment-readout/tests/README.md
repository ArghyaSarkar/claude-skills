# experiment-readout — test suite

Tests for the `experiment-readout` skill. Same inputs, same answer, every run — nothing
here depends on the clock, the machine, or the order the tests happen to run in. Written
against **CONTRACT.md v1.3** (the frozen contract plus AMENDMENTS 1, 2, 3).

- Standard library only: `/usr/bin/python3` (3.9.6) + `unittest`. No pytest, scipy, numpy, pandas, pyyaml.
- The implementation is imported **by path** (`importlib`), so the suite runs from any directory.
- A missing or broken `scripts/*.py` is reported as a **clean single-line failure**, never a traceback.

```
tests/run_tests.sh              # everything, with a pass/fail summary
tests/run_tests.sh -q           # dots instead of test names
tests/run_tests.sh -k srm       # substring filter
tests/run_tests.sh test_40_suppression   # one module
```

`run_tests.sh` rebuilds the fixtures from their seed first, then says whether
`manifest.json` came back byte-for-byte the same. If the test data has quietly changed
under you, that line is where you find out.

---

## How expected values are established

No expected value is copied from what the implementation prints. A test that checks the
code against itself passes whatever the code does, including the wrong thing. So the
expected values come from three places built without looking at it:

| Source | Used for |
|---|---|
| `fixtures/generate_fixtures.py` → `manifest.json` | Fixture ground truth. Arm means are **exact by construction** (values are rescaled multiplicatively so each arm mean equals the chosen target), so the true lift and guardrail delta are known to ~1e-9. |
| `unit/_ref.py` | A second, separately written version of `chi2_sf` / `t_sf` / Welch, kept as a yardstick — the classic Numerical Recipes algorithms for the incomplete gamma and beta functions. Checked in `test_00_reference.py` before anything is allowed to trust it. |
| Hand algebra in docstrings | Every unit-test expectation carries its own working, in the test itself, so a reader can redo the sum. |

`_ref.py` is not taken on trust either. It is checked against the cases where the exact
answer can be written down in one line — chi² at dof=1 is `erfc`, at dof=2 is `exp`; t at
dof=1 is the Cauchy distribution, at dof=2 is plain algebra — and against **published
critical-value tables**. Measured agreement: ~1e-15 relative against the closed forms,
~1e-7 against tables printed to 6–7 significant figures.

---

## Fixtures

A fixture is one made-up experiment: a `<name>_results.csv` and a `<name>_brief.yaml`,
plus an entry in `manifest.json` recording what is true of it and which verdict it should
produce. They all come out of `fixtures/generate_fixtures.py`, seeded with
`random.Random(20260821)`, so the same numbers come back every time.

**Every fixture pins an explicit `--asof`.** Under AMENDMENT 2 the fallback as-of date is
the system date, so a fixture without `--asof` would change its verdict as days pass — a
test that breaks weeks later with nobody having touched the code. Only `TestAsofDefault`
leaves `--asof` off, and it checks the provenance and the resolved date, never a verdict.

### All validity gates pass → conclusion gates run

| Fixture | Ground truth | Expected |
|---|---|---|
| `ship_clean` | 3000/3000, asof 2026-08-24 → **mature_share 1.0**, guardrail flat, rel lift +8.000%, p≈1.5e-12, rel CI [+5.79%, +10.21%] | `SHIP`, `stopped_at` null |
| `srm_mild` | 3050/2950 → χ²=1.6667, p=0.1967 — must **not** trip α=0.001 | `SHIP` |
| `maturity_exact_boundary` | all exposures 2026-07-27, asof = exposure **+ exactly 28d** | `SHIP`, maturity `PASS` (off-by-one probe, pass side) |
| `guardrail_breach` | +8.000% lift **and** cancel_rate +1.500pp (> 1pp) | `NO-SHIP`, guardrail `FAIL` |
| `guardrail_at_risk` | cancel_rate +0.950pp (≤1pp) with CI upper +1.104pp (>1pp) | `SHIP`, guardrail `WARN` |
| `sig_below_mde` | n=6000/arm, p≈0.0019 (<0.05) but rel lift +2.400% < 3% MDE | `NO-SHIP` (stat-sig, below MDE) |
| `mde_ruled_out` | n=6000/arm, p≈0.795, rel CI upper +1.705% < 3% MDE | `NO-SHIP` (MDE ruled out) |
| `inconclusive` | n=150/arm, p≈0.669, rel CI upper +11.18% > 3% MDE | `INCONCLUSIVE` (underpowered) |
| `dropped_at_2pct` | **20 of 1000** `cancel_rate` cells unparseable = **2.000%**, which does not *exceed* 2% | `SHIP`, design `WARN`, readout proceeds on 980 rows |

`mde_ruled_out` and `inconclusive` are the pair that separates *"there is no effect worth
having"* from *"we could not tell"*. Both sit at `p >= 0.05`, and the only thing telling
them apart is the CI upper bound.

### Validity failures → **both** conclusion gates `NOT_RUN`, everything suppressed

Every one of these carries a large lift **and** a real guardrail breach, and the numbers
differ from fixture to fixture. So if either number ever reaches the output, there is no
question about which one leaked or where from.

| Fixture | Ground truth | Expected |
|---|---|---|
| `srm_broken` | 3600/2400 → χ²=240.0, p=3.93e-54. Design + maturity clean, so gate 1 is isolated. Lift +11.730%, guardrail +2.310pp | `INVALID-SRM`, `["srm"]` |
| `immature` | 50/50, asof 2026-07-27, 28d metric → **mature_share 0.0**, cutoff 2026-06-29. Real-data trap #2. Lift +9.170%, guardrail +1.870pp | `INVALID-IMMATURE`, `["maturity"]` |
| `partial_maturity` | 57-day span, mature_share **0.5123** — a majority mature, still a FAIL | `INVALID-IMMATURE` |
| `maturity_off_by_one` | **exactly one** user one day short → mature_share 0.999667 | `INVALID-IMMATURE` (off-by-one probe, fail side) |
| `claim_vs_data_span` | 14-day exposure span vs a claimed "4 weeks". Real-data trap #1 in isolation | `INVALID-IMMATURE` |
| `truncation_gradient` | primary metric scaled 1.00 → 0.55 across cohorts → **corr −0.9955, late-vs-early −25.69%** | `INVALID-IMMATURE` + **truncation** reading |
| `flat_but_impossible` | flat cohorts (**corr −0.139, late-vs-early −0.50%**) while only 78.6% can be mature | `INVALID-IMMATURE` + **data-integrity** reading |
| `precedence_all_bad` | SRM-broken **and** immature **and** guardrail-breaching at once | `INVALID-SRM`, `["srm","maturity"]` |
| `trap_real_data` | both SCENARIO.md traps, using the verbatim brief text `completed_orders_28d (mean per user)`. 3300/2700 → χ²=60.0, p=9.49e-15 | `INVALID-SRM`, `["srm","maturity"]` |
| `real_dataset_shape` | shape of the real arena data: n=12000 split **6492/5508** → **χ²=80.688, p=2.64e-19**; asof 2026-08-21 → **78.6% mature**; cohorts flat (corr +0.091) | `INVALID-SRM`, `["srm","maturity"]`, data-integrity reading |
| `missing_metric_col` | brief names `completed_orders_28d`, CSV has no such column | `INVALID-DESIGN`, `["design_integrity"]`; srm + maturity still `PASS` |
| `missing_brief` | brief file absent entirely | `INVALID-DESIGN`, exit **0** |
| `sealed_after_exposure` | sealed 2026-07-20 **after** first exposure 2026-07-14 | `INVALID-DESIGN` |
| `dropped_over_2pct` | **21 of 1000** = **2.100%** — one row more than `dropped_at_2pct` | `INVALID-DESIGN` (2% escalation) |
| `monotone_but_tiny` | **r = −0.9064, p = 7.9e−06** (strongly monotone) but magnitude only **−0.32%**, inside the ±2% flat band | `INVALID-IMMATURE`, branch **`flat`**, data-integrity reading |

The contract quotes χ²≈80.7 / p≈3e-19 for the real dataset. The fixture reproduces
80.688 / 2.64e-19, and its flat-cohort reading lands in the same magnitude class as the
quoted corr −0.031 / −0.44%.

### Non-pair fixtures

| File | Purpose |
|---|---|
| `malformed_results.csv` | `NOT_A_NUMBER` in the primary metric, **valid in every other respect** and run with `--asof 2026-08-24` so all validity gates pass and the value genuinely has to be parsed → exit 1. (An earlier version failed maturity first, so the bad cell was never touched and the test proved nothing.) |
| `malformed_guardrail_results.csv` | `n/a` in `cancel_rate`, 1 of 6 rows = **16.7%**, which exceeds the 2% escalation threshold → `INVALID-DESIGN`, exit 0. Pairs with `malformed_results.csv` (same shape, same proportion, *primary* column → exit 1) to pin the **asymmetry** |
| `no_arm_col_results.csv` | required `arm` column absent → gate 0 → `INVALID-DESIGN`, exit 0 |

---

## What each test module asserts

| Module | Asserts |
|---|---|
| `test_00_reference.py` | Checks `_ref.py` itself, before anything uses it as the yardstick. Never touches the implementation. |
| `test_10_distributions.py` | `chi2_sf` / `t_sf` against exact closed forms, published tables, and `_ref`. Includes the **SRM decision boundary** (χ²(1)=10.827566 → p=0.001) and a straddling pair (5165/4835 → 9.67e-4 *detected*; 5160/4840 → 1.37e-3 *not detected*), the deep tail, fractional dof (Welch), `|t|` semantics, and monotonicity. |
| `test_20_stats.py` | `srm_chisq` (exact 50/50 → χ²=0; mild imbalance must not trip; clear imbalance must; unequal designed ratio), `welch_ttest` (two fully hand-derived cases, dof ≠ pooled, n−1 variance, two-sided p, CI symmetry, `rel_*` ÷ mean_b), `sample_size_per_arm` (two hand-computed cases + scaling laws), `duration_days`, `parse_metric_window`. |
| `test_30_gate_order.py` | Payload shape; verdict + gate statuses + `stopped_at` + `all_validity_failures` for every fixture; SRM precedence *without hiding* later failures; conclusion-gate gating; guardrail thresholds; maturity (mature_share, window, cutoff, span, provenance); the truncation gradient and its two readings. |
| `test_40_suppression.py` | **The headline behaviour.** See below. |
| `test_50_cli.py` | `--json` prints only JSON; exit 0 for every verdict; exit 1 only on genuine input error; `--asof` flips maturity `FAIL`→`PASS` on the same CSV; the as-of default; the human report; `power.py`. |
| `test_60_determinism.py` | Byte-identical JSON across two runs of every fixture; the same answer from any working directory; no key whose value comes from the clock. |
| `test_60_snapshot.py` | Byte-for-byte diffs of the rendered report for three fixtures, plus structural invariants (verdict on line 1, exactly one `WHY:` block, no repeated section header) so an intentional re-record cannot quietly bless a layout violation. Catches duplication and ordering regressions that value assertions cannot see. |
| `test_70_maturity_warn.py` | **AMENDMENT 4.** An assumed as-of date can never produce a maturity `PASS` — only `WARN`. The `PASS`-vs-`WARN` contrast on identical data; `WARN` does not block (the inverse of the suppression suite — conclusion gates still run, verdict still reached, lift still present); the three status lists never collide; the WARN wording states a conditional and never claims maturity as fact; a genuine `FAIL` outranks the caveat. **Clock-dependent by design — see below.** |

Three test classes carry the AMENDMENT 3 work:

| Class | Asserts |
|---|---|
| `TestDropEscalationBoundary` (3A) | Both sides of the 2% escalation, **one row apart**; `rows_dropped`, `rows_dropped_by_column`, `drop_escalation_share`; the offending column is named; the primary column keeps the stricter exit-1 rule; and the **asymmetry itself** (same proportion, different column, different rule). |
| `TestNotAssessableVsNotRun` (3B) | A missing brief makes `srm`/`maturity` `NOT_ASSESSABLE`, never `NOT_RUN`; the reason names the missing input; `validity_not_assessable` lists them as a sibling to `all_validity_failures`; the two statuses **never collide** anywhere (sweep over every fixture × gate); `NOT_ASSESSABLE` never appears on a conclusion gate; and the rendered report distinguishes them **per gate** (`[NO INPUT]` vs `[NOT RUN ]`) and never renders an unassessable gate as a PASS. |
| `TestGradientMagnitudePrecedence` (3C) | The branch keys **only** off `late_vs_early_rel` against the ±2% band; the rule is auditable via `flat_band`, `decided_by`, `corr_agrees_with_magnitude`; the magnitude is reported **before** r in document order; r is still reported as supporting context; and the monotone-but-tiny case is handled in **both halves**. |

### Tolerances (stated, not tuned to pass)

| Comparison | Tolerance |
|---|---|
| vs exact closed forms / `_ref`, p ≥ 1e-12 | 1e-6 relative. The well-known quick approximations to these functions (Wilson–Hilferty, Abramowitz–Stegun) are only good to about 1e-3, so they **fail** this bar — which is exactly why it is set here |
| vs closed forms, p < 1e-12 | 1e-3 relative (cancellation is unavoidable) |
| vs published critical values | 2e-4 relative |
| **at the SRM α boundary** | 1e-4 relative |
| Pure algebra (means, se, dof, `rel_diff`) | 1e-9 relative |

---

## The suppression suite

When the data is invalid the skill must not hand anyone a number to latch onto. Under
AMENDMENT 1 that covers **both** conclusion gates — the lift *and* the guardrail, because
a guardrail verdict on invalid data is a conclusion too.

Two layers, and they fail for **different reasons**, so neither can quietly cover for the
other:

**1. STRUCTURAL, on the JSON payload — check that the KEY is gone, not that the number is
gone.** A key that is not there cannot be there by coincidence, the way a number can.
- `gates.lift` and `gates.guardrail` are each *exactly* `{"status": "NOT_RUN", "reason": ...}` — two keys, so there is nowhere for a number to sit.
- No conclusion-only key (`rel_diff`, `rel_ci_high`, `effect_size`, `at_risk`, …) appears anywhere.
- No shared statistic key (`p_value`, `ci_low`, `diff`, `se`, `mean_a`, …) appears **outside** `gates.srm`, which legitimately owns its own p-value and dof.
- `guardrail.status` is never `PASS`/`FAIL`/`WARN`; no `BREACH` / `AT_RISK` token survives.
- An **exact-value** scan (1e-9 relative) over every numeric leaf proves none is the true lift, its p, t, CI, treatment mean, guardrail delta or guardrail CI.

**2. SEMANTIC, on the rendered human report — look for the forbidden idea, not for the
digits.** Hunting for digits in prose goes wrong in both directions:
- *false positive* — an unrelated number happens to match once rounded (the pooled cohort mean `2.1422` against a guardrail CI of `0.021444`, both rendering as `2.14`);
- *false negative*, which is worse — a leak that was **rounded** on its way into a sentence ("the lift was about +2%") never matches the full-precision value at all.

So the report is scanned for ideas instead. The two scans are called RULE A and RULE B in
`test_40_suppression.py`; those are the scanner's own names for them, not the labelled
`**RULE —**` blocks used in the skill's documents.
- **RULE A** — conclusion-only vocabulary (`lift`, `uplift`, `effect size`, `confidence interval`, `\bCI\b`, `moved the metric`, `% change`, …) and the hedged forms that are the realistic failure mode (`directionally`, `for context`, `worth noting`, `if the SRM were fixed`, `the guardrail at least`, `was ahead`, …). A term counts as a **leak only when asserted with a value** — the report may legitimately *label* the suppressed gate (`GATE 4 lift  srm failed`) and *state the denial* ("contains NO lift, no p-value, no confidence interval").
- **RULE B** — no single clause may name a **metric** and an **arm** together, because an arm comparison on a metric *is* the conclusion. This survives contact with the legitimate content: the SRM gate names arms and counts but no metric; the design gate echoes metric names but no arms; the truncation gradient names the primary metric but is pooled across arms.

**Pooled cohort means are deliberately not in any forbidden set** — they are a
legitimate arm-blind data-quality diagnostic. `TestCohortLevelsVsTrendSplit`
asserts the intended split instead: absolute levels (`early_mean`, `late_mean`)
present in the **JSON** for auditability, absent from the **prose**, which
carries trend only (cohorts, late-vs-early %, corr, direction).

### Scan controls

A test that can never fail proves nothing, so each scan is shown to fire when it should:
- `test_sanity_valid_fixtures_do_report_their_lift` — the numeric scan **must** find the lift on a valid fixture.
- `test_sanity_rule_a_fires_on_a_synthetic_leak` — denials and labels pass; `"For context the lift was about +2% anyway."` fails.
- `test_sanity_a_valid_report_does_use_conclusion_vocabulary` / `..._does_compare_arms_on_a_metric` — RULE A and RULE B both fire on a valid `SHIP` report.

RULE B's control is what caught a real bug in the scanner itself. The code that cut the
report into clauses was splitting on `:` and on runs of spaces, which chopped
`completed_orders_28d: treatment 2.16 vs control 2` into pieces — so no single piece named
both a metric and an arm, and RULE B had quietly stopped catching anything.

---

## Mutation testing

The suite was checked by deliberately breaking a **copy** of the implementation — never
the real `scripts/`. A mutant that survives is a hole in the suite. All 20 were caught:

| Mutant | Caught by |
|---|---|
| `chi2_sf` ×1.02 | 12 distribution tests |
| maturity `>= W` → `>= W-1` | 15 |
| validity failures narrowed to gate 0 (conclusion gates run on invalid data) | 29 |
| guardrail threshold 1pp → 2pp (in the brief parser) | 5 |
| `share < 1.0` → `share < 0.5` ("most users mature" heuristic) | 20 |
| Welch dof → pooled `n_a+n_b-2` | 5 |
| SRM α 0.001 → 0.05 | 1 |
| `parse_metric_window` regex de-anchored | 2 |
| as-of default → `max(exposure_date)` (the AMENDMENT 2 bug) | 5 |
| data-integrity reading suppressed | 29 |
| **rounded hedged prose leak** ("for context the lift was about +2% directionally") | 11 |
| absolute cohort levels back in the prose | 11 |
| arm comparison on a metric in the prose | 11 |
| extra key on the suppressed `gates.lift` | 2 |
| 2% drop-escalation threshold widened to 20% | 19 |
| `DROP_ESCALATION_SHARE` comparison loosened to 50% | 18 |
| `NOT_ASSESSABLE` collapsed into `NOT_RUN` | 5 |
| **the 3C branch keyed off r instead of the magnitude** | 5 |
| flat band widened 2% → 50% | 4 |
| absolute cohort level printed into prose at **full precision** | 1 |

The rounded-prose mutant is the one the original digit-based scan would have missed
completely. The full-precision mutant then exposed the mirror-image gap: the levels test
only matched *formatted* numbers, so a bare `2.0938572760580003` walked straight past it.
`test_absolute_levels_are_absent_from_the_prose` now runs **two** scans — a
formatted-string scan for rounded leaks, and a numeric-token scan at 1e-9 relative for
full-precision ones — because each one is sharp exactly where the other is blind.

## Helpers must never be the thing that fails

`_read()` in the suppression module called `float()` and had no handling for
missing-value markers. When the AMENDMENT 3A fixtures introduced `n/a` cells, it raised
during **setup** — so three suppression tests, the headline behaviour of the whole skill,
reported as ERRORs instead of running their checks at all. That is the worst way a test can
fail: it looks like an environment problem and gets waved through.

Every helper that touches fixture data now copes instead of raising. `_read()` and
`read_arm()` skip cells that are not numbers. `suppressed_quantities()` leaves out a metric
whose arm is too small for Welch. And every `_report()` helper checks the CLI's exit code
before it returns stdout, so a crashed subprocess fails loudly instead of handing back an
empty string — which would satisfy every "this must be absent" check by accident.

---

## Contract ambiguities and gaps found

Tests are written **to the contract**. Where the contract does not say, the test checks
only what the contract does support, and its docstring says which part was left open.

1. **`duration_days.total_weeks`** — the contract does not say whether this is the exact figure or rounded up. `48/7 = 6.857` and `7` are both accepted.
2. **`exposure_span_days`** — the contract does not say whether the day count includes both end dates (`max−min+1`) or neither (`max−min`). Both accepted.
3. **`required_days`** — the contract does not say whether this is `W` or `span + W`. Not checked tightly.
4. **Guardrail status vocabulary** — the contract names the outcomes `BREACH` / `AT_RISK`, but limits `status` to `{PASS,FAIL,WARN,NOT_RUN}`. `BREACH→FAIL` and `AT_RISK→WARN` is the only mapping that keeps the outcomes in the same order of severity, so that is what the tests assume — and they say so, in tests kept separate from the rest.
5. **Lift gate status when it runs** — the contract does not say whether a below-MDE result is `PASS` or `FAIL`, so the tests only check that it is not `NOT_RUN`.
6. **A missing brief file** — gate 0 asks whether the brief is *present and parseable*, so a missing brief is a **gate result** (exit 0, `INVALID-DESIGN`) rather than an input error. Either reading is defensible; tested to the contract as written.
7. ~~**`srm` / `maturity` when the brief is absent**~~ — **RESOLVED by AMENDMENT 3B.** A third status, `NOT_ASSESSABLE`, separates *"we could not check"* from `NOT_RUN`'s *"we chose not to conclude"*. Now pinned exactly, including the rule that the two must never collide.
8. **`parse_metric_window` and the scenario brief** — SCENARIO.md writes the metric as `completed_orders_28d (mean per user)`, and the contract's pattern `_(\d+)d$` only matches at the very end of the string, so it cannot match that. Cutting off the bracketed note has to be the brief parser's job. The tests assert `None` here, which is what the contract literally says, and `trap_real_data` covers the whole path end to end.
9. ~~**An unparseable value in a *secondary* metric column**~~ — **RESOLVED by AMENDMENT 3A.** Drop the row and say so, escalating to a gate-0 `FAIL` once dropped rows *exceed* 2%; the primary column keeps exit 1. The old test that accepted either behaviour is replaced by exact checks on both sides of the boundary.
10. **`power.py` key names** — the contract lists what `power.py` reports, but not what the keys are called. So the required-n and window values are matched as numbers, and the key names are only loosely checked.
11. ~~**Correlation on a flat series is not stably bounded**~~ — **RAISED BY THIS SUITE AND PROMOTED INTO THE CONTRACT (AMENDMENT 3C).** Over cohort means that are nearly equal, Pearson r has no scale to it and is mostly noise, so it cannot carry the flat / `late_lower` decision — and the DATA INTEGRITY branch fires on "flat", which means the strongest finding in the whole readout had been resting on an unstable number. The branch now keys only off the magnitude, with r as supporting context. Flatness checks bound `late_vs_early_rel`; only the fixtures built with a deliberate gradient bound r.

    One degenerate case the suite turned up: with **2 cohorts** Pearson r is mathematically ±1 whatever the data (`maturity_off_by_one` shows |r| = 1.000), so the suite's own r-guard skips fixtures with fewer than 4 cohorts. The implementation reports `insufficient_cohorts` there.

12. **The monotone-but-tiny trap** — a magnitude inside the flat band, with r ≤ −0.5 and p < 0.05. Going on magnitude alone calls it flat, and the data-integrity sentence *"the values do not move with follow-up time"* is then **false**: they do move, steadily downwards, just far too little. So r must be allowed to shape the **wording** while never touching the branch. `monotone_but_tiny` checks both halves, including a strict test that the reading never claims the values fail to move.

## The one module that must NOT pin `--asof`

Every other fixture pins `--asof`, enforced by `test_every_case_pins_asof`, because a verdict
that depends on the system clock would rot: a fixture passing today could flip weeks later with
no code change, and nobody could tell whether the skill changed or the calendar did.

`test_70_maturity_warn.py` is the deliberate exception, and the exception is the point. The
`WARN` branch fires *only* when the as-of date is assumed — which by construction means the
clock decides. Pinning `--asof` there moves the run onto the `given` path and silently deletes
all coverage of the rule.

So the assumed-branch assertions are bounded to properties true on **any** date: the status
word, the provenance prefix, the shape of the wording, the presence of the caveat. None asserts
a date or a mature count. Anything date-specific pins `--asof` and lives in the `FAIL` tests.

**If a test here looks non-deterministic: it is deliberate, it is bounded, and the fix is not to
pin the flag.**

### Why this rule exists at all

The defect it guards against shipped past 225 tests, 20 mutants and 20 live eval sessions. The
wall clock found it: the metric window happened to sit exactly one span from the last exposure
date, so on 2026-08-24 the gate began reporting "all 12000 users are mature" as fact. It is not
a fact. The CSV's values were computed once, at an unknown extraction time, and frozen; calendar
time passing does not mature data already on disk.

A test suite cannot see a bug whose trigger is the passage of time. A gate fed by the system
clock needs a test that **varies** the clock, not one that pins it.
