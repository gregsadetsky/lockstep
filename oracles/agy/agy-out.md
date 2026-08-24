The circuit simulator has been implemented strictly from the specification in [`SEMANTICS.md`](file:///Users/g/Desktop/circuiteval/new-attempt-aug-2026/oracles/agy/SEMANTICS.md) as a standalone Python 3 script at [`sim_agy.py`](file:///Users/g/Desktop/circuiteval/new-attempt-aug-2026/oracles/agy/sim_agy.py).

### Summary of Implementation

- **Validation & Spec Conformance:**
  - Net name formatting (`^[a-z][a-z0-9_]*$`) and reserved name check (`clk`).
  - Supported gate types (only `NAND`) and binary `init` / `trace` values (`0` or `1`).
  - Single driver constraint (every net driven by exactly one input, gate output, or DFF output).
  - Complete driving of all referenced nets (gate inputs, DFF inputs, output nets).
  - Combinational cycle detection via topological sorting of the gate network.
  - Trace length and key alignment with `inputs` and `cycles`.
  - Non-zero exit code with error message on `stderr` on any violation.
- **Cycle Stepping & Simulation:**
  - Step 1: Input nets take trace values; DFF `q` outputs hold their current state (or `init` at $t=0$).
  - Step 2: Instantaneous gate evaluation in topological dependency order.
  - Step 3: Recording output nets for the cycle.
  - Step 4: Simultaneous clock-edge update of all DFF states from their respective `d` nets.
  - Exactly one JSON object is printed to `stdout` at completion.

### Execution & Verification

Tested with `/usr/bin/python3` on a sample circuit ([`test_circuit.json`](file:///Users/g/Desktop/circuiteval/new-attempt-aug-2026/oracles/agy/test_circuit.json)):

```bash
/usr/bin/python3 sim_agy.py test_circuit.json
# Output:
# {"n0": [1, 0, 1, 1], "q0": [0, 1, 0, 1]}
```
