# Gates, thresholds, verdicts

Cite as `references/gates.md § <section>`. The engine (`scripts/run_readout.py`) implements
exactly this; read a gate here before you explain it.

Plain English explains; blocks labelled **RULE —** and **DEFINITION —** are exact and are
quoted as written, never paraphrased.

## Fixed thresholds

Nothing here is a judgement call. Every number was chosen before the data arrived, and
changing one after seeing results is how a check stops being a check.

**DEFINITION —**

| Thing | Value |
|---|---|
| SRM alpha | 0.001 (chi-squared goodness-of-fit, dof = k-1) |
| Significance alpha | 0.05, two-sided (Welch) |
| Multiplicity | Holm-Bonferroni across the k treatment arms, family-wise alpha 0.05 |
| Power | 0.80 |
| MDE | RELATIVE to the control mean unless the brief says otherwise |
| Guardrail BREACH | point diff (treatment - control) worse than the brief's threshold (e.g. > +0.01 = 1pp) |
| Guardrail AT_RISK | point diff within threshold but the 95% CI upper bound crosses it |
| Maturity | metric window W from `_(\d+)d$` in the metric name; a user is mature iff exposure + W <= asof |

## Gate order and class

A gate has one of two jobs. A **validity** gate asks whether the data can answer the
question at all. A **conclusion** gate answers it. Numbering them fixes their order, and the
order is the whole point: a comparison drawn from arms that were not built the same way, or
from a metric that has not finished counting, is not a weaker answer — it is an answer to a
different question.

**DEFINITION —**

| # | Gate | Class | Fails when | Verdict if first to fail |
|---|---|---|---|---|
| 0 | `design_integrity` | validity | no readable brief; required columns absent; arm labels not in the design; brief sealed after the first exposure; no usable numeric metric values; a unit appears in two arms | INVALID-DESIGN |
| 1 | `srm` | validity | chi-squared p < 0.001 against the designed ratio | INVALID-SRM |
| 2 | `maturity` | validity | `mature_share < 1.0` (0 mature and partially mature both fail); WARN, not PASS, when it would clear only under an ASSUMED as-of date | INVALID-IMMATURE |
| 3 | `guardrail` | conclusion | BREACH in any treatment arm (a breach bars the arm it was measured in; with one treatment arm that forces NO-SHIP); AT_RISK is a WARN | — |
| 4 | `lift` | conclusion | — | see verdict rules |

**RULE — Validity gates 0-2 all evaluate and are all reported, always** — even after an
earlier one fails. One fixed defect plus one unreported defect still yields an unreadable
rerun, so `all_validity_failures` carries every failure and your report must enumerate all of
them. The verdict is named by the *first* failure in gate order; the order is preserved in
the verdict, not by refusing to look further.

**RULE — Conclusion gates 3-4 are suppressed the moment any validity gate fails.** Both
become `{"status": "NOT_RUN", "reason": "<first failing gate> failed"}`. A guardrail verdict
on invalid data is a conclusion too.

## GATE 0 — design integrity

This gate asks a single question: did someone write down what they were going to measure,
before they measured it, and does the file match what they wrote?

**DEFINITION —** Checks, each reported individually: brief present and parseable; results
non-empty; arm column; exposure-date column; primary metric column present; guardrail column
present (WARN if absent); observed arm labels all belong to the designed assignment; metric
values numeric; **sealed date <= first exposure** (pre-registration — a design sealed after
exposure began is a design written around the result); one arm per unit; MDE declared.

**RULE — A missing brief is a GATE 0 FAIL, not a licence to invent the design.** Without the
sealed design there is no MDE, no designed ratio and no guardrail — nothing to hold the
result to. Reply with the specific list of what is needed and stop: designed assignment
ratio; primary metric and its observation window; MDE (and whether it is relative or
absolute); guardrail metric, threshold and direction; the seal date. Reconstructing any of
these from the results file re-derives the hypothesis from the evidence.

## GATE 1 — SRM (sample ratio mismatch)

Two arms that were filled by a coin flip end up close to the size the design asked for. A
gap much larger than chance allows is not bad luck, it is a bug: exposure events went
missing on one side, or a filter fired asymmetrically, or the ramp moved mid-flight. That
matters more than it sounds, because the arms are then no longer two samples of the same
population — whatever caused the imbalance is also mixed into every comparison you could
draw between them.

