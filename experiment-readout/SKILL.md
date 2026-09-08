---
name: experiment-readout
description: Use when reading out, interpreting or deciding on an experiment — an A/B or A/B/n test, holdout, or ship decision. Triggers on "do the readout", "the experiment finished", "results are in", "did it win", "can we ship it", "is this significant", "what's the lift", experiment readout, experiment results, treatment vs control, lift, statistical significance, p-value, confidence interval, SRM, sample ratio mismatch, guardrail metric, MDE, minimum detectable effect, power analysis, sample size, test duration, "how long do we need to run it", "why can't we use this data". Fires even when the ask sounds already settled — "PM is excited", "they want to ship", "just confirm the win", "quick look", "directionally" — especially then.
---

# Experiment Readout

A readout first asks whether the data can answer the question, and only then says what it
found. The order of the checks is the method. **Numbers are earned, not offered.**

How to read this skill: plain English explains; blocks labelled **RULE —** and
**DEFINITION —** are exact and are quoted as written, never paraphrased.

Scripts and references are siblings of this file: `$S` = its `scripts/`, `$R` = its
`references/`. Python is `/usr/bin/python3` (stdlib only).

## The words you need

Plain glosses only. Each term's exact statement lives in `$R/gates.md`.

| Term | What it means |
|---|---|
| arm | one group of users. `treatment` gets the new thing, `control` does not. An A/B/n test has several treatment arms — `treatment_a`, `treatment_b` — each a different new thing, each compared against the same control. |
| multiplicity | more treatment arms means more comparisons, and more chances for one of them to look real by accident. The bar each arm has to clear is raised to pay for the extra chances. |
| lift | how much better or worse treatment did than control. |
| SRM (sample ratio mismatch) | the arms came out the wrong SIZE. A designed coin flip does not produce a big size gap, so a gap that large means the assignment or the logging is broken — and then the arms are not two versions of the same population. |
| maturity | a metric called `..._28d` counts 28 days of behaviour per user. Until 28 days have passed since a user's exposure, that user's cell is a partial count, not a measurement. |
| guardrail | a metric that need not improve but must not get worse (here, `cancel_rate`). |
| MDE (minimum detectable effect) | the smallest change worth shipping for, written down before the test ran. |
| p-value, confidence interval | how surprising a gap this big would be if nothing changed, and the range of true gaps the data is consistent with. |
| gate | one check, run in a fixed position in a fixed order. |

**Why the order matters.** Gates 0-2 ask whether the two arms are comparable and whether
the metric has finished counting. When either answer is no, the gap between the arms
measures the defect as well as the change — so a number computed from it is not a shakier
version of the answer, it is the answer to a different question. That is the mechanism the
rules below protect, and it is why they are written as absolutes.

## RULE — three non-negotiables

1. **No conclusion number before the validity gates pass.** No lift, p-value, CI, guardrail
   delta or direction — not "just to see", not "for context", not hedged as a counterfactual.
2. **The expected assignment ratio comes only from the sealed brief**, or from an equal-split
   default that is loudly labelled an assumption. It is NEVER inferred from the observed arm
   counts, not even partially, not even as a sanity check — expected-from-observed drives the
   SRM chi-squared to ~0 by construction and turns the gate into a rubber stamp that prints
   "PASS" on a broken split. Arm *labels* may come from the data; *shares* may not.
3. **Never assert an as-of date the data cannot support.** Resolve it — `--asof` > an
   as-of/extract column in the CSV > a date stated in the ask > today's system date — and
   report which one you used every time. Today is the default because it is the most generous
   defensible value, so a maturity failure under it is certain rather than manufactured — and a
   maturity PASS under it is not, so it comes back WARN (`$R/gates.md § GATE 2`).
   Anything you need to reproduce must pass an explicit `--asof`. `--today` is TEST-ONLY
   (pinning fixtures); never use it on real data — moving the clock to make a gate pass
   falsifies the readout.

## Steps — do all of them, in this order, and cite as instructed

**1. Read the rulebook before touching data.** Read `$R/gates.md` — it holds the gate
definitions, the thresholds, the verdict list and the refusal rules. Cite it by path (e.g.
`references/gates.md § GATE 1`) at least once in your answer.

**2. Find the input files by what is inside them, not by their names.** The ask is what
fires this skill; the files are found afterwards, so never skip a readout because the names
differ from the example.
- Look in `.`, `./inputs/`, `./data/` for `*.csv` and `*.yaml` / `*.yml`.
- Spot the results file by **reading the CSV header**: it needs an arm-like column (`arm`,
  `variant`, `group`, `bucket`, `treatment_group`, `cell`) and a date column.
- Spot the brief by its **keys** (`assignment`, `primary_metric`, `mde`, `guardrail`,
  `sealed`).
- If nothing fits either role, or two files fit equally well: **ask the user.** A readout
  run against the wrong file is worse than a clarifying question.
