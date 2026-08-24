# fuzz

the golden reference (see `../oracles/`) was stress-tested with 1600 generated
circuits across two campaigns. all nine evaluators agreed on every bit of
every trace; the harness kills itself on the first disagreement — it never
fired.

- `verdicts-v2.jsonl` — 600 circuits across all six generator families
  (random, chain, mix, rule30, perm, ca; up to 882 gates — the ca family's
  rule synthesis gets big — 32 flip-flops, 48 cycles). one row per circuit with the verdict AND the full agreed golden
  trace — the values themselves, not just the word.
- `manifest.jsonl` — the earlier 1000-circuit campaign (4 families, 4x250).
  caveat on this one: its per-circuit verdicts were printed to a terminal and
  not saved; the row hashes were derived afterwards from the saved circuit
  files (kept locally with all their generated verilog, ~2.7GB, too big for
  the repo). the fail-fast runs completing all 250 each is the agreement
  evidence for that campaign.

both campaigns replay from their seeds with no toolchain and no key:

    uv run python scripts/fuzz_replay.py

regenerates every circuit deterministically, simulates it fresh, and compares
hashes (v1) and full stored values (v2) — nonzero exit on any mismatch.
to run a fresh nine-way campaign yourself (needs icarus-verilog + verilator):

    uv run python -m lockstep.harness --fuzz-v2 25 --seed 12345 \
      --build build-myfuzz --verdict-log my-verdicts.jsonl

ci also runs a fresh ~280-circuit campaign weekly on new seeds; each clean
run tightens the bound on any possible divergence rate.
