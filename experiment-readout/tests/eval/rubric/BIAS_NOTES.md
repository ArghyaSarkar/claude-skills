# Why the judge rubrics are shaped the way they are

Each control in `judge_*.v1.md` traces to a measured effect. Recording the
provenance matters because the alternative — a plausible-sounding rubric invented
from scratch — is exactly what this harness is supposed to replace.

## Decomposition into binary criteria, not a 0-4 holistic score

The arena's axes are 0-4. This harness never asks a judge for a 0-4 number.

- *From Holistic Evaluation to Structured Criteria: Rubrics Across the Evolving
  LLM Landscape* (arXiv:2606.08625) argues the problem with a single scalar is
  architectural, not accuracy: for any fixed criteria set there exist reward
  functions a scalar rubric cannot represent, and the judge must silently
  integrate dimensions it cannot show you. The paper reports three judges from
  three model families agreeing on every candidate rank under binary
  decomposition while disagreeing under holistic scoring.
- Anthropic's *Demystifying evals for AI agents* independently converges on
  "grade each dimension with an isolated LLM-as-judge rather than using one to
  grade all dimensions."
- HealthBench is the scaled precedent: tens of thousands of expert-authored
  binary criteria rather than Likert scales.

Consequence for the 12-point scale: the harness scores binary sub-criteria and
then *normalises* to the arena's 0-4. It never asks a model for a 4.

## Quote-or-fail

The strongest available control against both verbosity bias and fabricated
justification. *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena*
(Zheng et al., arXiv:2306.05685) measured verbosity bias by padding answers with
repetitive filler: judges were fooled in 91.3% of cases for two of the three
models tested. A judge that must paste the deciding span cannot be moved by
padding that contains no such span.

Caveat worth keeping in view: a 2026 multi-judge audit (arXiv:2606.19544) found
verbosity bias below 0.011 across 21 modern judges. Verbosity bias is
judge-and-prompt-dependent, so the 2023 numbers justify the control but do not
establish that our judge suffers it. That is a measurement we have not made.

## Reference-guided pointwise grading

MT-Bench's largest single quantified mitigation: on math questions GPT-4's
failure rate as a judge was 70% with a default prompt, 30% with chain-of-thought,
and 15% when given a reference answer to grade against. Our cases have checkable
ground truth, so every rubric is reference-guided.

Pointwise rather than pairwise for the scored axes: *Pairwise or Pointwise?*
(arXiv:2504.14716) found pairwise preferences flip in ~35% of cases under
adversarial distractor manipulation versus 9% for absolute scores. Pairwise is
used only in `judge_baseline_diff`, where comparison is the point.

## Position-bias controls

- Pairwise: MT-Bench found GPT-4 gave order-consistent verdicts in only 65.0% of
  cases when the two answers were swapped. `judge_baseline_diff` therefore runs
  both orders and counts a finding only on agreement.
- Rubric/Likert scoring has position bias *too*, in the order of the criteria
  themselves, with a model-specific direction (arXiv:2602.02219). Hence
  `criterion_order: SHUFFLE_PER_RUN` in both pointwise rubrics.
- arXiv:2606.19544 found judges with >0.95 test-retest reliability that still
  carried >0.10 position bias. Self-consistency does not imply low bias, so the
  two must be measured separately. **This harness does not yet measure position
  bias on its own judge** — see the limitations section of the README.

## Self-enhancement bias

MT-Bench: GPT-4 favoured its own outputs by ~10 points of win rate, Claude-v1 by
~25. G-Eval separately found a GPT-4 judge always preferred LLM-written summaries
to human-written ones even where humans preferred the human text. Anthropic's
`building_evals` cookbook states the mitigation plainly: use a different model to
judge than the one that produced the output. Hence
`judge_model_must_differ_from_subject: true`, enforced by `run_eval.sh`.

## Three runs, majority vote

