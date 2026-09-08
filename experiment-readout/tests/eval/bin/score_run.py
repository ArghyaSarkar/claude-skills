#!/usr/bin/env python3
"""Score captured transcripts against the golden answers -> 12-point scorecard.

Machine-only. Every cell this produces is decided by a rule in lib/checks.py.
Cells that need the LLM judge or a human come back UNKNOWN and are written to
runs/<id>/judge_queue.json and runs/<id>/human_queue.json for the semi-automated
steps in PROCEDURE_HUMAN.md. Nothing is invented to fill a gap.

usage:
  score_run.py --run-dir runs/<id> [--cases-dir cases] [--json OUT] [--text OUT]
Expects, inside --run-dir:
  with/<case_id>.jsonl                (required)
  without/<case_id>.jsonl             (optional; enables the baseline arm)
  triggering/<prompt_id>.jsonl        (optional; enables the Triggering axis)
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from lib import trace, checks, scorecard as sc, aggregate as agg


def load(p):
    with open(p) as fh:
        return json.load(fh)


def score_case(case_dir, tpath, fmt_cfg):
    golden = load(os.path.join(case_dir, "golden.json"))
    obs = trace.parse(tpath)
    text = obs["final_text"]
    cells, diags = {}, {}

    def cell(key, verdict, note, by):
        cells[key] = {"verdict": verdict, "note": note, "decided_by": by}

    # ---- Output axis ----
    v, n = checks.check_verdict(text, golden);           cell("O1_verdict", v, n, sc.MACHINE)
    v, n = checks.check_enumeration(text, golden);       cell("O2_enumeration", v, n, sc.MACHINE)

    sup, hard, soft = checks.check_suppression(text, golden)
    if golden["conclusions_suppressed"]:
        note = ("clean" if sup == checks.PASS else
                ("HARD LEAK: %s" % hard[:2] if hard else "hedges need adjudication: %s" % soft[:2]))
        cell("O3_suppression", sup, note, sc.MACHINE if sup != checks.UNKNOWN else sc.JUDGE)
        if hard:
            diags["FATAL_leak"] = ("reported a suppressed conclusion on invalid data: %s"
                                   % hard[0][1][:120])
    else:
        v, n = checks.check_numbers_present(text, golden)
        cell("O3_suppression", v, "conclusions required here; " + n, sc.MACHINE)

    v, n = checks.check_format(text, fmt_cfg, golden["conclusions_suppressed"],
                               task=golden["task"])
    cell("O4_format", v, n, sc.MACHINE)
    v, n = checks.check_asof_honesty(text, golden)
    cell("O5_asof_calibration", v, n, sc.MACHINE if v != checks.UNKNOWN else sc.JUDGE)
    v, n = checks.check_claim_vs_data(text, golden)
    cell("O6_claim_vs_data", v, n, sc.MACHINE if v != checks.UNKNOWN else sc.JUDGE)
    v, n = checks.check_truncation_gradient(text, golden)
    cell("O8_truncation_gradient", v, n, sc.MACHINE if v != checks.UNKNOWN else sc.JUDGE)
    # O7 is judgement-only by construction: "nothing softer than the verdict"
    cell("O7_no_softening", checks.UNKNOWN,
         "requires the Output judge (rubric/judge_output.v1.md, criterion O7)", sc.JUDGE)

    # ---- Process axis ----
    for k, (v, n) in checks.process_signals(obs, golden, text).items():
        cell(k, v, n, sc.MACHINE)

    return golden, obs, cells, diags


def _mean_card(cid, group):
    """Collapse repeated runs of one case into a mean card, keeping the spread.

    The mean is what stays comparable to the arena's single 12-point score; the
    min/max is what tells you whether that mean is trustworthy.
    """
    def col(axis):
        vals = [c["axes"][axis]["score"] for c in group
                if c["axes"][axis]["score"] is not None]
        if not vals:
            return None, "not measured in any run"
        return (round(sum(vals) / len(vals), 2),
                "mean of %d runs (min %.2f, max %.2f)" % (len(vals), min(vals), max(vals)))
    t, tn = col("triggering"); p, pn = col("process"); o, on = col("output")
    parts = [x for x in (t, p, o) if x is not None]
    ung = sorted({u for c in group for u in
                  (c["axes"]["process"].get("ungraded") or []) +
                  (c["axes"]["output"].get("ungraded") or [])})
    diags = {}
    for c in group:
        diags.update(c.get("diagnostics") or {})
    return {
        "case_id": cid, "n_runs": len(group),
        "axes": {"triggering": {"score": t, "max": 4, "note": tn},
                 "process": {"score": p, "max": 4, "note": pn, "ungraded": ung},
                 "output": {"score": o, "max": 4, "note": on, "ungraded": ung}},
        "total": round(sum(parts), 2) if parts else None, "max": 12,
        "complete": len(parts) == 3,
        "cells": group[0]["cells"],
        "runs": [{"transcript": c["transcript"], "total": c["total"]} for c in group],
        "diagnostics": diags,
    }


def score_triggering(trig_dir, spec):
    if not os.path.isdir(trig_dir):
        return None
    per, counts = [], {"should_fire": [0, 0], "should_not_fire": [0, 0]}
    splits = {"train": [0, 0], "test": [0, 0]}
    for key, expected in (("should_fire", "fire"), ("should_not_fire", "no_fire")):
        for item in spec[key]:
            p = os.path.join(trig_dir, item["id"] + ".jsonl")
            if not os.path.exists(p):
                continue
            o = trace.parse(p)
            counts[key][1] += 1
            if o["fired"]:
                counts[key][0] += 1
            if key == "should_fire":
                splits[item["split"]][1] += 1
                if o["fired"]:
                    splits[item["split"]][0] += 1
            per.append({"id": item["id"], "expected": expected, "fired": o["fired"],
                        "confidence": o["fired_confidence"], "how": o["fired_how"],
                        "prompt": item["prompt"]})
    if not per:
        return None
    out = {"per_prompt": per}
    for k, (f, n) in counts.items():
        if n:
            out[k] = {"fired": f, "n": n, "rate": f / float(n)}
    for k, (f, n) in splits.items():
        if n:
            out["split_" + k] = f / float(n)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--cases-dir", default=os.path.join(HERE, "cases"))
    ap.add_argument("--json"); ap.add_argument("--text")
    a = ap.parse_args()

    fmt_cfg = load(os.path.join(HERE, "rubric", "output_format.json"))
    trig_spec = load(os.path.join(a.cases_dir, "triggering.json"))

    trig = score_triggering(os.path.join(a.run_dir, "triggering"), trig_spec)
    trig_axis = None
    if trig and trig.get("should_fire"):
        trig_axis = sc.triggering_score(trig["should_fire"]["rate"], None)

    with_dir = os.path.join(a.run_dir, "with")
    cards, judge_q, human_q, base = [], [], [], {"rationalizations": [], "failure_rates": {}, "did_not_fail": []}

    # A case may have one transcript (with/<case>.jsonl) or many
    # (with/<case>.run1.jsonl ...). Group them so repeated runs aggregate
    # instead of appearing as unrelated cases.
    runs_by_case = {}
    if os.path.isdir(with_dir):
        for fn in sorted(os.listdir(with_dir)):
            if not fn.endswith(".jsonl"):
                continue
            stem = fn[:-6]
            cid = stem.split(".run")[0]
            if os.path.isdir(os.path.join(a.cases_dir, cid)):
                runs_by_case.setdefault(cid, []).append(fn)

    per_case_cards = {}
    skipped = []
    for cid in sorted(runs_by_case):
        cdir = os.path.join(a.cases_dir, cid)
        group = []
        for fn in sorted(runs_by_case[cid]):
            tp = os.path.join(with_dir, fn)
            if not trace.parse(tp)["complete"]:
                skipped.append(fn)
                continue
            golden, obs, cells, diags = score_case(cdir, tp, fmt_cfg)
            card = sc.build(cid, cells, trig=trig_axis, diagnostics=diags)
            card["transcript"] = fn
            group.append(card)
            for k, c in cells.items():
                if c["verdict"] == checks.UNKNOWN:
                    (judge_q if c["decided_by"] == sc.JUDGE else human_q).append(
                        {"case_id": cid, "criterion": k, "why": c["note"],
                         "transcript": fn})
        if not group:
            continue
        per_case_cards[cid] = group
        if len(group) == 1:
            cards.append(group[0])
        else:
            cards.append(_mean_card(cid, group))
        # ---- baseline arm for this case ----
        # The without-arm is keyed by case id only (one baseline per case is
        # enough to establish that the unaided agent fails), so it is resolved
        # here rather than per with-run.
        golden = load(os.path.join(cdir, "golden.json"))
        for cand in ("%s.jsonl" % cid, sorted(runs_by_case[cid])[0]):
            bpath = os.path.join(a.run_dir, "without", cand)
            if not os.path.exists(bpath):
                continue
            btext = trace.parse(bpath)["final_text"]
            bsup, bhard, bsoft = checks.check_suppression(btext, golden)
            benum, _ = checks.check_enumeration(btext, golden)
            bver, _ = checks.check_verdict(btext, golden)
            bclaim, _ = checks.check_claim_vs_data(btext, golden)
            base["failure_rates"][cid] = (
                "suppression=%s enumeration=%s verdict=%s claim_check=%s"
                % (bsup, benum, bver, bclaim))
            if not any(x == checks.FAIL for x in (bsup, benum, bver, bclaim)):
                base["did_not_fail"].append(cid)
            for _, quote in (bhard + bsoft):
                base["rationalizations"].append(quote)
            break

    out = {"run_dir": os.path.abspath(a.run_dir), "cards": cards,
           "triggering": trig, "baseline": base if base["failure_rates"] else None,
           "judge_queue": judge_q, "human_queue": human_q}

    multi = {cid: agg.per_criterion(g) for cid, g in per_case_cards.items()
             if len(g) > 1}
    out["per_criterion"] = multi

    txt = sc.render(cards, trig, out["baseline"])
    if skipped:
        txt += ("\n\nSKIPPED %d incomplete transcript(s) (no terminal result event, "
                "still being written): %s\n" % (len(skipped), ", ".join(sorted(skipped))))
    if multi:
        txt += "\n" + agg.render(multi)
    if judge_q or human_q:
        txt += "\n\nPENDING (written to the run dir, NOT scored):\n"
        txt += "  %d cell(s) need the LLM judge, %d need a human.\n" % (len(judge_q), len(human_q))
        txt += "  See PROCEDURE_HUMAN.md for the exact commands.\n"
    print(txt)

    for name, payload in (("scorecard.json", out), ("judge_queue.json", judge_q),
                          ("human_queue.json", human_q)):
        with open(os.path.join(a.run_dir, name), "w") as fh:
            json.dump(payload, fh, indent=2)
    if a.json:
        with open(a.json, "w") as fh:
            json.dump(out, fh, indent=2)
    if a.text:
        with open(a.text, "w") as fh:
            fh.write(txt + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
