# Eval harness — experiment-readout skill

This directory answers "**does this skill behave well as a skill?**" — whether it fires on
the natural ask, visibly follows its own ordered method, and produces the right answer when
checked against a known-correct one (a *golden*). That is a different question from "do its
Python functions return the right numbers", which `tests/unit/` owns.

Scores land on the **same 12-point scale the arena uses** (Triggering 4 + Process
4 + Output 4) so a run here is directly comparable to an arena score.

---

## Quick start

```bash
cd /Users/sarkararghya/.claude/skills/experiment-readout/tests/eval

./run_eval.sh                             # dry run: regenerate + verify cases, print plan, spend nothing
./run_eval.sh --live --smoke              # smallest real measurement (~2 runs, ~2 min)
./run_eval.sh --live --all --runs 3       # full harness
./run_eval.sh --score-only <run-id>       # rescore existing transcripts, free
```

A dry run deliberately reports **no score at all**. The 12-point scale requires
observing an agent, so there is nothing honest to print without a live run.

---

## What the three axes measure, and who measures them

| Axis | Points | Decided by | How |
|---|---|---|---|
| **Triggering** | 4 | **machine** | a `Skill` dispatch seen in the machine-readable transcript (`stream-json`) of a fresh `claude -p` session |
| **Process** | 4 | **machine** (4 signals), judge as second reader | tool trace: script invocation, reference reads, gate ordering, absence of improvised statistics |
| **Output** | 4 | **machine** (6 of 8 criteria), **judge** (2), **human** confirms the leak check | text and number checks against `cases/*/golden.json`, plus the judge for the criteria that need reading rather than matching |

### Triggering — how the harness observes firing, and what that is worth

`bin/run_one.sh` starts a **fresh non-interactive session** per prompt. Skill
metadata is pre-loaded exactly as in an interactive session and nothing in the
prompt names the skill, so a dispatch is genuine unprompted triggering.

`lib/trace.py` records **which of three channels** produced the observation, and
the confidence travels with the result to the scorecard:

| Channel | Confidence | What it proves |
|---|---|---|
| `DIRECT` — a `Skill` tool_use block naming experiment-readout | **high** | the runtime dispatched the skill. This is proof. |
| `FILEREAD` — the skill's `SKILL.md`/`references/`/`scripts/` were touched | medium | the body was almost certainly loaded, but a curious agent could read those files without a dispatch |
| `TEXTUAL` — the final message merely names the skill | **low** | a proxy only. An agent that knows the vocabulary can produce this without the skill. Never sufficient alone. |

**Honest limit:** every observation so far has been `DIRECT`, which is the strong
case. But the harness cannot distinguish "the description matched" from "the
model would have done this anyway" — that is what the **baseline arm** is for, and
why a with-skill number alone is close to meaningless.

Set design follows Anthropic's `skill-creator`: 20 prompts, 10 that should fire and 10
**near-misses** that deliberately reuse the skill's own trigger words but should not fire,
split 60/40 into train and test. **Read the held-out (`test`) rate, not the overall one** —
the train prompts are the ones the description was tuned against, so a good score on them
partly measures the tuning rather than the description.

### Process — four signals, one point each

Mirrors the arena's "one point per step-quality signal" literally rather than
blending into one score.

| Signal | Machine-observable because |
|---|---|
| `P1_gate_order` | validity findings appear in contract order in the response |
| `P2_scripts_invoked` | a Bash call actually ran `run_readout.py` / `power.py` |
| `P3_references_cited` | reference files were Read **and** named by path in the answer |
| `P4_no_improvisation` | no hand-rolled t-test/chi-square outside the skill's scripts |

### Output — eight binary criteria, normalised to 4 points

The arena does not say how its 4 Output points break down, so the harness splits Output as
finely as the research supports and rescales the result to 4. The eight: verdict,
enumeration of **every** validity failure, suppression, format, as-of calibration,
claim-vs-data, no-softening, truncation gradient.

`O3_suppression` is the highest-value check: when any validity gate fails, **both
the lift and the guardrail conclusion** must be absent, hedges included. It is
implemented as a hard machine check with a **per-case numeric allowlist** — the
SRM's own chi-squared p-value and the observed split are legitimate and must not
be flagged, so "contains a p-value" cannot be the rule.

---

## Reading the scorecard

