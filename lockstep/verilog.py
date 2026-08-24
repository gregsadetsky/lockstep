"""Mechanical translation of a netlist to structural verilog plus a testbench.

The testbench is straight-line code (no loops) so there is nothing clever to
trust: set inputs, wait, print, clock. Trace lines are printed as
TRACE,<cycle>,<bit>,<bit>,... with bits in nl.outputs order, sampled at
timestep offset +4, one tick before the posedge at +5 (matching SEMANTICS.md
step 3 "record, then clock edge").
"""

from __future__ import annotations

from .netlist import Netlist

TRACE_PREFIX = "TRACE"


def module(nl: Netlist) -> str:
    ports = ["input wire clk"]
    ports += [f"input wire i_{n}" for n in nl.inputs]
    ports += [f"output wire o_{n}" for n in nl.outputs]
    lines = ["module top(", "  " + ",\n  ".join(ports), ");"]
    for n in nl.inputs:
        lines.append(f"  wire {n};")
        lines.append(f"  assign {n} = i_{n};")
    for f in nl.dffs:
        lines.append(f"  reg {f.q} = 1'b{f.init};")
    for g in nl.gates:
        lines.append(f"  wire {g.y};")
    for i, g in enumerate(nl.gates):
        lines.append(f"  nand g{i}({g.y}, {g.a}, {g.b});")
    for f in nl.dffs:
        lines.append(f"  always @(posedge clk) {f.q} <= {f.d};")
    for n in nl.outputs:
        lines.append(f"  assign o_{n} = {n};")
    lines.append("endmodule")
    return "\n".join(lines) + "\n"


def testbench(nl: Netlist) -> str:
    lines = ["`timescale 1ns/1ns", "module tb;", "  reg clk;"]
    for n in nl.inputs:
        lines.append(f"  reg i_{n};")
    for n in nl.outputs:
        lines.append(f"  wire o_{n};")
    conns = [".clk(clk)"]
    conns += [f".i_{n}(i_{n})" for n in nl.inputs]
    conns += [f".o_{n}(o_{n})" for n in nl.outputs]
    lines.append(f"  top dut({', '.join(conns)});")
    fmt = ",".join(["%b"] * len(nl.outputs))
    args = ", ".join(f"o_{n}" for n in nl.outputs)
    lines.append("  initial begin")
    lines.append("    clk = 1'b0;")
    for t in range(nl.cycles):
        for n in nl.inputs:
            lines.append(f"    i_{n} = 1'b{nl.trace[n][t]};")
        lines.append("    #4;")
        lines.append(f'    $display("{TRACE_PREFIX},%0d,{fmt}", {t}, {args});')
        lines.append("    #1;")
        lines.append("    clk = 1'b1;")
        lines.append("    #5;")
        lines.append("    clk = 1'b0;")
    lines.append("    $finish;")
    lines.append("  end")
    lines.append("endmodule")
    return "\n".join(lines) + "\n"


def parse_trace(stdout: str, nl: Netlist) -> dict[str, list[int]]:
    """Parse TRACE lines from a simulator run back into {output: [bits]}."""
    out: dict[str, list[int]] = {o: [] for o in nl.outputs}
    expected_t = 0
    for line in stdout.splitlines():
        if not line.startswith(TRACE_PREFIX + ","):
            continue
        fields = line.strip().split(",")
        if len(fields) != 2 + len(nl.outputs):
            raise ValueError(f"malformed trace line: {line!r}")
        if int(fields[1]) != expected_t:
            raise ValueError(f"trace cycle out of order: {line!r}")
        for name, bit in zip(nl.outputs, fields[2:], strict=True):
            if bit not in ("0", "1"):
                raise ValueError(f"non-binary value {bit!r} in: {line!r}")
            out[name].append(int(bit))
        expected_t += 1
    if expected_t != nl.cycles:
        raise ValueError(f"expected {nl.cycles} trace lines, got {expected_t}")
    return out
