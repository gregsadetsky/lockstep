# oracles

the independent implementations behind the nine-way answer-key verification.
everything here is verbatim — never edited after the writing agent produced it
(the `out.md` / `agy-out.md` files are the agents' own transcripts, machine
paths and all).

- `codex/` — a simulator written by openai codex from `SEMANTICS.md` alone,
  in a directory containing nothing but the spec
- `agy/` — same, written by agy (a different agent, different model)
- `codex-translator/` — a json-to-verilog translator by codex, same protocol
- `agy-translator/` — same, by agy

the nine evaluators = our simulator (`lockstep/sim.py`) + these two sims +
three translators (ours in `lockstep/verilog.py` + these two), each translator
run through both icarus verilog and verilator. discovery is by filename glob
in `lockstep/harness.py` — drop in another `sim_*.py` or `translate_*.py` and
it joins the jury.

what this construction can and can't catch: a bug in any one implementation
shows up as a disagreement (the harness kills itself on the first one — see
`tests/test_metamorphic.py` for proof the comparator actually fires). a true
ambiguity in the spec itself, reproduced identically by everyone, would be
invisible to it.
