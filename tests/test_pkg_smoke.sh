#!/usr/bin/env bash
# Consumer-shaped package smoke test (issue #13).
#
# Stages EigenRegex the way `eigenscript --pkg add owner/regex <url>` would —
# cloned into eigs_modules/regex/ with just the root regex.eigs + eigs.json —
# then a consumer `import regex`s it and exercises the public surface. Also
# asserts the engine internals stay PRIVATE (the whole point of packaging:
# a consumer's own `_peek`/`pos`/`n` can't collide with the engine's).
set -euo pipefail

EIGS="${EIGENSCRIPT:-eigenscript}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PKG_NAME="$(python3 -c 'import json;print(json.load(open("eigs.json"))["name"])' <"$REPO_ROOT/eigs.json" 2>/dev/null || echo regex)"

TMP="$(mktemp -d)"
trap "rm -rf '$TMP'" EXIT

# A package ships ONLY its root <name>.eigs + eigs.json — no lib/ dir.
mkdir -p "$TMP/eigs_modules/$PKG_NAME"
cp "$REPO_ROOT/$PKG_NAME.eigs" "$TMP/eigs_modules/$PKG_NAME/"
cp "$REPO_ROOT/eigs.json"      "$TMP/eigs_modules/$PKG_NAME/"

cat > "$TMP/app.eigs" <<EOF
import $PKG_NAME
# Consumer globals that collide with engine internals — must all survive.
pos is 99
n is 7
_peek is "consumer-peek"

# Portable list-membership (list_contains is a newer builtin; keep this
# working against the CI-pinned runtime too).
define has(lst, key) as:
    for k in lst:
        if k == key:
            return 1
    return 0

prog is $PKG_NAME.re_compile of "[a-z]+([0-9])"
print of ["match", $PKG_NAME.re_match of [prog, "abc7"]]
print of ["search", $PKG_NAME.re_search of [prog, "  abc7  "]]
print of ["find_all_n", len of ($PKG_NAME.re_find_all of [prog, "a1 b2 c3"])]
dp is $PKG_NAME.re_compile of "[0-9]+"
print of ["replace", $PKG_NAME.re_replace of [dp, "a1 b22 c", "#"]]
print of ["compat_find", $PKG_NAME.compat_find of ["a1 b2", "[a-z][0-9]"]]

ks is keys of $PKG_NAME
print of ["surface_ok", (has of [ks, "re_compile"]) and (has of [ks, "compat_match"])]
print of ["_peek_private", 1 - (has of [ks, "_peek"])]
print of ["_rx_parse_private", 1 - (has of [ks, "_rx_parse"])]
print of ["pos_intact", pos == 99]
print of ["consumer_peek_intact", _peek == "consumer-peek"]
EOF

cd "$TMP"
OUT="$("$EIGS" app.eigs 2>&1)"
echo "$OUT"

fail=0
check() { # <label-substring> <expected-line>
    if ! printf '%s\n' "$OUT" | grep -qF "$2"; then
        echo "FAIL: $1"; fail=1
    fi
}
check "anchored match"        '["match", 1]'
check "find_all count"        '["find_all_n", 3]'
check "replace"               '["replace", "a# b# c"]'
check "compat_find shape"     '["compat_find", ["a1", "b2"]]'
check "public surface"        '["surface_ok", 1]'
check "_peek stays private"   '["_peek_private", 1]'
check "_rx_parse private"     '["_rx_parse_private", 1]'
check "caller pos intact"     '["pos_intact", 1]'
check "caller _peek intact"   '["consumer_peek_intact", 1]'

if [ "$fail" -eq 0 ]; then
    echo "PASS: package smoke — import regex composes with zero global collisions"
else
    echo "SOME FAILED (package smoke)"
fi
exit "$fail"
