# EigenScript gaps surfaced by EigenRegex

Log every ergonomic friction or runtime gap encountered while building EigenRegex.
Each entry should name the gap, the workaround used, and a thought on the upstream fix.

## Format

```
### <short name>
- **Encountered:** <stage / file:line>
- **Symptom:** <what didn't work>
- **Workaround:** <what I did instead>
- **Upstream fix:** <what should change in EigenScript>
```

## Entries

### String ordering operators (`<`, `<=`, `>`, `>=`) don't work on strings — FIXED 2026-05-31
- **Encountered:** S1 prep (probing single-char comparison)
- **Symptom:** `"a" < "m"` returns 0. `"m" < "z"` returns 0. `"z" > "a"` returns 0. All return false regardless of actual lex order. Only `==` and `!=` work on strings.
- **Workaround (S1):** None needed — literal matching uses only `==`.
- **Workaround (S4 char classes):** Now unnecessary; use natural `c >= "a" and c <= "z"`.
- **Upstream fix:** Both shipped. (a) `NUM_CMP` macro in `vm.c` now falls through to a byte-wise `strcmp` when both operands are `VAL_STR`. (b) `ord of s` builtin added in `builtins.c` (returns byte 0..255 or -1 for empty / non-string). Verified by `tests/run_all_tests.sh` (1044/1044) and a probe script.

### Parenthesized fn-call indexed inline as a fn arg returns uninitialized memory — FIXED 2026-05-31
- **Encountered:** S1 test writing (`tests/test_s1_literals.eigs`)
- **Symptom:** `check of [label, (regex_search of [prog, "abc"])[0], 0]` — the indexed expression evaluates to a denormal float like `4.76e-310` (uninitialized double) instead of the actual `0`. Same expression bound to a local first (`r is regex_search of [...]; r[0]`) returns the correct value. So argument evaluation of `(fn_call)[index]` in a fn-call context reads uninitialized memory off the value stack.
- **Workaround (no longer needed):** Bind subscripted fn-call results to a local before passing them as function arguments.
- **Root cause:** Use-after-free in `OP_INDEX_GET`'s VAL_NUM fast path. When the indexee was the sole owner of the list (typical for `(call())[i]` inline — list never bound to a local), `slot_decref(tgt_s)` freed the list, cascaded into `free_value` on the item, and `free_value(num)` memcpy's the num-freelist next pointer over `r->data`. Reading `r->data.num` afterward returned freelist garbage (denormal pointer-as-double, or 0 for the first freed item). Bound-to-local form hid the bug by keeping refcount > 1.
- **Upstream fix:** `src/vm.c` `CASE(INDEX_GET)` (~line 2037) and `jit_helper_index_get` (~line 760) both now snapshot `r->data.num` to a local **before** `slot_decref(tgt_s)`. Mirrors the pattern already used correctly by `jit_helper_dot_get`. Regression test: `tests/test_index_after_call.eigs` (21 checks) registered in `run_all_tests.sh` as `[67]`. Full suite: 1114/1114.

### No `ord` builtin (asymmetric with `chr`) — FIXED 2026-05-31
- **Encountered:** S1 prep
- **Symptom:** `chr of 97` returns `"a"`, but there's no `ord of "a"` to go the other way. This makes char-class compilation awkward — without numeric codes, ranges and bitmaps are hard to encode efficiently.
- **Workaround:** Now unnecessary.
- **Upstream fix:** Shipped alongside gap #1 — `ord of s` returns byte 0..255, or -1 for empty / non-string.

### load_file cross-module write asymmetry — FIXED upstream same day (EigenScript#373 → PR #374): module functions now never bind writes into the loader's scope, both orders; the `local` discipline below remains best practice for module self-state
- **Encountered:** verifying #5 (engine internals clobbering caller globals)
- **Symptom:** whether a lib function's bare `name is` clobbers a caller global depends on whether the global was declared **before** the `load_file` (clobbered) or after (insulated). Made #5 look like a non-repro — its example used the safe order — while the before-order corrupted the engine's own state from caller globals.
- **Workaround:** `local` on every function-internal first assignment (the #5 fix, `tests/test_s9_scope.eigs`); the discipline is load-order-proof.
- **Upstream:** EigenScript#373 — remove or document the asymmetry.

### `regex_match` builtin changed non-participating-group shape between v0.30.0 and v0.32.0 — OBSERVED 2026-07-24
- **Encountered:** running S8's shim-vs-builtin differential against a v0.32.0 runtime while packaging for `import` (#13). Suite is green on the CI-pinned v0.30.0; the single `diff match (a)|(b)` case fails only on v0.32.0.
- **Symptom:** the libc-backed `regex_match` changed how it reports non-participating capture groups.
  - v0.30.0: `regex_match of ["b", "(a)|(b)"]` → `["b"]` — truncates at the first unset group (the shape `lib/regex_compat.eigs`'s header documents and mirrors).
  - v0.32.0: `regex_match of ["b", "(a)|(b)"]` → `["b", null, "b"]` — emits `null` for the unset group and keeps positional slots. (`"a"` case: `["a","a"]` → `["a","a",null]`.)
- **Impact:** not an EigenRegex bug — the Pike-VM `compat_match` still truncates, matching v0.30.0. But bumping `EIGS_REF` to v0.32.0+ will break the S8 differential, and any consumer that indexed the builtin's result positionally saw its length/contents change under them.
- **Upstream question:** is the null-fill intentional (arguably more correct — positional groups are preserved) or a regression? If intentional, it's a breaking builtin-shape change worth a CHANGELOG note; `compat_match` should then be updated to null-fill too (and the compat header's "STOPS at the first non-participating group" line corrected) when EigenRegex moves onto that runtime.
