"""Find candidate reasoning transcripts for the article's reasoning gallery,
and answer 'do models write a simulator in their head or wing it?' by
scanning stored reasoning for code-writing.

usage: uv run python analysis/exemplars.py [--dump DIR]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plot import ALL_MODELS, RECORDS_DIR

CODEY = re.compile(r"\bdef |\bimport |for .+ in range\(|while |\.append\(|= \{|\[i\]")


def records() -> list[dict]:
    out = []
    for p in sorted(RECORDS_DIR.glob("*/*.json")):
        r = json.loads(p.read_text())
        if r["model"] in ALL_MODELS:
            r["_path"] = str(p)
            out.append(r)
    return out


def text_of(r: dict) -> str:
    return (r.get("reasoning") or "") + "\n" + (r.get("response") or "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", default=None, help="write candidate transcripts here")
    args = ap.parse_args()
    rs = records()

    # --- joão's question: code-writing inside reasoning, per model ---
    print("reasoning that contains code-like text (mental simulator writing):")
    for m in ALL_MODELS:
        sub = [r for r in rs if r["model"] == m and (r.get("reasoning") or "").strip()]
        if not sub:
            print(f"  {ALL_MODELS[m]:18s} no readable reasoning stored")
            continue
        codey = sum(1 for r in sub if CODEY.search(r["reasoning"]))
        print(f"  {ALL_MODELS[m]:18s} {codey}/{len(sub)} traces contain code-like text")

    # --- gallery candidates ---
    def pick(label: str, pred, key, n=3):
        got = sorted((r for r in rs if pred(r)), key=key)[:n]
        print(f"\n{label}:")
        for r in got:
            sc = r["score"]
            rl = len(r.get("reasoning") or "")
            print(f"  {ALL_MODELS[r['model']]:16s} {r['circuit']:24s} "
                  f"prefix={sc['prefix_cycles']}/{r['cycles']} reasoning={rl}ch  {r['_path']}")
        return got

    ok = lambda r: r["score"]["status"] == "ok"
    rlen = lambda r: len(r.get("reasoning") or "")
    exact = lambda r: ok(r) and r["score"]["prefix_cycles"] == r["cycles"]

    picks = []
    picks += pick("(a) short clean success (easy circuit, tiny reasoning)",
                  lambda r: exact(r) and 200 < rlen(r) < 3000 and r["gates"] <= 12,
                  rlen)
    picks += pick("(b) medium successful grind (hard circuit, solved)",
                  lambda r: exact(r) and r["gates"] >= 80 and 5000 < rlen(r) < 40000,
                  lambda r: -r["gates"])
    picks += pick("(c) sane-for-a-while failure (diverged mid-run)",
                  lambda r: ok(r) and 0.3 < r["score"]["prefix_cycles"] / r["cycles"] < 0.8
                  and rlen(r) > 1000,
                  lambda r: -rlen(r))
    picks += pick("(d) early haywire (died in the first cycles)",
                  lambda r: ok(r) and r["score"]["prefix_cycles"] <= 2
                  and r["score"]["prefix_cycles"] < r["cycles"] and rlen(r) > 500,
                  rlen)

    if args.dump:
        dest = Path(args.dump)
        dest.mkdir(parents=True, exist_ok=True)
        for r in picks:
            name = f"{ALL_MODELS[r['model']]}__{r['circuit']}__s{r.get('sample', 0)}.txt"
            (dest / name).write_text(
                f"model: {r['model']}\ncircuit: {r['circuit']}\n"
                f"score: {r['score']}\n\n=== reasoning ===\n{r.get('reasoning') or '(none)'}"
                f"\n\n=== response ===\n{r.get('response') or ''}"
            )
        print(f"\ndumped {len(picks)} transcripts to {dest}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
