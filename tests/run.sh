#!/usr/bin/env bash
# Run every EigenRegex test program against $EIGENSCRIPT and fail the build if
# any assertion prints FAIL or any script errors / crashes. The per-stage tests
# print "<label> OK" / "<label> FAIL" lines but exit 0 regardless, so this
# wrapper is what turns them into a CI gate. (bench_search.eigs is a manual
# timing bench, not a test — the glob below excludes it.)
set -uo pipefail
EIGS="${EIGENSCRIPT:-eigenscript}"
cd "$(dirname "$0")/.."

fail=0
total_ok=0
# test_s*.eigs covers test_s1..s5 AND test_smoke; bench_search.eigs is excluded.
for t in tests/test_s*.eigs; do
    out=$("$EIGS" "$t" 2>&1); rc=$?
    ok=$(printf '%s\n' "$out" | grep -c ' OK$' || true)
    bad=$(printf '%s\n' "$out" | grep -c 'FAIL' || true)
    if [ "$rc" -ne 0 ] || [ "$bad" -ne 0 ]; then
        echo "FAIL: $(basename "$t") (rc=$rc, $bad failing checks)"
        printf '%s\n' "$out" | grep -iE 'FAIL|error' | head -5
        fail=1
    else
        echo "PASS: $(basename "$t") ($ok checks)"
        total_ok=$((total_ok + ok))
    fi
done

echo "---"
# Cold-start regressions: one new EigenScript process per first-use probe.
if ! EIGENSCRIPT="$EIGS" bash tests/test_cold_start.sh; then
    echo "FAIL: test_cold_start.sh"
    fail=1
else
    echo "PASS: test_cold_start.sh"
fi

echo "---"
# Issue #35/#51 pathological Pike-VM scaling gate (Cachegrind Ir).
out=$(EIGENSCRIPT="$EIGS" bash tests/test_re2_linear.sh 2>&1); rc=$?
printf '%s\n' "$out"
if [ "$rc" -ne 0 ] || printf '%s\n' "$out" | grep -q 'FAIL'; then
    echo "FAIL: test_re2_linear.sh"
    fail=1
else
    echo "PASS: test_re2_linear.sh"
fi

echo "---"
# Issue #36a mutation witnesses for lookbehind state and polarity.
if ! EIGENSCRIPT="$EIGS" bash tests/test_lookaround_plants.sh; then
    echo "FAIL: test_lookaround_plants.sh"
    fail=1
else
    echo "PASS: test_lookaround_plants.sh"
fi

echo "---"
# Consumer-shaped package smoke: stage into eigs_modules/ and `import regex`.
EIGENSCRIPT="$EIGS" bash "$(dirname "$0")/test_pkg_smoke.sh" >/tmp/pkg_smoke.$$ 2>&1
smoke_rc=$?
if [ "$smoke_rc" -ne 0 ]; then
    # Print the smoke test's own last lines, never a grep for the failure we expected: an early exit that printed
    # no FAIL/error line once left CI showing nothing but this header (PR #37, round 10).
    echo "FAIL: test_pkg_smoke.sh (rc=$smoke_rc; last 40 lines follow)"
    tail -40 /tmp/pkg_smoke.$$ | sed 's/^/  | /'
    fail=1
else
    echo "PASS: test_pkg_smoke.sh"
fi
rm -f /tmp/pkg_smoke.$$

echo "---"
if [ "$fail" -eq 0 ]; then
    echo "ALL PASSED ($total_ok checks + package smoke)"
else
    echo "SOME FAILED"
fi
exit "$fail"