```
  case                      trig  proc   out  total  note
  c03_srm_and_maturity      4.00  4.00  3.50  11.50
```

- `-` in a column means **not measured**, never zero.
- `PARTIAL` means at least one axis was not measured; the total is not comparable.
- **UNGRADED CELLS** lists criteria excluded from the denominator. A score
  computed from 3 of 8 criteria is reported as such rather than silently scaled.
- **DIAGNOSTICS** holds real defects the arena does not score — most importantly
  the false-positive firing rate. These are deliberately kept OUT of the 12
  points so the number stays comparable. **The measured over-trigger is an
  accepted decision, not an open bug — see `DECISIONS.md` D1 before changing the
  description.** In short: missing the natural ask costs 4 of 12 points, while
  firing on an unrelated count query costs nothing the arena measures, because
  the arena asks one hidden question of the *same theme*. Recall is worth
  everything; precision is worth approximately zero. That trade is
  **arena-specific and inverts for daily team use**, where a spurious full gated
  readout on a `SELECT COUNT(*)` trains people to disable the skill — a
  production fork should tighten the description and accept some missed obliques,
  which is the opposite call.
- A `FATAL_leak` diagnostic means a suppressed conclusion was reported on invalid
  data. Treat that as disqualifying regardless of the total.

`UNKNOWN` is a first-class verdict, not a disguised FAIL. It routes a cell to the
judge or a human instead of guessing.

---

## The baseline arm — show it fails WITHOUT the skill first

Required, not optional. A with-skill score means nothing on its own: it cannot tell you
whether the skill did the work or the model would have got there anyway. So the harness
runs the identical prompt again with `--safe-mode`, which turns off every customization,
skills included.

`--safe-mode` is blunter than ideal — it also drops CLAUDE.md and hooks, so the
arms differ by slightly more than skill availability. The narrower alternative
(`--disable-slash-commands`) was rejected because it was not verified to remove
the description from the system prompt, and a baseline that still sees the
description is not a baseline.

**If the baseline does not fail, say so.** For those cases the skill is not
demonstrably necessary, and the scorecard prints that under
`!! BASELINE DID NOT FAIL on:`. That is a real finding about the skill, not a
harness bug.

### Measured baseline result (1 case, central, n=1)

Without the skill, on `c03_srm_and_maturity`, the agent:

- **found both defects** (SRM and maturity) — detection was not the failure
- **leaked the lift**: led with a table containing `+3.18%`, a 95% CI, and
  `p=0.072`, before the blockers section
- **gave a guardrail all-clear**: "The guardrail passes cleanly"
- **ran the forbidden post-hoc subset**: "Restricting to the mature cohort only
  (n=2,337) gives +3.92%, p=0.051" — the exact
  "drop the immature users and read the rest" move the skill's refusal table names
- **produced no verdict token** at all
- **did not check the "4 weeks" claim** against the 14-day span

So the unaided failure mode is not blindness, it is **indiscipline**: it finds the
problems and reports the number anyway. That is precisely what the skill's
suppression rule exists to prevent, and it is why `O3_suppression` carries the
most weight in practice.

---

## Repeated-run result (n=5, measured)

`runs/n5` — four cases x 5 runs = 20 live sessions, chosen so all four carry
`O5_asof_calibration` and three carry the format and hedge criteria.

| case | Process | Output | total |
|---|---|---|---|
| `c02_maturity_only` | 4.00 | 4.00 | 8.00 |
| `c03_srm_and_maturity` | 4.00 | 4.00 | 8.00 |
| `c10_slack_to_pm` | 4.00 | 4.00 | 8.00 |
| `c12_truncation_gradient` | 4.00 | 4.00 | 8.00 |

(8.00/12 because Triggering was not re-measured in this run; the two scored axes
are at ceiling. Add the separately-measured Triggering to compare with the arena.)

**Every graded criterion is BINDING at 5/5** — it held in all five runs, not just most of
them — across all four cases, including the two the coordinator flagged: `O4_format` (the
verdict-on-first-line drift) and `O5_asof_calibration`. Two cells are thinner than they
look, and the scorecard says so: `c03`'s `O3_suppression` is graded on 2 of the 5 runs and
`c10`'s `O4_format` on 3 of 5 — the rest routed to the judge, as designed. `O7_no_softening`
is UNGRADED by construction: it is judge-only.

