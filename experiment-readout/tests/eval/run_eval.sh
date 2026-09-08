#!/usr/bin/env bash
# Eval harness for the experiment-readout skill.
#
# Default is --dry-run: it regenerates and verifies the cases, prints the exact
# plan and a cost estimate, and runs NOTHING live. Live runs cost money and take
# ~60-90s each, so they are opt-in.
#
#   ./run_eval.sh                          # dry run: verify cases, print the plan
#   ./run_eval.sh --live --smoke           # 1 case + 1 baseline, ~3 runs
#   ./run_eval.sh --live --triggering      # the 20-prompt trigger set x N runs
#   ./run_eval.sh --live --cases           # all 11 cases, with-arm only
#   ./run_eval.sh --live --cases --baseline # with + without arms (RED/GREEN)
#   ./run_eval.sh --live --all --runs 3    # everything, 3 runs per item
#
# Flags: --runs N (default 1 for cases, 3 for triggering), --model M,
#        --isolate (run against a config dir holding ONLY this skill),
#        --run-id ID, --score-only ID
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
LIVE=0; DO_CASES=0; DO_TRIG=0; DO_BASE=0; SMOKE=0
RUNS=""; MODEL=""; ISOLATE=""; RUN_ID=""; SCORE_ONLY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --live) LIVE=1; shift;;
    --cases) DO_CASES=1; shift;;
    --triggering) DO_TRIG=1; shift;;
    --baseline) DO_BASE=1; shift;;
    --smoke) SMOKE=1; DO_CASES=1; DO_BASE=1; shift;;
    --all) DO_CASES=1; DO_TRIG=1; DO_BASE=1; shift;;
    --runs) RUNS="$2"; shift 2;;
    --model) MODEL="$2"; shift 2;;
    --isolate) ISOLATE="--isolate"; shift;;
    --run-id) RUN_ID="$2"; shift 2;;
    --score-only) SCORE_ONLY="$2"; shift 2;;
    --dry-run) LIVE=0; shift;;
    -h|--help) sed -n '2,20p' "$0"; exit 0;;
    *) echo "unknown arg: $1" >&2; exit 64;;
  esac
done
[ "$DO_CASES$DO_TRIG$DO_BASE" = "000" ] && { DO_CASES=1; DO_TRIG=1; DO_BASE=1; }

PY=/usr/bin/python3

if [ -n "$SCORE_ONLY" ]; then
  exec $PY "$HERE/bin/score_run.py" --run-dir "$HERE/runs/$SCORE_ONLY"
fi

echo "=== STEP 1: regenerate + verify eval cases (machine, free) ==="
$PY "$HERE/bin/gen_cases.py" || { echo "case generation FAILED -- stopping"; exit 1; }
echo ""

CASES=$(ls -1 "$HERE/cases" | grep '^c[0-9]' | sort)
[ "$SMOKE" = "1" ] && CASES="c03_srm_and_maturity"
N_CASES=$(echo "$CASES" | wc -w | tr -d ' ')
CRUNS=${RUNS:-1}; TRUNS=${RUNS:-3}
N_TRIG=$($PY -c "import json;d=json.load(open('$HERE/cases/triggering.json'));print(len(d['should_fire'])+len(d['should_not_fire']))")
[ "$SMOKE" = "1" ] && N_TRIG=0 && DO_TRIG=0

TOTAL=0
[ "$DO_CASES" = "1" ] && TOTAL=$((TOTAL + N_CASES*CRUNS))
[ "$DO_BASE" = "1" ] && TOTAL=$((TOTAL + N_CASES*CRUNS))
[ "$DO_TRIG" = "1" ] && TOTAL=$((TOTAL + N_TRIG*TRUNS))

