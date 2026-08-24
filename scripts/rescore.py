"""re-derive every published score and prompt from raw materials.

for each stored record in results/records/: parse the model's response text,
simulate the circuit fresh, score the parse against the simulation, and compare
to the stored score. also rebuild the prompt from SEMANTICS.md + the circuit
json and compare byte-for-byte to the stored prompt. any mismatch = nonzero
exit. no api key, no network.

usage: uv run python scripts/rescore.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lockstep.evalrun import build_prompt, extract_answer, score
from lockstep.netlist import load
from lockstep.sim import simulate

CIRCUIT_DIRS = ["circuits", "circuits/tier2", "circuits/tier3", "circuits/tier4",
                "circuits/x", "circuits/rand"]


def circuit_path(name: str) -> Path | None:
    for d in CIRCUIT_DIRS:
        p = ROOT / d / f"{name}.json"
        if p.exists():
            return p
    return None


def main() -> int:
    total = rescored = score_bad = prompt_bad = missing = no_prompt = 0
    goldens: dict[str, tuple] = {}
    for p in sorted((ROOT / "results" / "records").glob("*/*.json")):
        r = json.loads(p.read_text())
        total += 1
        cp = circuit_path(r["circuit"])
        if cp is None:
            missing += 1
            print(f"MISSING CIRCUIT: {p}")
            continue
        if r["circuit"] not in goldens:
            nl = load(cp)
            goldens[r["circuit"]] = (nl, simulate(nl))
        nl, golden = goldens[r["circuit"]]
        # key check: committed answer key must equal the fresh simulation
        key = json.loads((ROOT / "keys" / f"{r['circuit']}.json").read_text())
        if key != golden:
            score_bad += 1
            print(f"KEY MISMATCH: {r['circuit']}")
        # prompt check: stored prompt must be regenerable byte-for-byte
        if not r.get("prompt"):
            no_prompt += 1  # the early era predates prompt storage (see METHODS)
        elif r["prompt"] != build_prompt(nl):
            prompt_bad += 1
            print(f"PROMPT MISMATCH: {p}")
        # score check: refusals/api errors have no answer to rescore
        if r["score"]["status"] in ("refused", "api_error"):
            continue
        answer = extract_answer(r.get("response") or "")
        if answer is None and r.get("finish") == "length":
            # same overlay as the harness: no answer + token wall = truncated
            fresh = {"status": "truncated", "prefix_cycles": 0,
                     "pointwise": 0.0, "exact": False}
        else:
            fresh = score(golden, answer, r["cycles"])
        rescored += 1
        if fresh != r["score"]:
            score_bad += 1
            print(f"SCORE MISMATCH: {p}\n  stored {r['score']}\n  fresh  {fresh}")
    print(f"{total} records, {rescored} rescored, {score_bad} score mismatches, "
          f"{prompt_bad} prompt mismatches ({no_prompt} records store no prompt), "
          f"{missing} missing circuits")
    return 1 if (score_bad or prompt_bad or missing) else 0


if __name__ == "__main__":
    sys.exit(main())
