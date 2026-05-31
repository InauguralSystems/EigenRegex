# EigenRegex

A Pike-VM regex engine written in EigenScript.

Dual purpose:
1. A working regex library for EigenScript programs.
2. A forcing function — every ergonomic friction point or runtime gap encountered while building it gets logged in `GAPS.md` for upstream fixes in EigenScript itself.

## Status

S5 complete. Working: literals, concat, `|`, `( )`, `* + ?` (greedy + lazy),
`.`, `[abc]`, `[^abc]`, `[a-z]`, `^`, `$`, numbered capture groups.
220 test checks across S1–S5, all green. Next: fold into corpus for retraining (S6).

## Supported (target MVP)

- Literal characters
- Concatenation
- Alternation `|`
- Grouping `( ... )`
- Repetition `*`, `+`, `?` (greedy and lazy)
- Char classes: `.`, `[abc]`, `[^abc]`, `[a-z]`
- Anchors `^`, `$`
- Capturing groups (numbered)

## Not supported

- Backreferences (would force backtracking; out of scope for Pike-VM)
- Lookahead / lookbehind
- Named groups
- `{n,m}` quantifiers
- Unicode classes (`\p{...}`)
- Case-insensitive flags (yet)

## Layout

- `lib/regex.eigs` — public API
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
| features | `{n,m}`, POSIX classes | MVP: `* + ? . [] ^ $ ( )` |
| return shape | substring list | positional spans `[s, e, ...]` |

Pick the builtin for hot paths; pick `re_*` when you need a linear-time
guarantee or are running in a no-libc environment.

## Usage

```
load_file of "lib/regex.eigs"

prog is re_compile of "ab|cd"
m is re_match of [prog, "ab"]                    # → 1
m is re_match of [prog, "ef"]                    # → 0

prog is re_compile of "[a-zA-Z_][a-zA-Z0-9_]*"
r is re_search of [prog, "  foo_2 bar"]          # → [2, 7]

prog is re_compile of "(\\w+) (\\w+)"            # (not yet — use [a-z]+)
prog is re_compile of "([a-z]+) ([a-z]+)"
r is re_search of [prog, "hello world"]          # → [0, 11, 0, 5, 6, 11]

prog is re_compile of "a+"
all is re_find_all of [prog, "aaabaaab"]         # → [[0,3], [4,7]]
```
