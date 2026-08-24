"""Axiomatic layer: the python simulator's primitives checked against the
definitions in SEMANTICS.md (nand truth table, dff one-cycle delay). These are
the only 'expected values' in the whole project that come from a human-written
definition rather than from cross-simulator agreement."""

from typing import Any

import pytest

from lockstep.netlist import NetlistError, from_dict
from lockstep.sim import simulate


def build(**kw: Any) -> Any:
    base: dict[str, Any] = {
        "name": "t",
        "inputs": [],
        "outputs": [],
        "gates": [],
        "dffs": [],
        "trace": {},
        "cycles": 1,
    }
    base.update(kw)
    return from_dict(base)


def test_nand_truth_table() -> None:
    nl = build(
        inputs=["a", "b"],
        outputs=["y"],
        gates=[{"type": "NAND", "a": "a", "b": "b", "y": "y"}],
        trace={"a": [0, 0, 1, 1], "b": [0, 1, 0, 1]},
        cycles=4,
    )
    assert simulate(nl)["y"] == [1, 1, 1, 0]


def test_not_from_nand() -> None:
    nl = build(
        inputs=["a"],
        outputs=["y"],
        gates=[{"type": "NAND", "a": "a", "b": "a", "y": "y"}],
        trace={"a": [0, 1]},
        cycles=2,
    )
    assert simulate(nl)["y"] == [1, 0]


def test_xor_from_nands() -> None:
    nl = build(
        inputs=["a", "b"],
        outputs=["y"],
        gates=[
            {"type": "NAND", "a": "a", "b": "b", "y": "t1"},
            {"type": "NAND", "a": "a", "b": "t1", "y": "t2"},
            {"type": "NAND", "a": "b", "b": "t1", "y": "t3"},
            {"type": "NAND", "a": "t2", "b": "t3", "y": "y"},
        ],
        trace={"a": [0, 0, 1, 1], "b": [0, 1, 0, 1]},
        cycles=4,
    )
    assert simulate(nl)["y"] == [0, 1, 1, 0]


def test_dff_delays_by_one_cycle() -> None:
    nl = build(
        inputs=["a"],
        outputs=["q"],
        dffs=[{"d": "a", "q": "q", "init": 0}],
        trace={"a": [1, 0, 1, 1]},
        cycles=4,
    )
    assert simulate(nl)["q"] == [0, 1, 0, 1]


def test_dff_init_one_holds() -> None:
    nl = build(
        outputs=["q"],
        dffs=[{"d": "q", "q": "q", "init": 1}],
        cycles=3,
    )
    assert simulate(nl)["q"] == [1, 1, 1]


def test_dffs_update_simultaneously() -> None:
    # swap register: q0 <-> q1 every cycle; sequential (non-simultaneous)
    # update would collapse both to the same value
    nl = build(
        outputs=["q0", "q1"],
        dffs=[
            {"d": "q1", "q": "q0", "init": 0},
            {"d": "q0", "q": "q1", "init": 1},
        ],
        cycles=4,
    )
    out = simulate(nl)
    assert out["q0"] == [0, 1, 0, 1]
    assert out["q1"] == [1, 0, 1, 0]


# --- negatives: malformed circuits must be rejected, not silently accepted ---


def test_rejects_double_driven_net() -> None:
    with pytest.raises(NetlistError, match="driven twice"):
        build(
            inputs=["a"],
            outputs=["a"],
            gates=[{"type": "NAND", "a": "a", "b": "a", "y": "a"}],
            trace={"a": [0]},
        )


def test_rejects_combinational_loop() -> None:
    with pytest.raises(NetlistError, match="combinational cycle"):
        build(
            inputs=["a"],
            outputs=["y0"],
            gates=[
                {"type": "NAND", "a": "y1", "b": "a", "y": "y0"},
                {"type": "NAND", "a": "y0", "b": "a", "y": "y1"},
            ],
            trace={"a": [0]},
        )


def test_rejects_undriven_reference() -> None:
    with pytest.raises(NetlistError, match="never driven"):
        build(outputs=["ghost"])


def test_rejects_wrong_trace_length() -> None:
    with pytest.raises(NetlistError, match="expected 3"):
        build(inputs=["a"], outputs=["a"], trace={"a": [0, 1]}, cycles=3)


def test_rejects_unknown_gate_type() -> None:
    with pytest.raises(NetlistError, match="unsupported gate type"):
        build(
            inputs=["a"],
            outputs=["y"],
            gates=[{"type": "AND", "a": "a", "b": "a", "y": "y"}],
            trace={"a": [0]},
        )


def test_rejects_clk_as_net_name() -> None:
    with pytest.raises(NetlistError, match="bad net name"):
        build(inputs=["clk"], outputs=["clk"], trace={"clk": [0]})


def test_rejects_non_binary_trace_value() -> None:
    with pytest.raises(NetlistError, match="bad bit value"):
        build(inputs=["a"], outputs=["a"], trace={"a": [2]})
