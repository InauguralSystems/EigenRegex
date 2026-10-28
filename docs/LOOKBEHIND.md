# Linear-time lookbehind

EigenRegex implements captureless `(?<=...)` and `(?<!...)` using the
forward-automata construction described by Barrière and Pit-Claudel in
*Linear Matching of JavaScript Regular Expressions* (PLDI 2024).

Each lookbehind body is compiled into its own Pike-VM program. Before the main
program runs, those sub-automata are seeded at every Unicode-scalar boundary
and advanced forward in lockstep over the subject. Their accept bit at each
byte boundary forms a table consumed by the main program's zero-width
`assert_lookbehind` instruction. This supports arbitrary captureless bodies,
including variable-width and unbounded repetition, in
`O(subject length × compiled program size)` time; the engine never searches
backwards or reruns a sub-search at each candidate position.

The table is prepared once for the whole public operation. `re_find_all` and
`re_replace` retain it across every empty- or non-empty-match resume rather
than resetting the sub-automata or recomputing the table for each `_search`.

Capturing or named groups inside lookbehind and quantifying the lookbehind
assertion itself are compile-time errors. Lookahead remains unsupported until
issue 36b.