echo "=== STEP 2: plan ==="
echo "  cases            : $N_CASES x $CRUNS run(s)   with-arm=$DO_CASES baseline-arm=$DO_BASE"
echo "  triggering       : $N_TRIG x $TRUNS run(s)   enabled=$DO_TRIG"
echo "  total live runs  : $TOTAL"
echo "  est. wall clock  : ~$((TOTAL*75/60)) min sequential"
echo "  est. cost        : bounded by --max-budget-usd ${EVAL_BUDGET_USD:-0.75}/run => <= \$$(echo "$TOTAL" | awk -v b="${EVAL_BUDGET_USD:-0.75}" '{printf "%.2f", $1*b}')"
echo ""

if [ "$LIVE" != "1" ]; then
  cat <<'EOT'
=== DRY RUN -- nothing was executed live ===
The cases and goldens above are verified and ready. To measure the three axes you
must run live sessions; re-run with --live (start with --smoke).

Machine-measured without any live run: nothing on the 12-point scale. The scale
requires observing an agent, so a dry run deliberately reports no score rather
than a placeholder.
EOT
  exit 0
fi

RUN_ID=${RUN_ID:-$(date +%Y%m%d-%H%M%S)}
RD="$HERE/runs/$RUN_ID"
mkdir -p "$RD"/{with,without,triggering,prompts}
echo "=== STEP 3: live runs -> runs/$RUN_ID ==="

run_case_arm () {  # $1=case $2=arm $3=outdir [$4=suffix]
  local c="$1" arm="$2" od="$3" sfx="${4:-}"
  local wd; wd="$(mktemp -d)"
  cp "$HERE/cases/$c/inputs/"* "$wd/"
  $PY -c "import json;print(json.load(open('$HERE/cases/$c/case.json'))['prompt'],end='')" > "$wd/prompt.txt"
  cp "$wd/prompt.txt" "$RD/prompts/$c.txt"
  echo "  [$arm] $c$sfx"
  "$HERE/bin/run_one.sh" --out "$od/$c$sfx.jsonl" --prompt-file "$wd/prompt.txt" \
      --cwd "$wd" --arm "$arm" ${MODEL:+--model "$MODEL"} $ISOLATE >/dev/null 2>&1
  rm -rf "$wd"
}

if [ "$DO_CASES" = "1" ]; then
  # N>1 writes <case>.runK.jsonl so bin/score_run.py aggregates them into
  # per-criterion pass rates instead of treating them as separate cases.
  for c in $CASES; do
    if [ "$CRUNS" -le 1 ]; then
      run_case_arm "$c" with "$RD/with"
    else
      for k in $(seq 1 "$CRUNS"); do
        run_case_arm "$c" with "$RD/with" ".run$k"
      done
    fi
  done
fi
if [ "$DO_BASE" = "1" ]; then
  for c in $CASES; do run_case_arm "$c" without "$RD/without"; done
fi
if [ "$DO_TRIG" = "1" ]; then
  # Triggering runs happen in a directory that CONTAINS the input files, because
  # the arena session has them present too -- their presence is part of the
  # context the description competes in.
  TW="$(mktemp -d)"; cp "$HERE/cases/c03_srm_and_maturity/inputs/"* "$TW/"
  $PY - "$HERE" "$TW" <<'PYX'
import json, os, sys
h, tw = sys.argv[1], sys.argv[2]
d = json.load(open(os.path.join(h, "cases", "triggering.json")))
for key in ("should_fire", "should_not_fire"):
    for it in d[key]:
        open(os.path.join(tw, it["id"] + ".txt"), "w").write(it["prompt"])
PYX
  for f in "$TW"/*.txt; do
    id=$(basename "$f" .txt)
    echo "  [trigger] $id"
    "$HERE/bin/run_one.sh" --out "$RD/triggering/$id.jsonl" --prompt-file "$f" \
        --cwd "$TW" --arm with ${MODEL:+--model "$MODEL"} $ISOLATE >/dev/null 2>&1
  done
  rm -rf "$TW"
fi

echo ""
echo "=== STEP 4: score ==="
$PY "$HERE/bin/score_run.py" --run-dir "$RD" \
    --text "$RD/scorecard.txt" --json "$RD/scorecard.json"
echo ""
echo "artifacts: $RD"