**DEFINITION —** `chi2 = sum((observed - expected)^2 / expected)`, dof = k-1, alpha = 0.001.
Expected counts come from the designed ratio applied to the observed total.

The bar is deliberately strict, because this gate is a bug detector rather than a hypothesis
anybody is interested in. It is also why the gate can be tripped by a gap that looks small
to the eye: at large sample sizes, a couple of percent is not a rounding wobble.

**RULE — where the expected ratio may come from. This is the gate's whole integrity.**

| Source | Allowed? | What the output must say |
|---|---|---|
| Ratio declared in the sealed brief | yes | `ratio_source: brief (declared)` |
| No ratio in the brief -> equal split across the observed arm labels | yes, with a label | "the ratio was ASSUMED equal, not read; an SRM result under an assumed ratio is weaker evidence" |
| Inferred from the observed arm counts ("looks like 50/50, call that the design") | **never** | — |
| No brief at all | not applicable — GATE 0 already failed; do not run later gates | ask for the sealed design |

Expected-from-observed collapses `chi2` toward 0 by construction: the gate can then never
fail, and prints a reassuring "srm PASS" on data with a broken split. Arm **labels** may be
read from the data (they are names); **shares** may not (they are the hypothesis).

Where SRMs usually come from: exposure logging dropped on one variant, bot or eligibility
filters applied to one side only, a mid-flight ramp or reallocation, drop-off on a redirect,
one arm crashing, dedupe run on one side.

**RULE — Never "fix" an SRM by reweighting, trimming, capping, or dropping the excess
users.** That conditions on the bug. Find the cause, fix it, rerun.

## GATE 2 — maturity

A metric with an N-day window is a promise to count N days of behaviour per user. Until
those days have passed, the cell holds a partial count that happens to look like a small
number. So this gate asks whether the counting has actually finished — for everyone, not on
average.

**DEFINITION —** W is parsed from the metric name (`completed_orders_28d` → 28). A user is
mature iff `exposure_date + W <= asof`. Anything below `mature_share == 1.0` fails.

The catch is that a results file listing only exposure dates cannot tell you when the metric
was pulled. So the as-of date has to be resolved from somewhere, and which somewhere it came
from is part of the finding.

**DEFINITION —** Resolution order (v1.2), first hit wins; the provenance is reported with
the date every time: `--asof` (`given`) > an as-of/extract/snapshot column in the CSV
(`from data`) > a date stated in the ask (`from request`) > **today's system date**
(`assumed: today`).

Today is the default because it is the most generous defensible value — an upper bound on any
possible extract date, since data cannot describe the future — so a FAIL under it is certain
rather than manufactured. `max(exposure_date)` is a lower bound that made `mature_share == 1.0`
arithmetically impossible for any W > 0; it is removed as a default and must not come back.
See `maturity-and-duration.md § As-of resolution`.

`assumed: today` makes the verdict time-dependent, so any run you need to reproduce must pass
an explicit `--asof`. Never write a bare maturity share as fact when the date was assumed:
name the provenance next to the number and the input that would settle it.

**RULE — An assumed as-of date can never produce a PASS.** A file's metric values were
computed at some unknown extraction time and are frozen there, so calendar time passing does
not mature data already written to disk. Today's date shows only that maturity was POSSIBLE by
now, never that it happened. So when the as-of date was assumed and the gate would otherwise
pass, the status is **WARN**: state the conditional — every user is mature if and only if the
extract was taken on or after `last_exposure + W` — and name `--asof <extraction date>` as the
input that settles it. A clean PASS requires an as-of that the data or the user actually
supplied (`given`, `from data`, `from request`). This is the mirror image of the default
Amendment 2 removed, and the worse half of it: a false FAIL is loud, a false PASS is silent.

The gate also runs the **truncation gradient** (metric mean by exposure date, pooled across
arms): late-cohorts-lower confirms truncation from the data alone, while a flat or upward
gradient against a timeline that makes maturity impossible is a DATA INTEGRITY finding — the
values do not move with follow-up time the way a truncated window forces them to.

**RULE — Magnitude decides, correlation informs.** The branch keys only off the
late-half-vs-early-half percentage change against a ±2% flat band. Pearson r is reported as
supporting context and never decides anything: over near-equal cohort means r is scale-free
and noise-dominated, so an r of −0.03 is an artefact, not a measurement. Never present r as
the headline evidence for flatness — and never let the DATA INTEGRITY finding, the strongest
claim in the readout, rest on it. See `maturity-and-duration.md § The truncation gradient`.

