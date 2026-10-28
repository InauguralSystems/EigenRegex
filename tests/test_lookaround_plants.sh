#!/usr/bin/env bash
# Mutation self-test for the three issue-36a lookbehind failure modes.
set -u
EIGS="${EIGENSCRIPT:-eigenscript}"
ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
tmp="${TMPDIR:-/tmp}/eigenregex-lookbehind-plants.$$"
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
mkdir "$tmp" || exit 1
fail=0

cp -R "$ROOT/." "$tmp/control" || exit 1
control=$(cd "$tmp/control" && "$EIGS" tests/lookaround_plant_witness.eigs all 2>&1)
printf '%s\n' "$control"
if printf '%s\n' "$control" | grep -q 'FAIL'; then
    echo "clean control FAIL"
    exit 1
fi
echo "clean control PASS"

plant() {
    name=$1 witness=$2 old=$3 new=$4
    dir="$tmp/$name"
    cp -R "$ROOT/." "$dir" || return 1
    python3 - "$dir/regex.eigs" "$old" "$new" <<'PY'
import sys
from pathlib import Path
p=Path(sys.argv[1]); data=p.read_text(); old=sys.argv[2].replace(r"\n","\n"); new=sys.argv[3].replace(r"\n","\n")
if data.count(old) != 1: raise SystemExit(f"plant target count is {data.count(old)}, expected 1")
p.write_text(data.replace(old,new))
PY
    if cmp -s "$ROOT/regex.eigs" "$dir/regex.eigs"; then
        echo "plant $name left copy unchanged FAIL"
        fail=1
        return
    fi
    out=$(cd "$dir" && "$EIGS" tests/lookaround_plant_witness.eigs "$witness" 2>&1)
    printf '%s\n' "$out"
    if printf '%s\n' "$out" | grep -q 'FAIL'; then
        echo "plant $name red PASS"
    else
        echo "plant $name stayed green FAIL"
        fail=1
    fi
}

plant seed seed 'if (_is_scalar_boundary of [text, sp]) == 1:' 'if sp == 0:'
plant resume resume 'local results is []\n    if prog == null:\n        return results\n    _prepare_lookbehinds of [prog, text]\n    local pos is 0\n    local n is len of text\n    loop while pos <= n:\n        local caps is _rx_vm_run of [prog, text, pos, 0]' 'local results is []\n    if prog == null:\n        return results\n    _prepare_lookbehinds of [prog, text]\n    local pos is 0\n    local n is len of text\n    loop while pos <= n:\n        if pos > 0:\n            for table in _rx_lookbehind_tables:\n                table[pos] is 0\n        local caps is _rx_vm_run of [prog, text, pos, 0]'
plant negative negative 'if succeeded == inst[2]:' 'if succeeded == 1:'

if [ "$fail" -eq 0 ]; then
    echo "lookbehind plants PASS"
else
    echo "lookbehind plants FAIL"
fi
exit "$fail"
