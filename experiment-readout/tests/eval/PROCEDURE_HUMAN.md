# Semi-automated steps

Everything here needs either spend, a judge model, or a human. Each step states
exactly which, gives a copy-pasteable command, and names where the result is
recorded. Nothing in this file is inferred by the harness — a step not run stays
visibly blank on the scorecard rather than being filled with a guess.

---

## Step 1 — Live runs (MACHINE, costs money)

```bash
cd /Users/sarkararghya/.claude/skills/experiment-readout/tests/eval

./run_eval.sh                                # dry run: verify cases, print plan, spend nothing
./run_eval.sh --live --smoke                 # 1 case, both arms  (~2 runs, ~2 min)
./run_eval.sh --live --cases --baseline       # all 12 cases, both arms (24 runs, ~30 min)
./run_eval.sh --live --triggering --runs 3    # 20 prompts x 3 (60 runs, ~75 min)
./run_eval.sh --live --all --runs 3           # everything
```

Bound the spend per run with `EVAL_BUDGET_USD` (default 0.75):

```bash
EVAL_BUDGET_USD=0.40 ./run_eval.sh --live --cases
```

Recommended: add `--isolate`. It runs against a config dir containing ONLY this
skill, which matches the arena more closely than this machine's ~20 installed
skills all competing for the trigger.

Also run at least once per model you care about (`--model sonnet`, `--model
opus`). Anthropic's skill-authoring guidance is explicit that a skill sufficient
for Opus can under-specify for Haiku, so a single-model result does not
generalise.

---

## Step 2 — LLM judge (MACHINE + judge model, costs money)

Only for cells the machine checks left UNKNOWN.

```bash
RUN=runs/<run-id>
/usr/bin/python3 bin/make_judge_prompts.py --run-dir $RUN --runs 3

# Judge with a DIFFERENT model from the one under test (self-enhancement bias).
for f in $RUN/judge_prompts/*.md; do
  claude -p --model sonnet --no-session-persistence < "$f" \
    > "${f%.md}.verdict.json"
done

/usr/bin/python3 bin/apply_judge.py --run-dir $RUN
```

`apply_judge.py` majority-votes across the 3 runs. A criterion with no majority
stays UNKNOWN and moves to the human queue — a split judge is a finding, not
something to round away.

---

## Step 3 — Validate the judge, Phase 1: planted probes (MACHINE, 0 human minutes)

**Do this before spending any human time.** 12 planted responses with known
correct labels (`cases/judge_probes.json`), balanced 6 PASS / 6 FAIL, stacked on
`O3_suppression` and `O7_no_softening` — the criteria where the judge is asked to
prefer the *more hedged* answer and is therefore most likely to fail.

Because the truth is known, this measures the judge's **sensitivity and
specificity directly, with no human in the loop**. If it misses an easy planted
leak it is unusable, and no human minutes should be spent on it at all.

```bash
/usr/bin/python3 bin/label_batch.py --build-probes
cd runs/probes/judge_prompts
for f in p*.md; do
  # Pipe via stdin. Passing an ~11KB rubric as a positional argument fails
  # SILENTLY and writes an empty file -- that happened on all 12 the first time.
  claude -p --model sonnet --no-session-persistence < "$f" > "${f%.md}.verdict.json"
done
cd ../../..
/usr/bin/python3 bin/label_batch.py --score-probes
```

**Gate — the judge is usable only if both hold:**

| Metric | Bar | Why this bar |
|---|---|---|
| sensitivity on easy+medium leaks | **6/6, i.e. 100%** | Near-binary, not a rate. Missing an obvious leak on the highest-stakes criterion disqualifies the judge outright. |
| specificity | **>= 5/6** | Over-flagging is costly too: it penalises the skill for correctly refusing, and three probes (p08-p10) are exactly the false positives the machine checks used to emit. |

`p06` is the probe that matters most — an oblique leak ("the direction won't
surprise you") carrying no number and no hedge keyword. The machine check
provably cannot catch it (README limitation 6). If the judge misses it too, that
failure mode is undetected by anything in this harness, and Step 4 becomes
mandatory rather than optional.

---

## Step 4 — Validate the judge, Phase 2: human labels (HUMAN, ~15 min)

Only if Phase 1 passed. Phase 1 proves the judge on constructed cases; this
estimates agreement on the **real** distribution, where truth is unknown.

```bash
RUN=runs/n5
/usr/bin/python3 bin/label_batch.py --build-human --run-dir $RUN --max-items 16
open $RUN/human_batch.md          # blind: no judge verdict, no machine note
/usr/bin/python3 bin/label_batch.py --label --run-dir $RUN   # p/f/u per item
/usr/bin/python3 bin/agreement.py --run-dir $RUN
```

**16 items, roughly 45-75 seconds each, so 12-20 minutes.** The batch is blind by
construction — showing the judge's verdict first would anchor the labeller and
destroy the independence the whole number rests on.

### What kappa to accept, honestly

**A kappa precise enough to distinguish 0.6 from 0.8 needs ~100+ items.** At 16
items the 95% CI is roughly +/- 0.3, so a point estimate of 0.75 is compatible
with anything from 0.45 to 1.0. Nobody should sit through 100 items, so:

| Reading | Interpretation |
|---|---|
| Phase 1 gate passed **and** kappa >= 0.6 on 16 items | **judge is usable.** Phase 1 is the load-bearing evidence; this kappa is a directional confirmation that nothing pathological happens on real data. |
| kappa 0.4-0.6 | usable only for triage. Judge verdicts stay advisory and the leak check stays a human step. |
| kappa < 0.4 | **fix the rubric criterion, not the judge.** If two careful readers cannot agree using it, the criterion is ambiguous. |
| kappa UNDEFINED | expected if every real cell is PASS. `agreement.py` reports this rather than printing a fake number. It is why Phase 1 exists. |

I would not claim ">= 0.7 established" from 16 items and the harness does not
print such a claim. The honest summary is: **Phase 1 sensitivity/specificity is
the primary evidence; the 16-item kappa is a directional check.** An honest
directional read beats a fake kappa.

Label the items the judge got *right* as well as the suspicious ones — labelling
only suspected disagreements inflates apparent disagreement.

---

## Step 5 — Meta-testing when a case fails (HUMAN, ~5 min per failure)

From superpowers `testing-skills-with-subagents`. When the agent had the skill
and still failed, ask it directly, in the same session:

> You had the experiment-readout skill available and still [reported the lift on
> an invalid split / accepted the "4 weeks" claim]. How could that skill have
> been written differently to make it unambiguous that this was not acceptable?

Three answer shapes, three different fixes:

| Answer | Diagnosis | Fix |
|---|---|---|
| "The skill was clear, I chose to ignore it" | not a documentation problem | strengthen the foundational principle; add "violating the letter is violating the spirit" |
| "The skill should have said X" | documentation gap | add their wording verbatim to the refusal table |
| "I didn't see section Y" | information architecture | move it earlier / make it more prominent |

Record the verbatim answer in `runs/<id>/meta_tests.md`. These answers are the
REFACTOR-phase input, and paraphrasing them loses the signal.

---

## Step 6 — `claude plugin eval` (BLOCKED on this machine)

Gated. Verified:

```
$ claude plugin eval . --runs 1
`plugin eval` is currently in early access
```

When the gate lifts, the generated suite runs the same cases with a native
ablation arm:

```bash
claude plugin eval /Users/sarkararghya/.claude/skills/experiment-readout \
  --eval-dir tests/eval/plugin-eval-suite --ablation with-without --runs 3
```

Regenerate it after any golden change: `/usr/bin/python3 bin/gen_plugin_eval_suite.py`
