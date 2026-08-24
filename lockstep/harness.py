"""Run every circuit through every discovered evaluator and demand
bit-for-bit agreement. nine evaluators in this repo:

  1. the python simulator (sim.py), reading the json netlist directly
  2-3. two independently written simulators (oracles/*/sim_*.py — codex, agy),
       each produced from SEMANTICS.md alone without seeing our code
  4-9. three json->verilog translators (verilog.py + oracles/*/translate_*.py),
       each run through both icarus verilog (iverilog/vvp) and verilator

oracles and translators are discovered by filename glob and ALWAYS co-run —
they are not optional. --oracle name=path adds extras. the harness dies on
the first divergence.

usage:
  uv run python -m lockstep.harness circuits/*.json --random 25
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from . import gen, sim, verilog
from .netlist import Netlist, load, to_dict

Trace = dict[str, list[int]]

ORACLES_DIR = Path(__file__).resolve().parent.parent / "oracles"


def discover_oracles() -> dict[str, Path]:
    """All independently written simulators under oracles/*/sim_*.py."""
    return {
        script.parent.name: script for script in sorted(ORACLES_DIR.glob("*/sim_*.py"))
    }


def discover_translators() -> dict[str, Path]:
    """All independently written json->verilog translators under
    oracles/*/translate_*.py. Each runs against both icarus and verilator."""
    return {
        script.parent.name: script for script in sorted(ORACLES_DIR.glob("*/translate_*.py"))
    }


@dataclass
class Result:
    name: str
    n_gates: int
    n_dffs: int
    cycles: int
    traces: dict[str, Trace]  # evaluator name -> trace
    divergences: list[str]

    @property
    def ok(self) -> bool:
        return not self.divergences


def _run(cmd: list[str], cwd: Path) -> str:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=120, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"command failed ({proc.returncode}): {' '.join(cmd)}\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return proc.stdout


def _icarus_trace(nl: Netlist, build: Path, vfiles: list[str]) -> Trace:
    _run(["iverilog", "-g2012", "-o", "tb.vvp", *vfiles], build)
    return verilog.parse_trace(_run(["vvp", "tb.vvp"], build), nl)


def _verilator_trace(nl: Netlist, build: Path, vfiles: list[str]) -> Trace:
    _run(
        # no --quiet: older verilator 5.x (e.g. ubuntu apt) rejects it
        ["verilator", "--binary", "--timing", "-Wno-fatal",
         "--Mdir", "vl", "--top-module", "tb", "-o", "sim_vl", *vfiles],
        build,
    )
    return verilog.parse_trace(_run(["./vl/sim_vl"], build), nl)


def run_icarus(nl: Netlist, build: Path) -> Trace:
    return _icarus_trace(nl, build, ["tb.v", "top.v"])


def run_verilator(nl: Netlist, build: Path) -> Trace:
    return _verilator_trace(nl, build, ["tb.v", "top.v"])


def run_translated(nl: Netlist, name: str, script: Path, parent: Path) -> dict[str, Trace]:
    """Run an independently written translator, then both verilog simulators
    on whatever .v files it emitted."""
    build = parent / name
    build.mkdir(parents=True, exist_ok=True)
    circuit_json = (build / "circuit.json").resolve()
    circuit_json.write_text(json.dumps(to_dict(nl)))
    _run([sys.executable, str(script), str(circuit_json), str(build.resolve())], build)
    vfiles = sorted(p.name for p in build.glob("*.v"))
    if not vfiles:
        raise RuntimeError(f"{name}: translator produced no .v files")
    return {
        f"{name}-icarus": _icarus_trace(nl, build, vfiles),
        f"{name}-verilator": _verilator_trace(nl, build, vfiles),
    }


def run_external(nl: Netlist, script: Path, build: Path) -> Trace:
    """Run an independently written simulator: python3 <script> <circuit.json>,
    expecting one json object {output: [bits]} on stdout. Output is validated
    strictly — a malformed oracle is an error, not a silent skip."""
    circuit_json = (build / "circuit.json").resolve()
    circuit_json.write_text(json.dumps(to_dict(nl)))
    stdout = _run([sys.executable, str(script), str(circuit_json)], build)
    data = json.loads(stdout)
    if not isinstance(data, dict) or set(data) != set(nl.outputs):
        raise RuntimeError(f"{script.name}: output keys {sorted(data)} != {sorted(nl.outputs)}")
    trace: Trace = {}
    for out, vals in data.items():
        if (
            not isinstance(vals, list)
            or len(vals) != nl.cycles
            or any(v not in (0, 1) for v in vals)
        ):
            raise RuntimeError(f"{script.name}: bad trace for {out!r}: {vals!r}")
        trace[out] = [int(v) for v in vals]
    return trace