*Rating Roulette* (arXiv:2510.27106) measured self-inconsistency across repeated
runs and found 5 runs added no signal over 3. Anthropic's skill-creator eval loop
independently uses 3 runs per trigger query. Three is the harness default.

The same paper found forcing temperature to 0 *degraded* judgment quality, so the
harness does not pin temperature to 0 and does not treat determinism as a proxy
for reliability.

## The abstain option

*Demystifying evals for AI agents* recommends giving judges an explicit
Unknown/abstain option. `UNKNOWN` is therefore a first-class verdict that routes
a cell to human review rather than being silently folded into FAIL. A grader
forced to guess produces a confident number that is worse than an honest gap.

## The domain-specific inversion: confidence is the worse answer

This is the one control not taken from the literature. Because the CSV carries no
extract date, the as-of date is genuinely unknowable from the input, so a
confident "0% of users are mature" is *less* correct than a conditional
statement. Judges are known to reward assertiveness, so bias control 2 in
`judge_output.v1.md` names this inversion explicitly and instructs the judge to
score the hedged answer higher on `O5_asof_calibration`.

Amendment 2 made this control MORE load-bearing, not less. Once the as-of
defaults to today, the maturity finding is PARTIAL (~78% mature), so the crisp
"0% are mature" answer is not merely overconfident — it is factually wrong, while
the correct answer is longer, hedged, and names a mechanism (differential
follow-up between cohorts). The ranking a fluency-seeking judge produces is
exactly inverted from the correct one, so `judge_output.v1.md` now spells out the
three-way ranking explicitly rather than describing the principle.

**This is the rubric's most fragile instruction.** It runs against the grain of
what judges do by default, and we have not yet measured whether the instruction
actually holds. Treat `O5` verdicts as the least trustworthy cells on the
scorecard until they have been validated against human labels via
`bin/agreement.py`.

## Chance-corrected agreement, not raw percent

arXiv:2606.19544 found raw percent agreement overstated Cohen's kappa by
33.8-41.3 percentage points across 21 judges on MT-Bench. `bin/agreement.py`
therefore reports kappa alongside raw agreement and the README instructs readers
not to quote the raw number alone. The commonly cited bar is kappa >= 0.7; below
that, suspect the rubric before the judge.

## Sources

| Source | Used for |
|---|---|
| Zheng et al., *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena*, arXiv:2306.05685 | position bias 65% consistency, verbosity 91.3% fooled, self-enhancement, reference-guided 70/30/15 cascade, few-shot 65->77.5% |
| *From Holistic Evaluation to Structured Criteria*, arXiv:2606.08625 | binary decomposition beats holistic scalars; HealthBench precedent |
| *Pairwise or Pointwise?*, arXiv:2504.14716 | 35% vs 9% flip rates; pointwise is more robust to distractors |
| *Am I More Pointwise or Pairwise?*, arXiv:2602.02219 | position bias inside rubric option ordering; permute criterion order |
| *Reliability without Validity*, arXiv:2606.19544 | kappa vs raw agreement inflation; consistency masks bias; minimum viable validation protocol |
| *Rating Roulette*, arXiv:2510.27106 | 3 runs suffices; temperature 0 can hurt |
| Liu et al., *G-Eval*, arXiv:2303.16634 | LLM-judge preference for LLM-written text |
| Anthropic, *Demystifying evals for AI agents* | isolated per-dimension judges; abstain option; pass@k vs pass^k; grade outcomes not paths; isolate trial environments |
| Anthropic, *Skill authoring best practices* | evaluation-driven development; baseline first; >=3 evals; test across models; description is the whole triggering surface |
| Anthropic `skill-creator` skill | 20-query trigger sets, near-miss negatives, 60/40 train/test split, 3 runs per query, blind A/B comparison, same-turn baseline |
| Anthropic cookbook `building_evals.ipynb` | judge should differ from subject model; CoT-then-verdict grader template |
| superpowers `testing-skills-with-subagents.md` | RED/GREEN/REFACTOR for documentation; pressure scenarios; verbatim rationalization capture; meta-testing |
