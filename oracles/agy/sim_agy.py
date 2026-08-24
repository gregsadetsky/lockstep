#!/usr/bin/env python3
import json
import re
import sys
from collections import deque
from typing import Any

NET_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def error_exit(msg: str) -> None:
    sys.stderr.write(f"Error: {msg}\n")
    sys.exit(1)


def validate_net_name(name: Any, context: str = "") -> None:
    if not isinstance(name, str):
        error_exit(f"Net name must be a string, got {type(name).__name__} ({context})")
    if name == "clk":
        error_exit(f"Reserved net name 'clk' cannot be used ({context})")
    if not NET_NAME_RE.fullmatch(name):
        error_exit(f"Bad net name '{name}' ({context}): must match ^[a-z][a-z0-9_]*$")


def validate_gate(gate: Any, index: int) -> None:
    if not isinstance(gate, dict):
        error_exit(f"Gate {index} must be an object")
    if "type" not in gate:
        error_exit(f"Gate {index} missing 'type'")
    if gate["type"] != "NAND":
        error_exit(f"Unknown gate type '{gate['type']}' in gate {index}; only 'NAND' is supported")
    for key in ("a", "b", "y"):
        if key not in gate:
            error_exit(f"Gate {index} missing required field '{key}'")
        validate_net_name(gate[key], f"gate {index} field '{key}'")


def validate_dff(dff: Any, index: int) -> None:
    if not isinstance(dff, dict):
        error_exit(f"DFF {index} must be an object")
    for key in ("d", "q", "init"):
        if key not in dff:
            error_exit(f"DFF {index} missing required field '{key}'")
    validate_net_name(dff["d"], f"dff {index} field 'd'")
    validate_net_name(dff["q"], f"dff {index} field 'q'")
    init = dff["init"]
    if isinstance(init, bool) or not isinstance(init, int) or init not in (0, 1):
        error_exit(f"DFF {index} 'init' must be 0 or 1, got {init!r}")


