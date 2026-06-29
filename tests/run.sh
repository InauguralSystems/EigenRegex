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
if [ "$fail" -eq 0 ]; then
    echo "ALL PASSED ($total_ok checks)"
else
    echo "SOME FAILED"
fi
exit "$fail"
