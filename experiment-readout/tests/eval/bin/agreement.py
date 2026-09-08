#!/usr/bin/env python3
"""Judge-vs-human agreement: Cohen's kappa alongside raw agreement.

WHY BOTH NUMBERS
Raw percent agreement is inflated by chance and by category imbalance. A
large multi-judge audit (arXiv:2606.19544) found raw agreement overstated kappa
by 33.8-41.3 percentage points across 21 judges. Our label distribution is very
imbalanced (most cells are PASS), which is exactly the condition that inflates
raw agreement most -- so this script refuses to print the raw number alone.

Bar to clear: kappa >= 0.7. Below that, suspect the RUBRIC before the judge:
if two careful readers cannot agree using it, the criterion is ambiguous.

usage: agreement.py --run-dir runs/<id>
Reads runs/<id>/human_labels.json:
  [{"case_id": "...", "criterion": "O5_asof_calibration", "verdict": "PASS"}, ...]
"""
import argparse, json, os, re, sys
from collections import Counter


def cohens_kappa(pairs):
    n = len(pairs)
    if n == 0:
        return None
    labels = sorted({x for p in pairs for x in p})
    po = sum(1 for a, b in pairs if a == b) / float(n)
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum((ca[l] / float(n)) * (cb[l] / float(n)) for l in labels)
    if abs(1.0 - pe) < 1e-12:
        return None       # undefined: both raters used a single label throughout
    return (po - pe) / (1.0 - pe), po, pe


def selftest():
    """Verify the kappa implementation against textbook values.

    Worth having: a silently wrong kappa would be reported with the same
    confidence as a right one, and kappa is the number this harness leans on to
    decide whether the judge is trustworthy at all.
    """
    cases = [
        ("perfect agreement, balanced", [("P", "P")] * 5 + [("F", "F")] * 5, 1.0),
        ("chance-level agreement", [("P", "P"), ("P", "F"), ("F", "P"), ("F", "F")], 0.0),
        ("po=0.80, balanced marginals",
         [("P", "P")] * 40 + [("P", "F")] * 10 + [("F", "P")] * 10 + [("F", "F")] * 40, 0.6),
    ]
    ok = True
    for name, pairs, want in cases:
        got = cohens_kappa(pairs)[0]
        good = abs(got - want) < 1e-9
        ok = ok and good
        print("  %-32s kappa=%.3f expected %.3f  %s"
              % (name, got, want, "ok" if good else "MISMATCH"))
    r = cohens_kappa([("P", "P")] * 10)
    good = r is None
    ok = ok and good
    print("  %-32s -> %s  %s" % ("single label, no variance", r,
                                 "ok (undefined, as it must be)" if good else "MISMATCH"))
    print("\nselftest %s" % ("PASSED" if ok else "FAILED"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.run_dir:
        ap.error("--run-dir is required (or use --selftest)")
    hp = os.path.join(a.run_dir, "human_labels.json")
    if not os.path.exists(hp):
        print("no human_labels.json in %s -- judge validation NOT performed.\n"
              "Until it is, every judge-decided cell on the scorecard is "
              "unvalidated. See PROCEDURE_HUMAN.md step 4." % a.run_dir)
        return 1
    labels = json.load(open(hp))
    human = {(h["case_id"], h["criterion"]): h["verdict"].upper() for h in labels}

    HERE2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    probe_truth, probe_judge = {}, {}
    pp = os.path.join(HERE2, "cases", "judge_probes.json")
    if os.path.exists(pp):
        for pr in json.load(open(pp))["probes"]:
            probe_truth[pr["id"]] = pr["truth"].upper()
            vf = os.path.join(HERE2, "runs", "probes", "judge_prompts",
                              pr["id"] + ".verdict.json")
            if os.path.exists(vf):
                data = None
                txt = open(vf, errors="replace").read()
                for pat in (r"```(?:json)?\s*(\{.*?\})\s*```", r"(\{[\s\S]*\})"):
                    for m in re.finditer(pat, txt, re.DOTALL):
                        try:
                            data = json.loads(m.group(1)); break
                        except ValueError:
                            continue
                    if data:
                        break
                if data and data.get("criteria"):
                    probe_judge[pr["id"]] = (data["criteria"][0].get("verdict")
                                             or "UNKNOWN").upper()

    card = json.load(open(os.path.join(a.run_dir, "scorecard.json")))
    pairs, rows = [], []

    # --- planted items: human vs KNOWN TRUTH, and judge vs known truth --------
    ptot = pok = 0
    for (cid, crit), hv in sorted(human.items()):
        if not str(cid).startswith("PROBE:"):
            continue
        pid = cid.split(":", 1)[1]
        truth = probe_truth.get(pid)
        if not truth:
            continue
        ptot += 1
        pok += (hv == truth)
        jv = probe_judge.get(pid)
        if jv:
            pairs.append((jv, hv))
            rows.append(("PROBE:" + pid, crit, jv, hv))

    # --- real cells: judge vs human ------------------------------------------
    unjudged = 0
    for c in card["cards"]:
        for crit, cell in c["cells"].items():
            k = (c["case_id"], crit)
            if k not in human or cell.get("decided_by") != "judge":
                continue
            if cell["verdict"] == "UNKNOWN":
                # The judge has not actually ruled on this cell yet -- it is
                # queued. Counting "not yet judged" as a disagreement would
                # manufacture a bad kappa out of unfinished work.
                unjudged += 1
                continue
            pairs.append((cell["verdict"], human[k]))
            rows.append((c["case_id"], crit, cell["verdict"], human[k]))

    if ptot:
        print("PLANTED ITEMS -- human vs known truth: %d/%d" % (pok, ptot))
        print("  (a check on the LABELLER, not the judge. If this is low the "
              "criterion wording is the problem, not either rater.)\n")

    if unjudged:
        print("EXCLUDED %d human-labelled cell(s) the judge has not ruled on yet "
              "(still UNKNOWN).\n  Run PROCEDURE_HUMAN.md step 2 to judge them, "
              "then re-run this.\n" % unjudged)
    if not pairs:
        print("no overlapping judge-ruled cells to compare. Either the judge has "
              "not been run\n(step 2) or the labels cover different cells.")
        return 1
    print("%-24s %-22s %-8s %-8s" % ("case", "criterion", "judge", "human"))
    for r in rows:
        flag = "" if r[2] == r[3] else "   <-- DISAGREE"
        print("%-24s %-22s %-8s %-8s%s" % (r[0], r[1], r[2], r[3], flag))
    res = cohens_kappa(pairs)
    print("\nn compared        : %d" % len(pairs))
    if res is None:
        print("Cohen's kappa     : UNDEFINED (no label variance -- kappa is "
              "meaningless here; get more varied cases before trusting the judge)")
        return 0
    k, po, pe = res
    print("raw agreement     : %.1f%%  (do NOT quote this alone -- chance-inflated)" % (100 * po))
    print("chance agreement  : %.1f%%" % (100 * pe))
    print("Cohen's kappa     : %.2f  -> %s" % (
        k, "acceptable (>=0.70)" if k >= 0.7 else
           "BELOW BAR: fix the rubric criterion before trusting the judge"))
    if len(pairs) < 30:
        print("\nCAVEAT: %d compared cells is far below the triple-digit stratified "
              "samples used in published judge-validation studies. Treat this kappa "
              "as directional only." % len(pairs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