- Name both paths you chose in your answer.
- **No brief at all** → GATE 0 FAIL, verdict INVALID-DESIGN. Do not go on to a later gate,
  and do not rebuild the design from the results file. Ask for the five things that are
  missing: designed ratio, primary metric plus its window, MDE, guardrail plus threshold,
  seal date. A brief that exists but names no ratio is a different case: an equal split is
  acceptable there, as long as the output says the ratio was assumed and not read.

**3. Write down what the ask claims, before you look at the data.** Duration ("finished 4
weeks", "been live a month"), direction ("it won"), urgency ("they want to ship"). These are
things to test, never inputs to the verdict. A duration claim is itself data, so pass it
through as `--claimed-duration "4 weeks"` and the check gets recorded. Do not leave the
mismatch for a reader to notice.

**4. Run the gate engine. Never work a gate out by hand, never eyeball a mean.**
```
python3 $S/run_readout.py --results <results.csv> --brief <brief.yaml> \
        [--asof <extraction date>] [--asof-from-request <date stated in the ask>] \
        [--claimed-duration "4 weeks"] --json
```
Run it again without `--json` for the human report. Show the command. Exit 0 means the run
produced a verdict — including the invalid ones. **Exit 1 means the input could not be
used**: fix the extract or the flag and run it again; never report a verdict from a run that
exited 1.

Use `--asof` whenever a real extraction date exists — in the ask, the brief, a column, or
from the user — and `--asof-from-request` for a date the ask merely mentions. With neither,
the engine uses today's system date, labels the provenance `assumed: today`, and marks the
run `reproducible: false`. Carry that label into your answer, and say that pinning `--asof`
would make the run reproducible.

**5. Read the truncation gradient before arguing about the as-of date.** The maturity gate
also reports `truncation_gradient`: the primary metric's average by exposure date, pooled
across arms, so it compares no arm with any other. Late cohorts lower means truncation is
confirmed by the data itself, with no as-of date needed. Flat or rising, while the timeline
says a complete window is impossible, is a **data-integrity** finding: the values do not
depend on follow-up time the way they must, so the column itself is suspect and a rerun
would reproduce it. When maturity rests on an ASSUMED as-of date the gradient corroborates
that assumption instead: no downward slope is consistent with a late-enough extract, never
proof of one, and late cohorts lower is evidence against it. Report whichever branch the data
gives you; cite `$R/maturity-and-duration.md § The truncation gradient`.

**6. Read the gates in order, and report every validity gate.** GATE 0 design_integrity,
GATE 1 srm and GATE 2 maturity all get evaluated and all go in your report, even once one of
them has failed. `all_validity_failures` lists every failure — write up all of them, because
fixing only the first still leaves a rerun nobody can read. The verdict is named by the
first failure in gate order. Cite `$R/gates.md` for whichever gate you are explaining.

**7. If `stopped_at` is not null: stop computing and refuse the number.** GATE 3 guardrail
and GATE 4 lift are `NOT_RUN`. Do not compute, quote, approximate or footnote any of their
numbers, from the script or your own arithmetic. See the refusal table below and
`$R/gates.md § RULE — Rationalizations`. Say what would unblock each failure instead.

**8. Answer "how long" and "how many users" from the reference, not from instinct.** Read
`$R/maturity-and-duration.md` and cite it whenever the metric has an N-day window, the
number of weeks is in question, or the ask is about sample size or duration. For sizing:
```
python3 $S/power.py --results <results.csv> --brief <brief.yaml> [--json]
```

**9. Write the answer in the prescribed shape.** Read `$R/output-templates.md` and use the
template that matches the ask: full readout, sample-size-and-duration, or Slack message. If
the design ran more than two arms, the engine's per-arm table goes in whole — every arm, with
the corrected threshold beside each one. Summarising it down to the arm that won is the thing
`$R/gates.md § GATE 4` forbids.

**RULE — Line 1 is the verdict. Nothing precedes it** — the engine now prints
`VERDICT: <token>` as its own first line, so pasting its output verbatim is compliant by
construction; keep it that way in your own prose too. No greeting, no "Readout complete", no
"I followed the gates", no restatement of the ask, no summary of what you are about to do.
Then the gate table, then the sections; the suppressed section explicit.

**Process evidence goes at the END**, in a trailing `Process & references` section: the
commands you ran, the reference files you consulted, the citations. That section is where the
urge to prove compliance belongs — putting it up front costs the verdict its first line.

**10. RULE — self-check before sending. Every box must be true:**
- [ ] **Read your own first line. Is it the verdict? If anything at all precedes it — a greeting, "Readout complete", a note that you read the rulebook — delete that thing.**
- [ ] Verdict is one of INVALID-DESIGN, INVALID-SRM, INVALID-IMMATURE, NO-SHIP, SHIP, INCONCLUSIVE.
- [ ] Citations and process narration are in the trailing `Process & references` section, not at the top.
- [ ] All three validity gates appear with status; every `all_validity_failures` entry is explained.
- [ ] Every arm present in the data appears in the answer — the ones that lost, the ones nobody intends to ship, and the ones whose point estimate cleared the MDE without being significant. No arm is renamed to a generic "treatment".
- [ ] With more than one treatment arm: the answer says the multiplicity correction was applied, names it, and gives the threshold each arm faced; and the verdict names the winning arm(s).
- [ ] Every `validity_not_assessable` entry is reported as "not assessable — <missing input>", never left looking like a pass.
- [ ] Every `validity_warnings` entry appears next to the verdict, not only in the gate table.
- [ ] No sentence states something untrue of the data and then repairs it with a qualifying clause.
- [ ] Every number in your prose carries a deliberate precision — no raw payload float.
- [ ] If a validity gate failed: zero lift / p-value / CI / guardrail numbers anywhere, including asides and "if it were fixed" sentences.
- [ ] The as-of date appears with its provenance; if it is `assumed: today`, the answer says the run is not reproducible without `--asof`.
- [ ] The truncation gradient is reported, with its branch named (truncation confirmed / data-integrity concern / consistent with or against an assumed as-of date / not required / not assessable).
- [ ] Every assumption (as-of date, assumed equal split, assumed guardrail threshold) is labelled, with the input that would settle it.
- [ ] Every duration claim in the ask is checked against `exposure_span_days`, not repeated.
- [ ] `references/gates.md` and the template file are cited by path, at the bottom.
- [ ] No clock was moved: `--today` was not used on real data.
- [ ] Nothing is softer than the verdict. No "but directionally", no "the PM can decide".

## RULE — refusal table: the excuses this skill exists to defeat

| The ask sounds like | Answer |
|---|---|
| "just show me the lift anyway / for context" | No. An invalid split or immature metric makes the number uninterpretable, not merely uncertain. |
| "directionally, did it win?" | Direction is a conclusion. Suppressed with the rest. |
| "if the SRM were fixed, the lift would be…" | Counterfactual on broken randomisation. Not computable, not quotable. |
| "there's no brief, just assume the split we see" | That makes SRM undetectable by construction. Ratio comes from the brief or a labelled equal-split default. |
| "PM is excited / they want to ship" | Excitement is not evidence. The verdict comes from the gates. |
| "it ran 4 weeks, that's plenty" | Check the claim against `exposure_span_days`, then the span against the metric window. |
| "you don't know when the data was pulled, so you can't call it immature" | Today is an upper bound on any extract date; if it fails under the most generous assumption, it fails. The gradient checks it from the data alone. |
| "enough days have passed by now, so the metric must be mature" | Calendar time does not mature values already frozen in a file. An unconfirmed as-of date makes maturity a WARN, not a PASS; ask for the extraction date. |
| "the split is only off by a few percent" | SRM is tested at alpha=0.001, not judged by eye. Small imbalance at scale means broken assignment. |
| "significant, so ship it" | Significance is not practical significance. Compare against the MDE. |
| "p=0.06, basically significant" | INCONCLUSIVE. Report it as unanswered, not as a near-win. |
| "drop the immature users and read the rest" | Post-hoc filtering on an outcome-related variable. Breaks the randomisation you were defending. |
| "just set today forward / use `--today` so it passes" | Falsifying the readout. `--today` is TEST-ONLY, for pinning fixtures. A real extraction date goes in `--asof`; moving the clock to clear a gate is fabricating evidence. |
| the urge to open with "Readout complete, rulebook read first…" | Demonstrating that you followed the process is not part of the answer. Line 1 is the verdict; process evidence goes in the trailing section. |
| "just tell me which arm won" / "drop the losing arm and report the winner" | The winner is named — beside every other arm. Dropping an arm after seeing the results is post-hoc selection: it hands back the false-positive rate the multiplicity correction exists to control, and leaves no trace that the other comparison was ever made. |
| "arm B cleared the MDE too, so it also works" | Clearing the MDE asks whether an effect that size is worth it; the p-value asks whether it is there. A point estimate over the bar at p=0.25 has answered one question and not the other. |
| "extend it and keep peeking" | Fixed-horizon test. Peeking inflates false positives; re-plan with `power.py`. |

## RULE — red flags in your own draft

- Anything before the verdict on line 1 — especially a note that you followed the skill.
- A lift number and a failed validity gate in the same document.
- The word "but" between the verdict and a number.
- A verdict softened into a recommendation ("probably fine to ship").
- The ask's duration or "it won" framing repeated as established fact.
- A maturity share, or an SRM PASS, stated as fact when the as-of date or the ratio was assumed.
- A flat truncation gradient on a metric the timeline says must be truncated, reported as merely "immature" instead of as a data-integrity concern.
- A cited verdict from a run whose as-of date was `assumed: today`.
- An expected split that came from the observed counts.
- Reweighting, trimming or filtering proposed as a fix for an SRM.
- Silence about a second validity failure because the first already produced the verdict.
- A three-arm test written up as "treatment vs control", or an arm that appears in the SRM gate and nowhere else.
- A winning arm named without the arms it beat, or a "significant" claim with no threshold beside it when several arms were tested.

## References

| File | Read it for |
|---|---|
| `references/gates.md` | What each gate checks, the thresholds, the verdict list, the rationalization table |
| `references/maturity-and-duration.md` | MDE → sample size → weeks, and the N-day window rule |
| `references/output-templates.md` | The exact shape of the answer for each kind of ask |
