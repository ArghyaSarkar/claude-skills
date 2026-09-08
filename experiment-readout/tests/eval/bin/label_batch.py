#!/usr/bin/env python3
"""Judge validation in two phases, cheapest first.

THE POINT: spend ZERO human minutes until the judge has earned them.

  Phase 1  --build-probes / --score-probes    0 human minutes
      Run the judge against 12 PLANTED responses whose correct label is already
      known (cases/judge_probes.json). This yields sensitivity and specificity
      immediately, with no human in the loop. If the judge misses an easy planted
      leak, it is unusable and no human time should be spent on it at all.

  Phase 2  --build-human / --score-human      ~15 minutes
      Only if Phase 1 passes. A human labels real cells from live runs, where the
      truth is genuinely unknown, to estimate agreement on the real distribution.

WHY PLANTED PROBES AT ALL
Cohen's kappa is UNDEFINED when both raters use a single label throughout
(pe = 1.0), and on real runs almost every cell is PASS. A batch of real cells
alone can therefore produce no kappa. The probes are balanced 6 PASS / 6 FAIL by
construction, which guarantees label variance, and their known truth converts the
exercise from "do two raters agree" into "is the judge actually right" -- a
strictly stronger question.

usage:
  label_batch.py --build-probes                    -> runs/probes/judge_prompts/*.md
  label_batch.py --score-probes                    -> sensitivity / specificity
  label_batch.py --build-human --run-dir runs/n5   -> runs/n5/human_batch.md
  label_batch.py --label --run-dir runs/n5         -> interactive; writes human_labels.json
"""
import argparse, glob, json, os, random, re, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from lib import trace

PROBES = os.path.join(HERE, "cases", "judge_probes.json")
RUBRIC = os.path.join(HERE, "rubric", "judge_output.v1.md")

CRIT_TEXT = {
    "O3_suppression": "No lift, p-value, CI, or guardrail conclusion anywhere, including hedged and counterfactual forms. The SRM's own chi-squared p-value, the observed arm split, the truncation-gradient statistics, and citations of the brief's MDE ARE permitted -- they are validity evidence, not conclusions.",
    "O7_no_softening": "Nothing is softer than the verdict: no 'probably fine to ship', no 'the PM can decide', no 'but' that walks the verdict back.",
}


def build_probes():
    spec = json.load(open(PROBES))
    golden = json.load(open(os.path.join(HERE, "cases", "c03_srm_and_maturity",
                                         "golden.json")))
    tmpl = open(RUBRIC).read()
    out = os.path.join(HERE, "runs", "probes", "judge_prompts")
    os.makedirs(out, exist_ok=True)
    for pr in spec["probes"]:
        block = "- `%s`: %s" % (pr["criterion"], CRIT_TEXT[pr["criterion"]])
        body = (tmpl.replace("{{GOLDEN_JSON}}", json.dumps(golden, indent=2))
                    .replace("{{RESPONSE}}", pr["text"])
                    .replace("{{CRITERIA_BLOCK}}", block))
        open(os.path.join(out, pr["id"] + ".md"), "w").write(body)
    print("wrote %d probe prompts to %s\n" % (len(spec["probes"]), out))
    print("Judge them with a model OTHER than the one under test:\n")
    print("  for f in runs/probes/judge_prompts/*.md; do")
    print('    claude -p --model sonnet --no-session-persistence < "$f" \\')
    print('      > "${f%.md}.verdict.json"')
    print("  done")
    print("\n  NOTE: the prompt is piped via stdin. Passing an ~11KB rubric as a")
    print("  positional argument fails SILENTLY and writes an empty file -- that")
    print("  happened on all 12 probes the first time this was run.")
    print("\nThen: bin/label_batch.py --score-probes")


def _extract(text):
    for pat in (r"```(?:json)?\s*(\{.*?\})\s*```", r"(\{[\s\S]*\})"):
        for m in re.finditer(pat, text, re.DOTALL):
            try:
                return json.loads(m.group(1))
            except ValueError:
                continue
    return None


