"""Load and validate circuit netlists. See SEMANTICS.md for the spec."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

NET_RE = re.compile(r"^[a-z][a-z0-9_]*$")
RESERVED = {"clk"}


class NetlistError(ValueError):
    pass


@dataclass(frozen=True)
class Gate:
    a: str
    b: str
    y: str


@dataclass(frozen=True)
class Dff:
    d: str
    q: str
    init: int


@dataclass(frozen=True)
class Netlist:
    name: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    gates: tuple[Gate, ...]
    dffs: tuple[Dff, ...]
    trace: dict[str, tuple[int, ...]]
    cycles: int


def _check_name(name: object) -> str:
    if not isinstance(name, str) or not NET_RE.match(name) or name in RESERVED:
        raise NetlistError(f"bad net name: {name!r}")
    return name


def _check_bit(v: object) -> int:
    if v is not True and v is not False and v not in (0, 1):
        raise NetlistError(f"bad bit value: {v!r}")
    return int(v)


def from_dict(raw: dict[str, object]) -> Netlist:
    allowed = {"name", "inputs", "outputs", "gates", "dffs", "trace", "cycles"}
    unknown = set(raw) - allowed
    if unknown:
        raise NetlistError(f"unknown keys: {sorted(unknown)}")

    name = raw.get("name")
    if not isinstance(name, str) or not name:
        raise NetlistError("missing circuit name")
    cycles = raw.get("cycles")
    if not isinstance(cycles, int) or cycles < 1:
        raise NetlistError(f"cycles must be a positive int, got {cycles!r}")

    inputs = tuple(_check_name(n) for n in _as_list(raw.get("inputs", []), "inputs"))
    outputs = tuple(_check_name(n) for n in _as_list(raw.get("outputs", []), "outputs"))
    if not outputs:
        raise NetlistError("at least one output is required")

    gates: list[Gate] = []
    for g in _as_list(raw.get("gates", []), "gates"):
        if not isinstance(g, dict):
            raise NetlistError(f"gate is not an object: {g!r}")
        if g.get("type") != "NAND":
            raise NetlistError(f"unsupported gate type: {g.get('type')!r}")
        if set(g) != {"type", "a", "b", "y"}:
            raise NetlistError(f"gate must have exactly type/a/b/y: {g!r}")
        gates.append(Gate(_check_name(g["a"]), _check_name(g["b"]), _check_name(g["y"])))

    dffs: list[Dff] = []
    for f in _as_list(raw.get("dffs", []), "dffs"):
        if not isinstance(f, dict) or set(f) != {"d", "q", "init"}:
            raise NetlistError(f"dff must have exactly d/q/init: {f!r}")
        dffs.append(Dff(_check_name(f["d"]), _check_name(f["q"]), _check_bit(f["init"])))

    raw_trace = raw.get("trace", {})
    if not isinstance(raw_trace, dict):
        raise NetlistError("trace must be an object")
    if set(raw_trace) != set(inputs):
        raise NetlistError(f"trace keys {sorted(raw_trace)} != inputs {sorted(inputs)}")
    trace: dict[str, tuple[int, ...]] = {}
    for k, vals in raw_trace.items():
        vals_list = _as_list(vals, f"trace[{k}]")
        if len(vals_list) != cycles:
            raise NetlistError(f"trace[{k}] has {len(vals_list)} values, expected {cycles}")
        trace[_check_name(k)] = tuple(_check_bit(v) for v in vals_list)

    nl = Netlist(name, inputs, outputs, tuple(gates), tuple(dffs), trace, cycles)
    _validate_structure(nl)
    return nl


def _as_list(v: object, what: str) -> list[object]:
    if not isinstance(v, list):
        raise NetlistError(f"{what} must be a list")
    return v


def _validate_structure(nl: Netlist) -> None:
    drivers: dict[str, str] = {}
    for n in nl.inputs:
        _claim(drivers, n, "input")
    for g in nl.gates:
        _claim(drivers, g.y, "gate")
    for f in nl.dffs:
        _claim(drivers, f.q, "dff")
    for n in _referenced(nl):
        if n not in drivers:
            raise NetlistError(f"net {n!r} is referenced but never driven")
    topo_gates(nl)  # raises on combinational cycles


def _claim(drivers: dict[str, str], net: str, kind: str) -> None:
    if net in drivers:
        raise NetlistError(f"net {net!r} driven twice ({drivers[net]} and {kind})")
    drivers[net] = kind


def _referenced(nl: Netlist) -> set[str]:
    refs = set(nl.outputs)
    for g in nl.gates:
        refs.update((g.a, g.b))
    refs.update(f.d for f in nl.dffs)
    return refs


def topo_gates(nl: Netlist) -> tuple[Gate, ...]:
    """Gates in evaluable order; raises NetlistError on a combinational cycle."""
    by_out = {g.y: g for g in nl.gates}
    order: list[Gate] = []
    state: dict[str, int] = {}  # 1 = visiting, 2 = done

    def visit(g: Gate) -> None:
        if state.get(g.y) == 2:
            return
        if state.get(g.y) == 1:
            raise NetlistError(f"combinational cycle through net {g.y!r}")
        state[g.y] = 1
        # iterative dfs to survive deep chains
        path: list[tuple[Gate, list[Gate]]] = [(g, [by_out[n] for n in (g.a, g.b) if n in by_out])]
        while path:
            cur, deps = path[-1]
            if deps:
                dep = deps.pop()
                if state.get(dep.y) == 1:
                    raise NetlistError(f"combinational cycle through net {dep.y!r}")
                if state.get(dep.y) != 2:
                    state[dep.y] = 1
                    path.append((dep, [by_out[n] for n in (dep.a, dep.b) if n in by_out]))
            else:
                state[cur.y] = 2
                order.append(cur)
                path.pop()

    for g in nl.gates:
        visit(g)
    return tuple(order)


def stats(nl: Netlist) -> dict[str, int]:
    """Honest-difficulty numbers: combinational depth, and the live cone
    (gates/dffs that can actually influence an output on some cycle) —
    nominal gate count overstates difficulty when random DAGs contain dead
    logic."""
    by_out = {g.y: g for g in nl.gates}
    depth: dict[str, int] = {}
    for g in topo_gates(nl):
        depth[g.y] = 1 + max(depth.get(g.a, 0), depth.get(g.b, 0))
    qmap = {f.q: f for f in nl.dffs}
    live_nets = set(nl.outputs)
    live_gates: set[str] = set()
    live_dffs: set[str] = set()
    changed = True
    while changed:
        changed = False
        for n in list(live_nets):
            if n in by_out and n not in live_gates:
                live_gates.add(n)
                live_nets |= {by_out[n].a, by_out[n].b}
                changed = True
            if n in qmap and n not in live_dffs:
                live_dffs.add(n)
                live_nets.add(qmap[n].d)
                changed = True
    return {
        "depth": max(depth.values(), default=0),
        "live_gates": len(live_gates),
        "live_dffs": len(live_dffs),
    }


def to_dict(nl: Netlist) -> dict[str, object]:
    """Inverse of from_dict, for handing circuits to external evaluators."""
    return {
        "name": nl.name,
        "inputs": list(nl.inputs),
        "outputs": list(nl.outputs),
        "gates": [{"type": "NAND", "a": g.a, "b": g.b, "y": g.y} for g in nl.gates],
        "dffs": [{"d": f.d, "q": f.q, "init": f.init} for f in nl.dffs],
        "trace": {k: list(v) for k, v in nl.trace.items()},
        "cycles": nl.cycles,
    }


def load(path: str | Path) -> Netlist:
    with open(path) as fh:
        raw = json.load(fh)
    if not isinstance(raw, dict):
        raise NetlistError(f"{path}: top level must be an object")
    return from_dict(raw)
