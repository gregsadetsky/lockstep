# circuit netlist semantics (v0)

the entire language. if this page and an implementation disagree, this page wins.

## format

a circuit is a json object:

```json
{
  "name": "example",
  "inputs": ["a", "b"],
  "outputs": ["y", "q0"],
  "gates": [{"type": "NAND", "a": "a", "b": "b", "y": "n0"}],
  "dffs": [{"d": "n0", "q": "q0", "init": 0}],
  "trace": {"a": [0, 1], "b": [1, 1]},
  "cycles": 2
}
```

## rules

- every net is a single bit, value 0 or 1. there is no X, Z, or undefined.
- net names match `[a-z][a-z0-9_]*`. `clk` is reserved (the clock is implicit, never a net).
- the only gate type is `NAND`: `y = 1 - (a & b)`. two inputs, exactly.
- the only stateful element is `DFF`: on each clock edge, `q` takes the value `d` had
  just before the edge. `init` (0 or 1) is the value of `q` before cycle 0.
- every net is driven by exactly one of: a circuit input, a gate output `y`, a dff output `q`.
- every net referenced (gate inputs, dff `d`, circuit `outputs`) must be driven.
- the gate-only graph must be acyclic. feedback is legal only through a dff.
- `trace` gives each input net one value per cycle; every list has length `cycles`.

## time

for each cycle t = 0 .. cycles-1, in order:

1. input nets take their `trace` values for cycle t. dff `q` nets hold their current state
   (at t=0, their `init` values).
2. all gates settle instantly (zero delay — well-defined because the gate graph is acyclic).
3. the value of every net in `outputs` is recorded. this is the observed trace for cycle t.
4. clock edge: every dff simultaneously loads the settled value of its `d` net.

the result of a simulation is, for each output net, the list of `cycles` recorded values.

## what a correct evaluator must produce

exactly the recorded values from step 3, for every output, for every cycle.
no partial credit is defined at this layer; scoring policies live elsewhere.