def score_probes():
    spec = {p["id"]: p for p in json.load(open(PROBES))["probes"]}
    d = os.path.join(HERE, "runs", "probes", "judge_prompts")
    rows, missing = [], []
    for pid, pr in sorted(spec.items()):
        vf = os.path.join(d, pid + ".verdict.json")
        if not os.path.exists(vf):
            missing.append(pid)
            continue
        data = _extract(open(vf, errors="replace").read())
        got = "UNPARSED"
        if data and data.get("criteria"):
            got = (data["criteria"][0].get("verdict") or "UNKNOWN").upper()
        rows.append((pid, pr["criterion"], pr["difficulty"], pr["truth"], got))
    if missing:
        print("NOT YET JUDGED: %s" % ", ".join(missing))
        if not rows:
            print("Run --build-probes and judge them first.")
            return 1
    print("%-5s %-20s %-9s %-7s %-9s %s" % ("id", "criterion", "difficulty",
                                            "truth", "judge", ""))
    tp = fp = tn = fn = 0
    for pid, crit, diff, truth, got in rows:
        ok = (got == truth)
        if truth == "FAIL":
            if got == "FAIL": tp += 1
            else: fn += 1
        else:
            if got == "PASS": tn += 1
            else: fp += 1
        print("%-5s %-20s %-9s %-7s %-9s %s" % (pid, crit, diff, truth, got,
                                                "" if ok else "<-- WRONG"))
    print("\nplanted leaks caught (sensitivity) : %d/%d" % (tp, tp + fn))
    print("clean responses passed (specificity): %d/%d" % (tn, tn + fp))
    print("\nGATE -- judge is usable only if BOTH hold:")
    print("  sensitivity on ALL planted leaks = 100%  (missing an obvious leak on the")
    print("    highest-stakes criterion disqualifies it; this is near-binary, not a rate)")
    print("  specificity >= 85%                     (over-flagging compliance is")
    print("    costly too -- it penalises the skill for refusing correctly)")
    sens_ok = (tp + fn) > 0 and fn == 0
    spec_ok = (tn + fp) > 0 and (tn / float(tn + fp)) >= 0.85
    print("\n  sensitivity %s      specificity %s"
          % ("PASS" if sens_ok else "FAIL", "PASS" if spec_ok else "FAIL"))
    print("  => JUDGE IS %s" % ("USABLE" if (sens_ok and spec_ok) else "NOT USABLE"))

    hard_missed = [r[0] for r in rows if r[3] == "FAIL" and r[4] != "FAIL"
                   and r[2] == "hard"]
    if hard_missed:
        print("\nHard probes missed: %s" % hard_missed)
        print("  p06 in particular is an oblique leak with no number and no hedge")
        print("  keyword. The machine check CANNOT catch it (README limitation 6). If")
        print("  the judge misses it too, that failure mode is currently undetected by")
        print("  anything in this harness and needs the human step in PROCEDURE_HUMAN.md.")
    return 0


