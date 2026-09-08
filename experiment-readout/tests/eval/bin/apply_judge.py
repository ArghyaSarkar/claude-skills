#!/usr/bin/env python3
"""Fold judge verdicts back into the scorecard by majority vote.

Reads runs/<id>/judge_prompts/*.verdict.json (one per judge run), majority-votes
each criterion across runs, and rewrites scorecard.json/txt with those cells
filled. A criterion with no majority stays UNKNOWN and moves to the human queue
-- a split judge is a signal, not something to round away.

usage: apply_judge.py --run-dir runs/<id>
"""
import argparse, glob, json, os, re, sys
from collections import Counter

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from lib import scorecard as sc


def extract_json(text):
    """Judges wrap JSON in prose or fences more often than not."""
    for pat in (r"```(?:json)?\s*(\{.*?\})\s*```", r"(\{[\s\S]*\})"):
        for m in re.finditer(pat, text, re.DOTALL):
            try:
                return json.loads(m.group(1))
            except ValueError:
                continue
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    a = ap.parse_args()

    scpath = os.path.join(a.run_dir, "scorecard.json")
    card = json.load(open(scpath))
    manifest = {m["file"]: m for m in
                json.load(open(os.path.join(a.run_dir, "judge_manifest.json")))}

    votes = {}   # (case_id, criterion) -> [verdicts]
    quotes = {}
    unparsed = []
    for vf in sorted(glob.glob(os.path.join(a.run_dir, "judge_prompts", "*.verdict.json"))):
        key = os.path.basename(vf).replace(".verdict.json", ".md")
        meta = manifest.get(key)
        if not meta:
            continue
        data = extract_json(open(vf, errors="replace").read())
        if not data or "criteria" not in data:
            unparsed.append(os.path.basename(vf))
            continue
        for c in data["criteria"]:
            k = (meta["case_id"], c.get("id"))
            votes.setdefault(k, []).append((c.get("verdict") or "UNKNOWN").upper())
            if c.get("quote"):
                quotes.setdefault(k, c["quote"])

    filled, split = 0, []
    for c in card["cards"]:
        for crit, cell in c["cells"].items():
            k = (c["case_id"], crit)
            if k not in votes or cell["verdict"] != "UNKNOWN":
                continue
            tally = Counter(votes[k])
            top, n = tally.most_common(1)[0]
            if n * 2 > len(votes[k]):
                cell["verdict"] = top
                cell["decided_by"] = sc.JUDGE
                cell["note"] = "judge majority %d/%d (%s); quote: %s" % (
                    n, len(votes[k]), dict(tally), (quotes.get(k) or "")[:110])
                filled += 1
            else:
                split.append("%s/%s %s" % (c["case_id"], crit, dict(tally)))
        # recompute the axes now that cells changed
        p, pnote, punk = sc.process_score(c["cells"])
        o, onote, ounk = sc.output_score(c["cells"])
        t = c["axes"]["triggering"]["score"]
        c["axes"]["process"].update({"score": p, "note": pnote, "ungraded": punk})
        c["axes"]["output"].update({"score": o, "note": onote, "ungraded": ounk})
        parts = [x for x in (t, p, o) if x is not None]
        c["total"] = round(sum(parts), 2) if parts else None
        c["complete"] = len(parts) == 3

    json.dump(card, open(scpath, "w"), indent=2)
    txt = sc.render(card["cards"], card.get("triggering"), card.get("baseline"))
    open(os.path.join(a.run_dir, "scorecard.txt"), "w").write(txt + "\n")
    print(txt)
    print("\njudge cells filled: %d" % filled)
    if split:
        print("SPLIT judge verdicts left UNKNOWN (routed to human review):")
        for s in split:
            print("  " + s)
    if unparsed:
        print("UNPARSEABLE judge output (not counted): %s" % unparsed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
