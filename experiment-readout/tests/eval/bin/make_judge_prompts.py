#!/usr/bin/env python3
"""Materialise judge prompts for the cells the machine checks left UNKNOWN.

Deliberately does NOT call a model. Judge invocation is a separate, explicit step
so that (a) the harness has no hidden spend, and (b) the exact prompt that
produced a verdict is on disk and reviewable. Writes one prompt per (case,
criterion-set) plus a manifest.

Bias mitigations applied HERE rather than left to the rubric prose:
  * criterion order is shuffled per run, with the seed recorded (position bias
    inside rubric option lists is real and model-specific)
  * the arm label is stripped from everything the judge sees
  * runs_per_item copies are emitted so majority voting is possible

usage: make_judge_prompts.py --run-dir runs/<id> [--runs 3] [--seed 7]
"""
import argparse, json, os, random, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from lib import trace

OUTPUT_RUBRIC = os.path.join(HERE, "rubric", "judge_output.v1.md")
PROCESS_RUBRIC = os.path.join(HERE, "rubric", "judge_process.v1.md")

CRITERIA_TEXT = {
    "O1_verdict": "The response asserts the golden verdict as ITS verdict.",
    "O2_enumeration": "Every validity failure in the golden's all_validity_failures is surfaced AND explained actionably. Naming only the first is FAIL even if the verdict is right.",
    "O3_suppression": "No lift, p-value, CI, or guardrail conclusion anywhere, including hedged and counterfactual forms. The SRM's own chi-squared p-value and the observed split ARE permitted.",
    "O4_format": "Verdict on the first line; all three validity gates with a status; suppression stated explicitly; references cited by path.",
    "O5_asof_calibration": "The as-of date is treated as an assumption, labelled as one, with the input that would settle it named. A confident bare assertion scores LOWER here (see bias control 2).",
    "O6_claim_vs_data": "The ask's duration claim is checked against the observed exposure span rather than inherited.",
    "O7_no_softening": "Nothing is softer than the verdict: no 'probably fine to ship', no 'the PM can decide', no 'but' that walks it back.",
    "PJ1_order_is_causal": "The verdict is DERIVED from the first failing gate, not merely preceded by a gate recital.",
    "PJ2_citation_is_real": "Cited reference content visibly informs the answer rather than decorating it.",
    "PJ3_no_step_skipped": "Every prescribed step is visible in the trace or response.",
    "PJ4_hard_stop_honoured": "The hard stop is treated as a rule, not negotiated. Reporting later validity gates after an earlier failure is REQUIRED, not a violation.",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()

    q = json.load(open(os.path.join(a.run_dir, "judge_queue.json")))
    if not q:
        print("judge_queue.json is empty -- every cell was decided by machine check.")
        return 0

    by_case = {}
    for item in q:
        by_case.setdefault(item["case_id"], []).append(item["criterion"])

    outdir = os.path.join(a.run_dir, "judge_prompts")
    os.makedirs(outdir, exist_ok=True)
    rng = random.Random(a.seed)
    manifest = []

    for cid, crits in sorted(by_case.items()):
        golden = json.load(open(os.path.join(HERE, "cases", cid, "golden.json")))
        tpath = os.path.join(a.run_dir, "with", cid + ".jsonl")
        obs = trace.parse(tpath)
        out_crits = [c for c in crits if c.startswith("O")]
        proc_crits = [c for c in crits if c.startswith("P")]

        for rubric_path, subset, tag in ((OUTPUT_RUBRIC, out_crits, "output"),
                                         (PROCESS_RUBRIC, proc_crits, "process")):
            if not subset:
                continue
            tmpl = open(rubric_path).read()
            for r in range(a.runs):
                order = list(subset)
                rng.shuffle(order)
                block = "\n".join("- `%s`: %s" % (c, CRITERIA_TEXT[c]) for c in order)
                body = (tmpl
                        .replace("{{GOLDEN_JSON}}", json.dumps(golden, indent=2))
                        .replace("{{RESPONSE}}", obs["final_text"])
                        .replace("{{CRITERIA_BLOCK}}", block)
                        .replace("{{TRACE_SUMMARY}}", json.dumps({
                            k: obs[k] for k in ("tool_sequence", "scripts_run",
                                                "references_read",
                                                "references_named_in_text",
                                                "ad_hoc_stats_commands")}, indent=2))
                        .replace("{{MACHINE_SIGNALS}}",
                                 "(withheld from this judge run to avoid anchoring)"))
                fn = "%s.%s.run%d.md" % (cid, tag, r + 1)
                open(os.path.join(outdir, fn), "w").write(body)
                manifest.append({"file": fn, "case_id": cid, "axis": tag,
                                 "run": r + 1, "criterion_order": order,
                                 "seed": a.seed})

    open(os.path.join(a.run_dir, "judge_manifest.json"), "w").write(
        json.dumps(manifest, indent=2))
    print("wrote %d judge prompt(s) to %s" % (len(manifest), outdir))
    print("\nRun each with a judge model DIFFERENT from the model under test, e.g.:")
    print("  for f in %s/*.md; do" % outdir)
    print('    claude -p --model sonnet --no-session-persistence < "$f" \\')
    print('      > "${f%.md}.verdict.json"')
    print("  done")
    print("\n  NOTE: the prompt is piped via stdin. Passing an ~11KB rubric as a")
    print("  positional argument fails SILENTLY and writes an empty file -- that")
    print("  happened on all 12 probes the first time this was run.")
    print("\nThen fold the verdicts in with:  bin/apply_judge.py --run-dir %s" % a.run_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
