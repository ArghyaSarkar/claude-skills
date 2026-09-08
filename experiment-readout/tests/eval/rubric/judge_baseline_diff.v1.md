---
rubric_id: judge_baseline_diff
version: 1.0
scored_axis: baseline delta (diagnostic, not part of the 12 points)
protocol: PAIRWISE, position-swapped
runs_per_item: 2   # once per position order, A/B then B/A
aggregation: agreement required; disagreement is recorded as TIE
---

# Baseline-diff judge (RED/GREEN adjudication)

Two responses to the same ask. One came from an agent with a skill loaded, one
without. **You are not told which is which, and the order is randomised.**

Your job is not to pick the nicer answer. It is to answer specific factual
questions about each, because the value of the skill is measured by which
failure modes disappear.

## Inputs

<response_A>
{{RESPONSE_A}}
</response_A>

<response_B>
{{RESPONSE_B}}
</response_B>

<golden_answer>
{{GOLDEN_JSON}}
</golden_answer>

## Questions — answer for A and for B independently

| id | Question |
|---|---|
| `B1_accepted_claim` | Did it accept the ask's duration claim ("finished 4 weeks", "ran a month") without checking it against the data? |
| `B2_peeked` | Did it report a lift, p-value, CI, or a hedged directional read, on data the golden marks invalid? |
| `B3_found_first_defect` | Did it find the FIRST validity defect the golden lists? |
| `B4_found_all_defects` | Did it find EVERY validity defect the golden lists? |
| `B5_asserted_unknowable` | Did it assert an as-of date, or a maturity share, as fact when the CSV cannot establish it? |
| `B6_verdict_correct` | Did it reach the golden verdict? |
| `B7_checked_gradient` | Did it check the metric by exposure cohort at all? (The unaided agent is unlikely to; this is a sharp, binary gap.) |
| `B8_post_hoc_subset` | Did it drop the immature users and read the remainder? (A pre-registration violation dressed as diligence, and a very common unaided move.) |

Output STRICTLY:

```json
{"A": {"B1_accepted_claim": true, "B2_peeked": false, "...": null},
 "B": {"...": null},
 "notable_rationalizations": ["<verbatim quote of any excuse for skipping a check>"]}
```

`notable_rationalizations` is the most valuable field in this rubric. Quote
VERBATIM any sentence in either response that talks itself out of a check —
"the PM is excited so let me just check the lift", "it ran four weeks so the
data should be fine", "directionally this looks positive". These quotes are the
RED-phase evidence the harness exists to capture; do not paraphrase them.

## Position-bias control

This rubric is run TWICE per pair with A and B swapped. A finding counts only if
both orders agree; disagreement is recorded as TIE and flagged. Position bias
flips more than a third of pairwise verdicts in published measurements, so a
single-order pairwise result is not trustworthy on its own.
