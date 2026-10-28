#!/usr/bin/env bash
# Cachegrind instruction-count gate for the pathological Pike-VM rows.
set -u
EIGS="${EIGENSCRIPT:-eigenscript}"
cd "$(dirname "$0")/.."

tmp="${TMPDIR:-/tmp}/eigenregex-linear.$$"
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
mkdir "$tmp" || exit 1
fail=0

ir_run() {
    mode=$1 row=$2 size=$3 tag=$4
    out="$tmp/$tag.out"
    log="$tmp/$tag.log"
    valgrind --tool=cachegrind --cachegrind-out-file="$out" --log-file="$log" \
        "$EIGS" tests/test_re2_linear.eigs "$mode" "$row" "$size" >"$tmp/$tag.stdout" 2>&1
    rc=$?
    cat "$tmp/$tag.stdout" >&2
    if [ "$rc" -ne 0 ] || grep -q 'FAIL' "$tmp/$tag.stdout"; then
        echo "measurement row=$row size=$size mode=$mode FAIL" >&2
        return 1
    fi
    awk '/^summary:/ { print $2; found=1 } END { if (!found) exit 1 }' "$out"
}

echo "Cachegrind Ir gate: delta = Ir(CALL) - Ir(BASE); limits 1.70 <= doubling ratio <= 2.35"
printf '%-10s %7s %14s %14s %14s %7s\n' feature n Ir_call Ir_base delta_Ir ratio
for row in 0 1 2; do
    case $row in
        0) feature=boundary ;;
        1) feature=casefold ;;
        2) feature=named ;;
    esac
    prior=
    for n in 128 256 512 1024; do
        call=$(ir_run CALL "$row" "$n" "call-$row-$n") || { echo "cachegrind CALL feature=$feature size=$n FAIL"; fail=1; continue; }
        base=$(ir_run BASE "$row" "$n" "base-$row-$n") || { echo "cachegrind BASE feature=$feature size=$n FAIL"; fail=1; continue; }
        delta=$((call - base))
        ratio=-
        if [ "$delta" -le 0 ]; then
            echo "work feature=$feature size=$n delta_Ir=$delta FAIL"
            fail=1
        elif [ -n "$prior" ]; then
            ratio=$(awk -v now="$delta" -v old="$prior" 'BEGIN { printf "%.3f", now / old }')
            if ! awk -v r="$ratio" 'BEGIN { exit !(r >= 1.70 && r <= 2.35) }'; then
                echo "ratio feature=$feature size=$n value=$ratio limits=[1.70,2.35] FAIL"
                fail=1
            fi
        fi
        printf '%-10s %7d %14d %14d %14d %7s\n' "$feature" "$n" "$call" "$base" "$delta" "$ratio"
        prior=$delta
    done
done

aa1=$(ir_run CALL 0 128 aa-1) || fail=1
aa2=$(ir_run CALL 0 128 aa-2) || fail=1
if [ -n "$aa1" ] && [ "$aa1" = "$aa2" ]; then
    echo "A/A feature=boundary size=128 Ir=$aa1/$aa2 identical OK"
else
    echo "A/A feature=boundary size=128 Ir=$aa1/$aa2 identical FAIL"
    fail=1
fi

if [ "$fail" -eq 0 ]; then
    echo "linearity Cachegrind gate OK"
else
    echo "linearity Cachegrind gate FAIL"
fi
exit "$fail"
