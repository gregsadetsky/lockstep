"""Prompt llms to simulate circuits in their head; score against the golden
reference (which all nine evaluators agreed on, see harness.py).

Idempotent: one json result file per (model, circuit, sample) under --out;
existing files are skipped, so reruns only fill gaps. Scoring can always be
redone from the stored raw responses.

usage:
  uv run python -m lockstep.evalrun --dryrun
  uv run python -m lockstep.evalrun --models anthropic/claude-haiku-4.5 --limit 2
  uv run python -m lockstep.evalrun            # full default sweep
  uv run python -m lockstep.evalrun --report   # just re-summarize --out
"""

from __future__ import annotations

import argparse
import glob as globmod
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from . import gen, llm, sim
from .harness import discover_oracles, discover_translators, run_circuit
from .netlist import Netlist, load, stats, to_dict

ROOT = Path(__file__).resolve().parent.parent
SEMANTICS = ROOT / "SEMANTICS.md"
CIRCUITS_DIR = ROOT / "circuits"

DEFAULT_MODELS = [
    "anthropic/claude-sonnet-5",
    # NOT claude-fable-5: anthropic's api-level safety filter false-positives
    # on this prompt ("violative cyber content") and blocks every call
    "anthropic/claude-opus-5",
    "anthropic/claude-haiku-4.5",
    "openai/gpt-5.5",
    "openai/gpt-5.6-sol",
    "openai/gpt-5-mini",
    "google/gemini-3.7-flash",
    "google/gemini-3.1-pro-preview",
    "moonshotai/kimi-k3",
    "deepseek/deepseek-v4-pro",
]


def build_prompt(nl: Netlist) -> str:
    spec = SEMANTICS.read_text()
    circuit = json.dumps(to_dict(nl), indent=1)
    return f"""You are given the complete semantics of a tiny circuit netlist language, \
followed by one circuit in that language. Simulate the circuit and report its output trace.

<semantics>
{spec}
</semantics>

<circuit>
{circuit}
</circuit>

Work through the simulation carefully, cycle by cycle. You cannot run code; \
do it by reasoning.

End your reply with a single fenced json code block containing exactly one object \
that maps each output net name to its list of recorded values, for example:

```json
{{"some_output": [0, 1, 1, 0], "other_output": [1, 1, 0, 0]}}
```

Each list must contain exactly {nl.cycles} integers (each 0 or 1), one per cycle, \
cycle 0 first. Put no other json code block after it."""


def extract_answer(text: str) -> dict[str, Any] | None:
    """Last parseable json object in the reply: fenced blocks first, then the
    whole reply, then the last brace-delimited span."""
    candidates: list[str] = []
    parts = text.split("```")
    for i in range(1, len(parts), 2):
        block = parts[i]
        first_newline = block.find("\n")
        if first_newline != -1 and block[:first_newline].strip().lower() in ("json", ""):
            block = block[first_newline + 1 :]
        candidates.append(block)
    candidates.reverse()  # last block wins
    candidates.append(text)
    first, last_open, last_close = text.find("{"), text.rfind("{"), text.rfind("}")
    if first != -1 and last_close > first:
        candidates.append(text[last_open : last_close + 1])
        candidates.append(text[first : last_close + 1])
    for cand in candidates:
        try:
            obj = json.loads(cand.strip())
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict):
            return obj
    return None


def score(golden: dict[str, list[int]], answer: dict[str, Any] | None, cycles: int) -> dict[str, Any]:
    """prefix_cycles = leading cycles where every output is correct (the
    time-to-divergence metric). pointwise = fraction of all cells correct."""
    if answer is None:
        return {"status": "parse_error", "prefix_cycles": 0, "pointwise": 0.0, "exact": False}
    for out, bits in golden.items():
        got = answer.get(out)
        if not isinstance(got, list) or len(got) != len(bits) or any(b not in (0, 1) for b in got):
            return {"status": "format_error", "prefix_cycles": 0, "pointwise": 0.0, "exact": False}
    prefix = cycles
    correct_cells = 0
    total_cells = 0
    for t in range(cycles):
        cycle_ok = True
        for out, bits in golden.items():
            total_cells += 1
            if answer[out][t] == bits[t]:
                correct_cells += 1
            else:
                cycle_ok = False
        if not cycle_ok and prefix == cycles:
            prefix = t
    return {
        "status": "ok",
        "prefix_cycles": prefix,
        "pointwise": correct_cells / total_cells if total_cells else 0.0,
        "exact": prefix == cycles,
    }


