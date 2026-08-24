#!/usr/bin/env python3
"""
Translator from circuit netlist JSON format to Verilog (.v) with testbench.
Faithfully implements the specification in SEMANTICS.md.
"""

import json
import os
import re
import sys

NET_REGEX = re.compile(r"^[a-z][a-z0-9_]*$")


def error_exit(msg: str) -> None:
    sys.stderr.write(f"Error: {msg}\n")
    sys.exit(1)


def validate_net_name(name: str, context: str) -> None:
    if not isinstance(name, str):
        error_exit(f"Net name {name!r} in {context} must be a string")
    if not NET_REGEX.fullmatch(name):
        error_exit(f"Net name {name!r} in {context} does not match pattern [a-z][a-z0-9_]*")
    if name == "clk":
        error_exit(f"Net name 'clk' in {context} is reserved")


def validate_circuit(circuit: dict) -> None:
    if not isinstance(circuit, dict):
        error_exit("Top-level circuit JSON must be an object")

    required_keys = {"name", "inputs", "outputs", "gates", "dffs", "trace", "cycles"}
    missing = required_keys - set(circuit.keys())
    if missing:
        error_exit(f"Missing required keys in circuit JSON: {missing}")
    extra = set(circuit.keys()) - required_keys
    if extra:
        error_exit(f"Unknown keys in circuit JSON: {extra}")

    # Validate name
    if not isinstance(circuit["name"], str):
        error_exit("Circuit 'name' must be a string")

    # Validate cycles
    cycles = circuit["cycles"]
    if isinstance(cycles, bool) or not isinstance(cycles, int) or cycles < 0:
        error_exit(f"Circuit 'cycles' must be a non-negative integer, got {cycles!r}")

    # Validate inputs
    inputs = circuit["inputs"]
    if not isinstance(inputs, list):
        error_exit("Circuit 'inputs' must be a list")
    for net in inputs:
        validate_net_name(net, "inputs")
    if len(set(inputs)) != len(inputs):
        error_exit("Duplicate net names found in 'inputs'")
    input_set = set(inputs)

    # Validate outputs
    outputs = circuit["outputs"]
    if not isinstance(outputs, list):
        error_exit("Circuit 'outputs' must be a list")
    for net in outputs:
        validate_net_name(net, "outputs")

    # Validate gates
    gates = circuit["gates"]
    if not isinstance(gates, list):
        error_exit("Circuit 'gates' must be a list")
    gate_req_keys = {"type", "a", "b", "y"}
    gate_y_list = []
    for i, g in enumerate(gates):
        if not isinstance(g, dict):
            error_exit(f"Gate {i} must be an object")
        if set(g.keys()) != gate_req_keys:
            error_exit(f"Gate {i} keys must be exactly {gate_req_keys}, got {set(g.keys())}")
        if g["type"] != "NAND":
            error_exit(f"Gate {i} type must be 'NAND', got {g['type']!r}")
        validate_net_name(g["a"], f"gate {i} input 'a'")
        validate_net_name(g["b"], f"gate {i} input 'b'")
        validate_net_name(g["y"], f"gate {i} output 'y'")
        gate_y_list.append(g["y"])

    if len(set(gate_y_list)) != len(gate_y_list):
        error_exit("Multiple gates drive the same output net 'y'")
    gate_y_set = set(gate_y_list)

    # Validate dffs
    dffs = circuit["dffs"]
    if not isinstance(dffs, list):
        error_exit("Circuit 'dffs' must be a list")
    dff_req_keys = {"d", "q", "init"}
    dff_q_list = []
    for i, d in enumerate(dffs):
        if not isinstance(d, dict):
            error_exit(f"DFF {i} must be an object")
        if set(d.keys()) != dff_req_keys:
            error_exit(f"DFF {i} keys must be exactly {dff_req_keys}, got {set(d.keys())}")
        validate_net_name(d["d"], f"dff {i} input 'd'")
        validate_net_name(d["q"], f"dff {i} output 'q'")
        init_val = d["init"]
        if isinstance(init_val, bool) or not isinstance(init_val, int) or init_val not in (0, 1):
            error_exit(f"DFF {i} 'init' must be integer 0 or 1, got {init_val!r}")
        dff_q_list.append(d["q"])

    if len(set(dff_q_list)) != len(dff_q_list):
        error_exit("Multiple DFFs drive the same output net 'q'")
    dff_q_set = set(dff_q_list)

    # Check driver uniqueness across sets
    if input_set & gate_y_set:
        error_exit(f"Nets driven by both input and gate output: {input_set & gate_y_set}")
    if input_set & dff_q_set:
        error_exit(f"Nets driven by both input and DFF output: {input_set & dff_q_set}")
    if gate_y_set & dff_q_set:
        error_exit(f"Nets driven by both gate output and DFF output: {gate_y_set & dff_q_set}")

    drivers = input_set | gate_y_set | dff_q_set

    # Check all referenced nets are driven
    for i, g in enumerate(gates):
        if g["a"] not in drivers:
            error_exit(f"Net {g['a']!r} referenced in gate {i} input 'a' is not driven")
        if g["b"] not in drivers:
            error_exit(f"Net {g['b']!r} referenced in gate {i} input 'b' is not driven")

    for i, d in enumerate(dffs):
        if d["d"] not in drivers:
            error_exit(f"Net {d['d']!r} referenced in DFF {i} input 'd' is not driven")

    for i, out in enumerate(outputs):
        if out not in drivers:
            error_exit(f"Net {out!r} referenced in circuit outputs[{i}] is not driven")

    # Check gate-only graph acyclicity
    gate_deps = {g["y"]: set() for g in gates}
    for g in gates:
        y = g["y"]
        if g["a"] in gate_y_set:
            gate_deps[y].add(g["a"])
        if g["b"] in gate_y_set:
            gate_deps[y].add(g["b"])

    visited = {y: 0 for y in gate_y_set}  # 0: unvisited, 1: visiting, 2: visited

    def dfs(node: str) -> bool:
        visited[node] = 1
        for neighbor in gate_deps[node]:
            if visited[neighbor] == 1:
                return True
            if visited[neighbor] == 0:
                if dfs(neighbor):
                    return True
        visited[node] = 2
        return False

    for node in gate_y_set:
        if visited[node] == 0:
            if dfs(node):
                error_exit(f"Combinational cycle detected in gate-only graph involving net {node!r}")

    # Validate trace
    trace = circuit["trace"]
    if not isinstance(trace, dict):
        error_exit("Circuit 'trace' must be an object (dict)")
    if set(trace.keys()) != input_set:
        error_exit(f"Trace keys do not match circuit inputs. Trace: {set(trace.keys())}, Inputs: {input_set}")
    for net, vals in trace.items():
        if not isinstance(vals, list):
            error_exit(f"Trace for input {net!r} must be a list")
        if len(vals) != cycles:
            error_exit(f"Trace length for input {net!r} ({len(vals)}) does not match cycles ({cycles})")
        for step_idx, v in enumerate(vals):
            if isinstance(v, bool) or not isinstance(v, int) or v not in (0, 1):
                error_exit(f"Trace value at cycle {step_idx} for input {net!r} must be 0 or 1, got {v!r}")


