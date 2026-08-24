#!/usr/bin/env python3
"""Translate the SEMANTICS.md circuit JSON format to Verilog."""

from __future__ import annotations

import json
import re
import sys
from collections import deque
from pathlib import Path
from typing import Any


NET_RE = re.compile(r"^[a-z][a-z0-9_]*$")
TOP_KEYS = {"name", "inputs", "outputs", "gates", "dffs", "trace", "cycles"}
GATE_KEYS = {"type", "a", "b", "y"}
DFF_KEYS = {"d", "q", "init"}


class SpecError(Exception):
    pass


def fail(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 1


def no_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SpecError(f"duplicate JSON object key {key!r}")
        result[key] = value
    return result


def require_object(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SpecError(f"{context} must be an object")
    return value


def require_list(value: Any, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise SpecError(f"{context} must be an array")
    return value


def require_exact_keys(obj: dict[str, Any], keys: set[str], context: str) -> None:
    actual = set(obj)
    missing = sorted(keys - actual)
    extra = sorted(actual - keys)
    if missing:
        raise SpecError(f"{context} is missing required key(s): {', '.join(missing)}")
    if extra:
        raise SpecError(f"{context} has unknown key(s): {', '.join(extra)}")


def require_int(value: Any, context: str) -> int:
    if type(value) is not int:
        raise SpecError(f"{context} must be an integer")
    return value


def require_bit(value: Any, context: str) -> int:
    bit = require_int(value, context)
    if bit not in (0, 1):
        raise SpecError(f"{context} must be 0 or 1")
    return bit


def require_net_name(value: Any, context: str) -> str:
    if not isinstance(value, str):
        raise SpecError(f"{context} must be a string net name")
    if not NET_RE.fullmatch(value):
        raise SpecError(f"{context} {value!r} does not match [a-z][a-z0-9_]*")
    if value == "clk":
        raise SpecError(f"{context} uses reserved net name 'clk'")
    return value


def require_net_list(value: Any, context: str, *, unique: bool) -> list[str]:
    raw_items = require_list(value, context)
    items: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_items):
        net = require_net_name(item, f"{context}[{index}]")
        if unique and net in seen:
            raise SpecError(f"{context} contains duplicate net {net!r}")
        seen.add(net)
        items.append(net)
    return items


def add_driver(drivers: dict[str, str], net: str, source: str) -> None:
    previous = drivers.get(net)
    if previous is not None:
        raise SpecError(f"net {net!r} is driven by both {previous} and {source}")
    drivers[net] = source


def require_driven(drivers: dict[str, str], net: str, context: str) -> None:
    if net not in drivers:
        raise SpecError(f"{context} references undriven net {net!r}")


def validate_circuit(circuit: Any) -> dict[str, Any]:
    circuit = require_object(circuit, "circuit")
    require_exact_keys(circuit, TOP_KEYS, "circuit")

    if not isinstance(circuit["name"], str):
        raise SpecError("circuit.name must be a string")

    cycles = require_int(circuit["cycles"], "circuit.cycles")
    if cycles < 0:
        raise SpecError("circuit.cycles must be nonnegative")

    inputs = require_net_list(circuit["inputs"], "circuit.inputs", unique=True)
    outputs = require_net_list(circuit["outputs"], "circuit.outputs", unique=False)

    raw_gates = require_list(circuit["gates"], "circuit.gates")
    raw_dffs = require_list(circuit["dffs"], "circuit.dffs")
    trace = require_object(circuit["trace"], "circuit.trace")

    drivers: dict[str, str] = {}
    for net in inputs:
        add_driver(drivers, net, "circuit input")

    gates: list[dict[str, str]] = []
    gate_output_to_index: dict[str, int] = {}
    for index, raw_gate in enumerate(raw_gates):
        gate = require_object(raw_gate, f"circuit.gates[{index}]")
        require_exact_keys(gate, GATE_KEYS, f"circuit.gates[{index}]")
        if gate["type"] != "NAND":
            raise SpecError(f"circuit.gates[{index}].type must be 'NAND'")
        a = require_net_name(gate["a"], f"circuit.gates[{index}].a")
        b = require_net_name(gate["b"], f"circuit.gates[{index}].b")
        y = require_net_name(gate["y"], f"circuit.gates[{index}].y")
        add_driver(drivers, y, f"gate {index} output")
        gate_output_to_index[y] = index
        gates.append({"a": a, "b": b, "y": y})

    dffs: list[dict[str, Any]] = []
    for index, raw_dff in enumerate(raw_dffs):
        dff = require_object(raw_dff, f"circuit.dffs[{index}]")
        require_exact_keys(dff, DFF_KEYS, f"circuit.dffs[{index}]")
        d = require_net_name(dff["d"], f"circuit.dffs[{index}].d")
        q = require_net_name(dff["q"], f"circuit.dffs[{index}].q")
        init = require_bit(dff["init"], f"circuit.dffs[{index}].init")
        add_driver(drivers, q, f"dff {index} output")
        dffs.append({"d": d, "q": q, "init": init})

    for index, gate in enumerate(gates):
        require_driven(drivers, gate["a"], f"circuit.gates[{index}].a")
        require_driven(drivers, gate["b"], f"circuit.gates[{index}].b")
    for index, dff in enumerate(dffs):
        require_driven(drivers, dff["d"], f"circuit.dffs[{index}].d")
    for index, output in enumerate(outputs):
        require_driven(drivers, output, f"circuit.outputs[{index}]")

    input_set = set(inputs)
    trace_keys = set(trace)
    missing_trace = sorted(input_set - trace_keys)
    extra_trace = sorted(trace_keys - input_set)
    if missing_trace:
        raise SpecError(f"circuit.trace is missing input(s): {', '.join(missing_trace)}")
    if extra_trace:
        raise SpecError(f"circuit.trace has non-input key(s): {', '.join(extra_trace)}")
    for net in inputs:
        values = require_list(trace[net], f"circuit.trace[{net!r}]")
        if len(values) != cycles:
            raise SpecError(
                f"circuit.trace[{net!r}] length {len(values)} does not match cycles {cycles}"
            )
        for index, value in enumerate(values):
            require_bit(value, f"circuit.trace[{net!r}][{index}]")

    gate_order = topological_gate_order(gates, gate_output_to_index)

    return {
        "name": circuit["name"],
        "cycles": cycles,
        "inputs": inputs,
        "outputs": outputs,
        "gates": gates,
        "gate_order": gate_order,
        "dffs": dffs,
        "trace": trace,
    }


def topological_gate_order(
    gates: list[dict[str, str]], gate_output_to_index: dict[str, int]
) -> list[int]:
    indegree = [0] * len(gates)
    edges: list[list[int]] = [[] for _ in gates]
    for index, gate in enumerate(gates):
        for source_net in (gate["a"], gate["b"]):
            source_index = gate_output_to_index.get(source_net)
            if source_index is not None:
                edges[source_index].append(index)
                indegree[index] += 1

    ready = deque(index for index, degree in enumerate(indegree) if degree == 0)
    order: list[int] = []
    while ready:
        index = ready.popleft()
        order.append(index)
        for downstream in edges[index]:
            indegree[downstream] -= 1
            if indegree[downstream] == 0:
                ready.append(downstream)

    if len(order) != len(gates):
        raise SpecError("gate-only graph contains a cycle")
    return order


def v_net(name: str) -> str:
    return f"net_{name}"


def v_input(name: str) -> str:
    return f"in_{name}"


def v_output(index: int) -> str:
    return f"out_{index}"


def emit_port_list(port_decls: list[str]) -> list[str]:
    lines = ["("]
    for index, decl in enumerate(port_decls):
        comma = "," if index + 1 < len(port_decls) else ""
        lines.append(f"    {decl}{comma}")
    lines.append(");")
    return lines


def emit_dut(circuit: dict[str, Any]) -> str:
    inputs: list[str] = circuit["inputs"]
    outputs: list[str] = circuit["outputs"]
    gates: list[dict[str, str]] = circuit["gates"]
    dffs: list[dict[str, Any]] = circuit["dffs"]
    gate_order: list[int] = circuit["gate_order"]

    ports = (
        ["input wire clk"]
        + [f"input wire {v_input(net)}" for net in inputs]
        + [f"output wire {v_output(index)}" for index in range(len(outputs))]
    )

    lines: list[str] = ["`timescale 1ns/1ps", "module circuit_dut"]
    lines.extend(emit_port_list(ports))

    if inputs or gates or dffs:
        lines.append("")

    for net in inputs:
        lines.append(f"    wire {v_net(net)};")
    for gate in gates:
        lines.append(f"    wire {v_net(gate['y'])};")
    for dff in dffs:
        lines.append(f"    reg {v_net(dff['q'])};")

    if inputs:
        lines.append("")
        for net in inputs:
            lines.append(f"    assign {v_net(net)} = {v_input(net)};")

    if gates:
        lines.append("")
        for gate_index in gate_order:
            gate = gates[gate_index]
            lines.append(
                f"    assign {v_net(gate['y'])} = ~({v_net(gate['a'])} & {v_net(gate['b'])});"
            )

    if dffs:
        lines.append("")
        lines.append("    initial begin")
        for dff in dffs:
            lines.append(f"        {v_net(dff['q'])} = 1'b{dff['init']};")
        lines.append("    end")
        lines.append("")
        lines.append("    always @(posedge clk) begin")
        for dff in dffs:
            lines.append(f"        {v_net(dff['q'])} <= {v_net(dff['d'])};")
        lines.append("    end")

    if outputs:
        lines.append("")
        for index, net in enumerate(outputs):
            lines.append(f"    assign {v_output(index)} = {v_net(net)};")

    lines.append("endmodule")
    return "\n".join(lines) + "\n"


def emit_instance_ports(inputs: list[str], output_count: int) -> list[str]:
    ports = [".clk(clk)"]
    ports.extend(f".{v_input(net)}({v_input(net)})" for net in inputs)
    ports.extend(f".{v_output(index)}({v_output(index)})" for index in range(output_count))
    return ports


def emit_tb(circuit: dict[str, Any]) -> str:
    inputs: list[str] = circuit["inputs"]
    outputs: list[str] = circuit["outputs"]
    trace: dict[str, list[int]] = circuit["trace"]
    cycles: int = circuit["cycles"]

    lines: list[str] = ["`timescale 1ns/1ps", "module tb;", "    reg clk;"]
    for net in inputs:
        lines.append(f"    reg {v_input(net)};")
    for index in range(len(outputs)):
        lines.append(f"    wire {v_output(index)};")
    lines.append("    integer cycle;")
    lines.append("")

    lines.append("    circuit_dut dut (")
    ports = emit_instance_ports(inputs, len(outputs))
    for index, port in enumerate(ports):
        comma = "," if index + 1 < len(ports) else ""
        lines.append(f"        {port}{comma}")
    lines.append("    );")
    lines.append("")

    lines.append("    initial begin")
    lines.append("        clk = 1'b0;")
    for net in inputs:
        lines.append(f"        {v_input(net)} = 1'b0;")
    lines.append(f"        for (cycle = 0; cycle < {cycles}; cycle = cycle + 1) begin")
    if inputs:
        lines.append("            case (cycle)")
        for cycle in range(cycles):
            lines.append(f"                {cycle}: begin")
            for net in inputs:
                lines.append(f"                    {v_input(net)} = 1'b{trace[net][cycle]};")
            lines.append("                end")
        lines.append("                default: begin")
        lines.append("                end")
        lines.append("            endcase")
    lines.append("            #1;")

    display_format = "TRACE,%0d" + ",%0b" * len(outputs)
    display_args = ["cycle"] + [v_output(index) for index in range(len(outputs))]
    lines.append(f"            $display(\"{display_format}\", {', '.join(display_args)});")
    lines.append("            #1;")
    lines.append("            clk = 1'b1;")
    lines.append("            #1;")
    lines.append("            clk = 1'b0;")
    lines.append("            #1;")
    lines.append("        end")
    lines.append("    end")
    lines.append("endmodule")
    return "\n".join(lines) + "\n"


def clean_verilog_outputs(outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    if not outdir.is_dir():
        raise OSError(f"{outdir} is not a directory")
    for path in outdir.iterdir():
        if path.name.endswith(".v"):
            if path.is_file() or path.is_symlink():
                path.unlink()
            else:
                raise OSError(f"cannot replace non-file Verilog output {path}")


def write_verilog(circuit: dict[str, Any], outdir: Path) -> None:
    clean_verilog_outputs(outdir)
    (outdir / "circuit_dut.v").write_text(emit_dut(circuit), encoding="utf-8")
    (outdir / "tb.v").write_text(emit_tb(circuit), encoding="utf-8")


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: python3 translate_codex.py <circuit.json> <outdir>", file=sys.stderr)
        return 2

    circuit_path = Path(argv[1])
    outdir = Path(argv[2])

    try:
        with circuit_path.open("r", encoding="utf-8") as handle:
            circuit_json = json.load(handle, object_pairs_hook=no_duplicate_json_keys)
        circuit = validate_circuit(circuit_json)
        write_verilog(circuit, outdir)
    except SpecError as exc:
        return fail(str(exc))
    except json.JSONDecodeError as exc:
        return fail(f"invalid JSON: {exc}")
    except OSError as exc:
        return fail(str(exc))

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
