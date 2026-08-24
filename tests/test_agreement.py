"""Cross-simulator agreement, and — just as important — proof that the
pipeline detects disagreement when it exists. A comparator that never fires
would make every AGREE meaningless."""

import copy
import shutil
from pathlib import Path

import pytest

from lockstep import gen, verilog
from lockstep.harness import compare, discover_oracles, discover_translators, run_circuit
from lockstep.netlist import load

HAVE_SIMS = shutil.which("iverilog") and shutil.which("verilator")
needs_sims = pytest.mark.skipif(not HAVE_SIMS, reason="iverilog/verilator not installed")

CIRCUITS_DIR = Path(__file__).resolve().parent.parent / "circuits"
ORACLES = discover_oracles()


def test_expected_oracles_present() -> None:
    # the independently written simulators and translators must exist and
    # co-run on every circuit; if one vanishes, agreement silently weakens
    assert {"codex", "agy"} <= set(ORACLES), sorted(ORACLES)
    assert {"codex-translator", "agy-translator"} <= set(discover_translators())


@needs_sims
@pytest.mark.parametrize("path", sorted(CIRCUITS_DIR.glob("*.json")), ids=lambda p: p.stem)
def test_handwritten_circuits_agree(path: Path, tmp_path: Path) -> None:
    res = run_circuit(load(path), tmp_path, ORACLES)
    assert res.ok, res.divergences


@needs_sims
@pytest.mark.parametrize("seed", range(101, 106))
def test_random_circuits_agree(seed: int, tmp_path: Path) -> None:
    nl = gen.random_netlist(seed, n_inputs=3, n_gates=12, n_dffs=3, cycles=10)
    res = run_circuit(nl, tmp_path, ORACLES)
    assert res.ok, res.divergences


def test_comparator_detects_single_flipped_bit() -> None:
    nl = load(CIRCUITS_DIR / "tff_divider.json")
    from lockstep.sim import simulate

    good = simulate(nl)
    bad = copy.deepcopy(good)
    bad["q0"][3] ^= 1
    problems = compare({"python": good, "tampered": bad}, nl)
    assert len(problems) == 1
    assert "cycle 3" in problems[0]
    # and the untampered pair reports nothing
    assert compare({"python": good, "same": copy.deepcopy(good)}, nl) == []


@needs_sims
def test_pipeline_catches_wrong_translation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # sabotage the verilog translator: emit AND where the netlist says NAND.
    # if the harness still reports agreement, the whole methodology is broken.
    real_module = verilog.module

    def sabotaged(nl):  # type: ignore[no-untyped-def]
        return real_module(nl).replace("  nand g", "  and g")

    monkeypatch.setattr(verilog, "module", sabotaged)
    res = run_circuit(load(CIRCUITS_DIR / "xor_from_nand.json"), tmp_path)
    assert not res.ok, "sabotaged translation was not detected — comparator is broken"
