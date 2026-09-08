#!/usr/bin/env bash
# Run ONE (prompt, arm) pair as a fresh non-interactive Claude Code session and
# capture the full stream-json trace.
#
# WHY THIS IS A REAL TRIGGERING TEST
#   `claude -p` starts a fresh session. Skill metadata (name + description) is
#   pre-loaded into the system prompt exactly as in an interactive session, and
#   nothing in the prompt names the skill. So if the Skill tool is dispatched,
#   that is genuine unprompted triggering, not a scripted call.
#
# WHERE IT DIFFERS FROM THE ARENA  (stated so the scorecard is not over-read)
#   * one user turn, no conversational history
#   * this machine's full user skill set is loaded, so ~20 other skills compete
#     for the trigger. Pass --isolate to run against a config dir containing
#     ONLY the skill under test, which is closer to the arena.
#   * permissions are pre-granted; an interactive user might decline a Bash call
#
# usage: run_one.sh --out FILE --prompt-file FILE [--cwd DIR] [--arm with|without]
#                   [--model M] [--isolate] [--explicit]
set -u
ARM=with; MODEL=""; CWD="$PWD"; OUT=""; PROMPT_FILE=""; ISOLATE=0; EXPLICIT=0
while [ $# -gt 0 ]; do
  case "$1" in
    --out) OUT="$2"; shift 2;;
    --prompt-file) PROMPT_FILE="$2"; shift 2;;
    --cwd) CWD="$2"; shift 2;;
    --arm) ARM="$2"; shift 2;;
    --model) MODEL="$2"; shift 2;;
    --isolate) ISOLATE=1; shift;;
    --explicit) EXPLICIT=1; shift;;
    *) echo "unknown arg: $1" >&2; exit 64;;
  esac
done
[ -n "$OUT" ] && [ -n "$PROMPT_FILE" ] || { echo "need --out and --prompt-file" >&2; exit 64; }

SKILL_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"     # .../skills/experiment-readout
PROMPT="$(cat "$PROMPT_FILE")"
if [ "$EXPLICIT" = "1" ]; then
  PROMPT="/experiment-readout
$PROMPT"
fi

ARGS=(-p --output-format stream-json --verbose --no-session-persistence
      --permission-mode bypassPermissions --max-budget-usd "${EVAL_BUDGET_USD:-0.75}")
[ -n "$MODEL" ] && ARGS+=(--model "$MODEL")

# ---- arm construction -----------------------------------------------------
# without-arm: --safe-mode disables ALL customizations including skills. It is
# blunter than we would like (it also drops CLAUDE.md and hooks), but it is the
# only documented flag that is guaranteed to remove skills from the system
# prompt. Using a narrower flag that only hides the /slash surface would leave
# the description in context and silently invalidate the baseline.
TMPCFG=""
if [ "$ARM" = "without" ]; then
  ARGS+=(--safe-mode)
elif [ "$ISOLATE" = "1" ]; then
  TMPCFG="$(mktemp -d)"
  mkdir -p "$TMPCFG/skills"
  ln -s "$SKILL_ROOT" "$TMPCFG/skills/$(basename "$SKILL_ROOT")"
  export CLAUDE_CONFIG_DIR="$TMPCFG"
fi

mkdir -p "$(dirname "$OUT")"
START=$(date +%s)
( cd "$CWD" && printf '%s' "$PROMPT" | claude "${ARGS[@]}" ) > "$OUT" 2> "$OUT.stderr"
RC=$?
END=$(date +%s)

[ -n "$TMPCFG" ] && rm -rf "$TMPCFG"
cat > "$OUT.meta.json" <<META
{"arm": "$ARM", "rc": $RC, "seconds": $((END-START)), "isolate": $ISOLATE,
 "explicit": $EXPLICIT, "model": "${MODEL:-default}", "cwd": "$CWD",
 "prompt_file": "$PROMPT_FILE"}
META
exit $RC
