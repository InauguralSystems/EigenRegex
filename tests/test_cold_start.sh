#!/usr/bin/env bash
# Each probe gets a fresh runtime: its feature is the first regex compiled.
set -uo pipefail
EIGS="${EIGENSCRIPT:-eigenscript}"
cd "$(dirname "$0")/.."
fail=0
for probe in negated icase shorthand property replace; do
    out=$("$EIGS" "tests/cold_start/$probe.eigs" 2>&1); rc=$?
    printf '%s\n' "$out"
    if [ "$rc" -ne 0 ] || printf '%s\n' "$out" | grep -q 'FAIL'; then
        fail=1
    fi
done
exit "$fail"
