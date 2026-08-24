"""Which difficulty axis best predicts survival? Spearman rank correlation
between candidate measures and survival, per model and pooled.

usage: uv run python analysis/axis.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from plot import ALL_MODELS, RAND_PARAMS, ROOT, collect

from lockstep import gen
from lockstep.netlist import load, stats

_cache: dict[str, dict[str, int]] = {}


def circuit_stats(circuit: str) -> dict[str, int]:
    if circuit in _cache:
        return _cache[circuit]
    for sub in ("", "tier2", "tier3", "tier4", "x"):
        p = ROOT / "circuits" / sub / f"{circuit}.json"
        if p.exists():
            nl = load(p)
            break
    else:
        seed = int(circuit.split("_")[1][1:])
        n_in, g, d, c = RAND_PARAMS[seed]
        nl = gen.random_netlist(seed, n_inputs=n_in, n_gates=g, n_dffs=d, cycles=c)
    s = stats(nl)
    s["cycles"] = nl.cycles
    s["n_outputs"] = len(nl.outputs)
    _cache[circuit] = s
    return s


CANDIDATES = {
    "live_gates x cycles": lambda rec, s: s["live_gates"] * s["cycles"],
    "depth x cycles": lambda rec, s: s["depth"] * s["cycles"],
    "live_dffs x cycles": lambda rec, s: s["live_dffs"] * s["cycles"],
    "depth x live_dffs": lambda rec, s: s["depth"] * max(1, s["live_dffs"]),
    "live_gates": lambda rec, s: s["live_gates"],
    "depth": lambda rec, s: s["depth"],
    "cycles": lambda rec, s: s["cycles"],
    "live_dffs": lambda rec, s: s["live_dffs"],
    "prompt_tokens": lambda rec, s: rec.get("prompt_tokens"),
    "output_cells": lambda rec, s: s["n_outputs"] * s["cycles"],
}


def spearman(xs: list[float], ys: list[float]) -> float:
    def ranks(v: list[float]) -> list[float]:
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = ranks(xs), ranks(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx) ** 0.5
    vy = sum((b - my) ** 2 for b in ry) ** 0.5
    return cov / (vx * vy) if vx and vy else 0.0


if __name__ == "__main__":
    rows = collect()
    groups: dict[str, list[dict]] = {"POOLED (all models)": rows}
    for slug, label in ALL_MODELS.items():
        sub = [r for r in rows if r["model"] == slug]
        hard = [r for r in sub if r["survival"] < 1.0]
        if len(hard) >= 5:  # only models that actually got separated
            groups[label] = sub
    name_w = max(len(n) for n in CANDIDATES)
    for gname, grows in groups.items():
        print(f"\n{gname} (n={len(grows)}) — spearman rho vs survival (more negative = "
              "better difficulty axis)")
        scored = []
        for cname, fn in CANDIDATES.items():
            pairs = [
                (float(v), r["survival"])
                for r in grows
                if (v := fn(r, circuit_stats(r["circuit"]))) is not None
            ]
            xs, ys = [p[0] for p in pairs], [p[1] for p in pairs]
            scored.append((spearman(xs, ys), cname))
        for rho, cname in sorted(scored):
            print(f"  {cname:{name_w}s}  {rho:+.3f}")
