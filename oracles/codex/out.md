Implemented [sim_codex.py](/Users/g/Desktop/circuiteval/new-attempt-aug-2026/oracles/codex/sim_codex.py).

It validates the spec constraints, topologically evaluates NAND gates, simulates DFF updates after output recording, and prints exactly one compact JSON object on success.

Verified with a small NAND+DFF test circuit:

```json
{"y":[1,0,1,1],"q":[0,1,0,1]}
```

Temporary test/cache artifacts were cleaned up; `sim_codex.py` is the only new file.