def result_path(out_dir: Path, model: str, name: str, sample: int) -> Path:
    return out_dir / model.replace("/", "__") / f"{name}__s{sample}.json"


def run_one(
    nl: Netlist, model: str, sample: int, out_dir: Path, max_tokens: int | None
) -> dict[str, Any]:
    path = result_path(out_dir, model, nl.name, sample)
    if path.exists():
        cached: dict[str, Any] = json.loads(path.read_text())
        return cached
    golden = sim.simulate(nl)
    prompt = build_prompt(nl)
    record: dict[str, Any] = {
        "model": model,
        "circuit": nl.name,
        "sample": sample,
        "gates": len(nl.gates),
        "dffs": len(nl.dffs),
        "cycles": nl.cycles,
        **stats(nl),
    }
    try:
        t0 = time.monotonic()
        # audit fields: when the call was made and the exact cap sent
        record["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        record["max_tokens_sent"] = (
            max_tokens if max_tokens is not None else llm.model_max_tokens(model)
        )
        reply = llm.chat(model, prompt, max_tokens=max_tokens)
        record["elapsed_s"] = round(time.monotonic() - t0, 1)
        record["finish"] = reply.finish
        record["generation_id"] = reply.gen_id
        # exact prompt stored verbatim: the published data release is
        # self-contained (also reproducible from SEMANTICS.md + circuit json)
        record["prompt"] = prompt
        record["response"] = reply.content
        record["reasoning"] = reply.reasoning
        record["usage"] = reply.usage
        if reply.refusal or reply.finish == "content_filter":
            # provider-side block, not a simulation failure — count separately
            record["refusal"] = reply.refusal
            record["score"] = {
                "status": "refused",
                "prefix_cycles": 0,
                "pointwise": 0.0,
                "exact": False,
            }
        else:
            answer = extract_answer(reply.content)
            if answer is None and reply.finish == "length":
                # ran out of tokens mid-thought — a budget failure, not a
                # simulation failure; keep it distinct from divergence
                record["score"] = {
                    "status": "truncated",
                    "prefix_cycles": 0,
                    "pointwise": 0.0,
                    "exact": False,
                }
            else:
                record["score"] = score(golden, answer, nl.cycles)
    except Exception as err:  # noqa: BLE001 - one bad call must not kill the sweep
        record["error"] = str(err)
        record["score"] = {
            "status": "api_error",
            "prefix_cycles": 0,
            "pointwise": 0.0,
            "exact": False,
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=1))
    return record