def simulate(circuit: Any) -> dict[str, list[int]]:
    if not isinstance(circuit, dict):
        error_exit("Circuit must be a JSON object")

    for req in ("name", "inputs", "outputs", "gates", "dffs", "trace", "cycles"):
        if req not in circuit:
            error_exit(f"Missing required top-level field '{req}'")

    if not isinstance(circuit["name"], str):
        error_exit("Circuit field 'name' must be a string")

    if not isinstance(circuit["inputs"], list):
        error_exit("Circuit field 'inputs' must be a list")
    for i, inp in enumerate(circuit["inputs"]):
        validate_net_name(inp, f"inputs[{i}]")

    if not isinstance(circuit["outputs"], list):
        error_exit("Circuit field 'outputs' must be a list")
    for i, out in enumerate(circuit["outputs"]):
        validate_net_name(out, f"outputs[{i}]")

    if not isinstance(circuit["gates"], list):
        error_exit("Circuit field 'gates' must be a list")
    for i, gate in enumerate(circuit["gates"]):
        validate_gate(gate, i)

    if not isinstance(circuit["dffs"], list):
        error_exit("Circuit field 'dffs' must be a list")
    for i, dff in enumerate(circuit["dffs"]):
        validate_dff(dff, i)

    cycles = circuit["cycles"]
    if isinstance(cycles, bool) or not isinstance(cycles, int) or cycles < 0:
        error_exit(f"Field 'cycles' must be a non-negative integer, got {cycles!r}")

    trace = circuit["trace"]
    if not isinstance(trace, dict):
        error_exit("Circuit field 'trace' must be an object")

    # Check drivers uniqueness (each net driven by exactly one source)
    driver_counts: dict[str, int] = {}
    for inp in circuit["inputs"]:
        driver_counts[inp] = driver_counts.get(inp, 0) + 1
    for gate in circuit["gates"]:
        y = gate["y"]
        driver_counts[y] = driver_counts.get(y, 0) + 1
    for dff in circuit["dffs"]:
        q = dff["q"]
        driver_counts[q] = driver_counts.get(q, 0) + 1

    for net, count in driver_counts.items():
        if count > 1:
            error_exit(f"Net '{net}' is driven {count} times (must be driven exactly once)")

    all_drivers = set(driver_counts.keys())

    # Validate trace entries
    input_set = set(circuit["inputs"])
    trace_set = set(trace.keys())
    if trace_set != input_set:
        missing = input_set - trace_set
        extra = trace_set - input_set
        if missing:
            error_exit(f"Missing trace for inputs: {sorted(missing)}")
        if extra:
            error_exit(f"Extra trace entries for non-inputs: {sorted(extra)}")

    for inp_name, values in trace.items():
        validate_net_name(inp_name, f"trace key '{inp_name}'")
        if not isinstance(values, list):
            error_exit(f"Trace for input '{inp_name}' must be a list")
        if len(values) != cycles:
            error_exit(
                f"Wrong trace length for input '{inp_name}': got {len(values)}, expected {cycles}"
            )
        for t, val in enumerate(values):
            if isinstance(val, bool) or not isinstance(val, int) or val not in (0, 1):
                error_exit(
                    f"Non-binary value {val!r} in trace for input '{inp_name}' at cycle {t}"
                )

    # Validate referenced nets
    for i, gate in enumerate(circuit["gates"]):
        if gate["a"] not in all_drivers:
            error_exit(f"Undriven reference '{gate['a']}' in gate {i} input 'a'")
        if gate["b"] not in all_drivers:
            error_exit(f"Undriven reference '{gate['b']}' in gate {i} input 'b'")

    for i, dff in enumerate(circuit["dffs"]):
        if dff["d"] not in all_drivers:
            error_exit(f"Undriven reference '{dff['d']}' in DFF {i} input 'd'")

    for i, out in enumerate(circuit["outputs"]):
        if out not in all_drivers:
            error_exit(f"Undriven reference '{out}' in outputs[{i}]")

    # Combinational cycle check & topological sorting of gates
    gate_by_output = {g["y"]: g for g in circuit["gates"]}
    adj: dict[str, list[str]] = {g["y"]: [] for g in circuit["gates"]}
    in_degree: dict[str, int] = {g["y"]: 0 for g in circuit["gates"]}

    for gate in circuit["gates"]:
        y = gate["y"]
        prereqs = {net for net in (gate["a"], gate["b"]) if net in gate_by_output}
        in_degree[y] = len(prereqs)
        for p in prereqs:
            adj[p].append(y)

    queue = deque([y for y, deg in in_degree.items() if deg == 0])
    topo_order = []

    while queue:
        curr = queue.popleft()
        topo_order.append(gate_by_output[curr])
        for nxt in adj[curr]:
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                queue.append(nxt)

    if len(topo_order) < len(circuit["gates"]):
        error_exit("Combinational cycle detected in gate network")

    # Simulation execution
    dff_state = {dff["q"]: dff["init"] for dff in circuit["dffs"]}
    results: dict[str, list[int]] = {out: [] for out in circuit["outputs"]}

    for t in range(cycles):
        net_values: dict[str, int] = {}
        # 1. Inputs and DFF state
        for inp in circuit["inputs"]:
            net_values[inp] = trace[inp][t]
        for dff in circuit["dffs"]:
            net_values[dff["q"]] = dff_state[dff["q"]]

        # 2. Gate settling in topological order
        for gate in topo_order:
            val_a = net_values[gate["a"]]
            val_b = net_values[gate["b"]]
            net_values[gate["y"]] = 1 - (val_a & val_b)

        # 3. Record outputs
        for out in circuit["outputs"]:
            results[out].append(net_values[out])

        # 4. Clock edge: DFF update
        next_dff_state: dict[str, int] = {}
        for dff in circuit["dffs"]:
            next_dff_state[dff["q"]] = net_values[dff["d"]]
        dff_state = next_dff_state

    return results


def main() -> None:
    if len(sys.argv) != 2:
        sys.stderr.write(f"Usage: {sys.argv[0]} <circuit.json>\n")
        sys.exit(1)

    filepath = sys.argv[1]
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            circuit = json.load(f)
    except Exception as e:
        error_exit(f"Failed to read/parse JSON file '{filepath}': {e}")

    results = simulate(circuit)
    print(json.dumps(results))


if __name__ == "__main__":
    main()