def compare(traces: dict[str, Trace], nl: Netlist) -> list[str]:
    """All divergences between evaluators, as human-readable strings."""
    names = sorted(traces)
    base = names[0]
    problems: list[str] = []
    for other in names[1:]:
        for out in nl.outputs:
            a, b = traces[base][out], traces[other][out]
            for t, (x, y) in enumerate(zip(a, b, strict=True)):
                if x != y:
                    problems.append(f"{base} vs {other}: output {out!r} cycle {t}: {x} != {y}")
    return problems


def run_circuit(
    nl: Netlist,
    build_root: Path,
    oracles: dict[str, Path] | None = None,
    translators: dict[str, Path] | None = None,
) -> Result:
    build = build_root / nl.name
    build.mkdir(parents=True, exist_ok=True)
    (build / "top.v").write_text(verilog.module(nl))
    (build / "tb.v").write_text(verilog.testbench(nl))
    traces = {
        "python": sim.simulate(nl),
        "icarus": run_icarus(nl, build),
        "verilator": run_verilator(nl, build),
    }
    for oracle_name, script in (oracles or {}).items():
        traces[oracle_name] = run_external(nl, script, build)
    for trans_name, script in (translators or {}).items():
        traces.update(run_translated(nl, trans_name, script, build))
    return Result(
        name=nl.name,
        n_gates=len(nl.gates),
        n_dffs=len(nl.dffs),
        cycles=nl.cycles,
        traces=traces,
        divergences=compare(traces, nl),
    )


def fuzz_netlist(seed: int) -> Netlist:
    """Wide-parameter fuzzing across all generator families: inputs 0-6,
    outputs 1-6 (family-dependent), gates 4-150, dffs 0-20, cycles 1-48."""
    prng = random.Random(seed ^ 0xF00D)
    fam = seed % 4
    if fam == 0:
        n_in, n_dff = prng.randint(0, 6), prng.randint(0, 16)
        if n_in == 0 and n_dff == 0:
            n_in = 1
        return gen.random_netlist(
            seed, n_inputs=n_in, n_gates=prng.randint(4, 120),
            n_dffs=n_dff, cycles=prng.randint(1, 40),
        )
    if fam == 1:
        return gen.chain_netlist(
            seed, n_gates=prng.randint(10, 150), n_dffs=prng.randint(1, 16),
            cycles=prng.randint(2, 40), n_inputs=prng.randint(1, 4),
        )
    if fam == 2:
        return gen.mix_netlist(
            seed, n_dffs=prng.randint(2, 20), gates_per_dff=prng.randint(2, 8),
            cycles=prng.randint(2, 48), n_inputs=prng.randint(1, 4),
        )
    return gen.rule30_netlist(k=prng.randint(3, 24), cycles=prng.randint(2, 40), seed=seed)


