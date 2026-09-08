# Output templates

Cite as `references/output-templates.md § Template A/B/C`. Plain English explains; blocks
labelled **RULE —** and **DEFINITION —** are exact and are quoted as written, never
paraphrased.

Pick the template that matches the ask. `{...}` = fill from the engine payload. Never invent
a field the payload does not have.

## RULE — Universal rules, all templates

- **Line 1 is the verdict. Nothing precedes it.** No greeting, no "Readout complete", no "I
  read the rulebook first", no restatement of the ask, no preview of your steps. An LLM judge
  checks this mechanically: a correct readout with a two-word preamble scores below a worse one
  with none.
- **A qualifying clause does not unsay a false sentence.** If the first half of a sentence
  states something untrue of the data in hand, appending "…though in fact X" does not repair
  it — the reader has already banked the false claim, and a grep or a judge reads the halves
  separately. Rewrite the claim so it is true as stated, then qualify only what genuinely needs
  narrowing. This applies to every claim in a readout: a suppression declaration ("no p-value
  appears" when one does), a maturity statement, a gradient reading ("the values do not move
  with follow-up time" when they move, only too little), a verdict summary. Precision first,
  qualification second — never qualification as a repair.
- **Every number in prose carries an explicit format spec.** Never interpolate a numeric
  field raw: an unformatted float (`2.0938572760580003`) reads as false precision, and a
  formatted-string scan cannot see it. Choose the precision deliberately, per number.
- **Process evidence goes last**, in a trailing `Process & references` section — commands run,
  reference files consulted, citations. Every template below ends with it. Use that slot; do
  not invent one at the top.
- The gate table comes second, before any explanation.
- Report all three validity gates and every entry of `all_validity_failures`,
  `validity_not_assessable` **and** `validity_warnings`. A gate that could not be checked is not
  a pass: say "not assessable — <missing input>", never leave it looking clean, and never write
  it the same way as a suppressed conclusion gate (`NOT_RUN` = we chose not to conclude;
  `NOT_ASSESSABLE` = we could not check). A gate that WARNed is not a clean pass either: print
  it beside the verdict, because the conclusion gates ran under its assumption.
- Label every assumption (as-of date, assumed equal split) where it is used, not in a footnote.
- If `stopped_at` is not null: **no lift, no p-value, no CI, no guardrail delta, no direction,
  no "roughly", no "if it were fixed"** — anywhere, including headings, asides and appendices.
- Name the files you read and the command you ran.
- Cite `references/gates.md` for the gate whose failure you are explaining.

## Template A — full readout

Use this when the ask is "do the readout" or anything that wants a decision. It puts the
verdict first, the evidence second, and everything the reader might want to argue about after
that.

**DEFINITION —**

```
VERDICT: {verdict} — {one line, plain language, no hedge}

Inputs: {results path} ({n} rows), {brief path} (sealed {sealed date})
Command: python3 scripts/run_readout.py --results ... --brief ... [--asof ...] [--claimed-duration "..."]

| # | Gate | Status | What it found |
|---|------|--------|---------------|
| 0 | design_integrity | {PASS/WARN/FAIL} | {one line} |
| 1 | srm | {status} | {observed split vs designed, chi2, dof, p, alpha} |
| 2 | maturity | {status} | {window W, as-of + provenance, mature_share, cutoff, exposure span, gradient branch} |
| 3 | guardrail | {status or NOT_RUN} | {assessment + numbers, or "not run — {reason}"} |
| 4 | lift | {status or NOT_RUN} | {lift line, or "not run — {reason}"} |

Why this verdict
{2-5 bullets. One per validity failure and one per validity WARN, each naming the mechanism —
not just the number.}

Truncation gradient
{Lead with the MAGNITUDE — late-half vs early-half %, against the flat band — then the branch:
truncation confirmed / DATA INTEGRITY concern / not required / not assessable. Give corr + p
after it, explicitly labelled supporting context; never present r as the evidence for flatness.
Pooled across arms — say so. Report the TREND only; never quote the absolute cohort means,
which are metric levels and read as conclusion numbers. Omit the section only when the gate did not run.}

Claim check
{The duration/direction claims in the ask, each marked confirmed or contradicted by the data.}

Assumptions
{As-of date with its provenance (given / from data / from request / assumed: today), and for
`assumed: today` the note that the run is not reproducible without --asof; assigned ratio if
assumed; guardrail threshold if assumed. Each with the input that would settle it. Omit the
section only when there are none.}

What is NOT in this readout        <- include this section iff stopped_at is not null
No lift, p-value, confidence interval or guardrail verdict FOR THE PRIMARY METRIC OR THE
GUARDRAIL. {Reason in one sentence: on invalid data those numbers are uninterpretable, not
merely uncertain.} {If a cohort-trend p-value appears above, say so here and say why it is not
a conclusion: it pools across arms and carries no treatment comparison.}

To unblock — all of it, not just the first item
{One bullet per validity failure, with the concrete fix and who owns it.}
{Then the rerun size/duration from Template B if the ask implies a rerun.}

Process & references
- commands: {the exact run_readout.py / power.py invocations}
- consulted: references/gates.md § {sections}, references/maturity-and-duration.md § {sections},
  references/output-templates.md § Template A
```

**RULE — Scope the claim, do not sweep.** An absolute "no p-value appears anywhere" is false
the moment the gradient diagnostic prints one, and a reader who greps "p=" has then caught the
readout contradicting itself — which costs you the suppression guarantee exactly where it
matters. A narrow claim that is 100% true beats a sweeping one that is 99% true.

When `stopped_at` is null there is a real result to report, so the suppression section is
replaced by the numbers themselves.

**DEFINITION —**

```
Primary metric — {metric}
  control    n={n_b}  mean={mean_b}
  treatment  n={n_a}  mean={mean_a}
  abs diff   {diff}  (95% CI {ci_low} .. {ci_high})
  rel lift   {rel_diff as %}  (95% CI {rel_ci_low} .. {rel_ci_high})
  p-value    {p_value} (two-sided Welch, alpha=0.05)
  vs MDE     MDE={mde}; the effect {clears / does not clear} it
Guardrail — {metric}: {assessment}, diff {diff} vs threshold {threshold} (95% CI ...)
```

With more than one treatment arm the block below is replaced, not extended: there is no
single "treatment" row to write, and inventing one is the whole defect.

**DEFINITION —**

```
Primary metric — {metric}   ({k} treatment arms vs {control}; every arm is reported)
  {control}     n={n}  mean={mean}
  arm            n     mean    abs diff   rel lift   p-value   Holm thr   after Holm
  {arm}          ...                                                      {significant / not significant}
                 95% CI abs {ci_low} .. {ci_high}   rel {rel_ci_low} .. {rel_ci_high}
  MULTIPLICITY  {k} hypotheses about one control, corrected by Holm-Bonferroni at alpha=0.05
  vs MDE        MDE={mde}. Point estimate clears it: {arms}. Does not: {arms}.
Guardrail — {metric}, one comparison per treatment arm:
  {arm}  diff {diff}  (95% CI ...)  vs {threshold}  ->  {assessment}
```

The verdict names the arm. "SHIP" on its own is not an instruction anybody can follow when
there were three versions of it, so the winning arm — or arms, if several qualified — is
named in the same line as the verdict reason.

## Template B — sample size and duration

Use this when the ask is about planning rather than reading: how many users, how long, what
would a proper rerun cost.

**DEFINITION —**

```
To detect a {mde} {relative/absolute} change in {metric} at alpha=0.05, power=0.80:

  n per arm                {n}          ({n_total} total across {k} arms)
  baseline (control arm)   mean {mean}, sd {sd}
  enrolment                {exposure_days} days at {daily} users/arm/day
  maturation wait          {W} days (the metric's own window)
  TOTAL                    {total_days} days (~{total_weeks} weeks)

Command: python3 scripts/power.py --results ... --brief ...

How this compares to the run in hand: {observed n per arm}, shortfall {shortfall}.
Caveats: {sd from an immature column is a floor; traffic assumption; fixed horizon, read once}.
{If this is a rerun plan: the validity fixes that must land first, one bullet each.}

Process & references
- commands: {…}
- consulted: references/maturity-and-duration.md § Q1/Q2, references/output-templates.md § Template B
```

Cite `references/maturity-and-duration.md § Q1` for the chain and § Q2 for the window rule.
If the current data failed maturity, say plainly that the sizing is a floor.

## Template C — Slack message to the PM

Plain sentences, no markdown tables, no jargon without a gloss. Lead with the answer, name the
fix, keep it short. Never include a suppressed number, however friendly the framing.

**RULE — The first sentence is the bottom line — the same rule as line 1 of a readout.** No
warm-up, no "Hey! Quick update on the checkout test…", no thanks-for-your-patience, and **no
header or metadata line above it** — no "Experiment: checkout_flow_v2", no as-of line, no
"Readout summary:" label. If the experiment needs naming, name it inside the bottom-line
sentence. Any metadata worth sending (as-of date, files read) goes at the very bottom, after
the next step. The temptation is stronger here because the medium is social; the cost is that
the PM reads three friendly lines before learning the experiment is unusable. Warmth goes in
the wording of the bottom line, not in front of it. No process narration at all in a Slack
message: nobody in the channel needs to know which reference file you read.

**DEFINITION —**

```
{Verdict in one plain sentence: we can't use this experiment's data as it stands.}

{Reason 1, one sentence, mechanism first — e.g. the split came out X/Y against a designed
50/50, which at this sample size cannot happen by chance; that means assignment or logging
is broken, so the two groups aren't comparable.}

{Reason 2, if there is one — e.g. the metric is a 28-day measure and enrolment only ran N
days, so the window hasn't closed for anyone yet; the numbers in the file are partial counts.}

{Why I'm not sending a lift number: it would be uninterpretable, not just uncertain, and once
a number is in the thread it becomes the anchor.}

{What we do next: the fix, the rerun size and duration, and the date we'd read it.}

{One line acknowledging the cost, no apology for the verdict.}
```

**RULE — Tone rules:** no "unfortunately" stacking, no blame, no "the data is bad" without the
mechanism, no hedge that reopens the decision ("but if you need a directional read…").
If the PM asked a yes/no question, answer it in the first line.

## RULE — Anti-patterns: automatic fails

| Anti-pattern | Fix |
|---|---|
| Anything before the verdict on line 1 (greeting, "Readout complete", "rulebook read first") | Delete it. Move process evidence to the trailing section. |
| A false claim followed by a correcting clause ("the values do not move with follow-up time … though a small decline is present") | Rewrite the claim to be true as stated. A qualifying clause does not unsay a false sentence. |
| Verdict after the analysis | Verdict first, always. |
| "SRM detected, but the lift was +X%" | Delete the number. |
| "Directionally positive" on invalid data | Delete. Direction is a conclusion. |
| Only the first validity failure reported | Enumerate `all_validity_failures`. |
| A maturity share as bare fact | State the as-of date and its provenance alongside it. |
| A flat gradient reported as plain immaturity | Name the data-integrity concern; it is the stronger finding. |
| A cited number from a run with provenance `assumed: today` | Re-run with an explicit `--asof` and cite that. |
| Ratio described as 50/50 because that's what the file shows | Ratio comes from the brief; say if it was assumed. |
| MDE ignored once p < 0.05 | Compare the effect to the MDE before saying SHIP. |
| INCONCLUSIVE dressed up as a near-win | Report it as an unanswered question plus the rerun plan. |
| Verdict expressed as a recommendation to the PM | The verdict is the finding; the recommendation follows from it. |
