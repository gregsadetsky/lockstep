# circuits

the 63 evaluated circuits, frozen. names are the generator's parameters:
`s` seed, `g` nand gates, `d` flip-flops, `c` cycles, `k` cellular-automaton
cells — so `perm_s4632_d32_c40` is a permutation network from seed 4632 with
32 flip-flops run for 40 cycles.

- root — 9 hand-picked starters (a counter, shift registers, an lfsr, xor)
- `rand/` — random netlists, 40 and 80 gates
- `tier2/` — the shared hard set (100-gate chains, dense mixes, rule 30)
- `tier3/` — axis probes: pure-nand chains (d0), pure-dff perms, size sweeps
- `tier4/` — circuits minted to break opus-5 (depth 150-200, 24-dff mixes)
- `x/` — cellular automata with random rules and deliberately opaque names
  (anti-recognition controls: rule 30 by any other name)

all of these are public, answer keys included (`../keys/`), which means they
are burned for evaluating any model trained after this repo went up. the
generator (`lockstep/gen.py`) is seeded and public — fresh circuits are one
command away.
