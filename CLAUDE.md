# CLAUDE.md

Guidance for working in this repository.

## What this is

EigenRegex is a **Pike-VM regex engine written in EigenScript** —
linear-time guarantee, no backtracking.

Two missions:

1. A working regex library for EigenScript programs that need a
   `O(n·m)` worst-case guarantee or run in a no-libc environment.
2. **A forcing function for EigenScript itself.** Every friction
   point or runtime gap found while building this gets logged in
   `GAPS.md` for an upstream fix. The Pike-VM compiler/executor
   exercises a wider slice of EigenScript than most application
   code, so it's good at finding bugs (see GAPS.md for the
   uninitialized-memory `INDEX_GET` bug it surfaced).

Sibling stress repo to EigenGauntlet, EigenMiniSat, and Tidepool.

## Coexists with the EigenScript builtin

EigenScript ships `regex_match` / `regex_find` / `regex_replace` as
libc-POSIX-backed builtins. EigenRegex prefixes its public API with
`re_*` so both live in the same script:

|                | builtin (`regex_*`) | EigenRegex (`re_*`) |
|----------------|---------------------|---------------------|
| backend        | libc POSIX ERE in C | Pike-VM in EigenScript |
| speed          | native, fast        | interpreted, ~100–1000× slower |
| worst case     | can backtrack catastrophically | guaranteed `O(n·m)` |
| features       | POSIX ERE + GNU `\w \s \b` | ERE parity minus `\b`; lazy quantifiers extra |
| match rule     | leftmost-longest (POSIX) | leftmost-first (Pike-VM priority) |
| return shape   | substring list      | positional spans `[s, e, ...]` |

The namespaced `regex.compat_*` functions re-expose the builtins' exact
shapes on top of the Pike VM (for freestanding/WASM); divergences are
documented in the compat section of `regex.eigs` — chiefly
leftmost-longest vs leftmost-first, and no `\b`. Alias them to the bare
builtin names where libc regex is gone: `regex_match is regex.compat_match`.

**Pick the builtin for hot paths; pick `re_*` when you need a linear
worst-case guarantee or libc isn't available** (e.g. the WASM
playground build).

## Toolchain

EigenScript is **not** vendored. Pin v0.11.5 minimum (string
`<`/`<=` comparison, `ord of s`, and the `INDEX_GET`
use-after-free fix all first shipped in v0.11.5 — see GAPS.md
for the fix history). CI pins the runtime via
`.devcontainer/Dockerfile`'s `EIGS_REF` and builds it from source — bump
that to move the tested runtime. (The `import`-based package model needs a
runtime with `import`.)

## Run / test

CI builds the devcontainer (EigenScript pinned by `EIGS_REF`) and runs
the suite inside it via `devcontainers/ci`, so Codespace and CI can't
drift. The runner exits non-zero on any `FAIL` or crash — that's the
gate (the per-stage `.eigs` files print `OK`/`FAIL` but exit 0 on their
own).

```bash
# All stages + smoke, with a pass/fail exit code (what CI runs):
EIGENSCRIPT=eigenscript bash tests/run.sh

# Or against a specific binary, one file at a time:
EIGS=${EIGENSCRIPT_BIN:-eigenscript}
$EIGS tests/test_s1_literals.eigs   # ... s2 alt, s3 repeat, s4 classes,
$EIGS tests/test_s5_anchors_groups.eigs   # s5 anchors/groups, test_smoke
```

Tests run from the repo root (as `run.sh` does), where `import regex`
resolves to the root `regex.eigs`. `tests/test_pkg_smoke.sh` additionally
stages the package into `eigs_modules/regex/` and imports it the way a
real consumer (`--pkg add`) would.

Stages S1–S12 plus the package smoke (S9 = the import-isolation guard,
S10 = re_trace, S11 = tester_core oracle, S12 = the tester UI driven
headlessly).
(`tests/bench_search.eigs` is a manual timing bench, not part of the gate.)

## Layout

- **`regex.eigs` is the whole package in one importable file** (parse → compile
  → Pike-VM executor → public API). Public members namespace under `regex.*`;
  `_`-prefixed names (`_rx_parse`, `_peek`, …) are private. **Edit
  `regex.eigs` directly.**
- `eigs.json` is the package manifest (`name: regex`) — what makes
  `import regex` resolve this repo.
- `tests/test_s{1..12}_*.eigs` are per-stage (literals → alt → repeat →
  classes → anchors/groups → escapes/POSIX → intervals → compat/differential
  → import-isolation → trace → tester core → tester UI); `tests/bench_search.eigs`
  is a manual bench, not a gate.
