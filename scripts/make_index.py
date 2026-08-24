"""generate results/index.csv (one row per scored cell — the canonical
attempts only) and results/all-attempts.csv (one row per stored attempt).

canonical=1 marks the single attempt per (model, circuit) that the matrix and
all published numbers use — the one-shot selection from analysis/plot.py
(canonical_cells). everything else is archive: superseded batches, extra
samples from the pre-protocol era. nothing is deleted; this file just says
which row counts.

usage: uv run python scripts/make_index.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analysis"))

from plot import canonical_cells


def main() -> int:
    canon_paths = {r["_path"] for r in canonical_cells().values()}

    rows = []
    for p in sorted((ROOT / "results" / "records").glob("*/*.json")):
        r = json.loads(p.read_text())
        batch = p.stem.rsplit("__", 1)[1]
        is_canon = str(p) in canon_paths
        rows.append({
            "model": r["model"],
            "circuit": r["circuit"],
            "sample": r.get("sample", 0),
            "batch": batch,
            "canonical": int(bool(is_canon)),
            "status": r["score"]["status"],
            "prefix_cycles": r["score"]["prefix_cycles"],
            "cycles": r["cycles"],
            "exact": int(bool(r["score"].get("exact"))),
            "completion_tokens": (r.get("usage") or {}).get("completion_tokens", ""),
            "generation_id": r.get("generation_id", ""),
            "file": str(p.relative_to(ROOT)),
        })
    # index.csv = exactly the attempts the matrix presents (one per cell);
    # all-attempts.csv = the full ledger, nothing deleted, canonical flagged
    fields = list(rows[0].keys())
    canon_rows = [r for r in rows if r["canonical"]]
    with (ROOT / "results" / "index.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(canon_rows)
    with (ROOT / "results" / "all-attempts.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    n_canon = len(canon_rows)
    cells = len({(r["model"], r["circuit"]) for r in canon_rows})
    print(f"{len(rows)} attempts total, {n_canon} canonical -> index.csv, "
          f"{cells} distinct cells")
    if n_canon != cells:
        print("WARNING: canonical rows != distinct cells — ambiguity, investigate")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