def generate_circuit_verilog(circuit: dict) -> str:
    inputs = circuit["inputs"]
    outputs = circuit["outputs"]
    gates = circuit["gates"]
    dffs = circuit["dffs"]

    port_list = ["input wire clk"]
    for inp in inputs:
        port_list.append(f"input wire in_{inp}")
    for i in range(len(outputs)):
        port_list.append(f"output wire out_{i}")

    ports_str = ",\n  ".join(port_list)

    lines = []
    lines.append("`timescale 1ns/1ps")
    lines.append("")
    lines.append("module circuit (")
    lines.append(f"  {ports_str}")
    lines.append(");")

    # Declarations of all nets
    lines.append("  // Net declarations")
    for inp in inputs:
        lines.append(f"  wire n_{inp} = in_{inp};")
    for g in gates:
        lines.append(f"  wire n_{g['y']};")
    for d in dffs:
        q = d["q"]
        init_val = d["init"]
        lines.append(f"  reg r_{q} = 1'b{init_val};")
        lines.append(f"  wire n_{q} = r_{q};")

    # Gates logic
    if gates:
        lines.append("")
        lines.append("  // Gates")
        for g in gates:
            y = g["y"]
            a = g["a"]
            b = g["b"]
            lines.append(f"  assign n_{y} = ~(n_{a} & n_{b});")

    # DFFs sequential logic
    if dffs:
        lines.append("")
        lines.append("  // DFFs")
        lines.append("  always @(posedge clk) begin")
        for d in dffs:
            q = d["q"]
            d_net = d["d"]
            lines.append(f"    r_{q} <= n_{d_net};")
        lines.append("  end")

    # Outputs
    if outputs:
        lines.append("")
        lines.append("  // Outputs")
        for i, out_net in enumerate(outputs):
            lines.append(f"  assign out_{i} = n_{out_net};")

    lines.append("endmodule")
    lines.append("")
    return "\n".join(lines)


