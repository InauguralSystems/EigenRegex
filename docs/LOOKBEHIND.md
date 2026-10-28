# Linear-time lookaround

EigenRegex implements captureless lookbehind (`(?<=...)`, `(?<!...)`) and
lookahead (`(?=...)`, `(?!...)`) with Pike-VM tables, following the automata
construction described by Barrière and Pit-Claudel in *Linear Matching of
JavaScript Regular Expressions* (PLDI 2024).

Each lookbehind body is compiled into a forward Pike-VM program. Before the
main program runs, its automaton is seeded at every Unicode-scalar boundary
and advanced forward in lockstep. Its accept bit at each byte boundary records
whether a suffix ending there matches.

Lookahead bodies are compiled with concatenations and UTF-8 byte paths reversed,
then evaluated in a single right-to-left pass over the original subject bytes.
The subject's UTF-8 bytes are never reversed: consumption reads the preceding
byte, preserving scalar boundaries and multibyte character order. An accept bit
at a boundary records whether the original body matches from that boundary.

Nested lookarounds compile to table references. Inner tables are emitted and
prepared before outer tables, so ahead-in-behind, behind-in-ahead, same-kind,
and deeper nesting all remain table lookups rather than recursive searches.
The combined cost is `O(subject length × total compiled program size)`.

All tables are prepared once for the complete public operation. `re_find_all`
and `re_replace` retain them across every empty- or non-empty-match resume;
no `_search` call recomputes a lookaround table.

Capturing or named groups inside any lookaround, backreferences, and quantifying
a lookaround assertion are compile-time errors.