- `GAPS.md` — upstream-gap ledger (fixed/open status per entry).
- `tester_core.eigs` / `tester.eigs` / `tester_main.eigs` — the live
  tester (#18): pure model, gfx UI (load_file'd, state in the `T` dict),
  and the entry point (`eigenscript tester_main.eigs`, gfx build).
  The step view rides `regex.re_trace`; highlights ride code_view
  `spans` (EigenScript#838, carried by the pin since v0.36.0).

## Architecture notes

- **Pike-VM, not backtracking.** Patterns compile to a small
  instruction set; the executor advances a *set* of NFA states in
  lockstep with the input. State-set size is bounded by program
  length, giving the `O(n·m)` guarantee.
- **Return shape is positional spans.** `re_search` returns
  `[start, end, group1_start, group1_end, ...]`, not a list of
  substrings. Indexes are byte offsets into the input string.
- **Public API uses the `re_*` prefix** so the EigenScript builtin
  `regex_*` calls remain usable in the same script.
- **AST → instructions** keeps the parse and compile stages cleanly
  separated. Adding a feature usually touches all three of parse,
  compile, vm.

## Supported features (stable)

Literals, escaped metachars (`\.` `\*` …), concat, `|`, `( )`,
`* + ?` and `{n} {n,} {n,m}` (all greedy + lazy), `.`, `[abc]`,
`[^abc]`, `[a-z]`, POSIX `[[:alpha:]]`-style classes, `\w \W \s \S`
(`\d` is a literal `d` — glibc ERE parity, verified against the
oracle), `^`, `$`, numbered capture groups, `re_replace`, and the
builtin-shaped compat layer.

## Out of scope

- Backreferences (force backtracking — incompatible with Pike-VM
  guarantee)
- Lookahead / lookbehind; `\b` word boundaries (would need text access
  in the VM's epsilon-closure — doable, deferred until something needs it)
- Named groups
- Unicode classes (`\p{...}`)
- Case-insensitive flags (yet)

## Hard-won rules

- **Friction → GAPS.md, not local workaround.** If something is
  ergonomic-painful, that's the signal EigenScript should fix; log
  it. Two non-trivial language bugs (string `<`/`<=`, `INDEX_GET`
  use-after-free) shipped upstream because they were logged here.
- **Don't add features outside the Pike-VM-safe set.** Backreferences
  break the linear-time guarantee — that's the whole point of the
  library. If you genuinely need them, use the builtin instead.
- **Match return shape stays positional spans.** Don't return
  substrings: the consumer can slice cheaply, and span shape composes
  with `re_find_all` returning lists of `[s, e, ...]` arrays.

## Current state

**Packaged for `import`:** one importable root `regex.eigs` + `eigs.json`
(name `regex`). Consumers `import regex` and reach `regex.re_*` /
`regex.compat_*`; every internal is `_`-private, so caller-globals
collisions (issue #5, eigen-sheet's `_peek` clash in #13) are structurally
impossible — not just mitigated by `local`. S9 is the import-isolation
guard.

**ERE parity:** escapes + POSIX classes (S6); `{n,m}` intervals desugared
in the parser with no new VM ops — shared-subtree repetition gives glibc's
last-repetition-wins capture semantics (S7); `re_replace` + the
builtin-shaped compat layer, with a shim-vs-builtin differential suite that
uses the libc builtins as the oracle (S8). The compat layer is the regex
story for EigenScript's freestanding profile (EigenOS), where libc's
regcomp is gone. Still open: feeding the engine's own source + tests into
the iLambdaAi self-training corpus.

**Search is a single linear pass:** each step seeds a lowest-priority start
thread at `pc=0` (the implicit `.*?` prefix), preserving leftmost-match
priority. Never re-run the VM from each start position — that is O(n²) and
silently breaks the linear-time promise (`a*b` over `"aaaa…"` at n=1600:
~79 s against ~106 ms). `tests/bench_search.eigs` documents the scaling
(machine-dependent, so a manual bench, not a gate).

## Gotchas

- Patterns are compiled once and reused (`re_compile`). Don't compile
  inside a hot loop.
- `re_*` indexes are byte offsets, not codepoints. The MVP is
  byte-oriented; multi-byte input matches per-byte.
- Pike-VM is **~100–1000× slower than the libc-backed builtin** for
  patterns the builtin can handle without backtracking. If you don't
  *need* the linear-time guarantee, use `regex_*`.

## This design is pre-v1 and mostly written by older models — question it

**90% or more of this repo, and of EigenScript and the AOT it runs on, was
designed by Claude sessions running models many generations old.** Newer
models keep arriving that are substantially stronger, the ecosystem is
**pre-v1**, and there are no external consumers to break. A decision you
find in the tree — here or upstream — carries **no authority from
seniority**.

That applies in both directions, and the second one is the point of a
consumer repo. When you hit a rough edge in the runtime, the standing rule
is already to surface it as an upstream issue rather than work around it
silently. Add to that: ask whether the thing you hit is a **law** of the
language or an **earlier decision**. The tell is writing, or thinking,
*"X must be true because the runtime does Y."*

Bought 2026-08-28 (ouroboros#127 / DMG). The AOT then compiled a program's
main file but emitted `load_file` as a runtime call, so loaded modules were
interpreted by the linked VM (since fixed, ouroboros#129 — the reasoning is
the lesson, not the state). A real bug in that seam was found, minimised,
fixed and verified — and reported as "unlocking the AOT multiplier for
DMG". Measured on being challenged: DMG is 3,288 lines, 818 compiled and
2,470 interpreted, including the 128-function opcode dispatch. Every
emulated instruction ran interpreted, so the fix made it *run* and could not
make it *faster*. A whole investigation cycle had treated that design as
terrain, and the capability to do it the other way already existed upstream
for another purpose.
