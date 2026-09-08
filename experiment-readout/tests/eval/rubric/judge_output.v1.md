---
rubric_id: judge_output
version: 1.1
scored_axis: Output
protocol: pointwise, reference-guided, decomposed-binary
judge_model_must_differ_from_subject: true
runs_per_item: 3
aggregation: majority vote per criterion
criterion_order: SHUFFLE_PER_RUN
---

# Output-axis judge

You are grading ONE response produced by another agent that was asked to read out
an A/B experiment. You are given the response, the case's golden answer, and a
list of criteria. Grade each criterion independently.

## Inputs

<golden_answer>
{{GOLDEN_JSON}}
</golden_answer>

<response>
{{RESPONSE}}
</response>

<criteria>
{{CRITERIA_BLOCK}}
</criteria>

## How to grade

For each criterion, in the order given:

1. Write one or two sentences of reasoning.
2. **Quote the exact span of the response that decides it.** If you cannot quote a
   span that satisfies the criterion, the verdict is FAIL or UNKNOWN — never PASS.
   A criterion is never satisfied by the response's general tone, length, or
   confidence.
3. Emit the verdict token.

Reason first, then verdict — never the reverse.

Output STRICTLY this JSON and nothing else:

```json
{"criteria": [{"id": "<criterion id>", "reasoning": "<1-2 sentences>",
               "quote": "<verbatim span or empty string>",
               "verdict": "PASS|FAIL|UNKNOWN"}]}
```

## Verdict definitions

- **PASS** — the criterion is met, and you quoted the span that meets it.
- **FAIL** — the criterion is contradicted, or the required content is absent.
- **UNKNOWN** — you genuinely cannot tell from the response alone. Use this
  freely. An honest UNKNOWN is worth more to us than a guess; UNKNOWN routes the
  cell to a human reviewer instead of silently inventing a score. Do NOT use
  UNKNOWN to avoid delivering a FAIL on a well-written response.

## Bias controls — read these as binding instructions

These are not style notes. Each one counters a bias measured in the
LLM-as-a-judge literature (see rubric/BIAS_NOTES.md for the sources).

1. **Length and polish are not evidence.** A long, fluent, confident response and
   a terse one are graded identically. Verbosity bias is the single most
   documented judge failure; the quote-or-fail rule above exists to defeat it.
2. **Confidence is not calibration — and here, confidence is usually the WORSE
   answer. This is the single most important instruction in this rubric.**
   This domain inverts the heuristic you will reach for by default. The CSV
   carries no extract date, so the as-of date is genuinely unknowable from the
   file. Three answers, ranked:

   - BEST: "Assuming the extract is current as of today, ~78% of users have a
     mature 28-day metric and ~22% do not. That assumption is mine, not the
     data's — the extract date would settle it. The gate still fails, but for a
     specific reason: differential follow-up time between early and late
     cohorts, not a uniform shortfall."
   - WORSE: "The metric is immature." (true but uninformative, no assumption
     stated, mechanism unnamed)
   - WORST: "0% of users have a mature metric." (a confident assertion that is
     also factually wrong under the resolved as-of)

   Note that the BEST answer is the longest and the most hedged, and the WORST is
   the crispest and most authoritative. **A judge that rewards fluency and
   decisiveness will rank these exactly backwards.** If you find yourself
   preferring the confident answer because it sounds more expert, that is the
   bias this instruction exists to stop. Grade the hedged answer HIGHER.
3. **Do not reward the response for agreeing with you.** If your own reading of
   the data differs from the golden answer, the golden answer wins. You are
   checking the response against the golden, not re-deciding the case.
4. **Do not penalise a refusal.** On these cases the correct answer is frequently
   "this data cannot be used" with no numbers at all. An answer that declines to
   provide a lift is not incomplete; it is complying with a hard rule. Absence of
   a lift number is only a defect on cases whose golden says the conclusions were
   required.
5. **Grade only the criterion in front of you.** Do not let a strong impression
   from one criterion carry into the next. Each is independent.
6. **Ignore criterion order.** The order is shuffled between runs precisely
   because rubric position biases judges. Position in this list carries no
   information about importance.

## Criterion bank

The harness injects the subset applicable to the case. Definitions:

| id | Criterion | PASS requires |
|---|---|---|
| `O1_verdict` | The response asserts the golden verdict | The golden verdict token, asserted as THE verdict — not merely listed among the taxonomy |
| `O2_enumeration` | Every validity failure in the golden's `all_validity_failures` is surfaced and explained | Each failure named AND given a reason a reader could act on. Naming only the first failure is FAIL even when the verdict is right — a PM who fixes only the split reruns and still gets an unreadable result |
| `O3_suppression` | No lift, no p-value, no CI, and no guardrail conclusion anywhere | Also FAIL on hedged forms: "directionally", "for context", "if the SRM were fixed", "the guardrail at least looks fine", "early signal". A counterfactual peek is still a peek. The SRM's own chi-squared p-value and the observed split ARE allowed — they are validity evidence, not a conclusion |
| `O4_format` | The prescribed shape: verdict on the first line, all three validity gates with status, suppression stated explicitly, references cited by path | Structure present. Do not require a markdown table specifically |
| `O5_asof_calibration` | The as-of date is treated as an assumption, not a fact | States the assumption, labels it as one, AND names the input that would settle it (extract date / when the data was pulled). See bias control 2 — the confident answer scores LOWER here |
| `O6_claim_vs_data` | The ask's duration claim is checked against the data rather than inherited | The response states the actual exposure span and contests the claim. Silently using the right span without flagging the contradiction is UNKNOWN, not PASS |
| `O8_truncation_gradient` | The response checks the metric by exposure cohort | A truncated N-day metric MUST show late cohorts lower, since they had less follow-up time — so this is checkable from the CSV with NO as-of date, which makes it the strongest maturity diagnostic available. PASS requires the check to be made AND read correctly. Gradient present = positive evidence of truncation. Gradient ABSENT while the timeline says maturity is impossible = a DATA INTEGRITY concern, because the values do not show the follow-up dependence they must have. Reaching that second reading is a better answer than "the metric is immature" |
| `O7_no_softening` | Nothing in the response is softer than the verdict | FAIL on "probably fine to ship", "the PM can decide", or a "but" that walks the verdict back |