A failed maturity gate has two quite different stories behind it, and the report has to tell
the right one.

**DEFINITION —**
- **mature_share = 0** — the window has not closed for anyone; the metric is not yet
  observable, so every value in the column is a partial count.
- **0 < mature_share < 1** — differential follow-up: early cohorts have more exposure time
  than late ones, so a difference of means mixes the treatment effect with an exposure-age
  effect, and any arm-time imbalance leaks straight into the estimate.

**RULE — If the window cannot be determined the gate does not invent one:** no primary metric
declared → `NOT_RUN` ("nothing to check"); a declared metric with no `_<N>d` suffix → `WARN`,
meaning unverified rather than passed — confirm the window with the metric owner before
concluding.

The gate also reports `exposure_span_days` and, when given `--claimed-duration`,
`claim_matches_data`. A duration asserted in the ask is a claim to test, never an input.

### Status vocabulary — five words, five meanings

Two of these are easy to blur, and blurring them is a reporting bug rather than a wording
preference: a reader has to be able to tell a conclusion we withheld from a check we never
managed to run, because the next action is completely different.

**DEFINITION —**

| Status | Means | Next action |
|---|---|---|
| `PASS` | checked, and it held | none |
| `FAIL` | checked, and it did not hold | fix the thing named |
| `WARN` | checked, and the result is CONDITIONAL — it holds only on something that was assumed, or it holds with a detail that changes how it reads | read the detail, then supply what would settle it |
| `NOT_RUN` | **we chose not to conclude** — a conclusion gate suppressed because a validity gate failed | fix the validity failure, re-run |
| `NOT_ASSESSABLE` | **we could not check** — the gate had no inputs, because GATE 0 could not supply them; carries a `reason` naming the missing input | supply the missing input (usually the sealed brief) |

**RULE — Never let "we chose not to conclude" and "we could not check" render as the same
word.** A suppressed conclusion and an unperformed check call for completely different next
actions, and an unperformed check must never read as a clean pass. `all_validity_failures`
lists validity gates that FAILED; `validity_not_assessable` lists validity gates that had no
inputs, so nothing is silently dropped from the account.

**RULE — A validity WARN does not block, and it travels with the verdict.** A FAIL says the
data cannot answer the question; a WARN says the check ran and its result rests on an
assumption. So the conclusion gates still run, the verdict is still reached, and
`validity_warnings` carries every validity gate that WARNed — reported beside the verdict, not
only in the gate table, so nobody can take a verdict without the assumption it rested on.

### Unparseable metric values — the asymmetry is deliberate

One unreadable cell in the guardrail column should not sink the whole readout; one in the
primary metric should, because that is the column the verdict rests on. Hence two rules, and
a ceiling that catches the case where "one bad cell" was never the real story.

**DEFINITION —**

| Column | Unparseable value | Why |
|---|---|---|
| primary metric | **exit 1** (input error) | You cannot read out a primary metric you cannot parse, and silently dropping rows from the column the verdict rests on would bias the estimate invisibly. |
| guardrail / secondary | drop the row, GATE 0 **WARN** naming the column and counts | A guardrail is a constraint, not the estimand. One bad cell must not block the whole readout — but it must never be silent. |
| either | **>2% of rows dropped -> GATE 0 FAIL -> INVALID-DESIGN** | A file that cannot parse 2%+ of a metric column is a data-quality problem, not a rounding nuisance. |

Blank, `NA`, `null`, `none`, `nan`, `-` and `?` are recognised MISSING markers in either column:
dropped and counted, never an exit-1 error. The payload reports `rows_total`, `rows_usable`,
`rows_dropped` and `rows_dropped_by_column`.

**Exit codes.** The engine exits 0 for every verdict, including the invalid ones — a failed
gate is a finding, not a crash. Exit 1 means the *input* is unusable: a missing results file,
a bad `--asof`, or a genuinely non-numeric value in a metric column (blank / `NA` cells are
treated as missing and reported as a WARN). Fix the extract and re-run; do not report a
verdict from a run that exited 1.

## GATE 3 — guardrail

The guardrail is the thing you promised not to break while chasing the primary metric. Note
that `cancel_rate` is a per-user rate, so each user contributes their own number and the
comparison is between two averages — not between two lumped-together proportions.

