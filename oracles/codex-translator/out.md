Implemented [translate_codex.py](/Users/g/Desktop/circuiteval/new-attempt-aug-2026/oracles/codex-translator/translate_codex.py).

It validates the JSON spec, rejects violations nonzero, generates `circuit_dut.v` and `tb.v`, handles empty/zero-input/zero-gate cases, preserves output order including duplicate output entries, and samples outputs before each generated clock edge.

Verified:
- `python3 -m py_compile translate_codex.py`
- Generated and ran a small sequential NAND/DFF circuit with Icarus:
```text
TRACE,0,0,0,0
TRACE,1,1,1,1
TRACE,2,0,0,1
```
- Compiled and ran the generated Verilog with `verilator --binary --timing -Wno-fatal --top-module tb`.
- Checked empty circuit and state-only edge cases under Icarus.