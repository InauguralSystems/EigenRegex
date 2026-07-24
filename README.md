# EigenRegex

A Pike-VM regex engine written in EigenScript.

Dual purpose:
1. A working regex library for EigenScript programs.
2. A forcing function — every ergonomic friction point or runtime gap encountered while building it gets logged in `GAPS.md` for upstream fixes in EigenScript itself.

## Status

S8 complete (ERE parity). Working: literals, concat, `|`, `( )`, `* + ?`
and `{n} {n,} {n,m}` (all greedy + lazy), `.`, `[abc]`, `[^abc]`, `[a-z]`,
POSIX `[[:alpha:]]`-style classes, escapes (`\.` `\w` `\W` `\s` `\S`),
`^`, `$`, numbered capture groups, `re_replace`, and a builtin-shaped
compat layer (`regex.compat_*`) that mirrors the libc-backed
`regex_match` / `regex_find` / `regex_replace` builtins.
359 test checks across S1–S9 plus a consumer-shaped package smoke test,
all green — including a differential suite run against the live libc
builtins as the oracle.

Packaged for `import` (issue #13): the engine ships as a single root
`regex.eigs` with an `eigs.json` manifest, so its internals namespace
under `regex.*` and never collide with a consumer's globals.

## Supported

- Literal characters and escaped metacharacters (`\.` `\*` `\\` …)
- Concatenation
- Alternation `|`
- Grouping `( ... )`
- Repetition `*`, `+`, `?`, `{n}`, `{n,}`, `{n,m}` (greedy and lazy)
- Char classes: `.`, `[abc]`, `[^abc]`, `[a-z]`, POSIX `[[:alpha:]]` etc.,
  `\w` `\W` `\s` `\S` (note: `\d` is a literal `d`, matching glibc ERE)
- Anchors `^`, `$`
- Capturing groups (numbered)

## Not supported

- Backreferences (would force backtracking; out of scope for Pike-VM)
- Lookahead / lookbehind; `\b` word boundaries
- Named groups
- Unicode classes (`\p{...}`)
- Case-insensitive flags (yet)

## Layout

- `regex.eigs` — the package: parse → compile → Pike-VM → public API, one
  importable file. Public surface (namespaced under `regex.*`):
  - spans-shaped: `re_compile`, `re_match`, `re_search`, `re_find_all`,
    `re_replace`
  - builtin-shaped: `compat_match`, `compat_find`, `compat_replace`
    (substring lists; alias to the bare builtin names where libc regex
    is absent — see below)
  - everything else (`_rx_parse`, `_peek`, …) is `_`-private to the module
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
| features | POSIX ERE + GNU `\w \s \b` | ERE parity minus `\b`; lazy quantifiers extra |
| match rule | leftmost-longest (POSIX) | leftmost-first (Pike-VM priority) |
| return shape | substring list | positional spans `[s, e, ...]` |

Pick the builtin for hot paths; pick `re_*` when you need a linear-time
guarantee or are running in a no-libc environment. For the latter, the
namespaced `regex.compat_*` functions re-expose the builtins' exact
shapes on top of the Pike VM; alias them to the bare builtin names where
libc regex is gone (`regex_match is regex.compat_match`). Divergences —
leftmost-first vs POSIX leftmost-longest, no `\b` — are documented in the
compat section of `regex.eigs`.

## Install

```
eigenscript --pkg add InauguralSystems/regex https://github.com/InauguralSystems/EigenRegex v0.1.0
```

This clones the package into `eigs_modules/regex/` and records the
resolved commit in `eigs.lock.json`. Then `import regex` in your code.

## Usage

```
import regex

prog is regex.re_compile of "ab|cd"
m is regex.re_match of [prog, "ab"]                    # → 1
m is regex.re_match of [prog, "ef"]                    # → 0

prog is regex.re_compile of "[a-zA-Z_][a-zA-Z0-9_]*"
r is regex.re_search of [prog, "  foo_2 bar"]          # → [2, 7]

prog is regex.re_compile of "(\\w+) (\\w+)"
r is regex.re_search of [prog, "hello world"]          # → [0, 11, 0, 5, 6, 11]

prog is regex.re_compile of "a+"
all is regex.re_find_all of [prog, "aaabaaab"]         # → [[0,3], [4,7]]

prog is regex.re_compile of "[0-9]{2,4}"
out is regex.re_replace of [prog, "year 2026!", "Y"]   # → "year Y!"

# Builtin-shaped drop-ins (substring lists, not spans):
regex.compat_match of ["hello world", "h([a-z]+)"]     # → ["hello", "ello"]
```
