"""replay the fuzz campaigns from their seeds and verify the committed
manifests: regenerate each circuit deterministically, simulate it fresh, and
compare the golden trace hash (and, for v2 rows, the full stored values).
nonzero exit on any mismatch. no verilog toolchain, no api key.

- fuzz/manifest.jsonl      (v1): seed parsed from the circuit name; circuits
  regenerate via lockstep.harness.fuzz_netlist (frozen).
- fuzz/verdicts-v2.jsonl   (v2): seed parsed from the name; circuits
  regenerate via lockstep.harness.fuzz_netlist_v2; stored golden values are
  compared bit-for-bit, not just by hash.

usage: uv run python scripts/fuzz_replay.py [--limit N]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lockstep.harness import fuzz_netlist, fuzz_netlist_v2
from lockstep.sim import simulate


def seed_of(name: str) -> int:
    m = re.search(r"_s(\d+)", name) or re.match(r"x(\d+)$", name)
    if not m:
        raise ValueError(f"no seed in name: {name}")
    return int(m.group(1))


def sha(golden: dict) -> str:
    return hashlib.sha256(json.dumps(golden, sort_keys=True).encode()).hexdigest()[:16]


def replay(path: Path, generate, check_values: bool, limit: int | None) -> int:
    if not path.exists():
        print(f"skip (missing): {path}")
        return 0
    bad = n = 0
    for line in path.read_text().splitlines():
        row = json.loads(line)
        n += 1
        if limit and n > limit:
            n -= 1
            break
        nl = generate(seed_of(row["name"]))
        if nl.name != row["name"]:
            print(f"NAME MISMATCH: regenerated {nl.name} != manifest {row['name']}")
            bad += 1
            continue
        golden = simulate(nl)
        if sha(golden) != row["golden_sha256_16"]:
            print(f"HASH MISMATCH: {row['name']}")
            bad += 1
        elif check_values and row.get("golden") and golden != row["golden"]:
            print(f"VALUE MISMATCH: {row['name']}")
            bad += 1
    print(f"{path.name}: {n} rows replayed, {bad} mismatches")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="rows per manifest")
    args = ap.parse_args()
    bad = replay(ROOT / "fuzz" / "manifest.jsonl", fuzz_netlist, False, args.limit)
    bad += replay(ROOT / "fuzz" / "verdicts-v2.jsonl", fuzz_netlist_v2, True, args.limit)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
