#!/usr/bin/env bash
# Consumer-shaped package smoke test (issue #13).
#
# First stage only regex.eigs + eigs.json and prove ordinary character classes
# do not need generated Unicode data.  Then derive (rather than duplicate) the
# lazy data-file inventory from regex.eigs's literal load_file targets and test
# the complete package.  Finally omit one derived file deliberately and require
# the dependent compile to fail loudly.
set -euo pipefail

EIGS="${EIGENSCRIPT:-eigenscript}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# No python3 here: the devcontainer image carries only EigenScript and a C toolchain (PR #37 failed CI on it).
PKG_NAME="$(sed -n 's/^[[:space:]]*"name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$REPO_ROOT/eigs.json" | head -1)"
[ -n "$PKG_NAME" ] || { echo "FAIL: could not read the package name from eigs.json"; exit 1; }
mapfile -t DATA_FILES < <(
    grep -oE 'load_file of "[^"]+"' "$REPO_ROOT/$PKG_NAME.eigs" |
        sed -E 's/.*"([^"]+)"/\1/' | sort -u
)

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
PKG_DIR="$TMP/eigs_modules/$PKG_NAME"
mkdir -p "$PKG_DIR"
cp "$REPO_ROOT/$PKG_NAME.eigs" "$REPO_ROOT/eigs.json" "$PKG_DIR/"

cat > "$TMP/ordinary.eigs" <<EOF_APP
import $PKG_NAME
# Consumer globals that collide with engine internals must survive the import.
pos is 99
n is 7
_peek is "consumer-peek"
define has(lst, key) as:
    for k in lst:
        if k == key:
            return 1
    return 0
print of ["range", $PKG_NAME.re_match of [$PKG_NAME.re_compile of "[a-z]+", "az"]]
print of ["negated", $PKG_NAME.re_match of [$PKG_NAME.re_compile of "[^za]+", "bc"]]
print of ["word", $PKG_NAME.re_match of [$PKG_NAME.re_compile of "\\\\w+", "A_9"]]
prog is $PKG_NAME.re_compile of "[a-z]+([0-9])"
print of ["match", $PKG_NAME.re_match of [prog, "abc7"]]
print of ["search", $PKG_NAME.re_search of [prog, "  abc7  "]]
print of ["find_all_n", len of ($PKG_NAME.re_find_all of [prog, "a1 b2 c3"])]
dp is $PKG_NAME.re_compile of "[0-9]+"
print of ["replace", $PKG_NAME.re_replace of [dp, "a1 b22 c", "#"]]
ks is keys of $PKG_NAME
print of ["surface_ok", (has of [ks, "re_compile"]) and (has of [ks, "re_replace"])]
print of ["_peek_private", 1 - (has of [ks, "_peek"])]
print of ["_rx_parse_private", 1 - (has of [ks, "_rx_parse"])]
print of ["pos_intact", pos == 99]
print of ["consumer_peek_intact", _peek == "consumer-peek"]
EOF_APP

cd "$TMP"
ORDINARY_OUT="$("$EIGS" ordinary.eigs 2>&1)"
printf '%s\n' '--- minimal package (regex.eigs + eigs.json)' "$ORDINARY_OUT"
for expected in \
    '["range", 1]' \
    '["negated", 1]' \
    '["word", 1]' \
    '["match", 1]' \
    '["find_all_n", 3]' \
    '["replace", "a# b# c"]' \
    '["surface_ok", 1]' \
    '["_peek_private", 1]' \
    '["_rx_parse_private", 1]' \
    '["pos_intact", true]' \
    '["consumer_peek_intact", true]'; do
    if ! grep -qF "$expected" <<<"$ORDINARY_OUT"; then
        echo "FAIL: minimal package missing $expected"
        exit 1
    fi
done
echo 'PASS: ordinary classes need no data file'

printf '%s\n' "derived data files: ${DATA_FILES[*]}"
if [ "${#DATA_FILES[@]}" -ne 2 ]; then
    echo "FAIL: expected exactly two literal load_file targets"
    exit 1
fi
for file in "${DATA_FILES[@]}"; do
    cp "$REPO_ROOT/$file" "$PKG_DIR/"
done

cat > "$TMP/unicode.eigs" <<EOF_APP
import $PKG_NAME
print of ["property", $PKG_NAME.re_match of [$PKG_NAME.re_compile of "\\\\p{L}+", "É"]]
print of ["icase", $PKG_NAME.re_match of [$PKG_NAME.re_compile of "(?i)k", "K"]]
EOF_APP
UNICODE_OUT="$("$EIGS" unicode.eigs 2>&1)"
printf '%s\n' '--- full derived package' "$UNICODE_OUT"
for expected in '["property", 1]' '["icase", 1]'; do
    if ! grep -qF "$expected" <<<"$UNICODE_OUT"; then
        echo "FAIL: full package missing $expected"
        exit 1
    fi
done
echo 'PASS: Unicode property and case-fold data load lazily'

# Deliberate uncommitted plant: remove a derived table in the temporary stage,
# invoke its feature, and reject either a zero exit or a quiet diagnostic.
PLANT="${DATA_FILES[0]}"
rm "$PKG_DIR/$PLANT"
set +e
PLANT_OUT="$("$EIGS" unicode.eigs 2>&1)"
PLANT_RC=$?
set -e
printf '%s\n' "--- omission plant ($PLANT removed; failure expected)" "$PLANT_OUT" "plant exit: $PLANT_RC"
if [ "$PLANT_RC" -eq 0 ] || [ -z "$PLANT_OUT" ]; then
    echo "FAIL: omitted derived data file did not fail loudly"
    exit 1
fi
echo 'PASS: omitted derived data file fails loudly'
echo 'PASS: package smoke — minimal and full package shapes'
