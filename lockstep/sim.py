"""Reference python simulator. Implements SEMANTICS.md directly on the json netlist.

Deliberately tiny so it can be audited in one sitting. This is one of three
independent evaluation paths (the other two: icarus verilog and verilator via
the generated verilog in verilog.py).
"""

from __future__ import annotations

from .netlist import Netlist, topo_gates

Trace = dict[str, list[int]]


def simulate(nl: Netlist) -> Trace:
    order = topo_gates(nl)
    state = {ff.q: ff.init for ff in nl.dffs}
    out: Trace = {o: [] for o in nl.outputs}
    for t in range(nl.cycles):
        values = dict(state)
        for name in nl.inputs:
            values[name] = nl.trace[name][t]
        for g in order:
            values[g.y] = 1 - (values[g.a] & values[g.b])
        for o in nl.outputs:
            out[o].append(values[o])
        state = {ff.q: values[ff.d] for ff in nl.dffs}
    return out
