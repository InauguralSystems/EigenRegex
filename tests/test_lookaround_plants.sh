#!/usr/bin/env bash
# Mutation self-test for the five issue-36 lookaround failure modes.
set -u
EIGS="${EIGENSCRIPT:-eigenscript}"
ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
tmp="${TMPDIR:-/tmp}/eigenregex-lookaround-plants.$$"
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
mkdir "$tmp" || exit 1
fail=0

ir_run() {
    dir=$1 mode=$2 row=$3 size=$4 tag=$5
    out="$tmp/$tag.out"
    log="$tmp/$tag.log"
    (cd "$dir" && valgrind --tool=cachegrind --cachegrind-out-file="$out" \
        --log-file="$log" "$EIGS" tests/test_re2_linear.eigs "$mode" "$row" "$size") \
        >"$tmp/$tag.stdout" 2>&1
    rc=$?
    if [ "$rc" -ne 0 ] || grep -q 'FAIL' "$tmp/$tag.stdout"; then
        cat "$tmp/$tag.stdout" >&2
        return 1
    fi
    awk '/^summary:/ { print $2; found=1 } END { if (!found) exit 1 }' "$out"
}

linear_ratios() {
    dir=$1 row=$2 label=$3
    sizes=${4:-"128 256 512 1024"}
    prior=
    last=
    for n in $sizes; do
        call=$(ir_run "$dir" CALL "$row" "$n" "$label-call-$n") || return 1
        base=$(ir_run "$dir" BASE "$row" "$n" "$label-base-$n") || return 1
        ir=$((call - base))
        if [ "$ir" -le 0 ]; then
            echo "plant-linearity $label n=$n delta_Ir=$ir FAIL" >&2
            return 1
        fi
        ratio=-
        if [ -n "$prior" ]; then
            ratio=$(awk -v now="$ir" -v old="$prior" 'BEGIN { printf "%.3f", now / old }')
            last=$ratio
        fi
        printf 'plant-linearity %-24s n=%4d Ir_call=%12d Ir_base=%12d delta_Ir=%12d ratio=%s\n' \
            "$label" "$n" "$call" "$base" "$ir" "$ratio"
        prior=$ir
    done
    LINEAR_LAST=$last
}

cp -R "$ROOT/." "$tmp/control" || exit 1
control=$(cd "$tmp/control" && "$EIGS" tests/lookaround_plant_witness.eigs all 2>&1)
printf '%s\n' "$control"
if printf '%s\n' "$control" | grep -q 'FAIL'; then
    echo "clean control FAIL"
    exit 1
fi
echo "clean control PASS"

# L3 clean controls use the same Cachegrind instrument and sizes as the two
# planted runs below.  Their final ratios must remain in L1's linear band.
linear_ratios "$tmp/control" 7 control-ahead || exit 1
if ! awk -v r="$LINEAR_LAST" 'BEGIN { exit !(r >= 1.60 && r <= 2.25) }'; then
    echo "clean control ahead ratio=$LINEAR_LAST outside [1.60,2.25] FAIL"
    exit 1
fi
linear_ratios "$tmp/control" 8 control-find-all || exit 1
if ! awk -v r="$LINEAR_LAST" 'BEGIN { exit !(r >= 1.60 && r <= 2.25) }'; then
    echo "clean control find-all ratio=$LINEAR_LAST outside [1.60,2.25] FAIL"
    exit 1
fi
echo "clean linearity controls PASS"

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

plant seed seed 'local sp is 0\n    loop while sp <= n:\n        if (_is_scalar_boundary of [text, sp]) == 1:' 'local sp is 0\n    loop while sp <= n:\n        if sp == 0:'
plant resume resume 'local results is []\n    if prog == null:\n        return results\n    _prepare_lookarounds of [prog, text]\n    local pos is 0\n    local n is len of text\n    loop while pos <= n:\n        local caps is _rx_vm_run of [prog, text, pos, 0]' 'local results is []\n    if prog == null:\n        return results\n    _prepare_lookarounds of [prog, text]\n    local pos is 0\n    local n is len of text\n    loop while pos <= n:\n        if pos > 0:\n            for table in _rx_lookaround_tables:\n                table[pos] is 0\n        local caps is _rx_vm_run of [prog, text, pos, 0]'
plant negative negative 'if succeeded == inst[2]:' 'if succeeded == 1:'
plant ahead-shift ahead-shift 'table[sp] is 1\n            elif op == "char" and sp > 0' 'if sp > 0:\n                    table[sp - 1] is 1\n            elif op == "char" and sp > 0'
plant ahead-utf8 ahead-utf8 'append of [atoms, ["byte", bytes[j]]]' 'append of [atoms, ["byte", bytes[(len of bytes) - 1 - j]]]'

plant_linear() {
    name=$1 row=$2 old=$3 new=$4
    sizes=${5:-"128 256 512 1024"}
    dir="$tmp/$name"
    cp -R "$ROOT/." "$dir" || return 1
    python3 - "$dir/regex.eigs" "$old" "$new" <<'PY'
import sys
from pathlib import Path
p = Path(sys.argv[1])
data = p.read_text()
old, new = sys.argv[2].replace(r"\n", "\n"), sys.argv[3].replace(r"\n", "\n")
if data.count(old) != 1:
    raise SystemExit(f"plant target count is {data.count(old)}, expected 1")
p.write_text(data.replace(old, new))
PY
    if cmp -s "$ROOT/regex.eigs" "$dir/regex.eigs"; then
        echo "plant $name left copy unchanged FAIL"
        fail=1
        return
    fi
    echo "plant $name changed copied program PASS"
    if ! linear_ratios "$dir" "$row" "$name" "$sizes"; then
        echo "plant $name measurement FAIL"
        fail=1
        return
    fi
    if awk -v r="$LINEAR_LAST" 'BEGIN { exit !(r >= 3.0) }'; then
        echo "plant $name last-ratio=$LINEAR_LAST >=3.0 red PASS"
    else
        echo "plant $name last-ratio=$LINEAR_LAST below 3.0 FAIL"
        fail=1
    fi
}

# Re-run the complete reverse-pass table as a sub-search for every possible
# assertion position.  This deliberately turns (?=a*c) over a^n quadratic.
plant_linear ahead-per-position 7 \
    'table is _lookahead_table of [item[1], text]' \
    'table is _lookahead_table of [item[1], text]\n            local plant_sp is 0\n            loop while plant_sp <= (len of text):\n                local plant_subsearch is plant_sp\n                loop while plant_subsearch < (len of text) and (char_at of [text, plant_subsearch]) != "c":\n                    plant_subsearch is plant_subsearch + 1\n                plant_sp is plant_sp + 1'

# Public find_all prepares once, then calls _rx_vm_run at every resume.  This
# plant defeats that reuse by preparing again inside every VM search.
plant_linear ahead-per-search 8 \
    'define _rx_vm_run(args) as:\n    local prog is args[0]\n    local text is args[1]' \
    'define _rx_vm_run(args) as:\n    local prog is args[0]\n    local text is args[1]\n    _prepare_lookarounds of [prog, text]' \
    '128 256'

if [ "$fail" -eq 0 ]; then
    echo "lookaround plants PASS"
else
    echo "lookaround plants FAIL"
fi
exit "$fail"