**DEFINITION —** Difference of means (Welch) on the guardrail column, compared against the
brief's threshold in the direction the brief says is worse. `cancel_rate` is a per-user rate,
so "must not worsen by >1pp" is a difference of means at 0.01, not a pooled proportion test.
A BREACH bars the arm it was measured in, however good that arm's primary metric looks.
AT_RISK is a WARN that must appear in the verdict reasoning.

**DEFINITION — one comparison per treatment arm.** The test above is run for EVERY treatment
arm against control, and every comparison is reported. With one treatment arm that arm is the
whole experiment, so a BREACH there forces NO-SHIP. In an A/B/n test a BREACH bars the arm it
was measured in and says nothing about any other, because the arms are different changes
measured separately — reading one arm's guardrail onto another is the same mixing of arms as
reading one arm's lift as the experiment's. The gate's status is FAIL whenever any arm
breaches, and the breaching arms are named beside the verdict whether or not they were the
arms anyone wanted to ship.

## GATE 4 — lift

**DEFINITION —** Welch two-sample t-test on the primary metric, treatment vs control,
two-sided. Relative lift and relative CI are divided by the control mean. The p-value is
compared against alpha = 0.05 when the design has one treatment arm, and against the
Holm-corrected threshold below when it has more. For A/B/n each treatment arm is compared
against control separately; report every comparison and do not silently promote the best one.

### More arms need a stricter bar

Alpha is a budget for being wrong. At 0.05 you have agreed that about one comparison in
twenty will look real when nothing happened. Run one comparison and that is your whole
exposure. Run two and each one gets its own one-in-twenty, so the chance that AT LEAST ONE of
them comes back a false positive is 1 - 0.95^2 = 9.75%. Three treatment arms and it is
14.26%. Nothing about the arms got worse; you simply bought more tickets. A test that reports
"the winner was significant at p<0.05" out of three arms has not told you what its reader
thinks it has.

So the budget is spent across the whole family instead of being handed out fresh to each arm.
Holm-Bonferroni spends it unevenly on purpose: the smallest p-value faces the strictest
threshold and the largest faces plain alpha, which makes it strictly kinder than dividing
alpha by k for everyone while holding the same family-wise guarantee.

**DEFINITION — Holm-Bonferroni.** With k treatment arms there are k hypotheses, one per arm
against control. Sort the k p-values ascending. The hypothesis at 0-indexed sorted position i
is compared against `alpha / (k - i)`. Reject while `p < threshold`, and STOP at the first
hypothesis that fails: every hypothesis with a larger p-value is retained, whatever its own
threshold would have allowed. At k = 1 every threshold is alpha and the procedure is the
plain test, so a two-arm readout is unchanged by it. Implemented as `gates.holm_bonferroni`;
the corrected threshold and the corrected decision are reported next to each arm's raw
p-value.

Planning follows the same arithmetic backwards. `power.py` sizes a SINGLE comparison at the
alpha it is given, so a design with k treatment arms is under-sized by its default: the arm
that ends up with the smallest p-value faces alpha/k, not alpha. Pass `--alpha` at alpha/k
when planning an A/B/n test and expect a larger n per arm — extra arms are not free, and the
cost lands on sample size rather than on the verdict.

**RULE — an arm is never dropped after the results are in.** Choosing which arms to report
once you have seen which one won is post-hoc selection: it hands back the family-wise false
positive rate the correction was applied to control, and it does so invisibly, because a
discarded arm leaves no trace in the document for a reader to object to. Every arm present in
the data appears in the readout — the ones that lost, the ones nobody intends to ship, and
the ones whose point estimate cleared the MDE without being significant, which is the one
that gets quoted back at you six weeks later.

## Verdict taxonomy — exactly one

Two separate questions decide a valid readout. Significance asks whether the gap is real at
all; the MDE asks whether a real gap of that size was worth the work. A result can clear one
and fail the other, so both appear in the rules.

**DEFINITION —**
`INVALID-DESIGN | INVALID-SRM | INVALID-IMMATURE | NO-SHIP | SHIP | INCONCLUSIVE`

Given validity gates 0-2 all PASS, and ONE treatment arm:

