#!/bin/bash
# One entrypoint for the experiment-readout test suite.
#
#   tests/run_tests.sh              run everything
#   tests/run_tests.sh -q           quiet (dots instead of per-test names)
#   tests/run_tests.sh -k srm       only tests whose name matches a substring
#   tests/run_tests.sh test_40_suppression   only one module
#
# stdlib only: /usr/bin/python3 + unittest. No pytest, no scipy, no numpy.

set -u

PY=/usr/bin/python3
TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(dirname "$TESTS_DIR")"
UNIT_DIR="$TESTS_DIR/unit"
FIX_DIR="$TESTS_DIR/fixtures"
SCRIPTS_DIR="$SKILL_ROOT/scripts"

bar() { printf '%s\n' "------------------------------------------------------------------------"; }

bar
echo "experiment-readout test suite"
echo "  skill root : $SKILL_ROOT"
echo "  python     : $("$PY" -V 2>&1)"
bar

# --- 1. implementation presence check (informational, never fatal) ----------
missing=0
for f in gates.py run_readout.py power.py; do
  if [ -f "$SCRIPTS_DIR/$f" ]; then
    echo "  FOUND    scripts/$f"
  else
    echo "  MISSING  scripts/$f"
    missing=$((missing + 1))
  fi
done
if [ "$missing" -gt 0 ]; then
  bar
  echo "WARNING: $missing implementation file(s) missing."
  echo "The suite will still run and will report each dependent test as a"
  echo "clean FAILURE naming the missing file (not a traceback)."
fi
bar

# --- 2. regenerate fixtures and prove the generator is deterministic --------
before=""
if [ -f "$FIX_DIR/manifest.json" ]; then
  before=$("$PY" -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" "$FIX_DIR/manifest.json")
fi
echo "regenerating fixtures from seed ..."
if ! "$PY" "$FIX_DIR/generate_fixtures.py"; then
  echo "FATAL: fixture generation failed" >&2
  exit 2
fi
after=$("$PY" -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" "$FIX_DIR/manifest.json")
if [ -n "$before" ] && [ "$before" != "$after" ]; then
  echo "NOTE: manifest.json changed on regeneration (generator was edited)."
else
  echo "fixture manifest is reproducible (sha256 ${after:0:16}...)"
fi
bar

# --- 3. run the suite -------------------------------------------------------
VERBOSITY="-v"
PATTERN=""
FILTER=""
for arg in "$@"; do
  case "$arg" in
    -q) VERBOSITY="" ;;
    -k) FILTER="__NEXT__" ;;
    test_*) PATTERN="$arg" ;;
    *) if [ "$FILTER" = "__NEXT__" ]; then FILTER="$arg"; fi ;;
  esac
done

CMD=("$PY" -m unittest)
if [ -n "$PATTERN" ]; then
  CMD+=("$PATTERN")
else
  CMD+=(discover -s "$UNIT_DIR" -t "$UNIT_DIR" -p "test_*.py")
fi
[ -n "$VERBOSITY" ] && CMD+=("$VERBOSITY")
if [ -n "$FILTER" ] && [ "$FILTER" != "__NEXT__" ]; then
  CMD+=(-k "$FILTER")
fi

LOG="$(mktemp -t experiment-readout-tests)"
cd "$UNIT_DIR" || exit 2
"${CMD[@]}" 2>&1 | tee "$LOG"
rc=${PIPESTATUS[0]}

# --- 4. summary -------------------------------------------------------------
bar
"$PY" - "$LOG" "$rc" <<'PYEOF'
import re, sys
log, rc = sys.argv[1], int(sys.argv[2])
text = open(log, errors="replace").read()

ran = re.search(r"^Ran (\d+) tests? in ([\d.]+)s", text, re.M)
total = int(ran.group(1)) if ran else 0
fails = len(re.findall(r"^FAIL: ", text, re.M))
errors = len(re.findall(r"^ERROR: ", text, re.M))
skips = len(re.findall(r"^SKIP: ", text, re.M))
passed = max(total - fails - errors - skips, 0)

print("SUMMARY")
print("  total   %d" % total)
print("  passed  %d" % passed)
print("  failed  %d" % fails)
print("  errors  %d" % errors)
if skips:
    print("  skipped %d" % skips)
if ran:
    print("  time    %ss" % ran.group(2))

names = re.findall(r"^(?:FAIL|ERROR): (\S+) \(([^)]+)\)", text, re.M)
if names:
    print("")
    print("FAILING TESTS (%d):" % len(names))
    for meth, cls in names:
        print("  %s.%s" % (cls, meth))

# Call out suppression failures specifically -- they are the headline behaviour.
supp = [ (m, c) for m, c in names if "suppression" in c.lower() or "NotRun" in c ]
if supp:
    print("")
    print("!! %d SUPPRESSION TEST(S) FAILING -- a conclusion may be leaking out"
          % len(supp))
    print("!! of an invalid readout. This is the behaviour the skill exists for.")

print("")
print("RESULT: %s" % ("PASS" if rc == 0 else "FAIL"))
PYEOF
bar
rm -f "$LOG"
exit "$rc"