def fuzz_netlist_v2(seed: int) -> Netlist:
    """v2 fuzzing: all six generator families — the four from fuzz_netlist
    plus perm (pure dffs, zero gates) and ca (random-rule cellular automata).
    fuzz_netlist (v1) stays frozen so the original 1000-circuit campaign
    remains replayable from its seeds."""
    prng = random.Random(seed ^ 0xBEEF)
    fam = seed % 6
    if fam == 0:
        n_in, n_dff = prng.randint(0, 6), prng.randint(0, 16)
        if n_in == 0 and n_dff == 0:
            n_in = 1
        return gen.random_netlist(
            seed, n_inputs=n_in, n_gates=prng.randint(4, 120),
            n_dffs=n_dff, cycles=prng.randint(1, 40),
        )
    if fam == 1:
        return gen.chain_netlist(
            seed, n_gates=prng.randint(10, 150), n_dffs=prng.randint(1, 16),
            cycles=prng.randint(2, 40), n_inputs=prng.randint(1, 4),
        )
    if fam == 2:
        return gen.mix_netlist(
            seed, n_dffs=prng.randint(2, 20), gates_per_dff=prng.randint(2, 8),
            cycles=prng.randint(2, 48), n_inputs=prng.randint(1, 4),
        )
    if fam == 3:
        return gen.rule30_netlist(k=prng.randint(3, 24), cycles=prng.randint(2, 40), seed=seed)
    if fam == 4:
        n_dff = prng.randint(2, 32)
        # perm injects one dff per input, so n_inputs can't exceed n_dffs
        return gen.perm_netlist(
            seed, n_dffs=n_dff, cycles=prng.randint(2, 48),
            n_inputs=prng.randint(1, min(4, n_dff)),
        )
    return gen.ca_netlist(seed, k=prng.randint(3, 20), cycles=prng.randint(2, 40))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("circuits", nargs="*", help="circuit json files")
    ap.add_argument("--random", type=int, default=0, help="also run N seeded random circuits")
    ap.add_argument("--fuzz", type=int, default=0, help="also run N wide-parameter fuzz circuits")
    ap.add_argument("--fuzz-v2", type=int, default=0,
                    help="also run N v2 fuzz circuits (all six families)")
    ap.add_argument("--seed", type=int, default=1, help="base seed for --random/--fuzz")
    ap.add_argument("--verdict-log", default=None, metavar="PATH",
                    help="append one json line per circuit: name, params, verdict, "
                    "and the full agreed trace (the values, not just the word)")
    ap.add_argument("--build", default="build", help="scratch dir for verilog builds")
    ap.add_argument("--show-traces", action="store_true", help="print full traces")
    ap.add_argument(
        "--oracle",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help="extra evaluator on top of the always-on ones from oracles/*/sim_*.py",
    )
    args = ap.parse_args(argv)

    oracles = discover_oracles()
    for spec in args.oracle:
        oracle_name, _, path = spec.partition("=")
        if not path or not Path(path).is_file():
            ap.error(f"bad --oracle {spec!r} (want NAME=PATH to an existing file)")
        oracles[oracle_name] = Path(path).resolve()

    netlists = [load(p) for p in args.circuits]
    for i in range(args.random):
        seed = args.seed + i
        netlists.append(
            gen.random_netlist(
                seed,
                n_inputs=2 + seed % 3,
                n_gates=4 + (seed * 7) % 20,
                n_dffs=seed % 4,
                cycles=8 + seed % 9,
            )
        )
    for i in range(args.fuzz):
        netlists.append(fuzz_netlist(args.seed + i))
    for i in range(args.fuzz_v2):
        netlists.append(fuzz_netlist_v2(args.seed + i))
    if not netlists:
        ap.error("no circuits given (pass json files and/or --random/--fuzz N)")

    translators = discover_translators()
    evaluators = ["python", "icarus", "verilator", *oracles]
    for t in translators:
        evaluators += [f"{t}-icarus", f"{t}-verilator"]
    print(f"evaluators ({len(evaluators)}): {', '.join(evaluators)}")
    build_root = Path(args.build)
    failures = 0
    for nl in netlists:
        res = run_circuit(nl, build_root, oracles, translators)
        verdict = "AGREE" if res.ok else "DIVERGE"
        print(
            f"{res.name:32s} gates={res.n_gates:3d} dffs={res.n_dffs:2d} "
            f"cycles={res.cycles:3d}  {verdict}"
        )
        if args.verdict_log:
            import hashlib
            golden = res.traces["python"]
            row = {
                "name": res.name, "gates": res.n_gates, "dffs": res.n_dffs,
                "cycles": res.cycles, "n_evaluators": len(evaluators),
                "verdict": verdict, "golden": golden,
                "golden_sha256_16": hashlib.sha256(
                    json.dumps(golden, sort_keys=True).encode()).hexdigest()[:16],
            }
            with open(args.verdict_log, "a") as vf:
                vf.write(json.dumps(row) + "\n")
        if args.show_traces or not res.ok:
            for evaluator, trace in sorted(res.traces.items()):
                for out in nl.outputs:
                    bits = "".join(str(b) for b in trace[out])
                    print(f"    {evaluator:12s} {out}: {bits}")
        if not res.ok:
            for d in res.divergences:
                print(f"    !! {d}")
            print(f"\nSTOP: divergence on {nl.name} — aborting immediately, "
                  "golden reference cannot be trusted until this is explained")
            return 1
        failures += 0  # kept for readability; a divergence never reaches here
    n = len(netlists)
    print(f"\nall {len(evaluators)} evaluators agree on all {n} circuits")
    return 0


if __name__ == "__main__":
    sys.exit(main())