def build_human(run_dir, max_items=16, seed=11, include_probes=0):
    """Assemble a BLIND batch of real cells: no judge verdict, no machine note."""
    q = json.load(open(os.path.join(run_dir, "judge_queue.json")))
    pri = {"O3_suppression": 0, "O7_no_softening": 1}
    q = [x for x in q if x["criterion"] in pri]
    q.sort(key=lambda x: (pri[x["criterion"]], x["case_id"], x.get("transcript", "")))

    # DIVERSITY CAP. At n=5 runs per case, an uncapped batch is 16 near-identical
    # items from one or two cases. That wastes the scarce resource (a person's
    # attention) and, worse, inflates apparent agreement: correlated items are not
    # independent trials, so agreeing on 5 copies of the same response is one
    # data point dressed up as five. Cap per (case, criterion) and spread across
    # cases instead.
    PER_PAIR = 2
    seen, picked = {}, []
    for x in q:
        key = (x["case_id"], x["criterion"])
        if seen.get(key, 0) >= PER_PAIR:
            continue
        seen[key] = seen.get(key, 0) + 1
        picked.append(x)
    q = picked[:max_items]
    if q:
        print("selected %d items across %d (case, criterion) pairs, max %d per pair"
              % (len(q), len(seen), PER_PAIR))
    if not q:
        print("no O3/O7 cells pending in %s -- nothing to label." % run_dir)
        return 1
    # OPTIONAL: salt the batch with planted probes whose truth is known.
    #
    # Why this is offered: the real distribution is nearly all-PASS, so a batch of
    # real cells alone very often yields pe=1.0 and an UNDEFINED kappa -- the
    # labeller spends 11 minutes and gets no coefficient. Adding a balanced set of
    # planted items guarantees label variance, so kappa is computable, AND lets the
    # human's own labels be checked against known truth.
    #
    # What it costs: the resulting kappa describes agreement on a DELIBERATELY
    # BALANCED set, not on the real distribution. It is a measure of whether judge
    # and human apply the criterion the same way, not of how often they agree in
    # production. Report it as such.
    probes = []
    if include_probes:
        spec = json.load(open(PROBES))["probes"]
        fails = [x for x in spec if x["truth"] == "FAIL"]
        passes = [x for x in spec if x["truth"] == "PASS"]
        half = max(1, include_probes // 2)
        for pr in (fails[:half] + passes[:include_probes - half]):
            probes.append({"case_id": "PROBE:" + pr["id"], "criterion": pr["criterion"],
                           "transcript": None, "response": pr["text"]})

    items = []
    for i, x in enumerate(q, 1):
        tp = os.path.join(run_dir, "with", x.get("transcript") or (x["case_id"] + ".jsonl"))
        txt = trace.parse(tp)["final_text"] if os.path.exists(tp) else "(transcript missing)"
        items.append({"n": i, "case_id": x["case_id"], "criterion": x["criterion"],
                      "transcript": x.get("transcript"), "response": txt})
    items.extend(probes)
    random.Random(seed).shuffle(items)
    for i, it in enumerate(items, 1):
        it["n"] = i

    md = ["# Human label batch — %d items" % len(items), "",
          "**Blind by design:** neither the judge's verdict nor the machine check's note",
          "appears below. Seeing them first would anchor you and destroy the",
          "independence the agreement number depends on.", "",
          "For each item answer **PASS / FAIL / UNKNOWN** for the named criterion only.",
          "UNKNOWN is a real answer — use it when the text genuinely does not settle it.", "",
          "Record answers by running: `bin/label_batch.py --label --run-dir %s`" % run_dir,
          "", "---", ""]
    for it in items:
        md += ["## Item %d — `%s`" % (it["n"], it["criterion"]), "",
               "Criterion: %s" % CRIT_TEXT[it["criterion"]], "",
               "<details><summary>response (click)</summary>", "",
               "```", it["response"][:6000], "```", "", "</details>", "", "---", ""]
    open(os.path.join(run_dir, "human_batch.md"), "w").write("\n".join(md))
    json.dump(items, open(os.path.join(run_dir, "human_batch.json"), "w"), indent=2)
    n_planted = sum(1 for x in items if str(x["case_id"]).startswith("PROBE:"))
    print("wrote %d items (%d real, %d planted) -> %s/human_batch.md"
          % (len(items), len(items) - n_planted, n_planted, run_dir))
    print("estimated time: ~%d-%d min (45-75s per item)"
          % (int(len(items) * 0.75), int(len(items) * 1.25) + 1))
    if probes:
        print("planted items are interleaved and unlabelled; agreement.py will "
              "separate them.")
    else:
        print("NOTE: no planted items. If every real cell is PASS, kappa will be "
              "UNDEFINED -- rerun with --include-probes 8 if you want a coefficient.")
    return 0


def label(run_dir):
    items = json.load(open(os.path.join(run_dir, "human_batch.json")))
    out = []
    print("Labelling %d items. p=PASS  f=FAIL  u=UNKNOWN  s=skip  q=quit\n" % len(items))
    for it in items:
        print("=" * 72)
        print("Item %d/%d  criterion: %s" % (it["n"], len(items), it["criterion"]))
        print("=" * 72)
        print(it["response"][:3500])
        print("-" * 72)
        while True:
            try:
                a = input("[%s] p/f/u/s/q > " % it["criterion"]).strip().lower()
            except EOFError:
                a = "q"
            if a in ("p", "f", "u", "s", "q"):
                break
        if a == "q":
            break
        if a == "s":
            continue
        out.append({"case_id": it["case_id"], "criterion": it["criterion"],
                    "transcript": it.get("transcript"),
                    "verdict": {"p": "PASS", "f": "FAIL", "u": "UNKNOWN"}[a]})
    p = os.path.join(run_dir, "human_labels.json")
    json.dump(out, open(p, "w"), indent=2)
    print("\nwrote %d labels -> %s" % (len(out), p))
    print("now run: bin/agreement.py --run-dir %s" % run_dir)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-probes", action="store_true")
    ap.add_argument("--score-probes", action="store_true")
    ap.add_argument("--build-human", action="store_true")
    ap.add_argument("--label", action="store_true")
    ap.add_argument("--run-dir")
    ap.add_argument("--max-items", type=int, default=16)
    ap.add_argument("--include-probes", type=int, default=0,
                    help="salt the batch with N planted items (balanced) so "
                         "kappa is defined; 8 is a good default")
    a = ap.parse_args()
    if a.build_probes:
        return build_probes() or 0
    if a.score_probes:
        return score_probes()
    if not a.run_dir:
        ap.error("--build-human/--label need --run-dir")
    if a.build_human:
        return build_human(a.run_dir, a.max_items, include_probes=a.include_probes)
    if a.label:
        return label(a.run_dir)
    ap.error("pick a mode")


if __name__ == "__main__":
    sys.exit(main())
