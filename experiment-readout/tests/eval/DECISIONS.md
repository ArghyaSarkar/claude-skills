# Eval decisions of record

Decisions that look like defects unless the reasoning is written down. Anything
here has been deliberately chosen. **Do not "fix" an item on this list without
reversing the decision explicitly.**

---

## D1 — The over-trigger is ACCEPTED. Do not tighten the description.

**Status:** accepted 2026-08-21, on the coordinator's decision.
**Observation:** `n9` — "how many users signed up in the treatment group cohort
last week?" — fires the skill. It is a plain count query and the skill should not
be needed. Measured false-positive rate 50% on n=2 near-miss prompts.
**Decision:** leave the description alone. Recall is worth everything; precision
is worth approximately zero.

### Why the payoff matrix is this asymmetric

| Outcome | Arena cost |
|---|---|
| Misses the natural ask | **−4 of 12 points**, and the rubric says "0: never fired — regardless of answer quality. Always." |
| Fires on an unrelated count query | **0 points.** The arena scores one hidden question of the *same theme*. A false positive on an off-theme prompt is never scored, because that prompt is never asked. |

The arena grades a single question drawn from the same theme as the practice set.
Under-triggering forfeits a third of the total and cannot be recovered by a
perfect answer. Over-triggering costs nothing that is measured. With a payoff
matrix that lopsided, a description tuned for precision is strictly worse.

So: firing on "how many users signed up in the treatment group cohort last week"
is a real annoyance, and it is accepted in exchange for never missing the natural
ask.

### This trade is ARENA-SPECIFIC, and inverts for real use

If this skill were being shipped for a team's daily use, **the correct call is the
opposite one**. In production the payoff matrix flips:

- a missed trigger costs one mildly worse answer, and the user can re-ask or
  invoke `/experiment-readout` explicitly
- a false trigger costs a full gated readout — script runs, three reference file
  reads, a validity audit — on someone who wanted a `SELECT COUNT(*)`. Repeated,
  it trains the team to distrust and disable the skill, which costs every future
  correct firing too

A production version should therefore narrow the description to require an
experiment/readout/ship-decision context rather than mere vocabulary overlap
("treatment", "cohort", "variant"), and should accept some missed obliques as the
price. Anyone forking this skill for real use should start by reversing D1.

### Consequence for the harness

The false-positive rate is reported as a **DIAGNOSTIC, deliberately outside the
12 points** (`lib/scorecard.py`). Folding it in would silently shift the scale and
break comparability with the arena, which is the one thing the scorecard exists to
preserve. It stays visible so the trade is never invisible, and never scored so
the number stays comparable.

---

## D2 — `UNKNOWN` is never counted as a failure.

Ungraded cells are excluded from the denominator and listed explicitly. A score
computed from 6 of 8 criteria is reported as `6/8 graded`, not silently rescaled
as though all 8 passed. Rationale: a grader forced to guess produces a confident
number that is worse than an honest gap.

---

## D3 — Goldens are never computed by the code under test.

`lib/refcalc.py` is a deliberately separate, simpler implementation and never
imports `scripts/gates.py`. Because it is an approximation, `lib/verify.py`
enforces wide decision margins on every case and `bin/gen_cases.py` exits
non-zero if a case cannot clear them. A golden produced by the implementation it
is meant to check is a tautology, not a golden.

---

## D4 — The baseline arm uses `--safe-mode`, accepting that it changes more than one variable.

`--safe-mode` removes CLAUDE.md and hooks along with skills, so the measured
with/without gap is an **upper bound** on the skill's contribution. The narrower
`--disable-slash-commands` was rejected because it was not verified to remove the
skill *description* from the system prompt, and a baseline arm that still sees the
description is not a baseline. Over-attributing to the skill is the safer error
here than silently not ablating it at all.

---

## D5 — Judge prompts are piped via stdin, never passed as an argument.

**Found the hard way 2026-08-21.** The first Phase 1 run produced twelve empty
`.verdict.json` files and a scorecard reading `sensitivity 0/6`. That looked like
a catastrophic judge failure. It was not: `claude -p "<11KB prompt>"` as a
positional argument fails **silently**, exit code 0, no stderr, empty stdout.
Piping the same prompt via `< file` works perfectly.

Every documented judge command therefore uses stdin redirection, and
`bin/label_batch.py` / `bin/make_judge_prompts.py` print the warning alongside the
command they emit.

**Generalisable lesson for this harness:** a measurement that reports total
failure of a component should be suspected of being an instrument fault until the
instrument is checked on a single case by hand. The 0/6 result was indistinguishable
from a real finding, and would have been reported as one.

---

## D6 — The human-label batch caps items per (case, criterion) pair.

At n=5 runs per case an uncapped batch of 16 is mostly near-duplicate responses to
the same prompt. Two reasons that is wrong:

1. It wastes the scarce resource — a person's attention — on re-reading variants.
2. It **inflates apparent agreement.** Correlated items are not independent
   trials; agreeing with the judge on five copies of one response is a single data
   point presented as five, which would make a kappa look better-supported than it is.

`PER_PAIR = 2` in `bin/label_batch.py`, spread across cases instead.

---

## D7 — Raising reps to n=5 found HARNESS bugs, not skill bugs. Expect that.

The reason to raise reps was to stop quoting rates off n=1. What it actually
produced first was three more false positives in `lib/checks.py`, all in
`check_asof_honesty`, all surfaced because five runs word things five ways:

| Bug | Matched | Should have |
|---|---|---|
| negation blind | "Partial maturity, **not zero maturity**" | recognised a *denial* of the error, not the error |
| digit boundary on `%` | "a read at 8**0%** mature" | required a non-digit before the `0` |
| digit boundary on `/` | "162**0/1380**" split | same |

Before the fixes, `c12`'s `O5_asof_calibration` read **2/5 — NOT BINDING**, which
looks exactly like a skill defect and would have been reported as one. After:
**5/5 BINDING**. The skill was never wrong.

**Lesson to carry:** on this harness, a criterion that fails intermittently is
more likely to be a brittle regex than a wobbly skill, because the machine checks
are pattern matches over free prose and every extra run is another chance to phrase
something the pattern mishandles. So the triage order for any flagged criterion is:

1. Read the *matched span*, not just the verdict. (`check_*` returns the span.)
2. Decide whether the detector or the skill is wrong.
3. Only then call it a skill defect.

The `!! FLAGGED` block in `lib/aggregate.py` says "read these as SKILL defects" —
that advice is now qualified: read them as defects *somewhere*, and check the
detector first. Corollary: the per-criterion pass rates are only as trustworthy as
the detector, so a 100% rate on a brittle pattern is not the same as a 100% rate
on a robust one.