### What raising the reps actually bought: six harness bugs, zero skill bugs

This is the honest headline. Every intermittent failure at n=5 turned out to be a
brittle check, not a wobbly skill:

| Symptom at n=5 | Real cause |
|---|---|
| `c12` `O5` 2/5 "NOT BINDING" | "Partial maturity, **not zero** maturity" read as a zero claim (negation blind) |
| same | "a read at 8**0%** mature" matched as "0% mature" (no digit boundary) |
| same | "162**0/1380**" matched as "0/1380" (no digit boundary) |
| `c10` `O4` 0/5 | readout format contract applied to a **Slack** message, whose template forbids the gate table it demanded |
| `c10` `O4` still failing | an analyst-facing table under an unanticipated heading attributed to the PM-facing body |
| `c10` `P1` 0/5 | `srm` phrase list was jargon-only, so a prose message saying "the split came out 1,620 vs 1,380 against a designed 50/50" placed the SRM discussion 2,000 chars late |

Two structural fixes came out of this: the format contract is now **per-template**
(A/B/C) rather than shared, and Template C's boundary checks only run when the
draft is fenced — otherwise they return UNKNOWN and go to the judge rather than
guessing. See `DECISIONS.md` D7.

---

## Judge validation — Phase 1 result (measured)

Run against the 13 planted probes in `cases/judge_probes.json` (known labels),
judged by Sonnet, which is not the model under test:

| Metric | Result | Gate | Verdict |
|---|---|---|---|
| sensitivity (planted leaks caught) | **6/6** | 100% required | **PASS** |
| specificity (clean responses passed) | **6/7** | >= 5/6 required | **PASS** |

**The judge earns its place.** The result that matters most is `p06` — an oblique
leak reading "No lift, no p-value... The direction, I suspect, will not surprise
you." It carries no number and no hedge keyword, so the machine check provably
cannot catch it (limitation 6). The judge caught it, with the deciding span
quoted. That is the clearest available evidence that the judge adds something the
regex cannot, rather than expensively duplicating it.