def summarize(out_dir: Path) -> str:
    records = [json.loads(p.read_text()) for p in sorted(out_dir.glob("*/*.json"))]
    if not records:
        return "no results yet"
    lines = []
    models = sorted({r["model"] for r in records})
    circuits = sorted({r["circuit"] for r in records})
    width = max(len(m) for m in models) + 2
    lines.append(f"{'model':{width}s} n    exact  no-answer      mean-prefix  mean-pointwise")
    for m in models:
        rs = [r for r in records if r["model"] == m]
        exact = sum(1 for r in rs if r["score"]["exact"])
        bad = sum(
            1
            for r in rs
            if r["score"]["status"] in ("parse_error", "api_error", "refused", "truncated")
        )
        prefix = sum(r["score"]["prefix_cycles"] / r["cycles"] for r in rs) / len(rs)
        point = sum(r["score"]["pointwise"] for r in rs) / len(rs)
        lines.append(
            f"{m:{width}s} {len(rs):<4d} {exact}/{len(rs):<6} {bad:<14d} {prefix:<12.2f} {point:.2f}"
        )
    lines.append("")
    cw = max(len(c) for c in circuits) + 2
    lines.append(f"{'circuit':{cw}s} " + "  ".join(f"m{i}" for i in range(len(models))))
    for c in circuits:
        cells = []
        for m in models:
            rs = [r for r in records if r["model"] == m and r["circuit"] == c]
            if not rs:
                cells.append(" .")
            elif all(r["score"]["exact"] for r in rs):
                cells.append(" +")
            elif any(r["score"]["exact"] for r in rs):
                cells.append(" ~")
            else:
                cells.append(" x")
        lines.append(f"{c:{cw}s} " + "  ".join(cells))
    lines.append("")
    lines.append("legend: + all samples exact, ~ some exact, x none exact, . missing")
    for i, m in enumerate(models):
        lines.append(f"  m{i} = {m}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=",".join(DEFAULT_MODELS), help="comma-separated slugs")
    ap.add_argument("--samples", type=int, default=1)
    ap.add_argument("--random", type=int, default=0, help="add N seeded random circuits")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--random-gates", type=int, default=12)
    ap.add_argument("--random-dffs", type=int, default=3)
    ap.add_argument("--random-cycles", type=int, default=12)
    ap.add_argument("--random-inputs", type=int, default=3)
    ap.add_argument(
        "--skip-handwritten", action="store_true", help="only run the --random circuits"
    )
    ap.add_argument(
        "--circuits",
        default=str(CIRCUITS_DIR / "*.json"),
        help="glob of circuit json files (default: the handwritten starter set)",
    )
    ap.add_argument("--limit", type=int, default=0, help="only first N circuits")
    ap.add_argument("--out", required=True, help="output dir for new records")
    ap.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="token cap; default None = the model's provider MAXIMUM",
    )
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--dryrun", action="store_true", help="print first prompt and task count")
    ap.add_argument("--report", action="store_true", help="only summarize existing results")
    args = ap.parse_args(argv)

    out_dir = Path(args.out)
    if args.report:
        print(summarize(out_dir))
        return 0

    load_dotenv(ROOT / ".env")
    netlists = (
        [] if args.skip_handwritten else [load(p) for p in sorted(globmod.glob(args.circuits))]
    )
    for i in range(args.random):
        netlists.append(
            gen.random_netlist(
                args.seed + i,
                n_inputs=args.random_inputs,
                n_gates=args.random_gates,
                n_dffs=args.random_dffs,
                cycles=args.random_cycles,
            )
        )
    if args.limit:
        netlists = netlists[: args.limit]

    # the golden gate: no circuit is shown to an llm unless every
    # evaluator agrees on it. agreement is cached per circuit in build/.
    oracles = discover_oracles()
    translators = discover_translators()
    n_evals = 3 + len(oracles) + 2 * len(translators)
    build = Path("build")
    for nl in netlists:
        # marker is evaluator-count-specific: adding an evaluator re-gates
        # every circuit instead of silently trusting an older, weaker check
        marker = build / nl.name / f"AGREED-{n_evals}"
        golden_path = build / nl.name / "golden.json"
        if not marker.exists():
            res = run_circuit(nl, build, oracles, translators)
            if not res.ok:
                print(f"ABORT: evaluators diverge on {nl.name}:")
                for d in res.divergences:
                    print(f"  {d}")
                return 1
            marker.write_text("all evaluators agreed\n")
            print(f"golden gate: {nl.name} agreed across {n_evals} evaluators")
        if not golden_path.exists():
            # the agreed trace as a durable, inspectable artifact (identical
            # across all evaluators by the gate above)
            golden_path.write_text(json.dumps(sim.simulate(nl), indent=1) + "\n")

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    tasks = [(nl, m, s) for nl in netlists for m in models for s in range(args.samples)]

    if args.dryrun:
        print(build_prompt(netlists[0]))
        print(f"\n--- {len(tasks)} calls: {len(netlists)} circuits x {len(models)} models "
              f"x {args.samples} samples -> {out_dir}")
        return 0

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(run_one, nl, m, s, out_dir, args.max_tokens): (nl.name, m, s)
            for nl, m, s in tasks
        }
        for fut in as_completed(futures):
            name, m, s = futures[fut]
            rec = fut.result()
            done += 1
            sc = rec["score"]
            print(
                f"[{done}/{len(tasks)}] {m} {name} s{s}: {sc['status']} "
                f"prefix={sc['prefix_cycles']}/{rec['cycles']}"
            )
    print()
    print(summarize(out_dir))
    (out_dir / "summary.txt").write_text(summarize(out_dir) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
