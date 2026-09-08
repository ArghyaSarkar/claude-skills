#!/usr/bin/env python3
"""Emit a `claude plugin eval` suite from the SAME cases + goldens.

WHY THIS EXISTS
`claude plugin eval` is the better long-term host for these evals than the
hand-rolled runner: it already implements the baseline-ablation arm
(--ablation with-without), per-case run repetition, tool_used graders that detect
skill dispatch directly, and a published JSON result shape. It is currently
EARLY-ACCESS GATED on this machine ("`plugin eval` is currently in early
access"), so it cannot be run here -- but the suite is generated from the same
source of truth so that the day the gate lifts, it runs without a rewrite.

Generated from cases/*/golden.json, never hand-edited: a golden change
regenerates the graders.

Run when the gate lifts:
  claude plugin eval /Users/sarkararghya/.claude/skills/experiment-readout \
    --eval-dir tests/eval/plugin-eval-suite --ablation with-without --runs 3

usage: gen_plugin_eval_suite.py
"""
import json, os, shutil, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES = os.path.join(HERE, "cases")
OUT = os.path.join(HERE, "plugin-eval-suite")

GATE_RX = {
    "design_integrity": r"design.?integrity|sealed",
    "srm": r"SRM|sample ratio mismatch",
    "maturity": r"matur|immature|28.?day",
}