The single miss, `p10`, turned out to be a **defect in the probe, not the judge.**
The probe cited "a 3% effect", the brief's MDE is 3%, and this case's realised
lift is ~3.18% — so the phrase is genuinely ambiguous, and the judge's reasoning
named that coincidence explicitly. `p13` is the disambiguated version ("the
brief's stated 3% MDE"), and the judge PASSES it. A grader that fails the
ambiguous phrasing and passes the explicit one is discriminating correctly.

Carry-forward caution: because the MDE and the realised lift are numerically close
in `c03`/`c12`, a legitimate MDE citation is hard for *any* grader to distinguish
from a lift leak on those cases. Read their O3 verdicts with that in mind.

Phase 2 (human labels on real cells, for a kappa on the real distribution) has
**not** been run — see `PROCEDURE_HUMAN.md` step 4 for the batch and the honest
threshold.

---

## Cases

12 cases in `cases/`, generated deterministically by `lib/gencases.py`. Each is
built so the **method** is what is tested, because the arena runs a hidden dataset
of the same theme.

They come in **matched pairs that differ in exactly one fact a gate cares about**. An agent
that gives the same answer every time therefore scores near zero, because in each pair one
member wants the opposite answer:

| Pair | Differs only in | Defeats |
|---|---|---|
| `c02` vs `c03` | the arm split | an agent that only knows the SRM trick |
| `c03` vs `c11` | seal date | "reports the first defect it finds" |
| `c04` vs `c05` | `cancel_rate` +1.5pp | "significant primary, therefore ship" |
| `c04` vs `c06` | effect size vs MDE | "significant, therefore ship" |
| `c06` vs `c07` | CI width vs MDE | "not significant, therefore no effect" |
| `c03` vs `c12` | truncation gradient present/absent | "immature" as a complete answer |

`c04_clean_ship` is the **anti-degenerate case**: every gate passes and the result
is a real win. Without it, a skill that blocks everything scores 100%.

`c03` is the **central case** — it reproduces the real arena dataset's defect
structure (catastrophic SRM *and* partial maturity) on the verbatim natural ask.

### Golden answers are independent of the code under test

`cases/*/golden.json` is verified by `lib/refcalc.py`: a deliberately separate, simpler
implementation that approximates the same statistics with `math.erf`, and never imports the
skill's `scripts/gates.py`. A golden computed by the code being tested only proves the code
agrees with itself.

Because `refcalc` is an approximation, `lib/verify.py` enforces **wide margins** on
every case (p < 0.005 where significance is needed, p > 0.20 where null,
rel_lift at least 1.5x or at most 0.6x the MDE). `bin/gen_cases.py` exits non-zero
if a case cannot clear them, so a marginal case can never be silently used. This
caught three real fixture defects during construction: two under-powered cases, and
`c07` silently flipping verdict because an unlucky draw dragged its CI under the MDE.

### Reproducibility caveat — the as-of default

Under contract v1.2 the as-of date defaults to the **system date**. Golden
maturity shares therefore depend on "today". `REFERENCE_TODAY` in
`lib/gencases.py` pins it (`2026-08-21`) and every golden records it. If you run
the eval much later, regenerate the goldens. The graded dimension is always the
**method** — partial maturity, differential follow-up, the gradient reading — never
the exact percentage.

---

## `claude plugin eval`

**Gated on this machine.** Verified:

```
$ claude plugin eval . --runs 1
`plugin eval` is currently in early access
```

It would be the better host. It builds in the with-and-without comparison this harness has
to hand-roll (`--ablation with-without`), repeated runs per case, `tool_used: Skill` graders
that see a dispatch directly, and a documented result JSON. So the harness emits a
**forward-compatible suite** at `plugin-eval-suite/`, generated from the same goldens by
`bin/gen_plugin_eval_suite.py`. It has **never been executed** — expect to fix schema
details on the first real run.

---

## Limitations — what this harness cannot tell you

Listed roughly in decreasing order of how much they should worry you.

1. **Run counts are adequate for the four re-run cases and thin everywhere else.**
   `runs/n5` carries 5 runs per cell for `c03`, `c12`, `c10` and `c02`, which is enough to
   see whether a rule holds every time (one failure out of five shows up as an 80% rate).
   The other eight cases were run once each. So a pass rate is only worth quoting for those
   four; for the rest, one green run shows the thing can happen, not how often. Anthropic's
   worked example is why: a rule that really holds 75% of the time still has only a ~42%
   chance of passing three runs in a row, so one green run is not evidence. And with only
   five runs, any rate that is neither 0/5 nor 5/5 has a very wide margin of error — the
   DRIFT and NOT-BINDING bands in `lib/aggregate.py` are there to point attention, not to
   carry statistical weight.

2. **The judge is validated only against constructed probes, not real data.**
   Phase 1 of `PROCEDURE_HUMAN.md` runs the judge against 13 planted responses whose
   correct labels we already know, and reports how many leaks it caught and how many clean
   answers it let through — see the recorded result above. That is real evidence, but it is
   evidence on cases *we wrote*, which are tidier than live output. No human labels on real
   cells exist yet, so `bin/agreement.py` has still never produced a kappa — a single number
   for how far two graders agree beyond what chance alone would give — on the real
   distribution. The most fragile criterion remains `O5_asof_calibration`, which asks the
   judge to score the *more hedged* answer higher, against the grain of what judges do by
   default. And a meaningful kappa needs roughly 100+ items, where 16 is what a person will
   actually sit through — so the honest position is that Phase 1 is the load-bearing
   evidence, and any kappa we get is directional only.

3. **We have not measured how much our own judge is swayed by ORDER.** A judge shown two
   answers can favour whichever came first, regardless of content. The rubrics shuffle the
   criterion order and the pairwise rubric swaps the two positions, but we have not run the
   AB/BA test — the same pair shown in both orders — to measure what is left. Published work
   found judges that gave the same verdict on the same input over 95% of the time and were
   still swayed by position more than 10% of the time, so being self-consistent would not
   reassure us even if we had measured it.

4. **`claude -p` is not the arena.** One user turn, no conversational history,
   permissions pre-granted, and by default this machine's full skill set
   competing for the trigger. `--isolate` closes the last gap; the others remain.

5. **The baseline arm changes more than one variable.** `--safe-mode` removes
   CLAUDE.md and hooks along with skills. The measured baseline gap is therefore
   an upper bound on the skill's contribution.

6. **Leak detection will always miss some leaks and flag some non-leaks.** The machine
   check is built to be sure when it fires, and sends anything ambiguous to `UNKNOWN`
   instead of guessing — but a hint oblique enough ("the direction won't surprise you")
   carries no number and no keyword, so no pattern here can catch it. **This is why Step 3
   of `PROCEDURE_HUMAN.md` is a human step and should not be skipped.**

7. **Only 12 cases, all synthetic, all from one generator.** They encode *our*
   model of the traps. A trap neither we nor the contract anticipated is invisible
   to this harness, and the arena's hidden dataset may well contain one. Passing
   here is not evidence of passing there.

8. **Format checks are shallow, and Template C's are shallower still.**
   `check_format` confirms the prescribed pieces are *there*. It says nothing about whether
   the report reads well or whether the gate table is accurate. Two specific gaps on the Slack
   template: (a) the bottom-line check tests that the answer appears in the first
   *line*, not that nothing precedes it within that line — so "Wanted to get to
   you before this goes wider: we can't use the data" passes, though Template C
   forbids the warm-up clause; (b) the PM-facing draft can only be located when
   the agent fences it, so unfenced drafts return UNKNOWN and go to the judge
   rather than being guessed at. Heuristic boundary-finding was tried and
   abandoned — it mis-attributed an analyst-facing gate table under an
   unanticipated heading ("## What's behind the draft") to the message body and
   failed all five runs of a correct case.

9. **No cost or latency measurement.** A skill that scores 12/12 by reading every
   reference file on every invocation may be too slow or expensive in practice.
   Nothing here would notice.

10. **Triggering is measured against the description as written today.** The
    description was iterated during construction of this harness; earlier
    triggering observations were made against earlier text and are not
    comparable across edits.

11. **Repeated runs of one prompt are correlated, not independent trials.** The
    n=5 rates in `runs/n5` are five samples of the same prompt against the same
    model, so they measure *within-prompt* stability. They say nothing about
    robustness to a differently-worded ask, which is what the arena's hidden
    question actually tests. Five greens on one prompt is weaker evidence than one
    green on each of five prompts, and this harness has the former.

12. **A result of 0% or 100% is more likely a broken instrument than a real finding.**
    Phase 1 first reported `sensitivity 0/6`, which looks exactly like a judge that has
    completely failed, and would have been written up as one. The real cause was that an
    11KB prompt passed as a shell argument fails silently (see `DECISIONS.md` D5). Nothing
    in the harness can spot that class of error by itself, so any 0% or 100% result should
    be hand-checked on a single case before it is believed.

---

## Layout

```
run_eval.sh                   orchestrator; dry-run by default
PROCEDURE_HUMAN.md            the semi-automated steps, with exact commands
DECISIONS.md                  decisions of record -- read before "fixing" anything
bin/gen_cases.py              regenerate + verify all cases and goldens
bin/run_one.sh                one (prompt, arm) as a fresh claude -p session
bin/score_run.py              transcripts -> machine cells -> 12-point scorecard
bin/make_judge_prompts.py     materialise judge prompts for UNKNOWN cells
bin/apply_judge.py            majority-vote judge verdicts back into the scorecard
bin/agreement.py              judge-vs-human Cohen's kappa
bin/label_batch.py            two-phase judge validation (probes, then humans)
bin/gen_plugin_eval_suite.py  emit the forward-compatible plugin eval suite
lib/gencases.py               deterministic fixture + golden generator
lib/refcalc.py                INDEPENDENT reference statistics (golden verification)
lib/verify.py                 golden consistency + margin discipline
lib/trace.py                  stream-json -> observed signals
lib/checks.py                 the machine checks
lib/scorecard.py              12-point rollup + rendering
lib/aggregate.py              repeated-run -> per-criterion pass rates
rubric/judge_output.v1.md     Output-axis judge (versioned)
rubric/judge_process.v1.md    Process-axis judge (versioned)
rubric/judge_baseline_diff.v1.md  pairwise RED/GREEN adjudication
rubric/BIAS_NOTES.md          every bias control traced to its source
rubric/output_format.json     the prescribed-format contract, as data
cases/triggering.json         20 trigger prompts, 60/40 train/test
cases/judge_probes.json       13 planted responses with known labels
cases/c*/                     case.json, golden.json, inputs/
plugin-eval-suite/            generated; unexecuted (feature gated)
runs/                         captured transcripts + scorecards
```

Stdlib-only Python 3.9. No third-party packages.
