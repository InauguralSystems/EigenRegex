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

`lib/regex_compat.eigs` re-exposes the builtins' exact names/shapes on
top of the Pike VM (for freestanding/WASM); divergences are documented
in its header — chiefly leftmost-longest vs leftmost-first, and no `\b`.

**Pick the builtin for hot paths; pick `re_*` when you need a linear
worst-case guarantee or libc isn't available** (e.g. the WASM
playground build).

## Toolchain

EigenScript is **not** vendored. Pin v0.11.5 minimum (string
`<`/`<=` comparison, `ord of s`, and the `INDEX_GET`
use-after-free fix all first shipped in v0.11.5 — see GAPS.md
for the fix history). CI pins the runtime via
`.devcontainer/Dockerfile`'s `EIGS_REF` (currently **v0.26.0**) and
builds it from source — bump that to move the tested runtime.

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

358 test checks across S1–S9, all green (S9 = the #5 caller-globals scope suite). (`tests/bench_search.eigs` is
a manual timing bench, not part of the gate.)

## Layout

| Path | Role |
|---|---|
| `lib/regex.eigs` | Public API (`re_compile`, `re_match`, `re_search`, `re_find_all`, `re_replace`) |
| `lib/regex_parse.eigs` | Pattern string → AST |
| `lib/regex_compile.eigs` | AST → instruction list |
| `lib/regex_vm.eigs` | Pike-VM executor (parallel-thread simulation) |
| `lib/regex_compat.eigs` | Builtin-shaped shim (`regex_match`/`regex_find`/`regex_replace` over the Pike VM) |
| `tests/test_s{1..9}_*.eigs` | Per-stage tests (literals → alt → repeat → classes → anchors/groups → escapes/POSIX → intervals → compat/differential → scope) |
| `tests/test_smoke.eigs` | S0 end-to-end load + API smoke |
| `tests/run.sh` | Suite runner — runs every test, exits non-zero on any FAIL/crash (the CI gate) |
| `tests/bench_search.eigs` | Manual scaling bench for `re_search` (not a pass/fail gate) |
| `.devcontainer/`, `.github/workflows/test.yml` | Pinned (`EIGS_REF`) devcontainer + CI running the suite |
| `GAPS.md` | Upstream-gap ledger (with fixed/open status per entry) |

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

**S8 complete (ERE parity, 2026-07-01).** All checks across S1–S9
green. S6 added escapes + POSIX classes, S7 added `{n,m}` intervals
(desugared in the parser — no new VM ops; shared-subtree repetition
gives glibc's last-repetition-wins capture semantics), S8 added
`re_replace` + `lib/regex_compat.eigs` and a differential suite that
runs shim-vs-builtin over shared inputs with the libc builtins as the
oracle. Built for EigenScript's freestanding profile (EigenOS): the
compat layer is the planned regex story when libc's regcomp is gone.
Still open: fold into corpus for retraining — feeding the engine's own
source + tests into the iLambdaAi self-training pipeline.

**Search is now genuinely O(n·m).** `re_search` used to loop over every
start position and re-run the VM from each — O(n²), which silently
violated the library's whole linear-time promise (`a*b` over `"aaaa…"`:
~4× per doubling, n=1600 took ~79 s). Replaced with a single linear
pass that seeds a lowest-priority start thread at `pc=0` each step (the
implicit `.*?` prefix), preserving leftmost-match priority. Now ~2× per
doubling; n=1600 ≈ 106 ms (~745× faster), all 220 checks unchanged.
`tests/bench_search.eigs` documents the scaling (timings are
machine-dependent, so it's a manual bench, not a pass/fail gate).

## Gotchas

- Patterns are compiled once and reused (`re_compile`). Don't compile
  inside a hot loop.
- `re_*` indexes are byte offsets, not codepoints. The MVP is
  byte-oriented; multi-byte input matches per-byte.
- Pike-VM is **~100–1000× slower than the libc-backed builtin** for
  patterns the builtin can handle without backtracking. If you don't
  *need* the linear-time guarantee, use `regex_*`.