def generate_tb_verilog(circuit: dict) -> str:
    inputs = circuit["inputs"]
    outputs = circuit["outputs"]
    trace = circuit["trace"]
    cycles = circuit["cycles"]

    lines = []
    lines.append("`timescale 1ns/1ps")
    lines.append("")
    lines.append("module tb;")
    lines.append("  reg clk;")

    if inputs:
        for inp in inputs:
            lines.append(f"  reg in_{inp};")

    if outputs:
        for i in range(len(outputs)):
            lines.append(f"  wire out_{i};")

    lines.append("")
    lines.append("  circuit dut (")
    dut_conns = [".clk(clk)"]
    for inp in inputs:
        dut_conns.append(f".in_{inp}(in_{inp})")
    for i in range(len(outputs)):
        dut_conns.append(f".out_{i}(out_{i})")
    lines.append("    " + ",\n    ".join(dut_conns))
    lines.append("  );")
    lines.append("")
    lines.append("  initial begin")
    lines.append("    clk = 0;")

    for t in range(cycles):
        lines.append(f"    // Cycle {t}")
        for inp in inputs:
            val = trace[inp][t]
            lines.append(f"    in_{inp} = 1'b{val};")
        lines.append("    #1;")
        if outputs:
            fmt = "TRACE," + str(t) + "," + ",".join(["%b"] * len(outputs))
            args = ", ".join(f"out_{i}" for i in range(len(outputs)))
            lines.append(f'    $display("{fmt}", {args});')
        else:
            lines.append(f'    $display("TRACE,{t}");')
        lines.append("    clk = 1;")
        lines.append("    #1;")
        lines.append("    clk = 0;")

    lines.append("    $finish(0);")
    lines.append("  end")
    lines.append("endmodule")
    lines.append("")
    return "\n".join(lines)


def main():
    if len(sys.argv) != 3:
        error_exit(f"Usage: {sys.argv[0]} <circuit.json> <outdir>")

    circuit_file = sys.argv[1]
    outdir = sys.argv[2]

    try:
        with open(circuit_file, "r", encoding="utf-8") as f:
            circuit = json.load(f)
    except Exception as e:
        error_exit(f"Failed to read or parse JSON from {circuit_file}: {e}")

    validate_circuit(circuit)

    try:
        os.makedirs(outdir, exist_ok=True)
    except Exception as e:
        error_exit(f"Failed to create output directory {outdir}: {e}")

    circuit_v = generate_circuit_verilog(circuit)
    tb_v = generate_tb_verilog(circuit)

    circuit_v_path = os.path.join(outdir, "circuit.v")
    tb_v_path = os.path.join(outdir, "tb.v")

    try:
        with open(circuit_v_path, "w", encoding="utf-8") as f:
            f.write(circuit_v)
        with open(tb_v_path, "w", encoding="utf-8") as f:
            f.write(tb_v)
    except Exception as e:
        error_exit(f"Failed to write Verilog files to {outdir}: {e}")


if __name__ == "__main__":
    main()
