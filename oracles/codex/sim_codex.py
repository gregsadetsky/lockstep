#!/usr/bin/env python3
import json
import re
import sys
from collections import deque


NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def fail(message):
    print(message, file=sys.stderr)
    sys.exit(1)


def is_plain_int(value):
    return type(value) is int


def require_bit(value, where):
    if not is_plain_int(value) or value not in (0, 1):
        fail(f"{where}: expected bit 0 or 1")
    return value


def require_name(value, where):
    if not isinstance(value, str) or not NAME_RE.fullmatch(value) or value == "clk":
        fail(f"{where}: invalid net name")
    return value


def require_list(value, where):
    if not isinstance(value, list):
        fail(f"{where}: expected list")
    return value


def require_object(value, where):
    if not isinstance(value, dict):
        fail(f"{where}: expected object")
    return value


def load_circuit(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except OSError as exc:
        fail(f"cannot read {path}: {exc}")
    except json.JSONDecodeError as exc:
        fail(f"invalid json: {exc}")

    return require_object(data, "circuit")


def add_driver(drivers, net, kind):
    if net in drivers:
        fail(f"net driven twice: {net}")
    drivers[net] = kind


def get_required(circuit, key):
    if key not in circuit:
        fail(f"missing required field: {key}")
    return circuit[key]


def validate_and_prepare(circuit):
    if not isinstance(get_required(circuit, "name"), str):
        fail("name: expected string")

    inputs = require_list(get_required(circuit, "inputs"), "inputs")
    outputs = require_list(get_required(circuit, "outputs"), "outputs")
    gates = require_list(get_required(circuit, "gates"), "gates")
    dffs = require_list(get_required(circuit, "dffs"), "dffs")
    trace = require_object(get_required(circuit, "trace"), "trace")
    cycles = get_required(circuit, "cycles")
    if not is_plain_int(cycles) or cycles < 0:
        fail("cycles: expected nonnegative integer")

    input_names = []
    output_names = []
    drivers = {}

    for i, net in enumerate(inputs):
        net = require_name(net, f"inputs[{i}]")
        input_names.append(net)
        add_driver(drivers, net, "input")

    for i, net in enumerate(outputs):
        net = require_name(net, f"outputs[{i}]")
        if net in output_names:
            fail(f"outputs[{i}]: duplicate output net {net}")
        output_names.append(net)

    gate_infos = []
    for i, gate in enumerate(gates):
        gate = require_object(gate, f"gates[{i}]")
        if gate.get("type") != "NAND":
            fail(f"gates[{i}]: unknown gate type")
        if set(gate.keys()) != {"type", "a", "b", "y"}:
            fail(f"gates[{i}]: NAND gate must have exactly type, a, b, y")
        a = require_name(gate["a"], f"gates[{i}].a")
        b = require_name(gate["b"], f"gates[{i}].b")
        y = require_name(gate["y"], f"gates[{i}].y")
        gate_infos.append({"a": a, "b": b, "y": y})
        add_driver(drivers, y, "gate")

    dff_infos = []
    for i, dff in enumerate(dffs):
        dff = require_object(dff, f"dffs[{i}]")
        if set(dff.keys()) != {"d", "q", "init"}:
            fail(f"dffs[{i}]: DFF must have exactly d, q, init")
        d = require_name(dff["d"], f"dffs[{i}].d")
        q = require_name(dff["q"], f"dffs[{i}].q")
        init = require_bit(dff["init"], f"dffs[{i}].init")
        dff_infos.append({"d": d, "q": q, "init": init})
        add_driver(drivers, q, "dff")

    expected_trace_keys = set(input_names)
    actual_trace_keys = set()
    for key, values in trace.items():
        net = require_name(key, f"trace key {key!r}")
        actual_trace_keys.add(net)
        values = require_list(values, f"trace.{net}")
        if len(values) != cycles:
            fail(f"trace.{net}: wrong trace length")
        for i, value in enumerate(values):
            require_bit(value, f"trace.{net}[{i}]")

    if actual_trace_keys != expected_trace_keys:
        missing = expected_trace_keys - actual_trace_keys
        extra = actual_trace_keys - expected_trace_keys
        if missing:
            fail(f"trace missing input: {sorted(missing)[0]}")
        fail(f"trace has non-input net: {sorted(extra)[0]}")

    for i, gate in enumerate(gate_infos):
        for pin in ("a", "b"):
            if gate[pin] not in drivers:
                fail(f"gates[{i}].{pin}: undriven reference {gate[pin]}")

    for i, dff in enumerate(dff_infos):
        if dff["d"] not in drivers:
            fail(f"dffs[{i}].d: undriven reference {dff['d']}")

    for i, net in enumerate(output_names):
        if net not in drivers:
            fail(f"outputs[{i}]: undriven reference {net}")

    gate_order = topo_sort_gates(gate_infos, drivers)

    return {
        "inputs": input_names,
        "outputs": output_names,
        "gates": gate_order,
        "dffs": dff_infos,
        "trace": trace,
        "cycles": cycles,
    }


def topo_sort_gates(gates, drivers):
    producer = {gate["y"]: i for i, gate in enumerate(gates)}
    outgoing = [[] for _ in gates]
    indegree = [0] * len(gates)

    for i, gate in enumerate(gates):
        dependencies = set()
        for pin in ("a", "b"):
            source = gate[pin]
            if drivers[source] == "gate":
                dependencies.add(producer[source])
        for dep in dependencies:
            outgoing[dep].append(i)
            indegree[i] += 1

    ready = deque(i for i, degree in enumerate(indegree) if degree == 0)
    ordered_indices = []
    while ready:
        i = ready.popleft()
        ordered_indices.append(i)
        for child in outgoing[i]:
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)

    if len(ordered_indices) != len(gates):
        fail("combinational cycle")

    return [gates[i] for i in ordered_indices]


def simulate(prepared):
    trace = prepared["trace"]
    cycles = prepared["cycles"]
    gates = prepared["gates"]
    dffs = prepared["dffs"]
    outputs = prepared["outputs"]

    values = {dff["q"]: dff["init"] for dff in dffs}
    recorded = {net: [] for net in outputs}

    for t in range(cycles):
        for net in prepared["inputs"]:
            values[net] = trace[net][t]

        for gate in gates:
            values[gate["y"]] = 1 - (values[gate["a"]] & values[gate["b"]])

        for net in outputs:
            recorded[net].append(values[net])

        next_state = {}
        for dff in dffs:
            next_state[dff["q"]] = values[dff["d"]]
        values.update(next_state)

    return recorded


def main(argv):
    if len(argv) != 2:
        fail("usage: python3 sim_codex.py <circuit.json>")
    circuit = load_circuit(argv[1])
    prepared = validate_and_prepare(circuit)
    result = simulate(prepared)
    print(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main(sys.argv)
