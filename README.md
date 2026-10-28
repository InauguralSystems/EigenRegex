# EigenRegex

A Pike-VM regex engine written in EigenScript.

Dual purpose:
1. A working regex library for EigenScript programs.
2. A forcing function — every ergonomic friction point or runtime gap encountered while building it gets logged in `GAPS.md` for upstream fixes in EigenScript itself.

## Status

S8 complete (ERE parity). Working: literals, concat, `|`, `( )`, `* + ?`
and `{n} {n,} {n,m}` (all greedy + lazy), `.`, `[abc]`, `[^abc]`, `[a-z]`,
POSIX `[[:alpha:]]`-style classes, escapes (`\.` `\w` `\W` `\s` `\S`),
`^`, `$`, numbered capture groups, and `re_replace`.
The test suite covers S1–S13 plus a consumer-shaped package smoke test.

Packaged for `import` (issue #13): the package consists of `regex.eigs`,
`eigs.json`, and the two lazily loaded data files `unicode_categories.eigs` and
`unicode_casefold.eigs`. Its internals namespace under `regex.*` and never
collide with a consumer's globals. Ordinary classes and shorthands need only
`regex.eigs` and `eigs.json`; `\p{...}` and `(?i)` load their respective data
tables on first use.

## Supported

- Literal characters and escaped metacharacters (`\.` `\*` `\\` …)
- Concatenation
- Alternation `|`
- Grouping `( ... )`
- Repetition `*`, `+`, `?`, `{n}`, `{n,}`, `{n,m}` (greedy and lazy)
- Char classes: `.`, `[abc]`, `[^abc]`, `[a-z]`, POSIX `[[:alpha:]]` etc.,
  `\d` `\D` `\w` `\W` `\s` `\S` (RE2 ASCII semantics: digit is
  `[0-9]`, word is `[A-Za-z0-9_]`, and space is `[\t-\r ]`; uppercase forms
  are their Unicode-scalar complements)
- Anchors `^`, `$`
- Capturing groups (numbered and `(?P<name>...)` named groups)
- ASCII word-boundary assertions `\b` and `\B` (RE2 semantics: Unicode
  letters are non-word characters)
- Unicode-aware simple case folding via `(?i)` or `re_compile([pattern, "i"])`
- Unicode general-category properties `\p{L}`, `\P{Nd}`, etc. (Unicode 15.0.0, generated from pinned UCD files)

## Not supported

The RE2 differential is generated with the pinned `google-re2==1.1.20251105`
oracle. Unicode categories and simple case folds come from the pinned Unicode
15.0.0 `UnicodeData.txt` and `CaseFolding.txt` inputs in `tools/ucd/`, whose
SHA-256 digests are enforced by the generator.

- Backreferences (would force backtracking; out of scope for Pike-VM)
- Lookahead / lookbehind
- Unicode property escapes inside compound character classes (for example,
  `[\p{L}0-9]`); these are rejected rather than silently miscompiled
- General categories outside the listed `L`, `Lu`, `Ll`, `Lt`, `Lm`, `Lo`,
  `N`, `Nd`, `Nl`, `No`, `P`, `S`, and `Z` set, including `M*`, `C*`,
  `Zs`/`Zl`/`Zp`, and the `P*`/`S*` subcategories

## Layout

- `regex.eigs` — the package: parse → compile → Pike-VM → public API, one
  importable file. Public surface (namespaced under `regex.*`):
  - spans-shaped: `re_compile`, `re_match`, `re_search`, `re_find_all`,
    `re_replace`, `re_search_named`, `re_group_names`, `re_compile_error`
  - everything else (`_rx_parse`, `_peek`, …) is `_`-private to the module
- `unicode_categories.eigs` — lazy generated data for `\p{...}`
- `unicode_casefold.eigs` — lazy generated data for `(?i)`
- `eigs.json` — package manifest (`name: regex`)
- `tests/` — per-stage tests + `test_pkg_smoke.sh` (consumer-shaped)

## Coexists with the EigenScript builtin

EigenScript already exposes `regex_match` / `regex_find` / `regex_replace`
as native builtins backed by libc POSIX regex. EigenRegex's public API
uses the `re_*` prefix so both can be used in the same script:

| | builtin (`regex_*`) | EigenRegex (`re_*`) |
| --- | --- | --- |
| backend | libc POSIX ERE in C | Pike-VM in EigenScript |
| speed | native, fast | interpreted, ~100–1000× slower |
| worst case | can backtrack catastrophically | guaranteed O(n·m) |
| features | POSIX ERE + GNU `\w \s \b` | ERE parity + RE2 ASCII `\d \w \s` (and complements), `\b`, named groups, case folding; lazy quantifiers extra |
| match rule | leftmost-longest (POSIX) | leftmost-first (Pike-VM priority) |
| return shape | substring list | positional spans `[s, e, ...]` |

Pick the builtin for hot paths; pick `re_*` when you need a linear-time
guarantee or are running in a no-libc environment. The `re_*` API uses
positional spans rather than the builtins' substring-list return shape.

## Install

```
eigenscript --pkg add InauguralSystems/regex https://github.com/InauguralSystems/EigenRegex v0.1.0
```

This clones the package into `eigs_modules/regex/` and records the
resolved commit in `eigs.lock.json`. Then `import regex` in your code.

## Usage

The Unicode tables are regenerated with `python tools/gen_unicode_categories.py`. The generator downloads Unicode 15.0 `UnicodeData.txt` and `CaseFolding.txt` into the gitignored `.cache/ucd/15.0.0/` directory, rejects missing downloads or SHA-256 mismatches, and writes the pinned URLs and hashes into both generated assets; the upstream text files are not redistributed. Compound character classes containing `\p{...}` and Unicode categories beyond the documented set remain excluded pending issue #38.

```
import regex

prog is regex.re_compile of "ab|cd"
m is regex.re_match of [prog, "ab"]                    # → 1
m is regex.re_match of [prog, "ef"]                    # → 0

prog is regex.re_compile of "[a-zA-Z_][a-zA-Z0-9_]*"
r is regex.re_search of [prog, "  foo_2 bar"]          # → [2, 7]

prog is regex.re_compile of "(\\w+) (\\w+)"
r is regex.re_search of [prog, "hello world"]          # → [0, 11, 0, 5, 6, 11]

# RE2-style ASCII word boundaries and Unicode simple case folding:
r is regex.re_search of [regex.re_compile of "\\bcat\\b", "a cat!"] # → [2, 5]
folded is regex.re_compile of ["École", "i"]
regex.re_match of [folded, "éCOLE"]                    # → 1

# Named groups retain positional spans and are also available by name:
named is regex.re_compile of "(?P<word>\\w+)"
r is regex.re_search_named of [named, "hello"]
# → {"spans": [0,5,0,5], "groups": {"word": [0,5]}}

prog is regex.re_compile of "a+"
all is regex.re_find_all of [prog, "aaabaaab"]         # → [[0,3], [4,7]]

prog is regex.re_compile of "\\d{2,4}"                 # RE2 ASCII digit shorthand
out is regex.re_replace of [prog, "year 2026!", "Y"]   # → "year Y!"
```