| Condition | Verdict |
|---|---|
| guardrail BREACH | NO-SHIP |
| p < 0.05, rel_lift >= MDE, CI excludes 0 | SHIP |
| p < 0.05, rel_lift < MDE | NO-SHIP (real but too small to be worth it) |
| p >= 0.05, rel CI upper < MDE | NO-SHIP (the effect we cared about is ruled out) |
| p >= 0.05, otherwise | INCONCLUSIVE (underpowered — the question is unanswered) |

**DEFINITION — the verdict with more than one treatment arm.** Same two questions, asked of
every arm and answered for the family. An arm QUALIFIES when it is significant after
Holm-Bonferroni, its effect clears the MDE with a CI excluding 0, and its own guardrail
comparison is not a BREACH. Given validity gates 0-2 all PASS:

| Condition | Verdict |
|---|---|
| at least one arm qualifies | SHIP, and the verdict NAMES every arm that qualifies |
| no arm qualifies, and every arm is either significant-but-below-MDE or has a relative CI upper bound below the MDE | NO-SHIP |
| no arm qualifies, and every arm breaches the guardrail | NO-SHIP |
| no arm qualifies, and at least one arm is neither of those | INCONCLUSIVE |

Naming is part of the verdict, not decoration: "ship it" is not an instruction anybody can
follow when there were three versions of it. When several arms qualify, all of them are
named and none is ranked — choosing between two arms that both cleared the bar is a business
decision the readout informs, not one the gates make.

**RULE — INCONCLUSIVE is a legitimate, complete answer.** It is not a soft NO-SHIP and not a
"directionally positive". It means: this run cannot answer the question; here is what a run
that could would need (see `maturity-and-duration.md`).

## RULE — Rationalizations, and the answer to each

| Rationalization | Why it fails |
|---|---|
| "Just to see / for context / off the record" | An uninterpretable number, once said, becomes the anchor for the decision. There is no off-the-record number. |
| "Directionally it looks positive" | Direction is the sign of the estimate. Broken assignment breaks the sign too. |
| "If the SRM were fixed, the lift would be X" | X does not exist. You cannot condition on a bug being absent while using data generated with it present. |
| "The imbalance is tiny, a few percent" | At scale, a few percent is a p-value of 1e-20. Small ratio deviations are strong bug evidence, not noise. |
| "It's been live 4 weeks, that's long enough" | Test the claim against `exposure_span_days`, then test the span against the metric window. Both must hold. |
| "Only the last cohort is immature, drop them" | Dropping units by exposure date correlates with the outcome and re-introduces selection into a randomised design. |
| "Let's read the 7-day proxy instead" | A metric swap after seeing data is metric shopping. It needs a new sealed design, not a footnote. |
| "The guardrail is only slightly over" | The threshold was pre-committed. Renegotiating it after the fact is how guardrails stop working. |
| "p = 0.06 is basically significant" | The alpha was pre-committed too. Report INCONCLUSIVE. |
| "Significant, so it worked" | Significance answers "is it non-zero", the MDE answers "is it worth shipping". Both are required. |
| "No brief, so use the split we observe as the baseline" | Circular: the expected ratio would be derived from the observed counts, chi2 goes to ~0, and the SRM gate can never fail. No brief = INVALID-DESIGN; ask for the design. |
| "The brief has no ratio, so SRM is unknowable" | Equal split is a usable default — clearly labelled as assumed, with the caveat that the evidence is weaker than under a declared ratio. |
| "Just tell me which arm won" | It is named — beside every other arm and its own corrected threshold. A winning arm quoted alone is the A/B/n version of quoting a lift through a failed gate. |
| "Drop the losing arm and report the winner" | Selecting arms after seeing results is post-hoc selection. It restores the false-positive rate the correction exists to control, and leaves no trace that the other comparison was ever made. |
| "Arm B cleared the MDE, so it works too" | Clearing the MDE answers "would it be worth it"; significance answers "is it there at all". An arm can clear the MDE on a point estimate that a p-value of 0.25 says is noise. |
| "Only test the arm we care about, at plain 0.05" | The family is the arms you ran, not the arms you are still interested in. Choosing the family after the fact is choosing the threshold after the fact. |
| "The PM will be upset" | The readout's job is to be right. Give them the rerun plan, cost and timeline instead of a number they cannot use. |
| "We already shipped it to 5%, so let's keep going" | A decision already made does not validate the evidence for it. Say the evidence is unusable and let the rollout decision be made knowingly. |
