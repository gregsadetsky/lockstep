"""Export per-circuit data for the site's /c/ pages: every circuit json +
each model's single one-shot attempt (plot.canonical_cells — first attempt
at model max) with its parsed answer bits so the page can
replay the attempt against the golden trace. Extra attempts stay in the
local archive and are not shipped.

usage: uv run python analysis/export_site.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analysis"))

from plot import ALL_MODELS, canonical_cells

from lockstep.evalrun import extract_answer
from lockstep.netlist import load
from lockstep.sim import simulate

# mono-repo: the site lives next to the benchmark
SITE = ROOT / "site" / "public"
CIRCUIT_DIRS = ["circuits", "circuits/tier2", "circuits/tier3", "circuits/tier4",
                "circuits/x", "circuits/rand"]


def canonical_records() -> list[dict]:
    # one record per (model, circuit): the one-shot attempt the matrix scores
    return list(canonical_cells().values())


def main() -> int:
    records = canonical_records()
    names = sorted({r["circuit"] for r in records})

    # clean output dirs first: a reclassified cell must not leave a stale
    # transcript or result behind (they'd contradict the matrix)
    import shutil
    for sub in ("circuits", "results", "records"):
        shutil.rmtree(SITE / sub, ignore_errors=True)

    # 1. all circuits + goldens
    (SITE / "circuits").mkdir(exist_ok=True)
    (SITE / "results").mkdir(exist_ok=True)
    shipped = []
    for name in names:
        src = next((ROOT / d / f"{name}.json" for d in CIRCUIT_DIRS
                    if (ROOT / d / f"{name}.json").exists()), None)
        if src is None:
            print(f"MISSING circuit file: {name}")
            continue
        (SITE / "circuits" / f"{name}.json").write_text(src.read_text())
        shipped.append(name)

        nl = load(src)
        golden = simulate(nl)
        attempts = []
        (SITE / "records").mkdir(exist_ok=True)
        for r in sorted((r for r in records if r["circuit"] == name),
                        key=lambda r: (r["model"], r.get("sample", 0))):
            ans = extract_answer(r.get("response") or "")
            ok_shape = (
                isinstance(ans, dict)
                and all(isinstance(ans.get(o), list) and len(ans[o]) == nl.cycles
                        and all(b in (0, 1) for b in ans[o]) for o in nl.outputs)
            )
            if True:
                label = ALL_MODELS[r["model"]]
                fn = f"{label}__{name}__s{r.get('sample', 0)}.txt"
                (SITE / "records" / fn).write_text(
                    f"model: {r['model']}\ncircuit: {name}\nscore: {r['score']}\n\n"
                    f"=== reasoning ===\n{r.get('reasoning') or '(not returned by provider)'}\n\n"
                    f"=== response ===\n{r.get('response') or ''}"
                )
                transcript = f"/records/{fn}"
            attempts.append({
                "model": ALL_MODELS[r["model"]],
                "sample": r.get("sample", 0),
                "status": r["score"]["status"],
                "prefix": r["score"]["prefix_cycles"],
                "cycles": r["cycles"],
                "answer": {o: ans[o] for o in nl.outputs} if ok_shape and ans else None,
                "transcript": transcript,
            })
        (SITE / "results" / f"{name}.json").write_text(json.dumps({
            "golden": golden, "attempts": attempts,
        }))
    (SITE / "circuits" / "index.json").write_text(json.dumps(shipped, indent=1))
    print(f"shipped {len(shipped)} circuits, {len(records)} attempts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