def w(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(text)


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    n = 0
    for cid in sorted(os.listdir(CASES)):
        cdir = os.path.join(CASES, cid)
        if not os.path.isdir(cdir):
            continue
        golden = json.load(open(os.path.join(cdir, "golden.json")))
        case = json.load(open(os.path.join(cdir, "case.json")))
        cd = os.path.join(OUT, cid)

        # inputs travel with the case via a scaffold script
        for f in os.listdir(os.path.join(cdir, "inputs")):
            shutil.copy(os.path.join(cdir, "inputs", f), os.path.join(cd, f)) \
                if os.path.isdir(cd) else None
        os.makedirs(cd, exist_ok=True)
        for f in os.listdir(os.path.join(cdir, "inputs")):
            shutil.copy(os.path.join(cdir, "inputs", f), os.path.join(cd, f))

        w(os.path.join(cd, "case.yaml"),
          'schema_version: "1.1"\n'
          'name: %s\n'
          'runs: 3\n'
          'max_turns: 14\n'
          'timeout_seconds: 300\n'
          'tags: [experiment-readout, %s%s]\n'
          'prompt: |\n  %s\n'
          'context:\n  add_dirs:\n    - path: "*.csv"\n    - path: "*.yaml"\n'
          % (cid, golden["task"],
             ", central" if golden.get("central") else "",
             case["prompt"].replace("\n", "\n  ")))

        g = os.path.join(cd, "graders")

        # Triggering indicator. with_only, so it reports plugin-fired without
        # polluting the score in the ablation arm.
        w(os.path.join(g, "skill_fired.md"),
          "---\ntype: tool_used\ntool: Skill\n"
          "input_match: '\"skill\"\\s*:\\s*\"(?:[\\w-]+:)?experiment-readout\"'\n"
          "min: 1\nwith_only: true\n---\n"
          "Unprompted triggering. with_only because the baseline arm cannot fire a\n"
          "skill it does not have, so scoring it in both arms would be meaningless.\n")

        w(os.path.join(g, "script_invoked.md"),
          "---\ntype: tool_used\ntool: Bash\ninput_match: '%s'\nmin: 1\n---\n"
          "Process: the skill's own orchestrator ran, rather than the agent\n"
          "improvising statistics.\n"
          % ("power\\.py" if golden["task"] == "power" else "run_readout\\.py"))

        if golden["verdict"]:
            w(os.path.join(g, "verdict_correct.md"),
              "---\ntype: regex\npattern: '%s'\nmatch: contains\n"
              "target: last_message\n---\nOutput: the golden verdict.\n"
              % golden["verdict"])
            w(os.path.join(g, "verdict_first_line.md"),
              "---\ntype: regex\npattern: '\\A[^\\n]*%s'\nflags: 'm'\n"
              "match: contains\ntarget: last_message\n---\n"
              "Format: SKILL.md requires the verdict on the first line.\n"
              % golden["verdict"])

        for gate in golden["all_validity_failures"]:
            w(os.path.join(g, "enumerates_%s.md" % gate),
              "---\ntype: regex\npattern: '%s'\nflags: 'i'\nmatch: contains\n"
              "target: last_message\n---\n"
              "Amendment 1: EVERY validity failure must be surfaced, not only the\n"
              "first. This case has %d.\n"
              % (GATE_RX[gate], len(golden["all_validity_failures"])))

        if golden["conclusions_suppressed"]:
            w(os.path.join(g, "no_lift_leak.md"),
              "---\ntype: regex\n"
              "pattern: '[-+]?\\d+(?:\\.\\d+)?\\s*%\\s*(?:relative\\s*)?"
              "(?:lift|uplift|increase|improvement|effect)'\n"
              "flags: 'i'\nmatch: not_contains\ntarget: last_message\n---\n"
              "The highest-value negative check: a validity gate failed, so no lift\n"
              "may appear anywhere.\n")
            w(os.path.join(g, "no_hedged_peek.md"),
              "---\ntype: llm\n"
              "criteria: \"The response must contain NO directional read on the "
              "experiment's outcome and NO guardrail conclusion, because a validity "
              "gate failed. FAIL it for hedged forms too: 'directionally', 'for "
              "context', 'if the SRM were fixed the lift would be', 'the guardrail "
              "at least looks fine', 'early signal'. The SRM's own chi-squared "
              "p-value and the observed arm split ARE permitted -- they are validity "
              "evidence, not a conclusion. Do not reward length or confidence.\"\n"
              "focus: last_message\n---\n")
        else:
            w(os.path.join(g, "reports_conclusion.md"),
              "---\ntype: regex\npattern: '%.0f'\nmatch: contains\n"
              "target: last_message\n---\n"
              "Validity passed here, so the conclusion is REQUIRED. Guards against a\n"
              "skill that has learned to block everything.\n"
              % abs(round(golden["reference"]["lift"]["rel_diff"] * 100)))

        if golden["asof"]["must_flag_as_assumption"]:
            w(os.path.join(g, "asof_calibrated.md"),
              "---\ntype: llm\n"
              "criteria: \"The CSV carries no extract date, so the as-of date is "
              "unknowable from the input. PASS only if the response labels the as-of "
              "as an ASSUMPTION and names the input that would settle it (the "
              "extract/pull date). FAIL a bare factual assertion such as '0% of "
              "users are mature'. NOTE: the more confident-sounding answer is the "
              "WORSE answer on this criterion -- do not reward assertiveness.\"\n"
              "focus: last_message\n---\n")

        if golden["truncation_gradient"]["graded"]:
            tg = golden["truncation_gradient"]
            w(os.path.join(g, "truncation_gradient.md"),
              "---\ntype: llm\n"
              "criteria: \"A truncated N-day metric MUST show late exposure cohorts "
              "lower than early ones, so the metric mean BY EXPOSURE COHORT is a "
              "maturity diagnostic that needs no as-of date. PASS only if the "
              "response actually checks it and reads it correctly. On this case the "
              "gradient is %s (corr=%+.2f, late vs early %+.1f%%), so the correct "
              "reading is: %s. A bare mention of the word 'cohort' is NOT a "
              "gradient check.\"\nfocus: last_message\n---\n"
              % (tg["branch"].replace("_", " "),
                 tg["corr_cohort_index_vs_mean"],
                 100 * tg["late_vs_early_rel"],
                 tg["expected_reading"]))

        m = golden["maturity"]
        if m["branch"] == "partial":
            w(os.path.join(g, "partial_maturity.md"),
              "---\ntype: llm\n"
              "criteria: \"Maturity here is PARTIAL: about %.0f%% of users have a "
              "complete window and about %.0f%% do not. PASS requires the response to "
              "identify PARTIAL maturity and name DIFFERENTIAL FOLLOW-UP TIME between "
              "early and late cohorts as why the gate fails. FAIL a claim that no "
              "users are mature -- that is not overconfidence, it is wrong. Remember "
              "the hedged answer is the better answer here; do not reward "
              "confidence.\"\nfocus: last_message\n---\n"
              % (100 * m["mature_share"], 100 * (1 - m["mature_share"])))

        if golden["claim_vs_data"]["graded"]:
            w(os.path.join(g, "claim_checked.md"),
              "---\ntype: llm\n"
              "criteria: \"The ask claims the experiment ran '%s'. The data shows an "
              "exposure span of %d days. PASS only if the response CHECKS the claim "
              "against the data and flags the contradiction. FAIL if it repeats the "
              "claim as established fact.\"\nfocus: last_message\n---\n"
              % (golden["claim_vs_data"]["claimed_duration"],
                 golden["claim_vs_data"]["actual_span_days"]))

        w(os.path.join(g, "cites_references.md"),
          "---\ntype: regex\npattern: 'references/[a-z-]+\\.md'\n"
          "match: contains\ntarget: last_message\n---\n"
          "Process: references cited by path, per SKILL.md's self-check.\n")
        n += 1

    w(os.path.join(OUT, "README.md"),
      "# plugin-eval suite (generated -- do not hand-edit)\n\n"
      "Generated by `bin/gen_plugin_eval_suite.py` from `cases/*/golden.json`.\n"
      "Regenerate after any golden change.\n\n"
      "`claude plugin eval` was EARLY-ACCESS GATED when this was written, so this\n"
      "suite is unexecuted. Verified by running it and receiving:\n\n"
      "    `plugin eval` is currently in early access\n\n"
      "When the gate lifts:\n\n"
      "```\nclaude plugin eval /Users/sarkararghya/.claude/skills/experiment-readout \\\n"
      "  --eval-dir tests/eval/plugin-eval-suite --ablation with-without --runs 3\n```\n\n"
      "`--ablation with-without` builds the no-skill baseline arm natively, which is\n"
      "the same RED/GREEN comparison `run_eval.sh --baseline` does by hand. Graders\n"
      "marked `with_only: true` (skill dispatch) are reported as plugin-fired\n"
      "indicators rather than scored, which is the correct treatment: a baseline arm\n"
      "cannot dispatch a skill it does not have.\n\n"
      "CAVEAT: the schema here follows the documented `case.yaml`/`graders` format\n"
      "but has never been executed. Expect to fix schema details on first real run.\n")
    print("generated %d plugin-eval cases in %s" % (n, OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
