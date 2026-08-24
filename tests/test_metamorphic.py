"""Meta-tests of the agreement machinery itself, via mutation testing.

'All evaluators agree on every circuit' is only evidence if the pipeline
would catch disagreement. Here we manufacture disagreement on purpose:
single-point mutations of real circuits (rewire one gate input, flip one
dff init) and check that (a) most mutations visibly change behavior,
(b) every behavior-changing mutant is flagged when evaluators run
different circuits, and (c) known-neutral mutations (nand input swap —
commutative) change nothing, so the battery isn't just detecting noise."""

import random
import shutil
from pathlib import Path
from typing import Any

import pytest

from lockstep import gen, verilog
from lockstep.harness import compare, run_icarus
from lockstep.netlist import Netlist, NetlistError, from_dict, to_dict
from lockstep.sim import simulate

needs_icarus = pytest.mark.skipif(not shutil.which("iverilog"), reason="iverilog not installed")


def _mutants(nl: Netlist, rng: random.Random, n: int) -> list[tuple[Netlist, str]]:
    """Up to n random single-point mutations. Mutations that produce an
    invalid circuit (e.g. a combinational loop) are skipped — the validator
    rejecting them is itself part of the pipeline under test."""
    out: list[tuple[Netlist, str]] = []
    for _ in range(n):
        d: dict[str, Any] = to_dict(nl)
        gates: list[dict[str, Any]] = d["gates"]
        dffs: list[dict[str, Any]] = d["dffs"]
        if dffs and rng.random() < 0.3:
            f = rng.choice(dffs)
            f["init"] ^= 1
            desc = f"flip init of {f['q']}"
        else:
            g = rng.choice(gates)
            nets = [x["y"] for x in gates] + list(d["inputs"]) + [x["q"] for x in dffs]
            g["a"] = rng.choice(nets)
            desc = f"rewire {g['y']}.a -> {g['a']}"
        try:
            out.append((from_dict(d), desc))
        except NetlistError:
            continue
    return out


BASE = gen.random_netlist(52, n_inputs=3, n_gates=20, n_dffs=4, cycles=12)


def test_most_single_point_mutations_are_visible() -> None:
    # sensitivity: golden traces must actually depend on circuit structure
    rng = random.Random(5)
    muts = _mutants(BASE, rng, 24)
    assert len(muts) >= 12
    base_trace = simulate(BASE)
    changed = sum(1 for m, _ in muts if simulate(m) != base_trace)
    assert changed >= len(muts) * 0.6, f"only {changed}/{len(muts)} mutations visible"


def test_nand_input_swap_changes_nothing() -> None:
    # negative control: a semantically null rewrite must NOT trip anything
    d: dict[str, Any] = to_dict(BASE)
    for g in d["gates"]:
        g["a"], g["b"] = g["b"], g["a"]
    assert simulate(from_dict(d)) == simulate(BASE)


@needs_icarus
def test_cross_evaluator_catches_every_visible_mutant(tmp_path: Path) -> None:
    # the actual meta-test: evaluator A (python) runs the original, evaluator
    # B (icarus, via the verilog path) runs the mutant. every mutant that
    # changes behavior must produce a reported divergence — none may slip
    # through the comparator.
    rng = random.Random(7)
    base_trace = simulate(BASE)
    checked = 0
    for i, (mut, desc) in enumerate(_mutants(BASE, rng, 40)):
        if simulate(mut) == base_trace:
            continue  # semantically null under python; nothing to detect
        build = tmp_path / f"m{i}"
        build.mkdir()
        (build / "top.v").write_text(verilog.module(mut))
        (build / "tb.v").write_text(verilog.testbench(mut))
        icarus_trace = run_icarus(mut, build)
        problems = compare({"python": base_trace, "icarus": icarus_trace}, BASE)
        assert problems, f"UNDETECTED mutant ({desc}) — comparator or verilog path is blind"
        checked += 1
    assert checked >= 10, f"battery too weak: only {checked} visible mutants exercised"
