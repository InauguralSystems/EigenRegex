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
compat layer (`lib/regex_compat.eigs`) that drops in for the libc-backed
`regex_match` / `regex_find` / `regex_replace` builtins.
347 test checks across S1–S8, all green — including a differential suite
run against the live libc builtins as the oracle.

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

- `lib/regex.eigs` — public API (spans-shaped: `re_compile`, `re_match`,
  `re_search`, `re_find_all`, `re_replace`)
- `lib/regex_compat.eigs` — builtin-shaped shim (`regex_match` /
  `regex_find` / `regex_replace` over the Pike VM; shadows the builtins)
- `lib/regex_parse.eigs` — pattern string → AST
- `lib/regex_compile.eigs` — AST → instruction list
- `lib/regex_vm.eigs` — Pike-VM executor
- `tests/` — per-stage tests

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
guarantee or are running in a no-libc environment. For the latter,
`lib/regex_compat.eigs` re-exposes the builtins' exact names and shapes
on top of the Pike VM (divergences documented in its header).

## Usage

```
load_file of "lib/regex.eigs"

prog is re_compile of "ab|cd"
m is re_match of [prog, "ab"]                    # → 1
m is re_match of [prog, "ef"]                    # → 0

prog is re_compile of "[a-zA-Z_][a-zA-Z0-9_]*"
r is re_search of [prog, "  foo_2 bar"]          # → [2, 7]

prog is re_compile of "(\\w+) (\\w+)"
r is re_search of [prog, "hello world"]          # → [0, 11, 0, 5, 6, 11]

prog is re_compile of "a+"
all is re_find_all of [prog, "aaabaaab"]         # → [[0,3], [4,7]]

prog is re_compile of "[0-9]{2,4}"
out is re_replace of [prog, "year 2026!", "Y"]   # → "year Y!"

# Builtin-shaped drop-ins (substring lists, not spans):
load_file of "lib/regex_compat.eigs"
regex_match of ["hello world", "h([a-z]+)"]      # → ["hello", "ello"]
```
