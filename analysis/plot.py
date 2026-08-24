"""Charts over results/records (the matrix and friends). Rerunnable any
time; reads only stored result files.

usage: uv run python analysis/plot.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lockstep import gen
from lockstep.netlist import load, stats

# one flat dir of verbatim attempts; the batch tag in each filename
# (__feel1 / __max1 / __retry1..3 / __fable-retest) records which run wrote it
RECORDS_DIR = ROOT / "results" / "records"
OUT = ROOT / "analysis"

# top 3 by all-circuits mean (the matrix sort score), printed for the
# terminal summary; assigned at runtime by refresh_top3().
MODELS: dict[str, tuple[str, str]] = {}
_SLOT_COLORS = ["#2a78d6", "#eb6834", "#1baf7a"]


def refresh_top3(rows: list[dict]) -> None:
    def hard_mean(m: str) -> float:
        vals = [r["survival"] for r in rows if r["model"] == m]
        return sum(vals) / len(vals) if vals else 0.0

    ranked = sorted(ALL_MODELS, key=lambda m: -hard_mean(m))[:3]
    MODELS.clear()
    for slug, color in zip(ranked, _SLOT_COLORS):
        MODELS[slug] = (ALL_MODELS[slug], color)
ALL_MODELS = {
    "anthropic/claude-opus-5": "opus-5",
    "openai/gpt-5.6-sol": "gpt-5.6-sol",
    "google/gemini-3.1-pro-preview": "gemini-3.1-pro",
    "openai/gpt-5.5": "gpt-5.5",
    "anthropic/claude-sonnet-5": "sonnet-5",
    "moonshotai/kimi-k3": "kimi-k3",
    "deepseek/deepseek-v4-pro": "deepseek-v4-pro",
    "google/gemini-3.7-flash": "gemini-3.7-flash",
    "openai/gpt-5-mini": "gpt-5-mini",
    "anthropic/claude-haiku-4.5": "haiku-4.5",
    # fable-5 deliberately absent: every attempt is refused by anthropic's
    # safety filter (even via the cyber-exception org) — covered in prose
}
# sequential ramp (palette.md blue, light->dark = 0%->100%)
RAMP = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
FAMILIES = ["starter", "rand-40g", "rand-80g", "mix", "rule30", "ca", "chain"]

SURFACE, INK, INK2, MUTED, GRID, BASE = (
    "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7",
)

RAND_PARAMS = {  # seed -> (inputs, gates, dffs, cycles), from the sweep commands
    **{s: (3, 40, 6, 24) for s in (900, 901, 902)},
    **{s: (3, 80, 10, 32) for s in (910, 911, 912)},
}


def family_of(circuit: str) -> str:
    if circuit.startswith("rand_s9"):
        return "rand-80g" if circuit.startswith("rand_s91") else "rand-40g"
    if circuit.startswith("rand_s4"):
        return "size-sweep"  # tier3: gates vary, dffs/cycles fixed
    if circuit.startswith("x") and circuit[1:].isdigit():
        return "ca"  # anti-recognition random-rule cellular automata
    if circuit.startswith("chain") and circuit.endswith("_d0"):
        return "nand-land"  # tier3: pure combinational, zero dffs
    if circuit.startswith("perm"):
        return "dff-land"  # tier3: pure state shuffling, zero gates
    for fam in ("chain", "mix", "rule30"):
        if circuit.startswith(fam):
            return fam
    return "starter"


def circuit_work(circuit: str) -> int:
    """serial work per circuit: combinational depth x cycles."""
    candidates = [
        ROOT / "circuits" / f"{circuit}.json",
        ROOT / "circuits" / "tier2" / f"{circuit}.json",
        ROOT / "circuits" / "tier3" / f"{circuit}.json",
        ROOT / "circuits" / "tier4" / f"{circuit}.json",
        ROOT / "circuits" / "x" / f"{circuit}.json",
        ROOT / "circuits" / "rand" / f"{circuit}.json",
    ]
    existing = [p for p in candidates if p.exists()]
    if existing:
        nl = load(existing[0])
    else:
        seed = int(circuit.split("_")[1][1:])
        n_in, g, d, c = RAND_PARAMS[seed]
        nl = gen.random_netlist(seed, n_inputs=n_in, n_gates=g, n_dffs=d, cycles=c)
        assert nl.name == circuit, (nl.name, circuit)
    # depth x cycles: the most survival-predictive axis measured so far
    # (analysis/axis.py, pooled spearman -0.56, beats live_gates x cycles)
    return max(1, stats(nl)["depth"]) * nl.cycles


def canonical_cells() -> dict[tuple[str, str], dict]:
    """One-shot protocol: each (model, circuit) cell is the model's first
    attempt at its maximum output budget — the lowest-sample record, with the
    model-max batch (__max1) beating the capped-era original (__feel1) at the
    same sample index. Later samples stay in the archive and never affect
    scoring or display."""
    cand: dict[tuple[str, str], list[tuple[int, int, dict]]] = {}
    # every attempt lives flat in results/records/<model>/<circuit>__sN__<batch>.json
    # retry1 = later-day retries of cells whose every earlier record was a
    # safety refusal; it ranks last so it only ever supplies the attempt when
    # all earlier records were refusals
    batch_rank = {"max1": 0, "feel1": 1, "retry1": 2, "retry2": 3, "retry3": 4,
                  "retry4": 5, "fable-retest": 6}
    demo_max: dict[str, int] = {}  # per-model demonstrated output ceiling
    for p in sorted(RECORDS_DIR.glob("*/*.json")):
        batch = p.stem.rsplit("__", 1)[1]
        r = json.loads(p.read_text())
        if r["model"] not in ALL_MODELS:
            continue
        r["_path"] = str(p)  # lets index/export point at the exact file
        ct = (r.get("usage") or {}).get("completion_tokens") or 0
        demo_max[r["model"]] = max(demo_max.get(r["model"], 0), ct)
        key = (r["model"], r["circuit"])
        # unknown batches (e.g. a reproducer's fresh runs) rank after all
        # known ones instead of crashing
        cand.setdefault(key, []).append((r.get("sample", 0), batch_rank.get(batch, 99), r))
    cells: dict[tuple[str, str], dict] = {}
    for key, lst in cand.items():
        lst.sort(key=lambda t: (t[0], t[1]))
        # one shot = the model's first ATTEMPT at its full budget. NOT attempts:
        # a transport api_error; a safety refusal; an undelivered reply (zero
        # output tokens, an error finish, or no response content at all); and
        # a truncation whose token count is far below the model's demonstrated
        # output ceiling (openrouter routed some models to providers with much
        # smaller caps — dying at a 16k route ceiling when the model has
        # produced 145k elsewhere is a routing artifact, not a budget failure).
        # none of those consume the shot; such cells were retried on later
        # days and the first full-budget delivered attempt counts. a cell
        # whose every record is a refusal stays blocked (gray x).
        def is_attempt(r: dict) -> bool:
            if r["score"]["status"] in ("api_error", "refused"):
                return False
            if r.get("finish") == "error":
                return False
            ct = (r.get("usage") or {}).get("completion_tokens")
            if ct == 0:
                return False
            if r["score"]["status"] == "truncated":
                # a real at-ceiling truncation is a scored failure; one capped
                # far below the model's own demonstrated ceiling is a routing
                # artifact, not an attempt at max budget
                return not (isinstance(ct, int)
                            and ct < 0.8 * demo_max.get(r["model"], 0))
            # non-truncated replies must actually contain answer text —
            # a record with no response at all was never delivered, even if
            # the provider billed reasoning tokens for it
            return bool(r.get("response"))

        chosen = next((r for _, _, r in lst if is_attempt(r)), None)
        if chosen is None:
            chosen = next((r for _, _, r in lst
                           if r["score"]["status"] == "refused"), None)
            if chosen is None:
                # only non-attempts (api errors / undelivered replies):
                # the cell is not-run
                continue
        cells[key] = chosen
    return cells


def collect() -> list[dict]:
    rows = []
    for r in canonical_cells().values():
        # refused = provider filter, not a model failure; truncated stays
        # (counted 0, it failed in budget)
        if r["score"]["status"] == "refused":
            continue
        rows.append(
            {
                "model": r["model"],
                "circuit": r["circuit"],
                "family": family_of(r["circuit"]),
                # truncated = failed within budget -> survival 0 (see caption)
                "survival": r["score"]["prefix_cycles"] / r["cycles"],
                "status": r["score"]["status"],
                "work": circuit_work(r["circuit"]),
                "prompt_tokens": (r.get("usage") or {}).get("prompt_tokens"),
            }
        )
    return rows



def refused_pairs() -> set[tuple[str, str]]:
    """(model, circuit) cells whose one-shot attempt was refused by the
    provider safety filter — distinct from not-run and from failure."""
    return {k for k, r in canonical_cells().items()
            if r["score"]["status"] == "refused"}


def heatmap(rows: list[dict]) -> None:
    """models (best all-circuits mean on top) x circuits; cell = % of the run
    right before the first wrong bit. gray square + x = blocked by the
    provider safety filter; dot = not run."""
    from matplotlib.colors import LinearSegmentedColormap
    from matplotlib.offsetbox import AnnotationBbox, OffsetImage

    cmap = LinearSegmentedColormap.from_list("seq", RAMP)
    refused = refused_pairs()

    # one record per (model, circuit) under the one-shot protocol
    def cell(slug: str, circ: str) -> float | None:
        vals = [r["survival"] for r in rows if r["model"] == slug and r["circuit"] == circ]
        return vals[0] if vals else None

    def all_truncated(slug: str, circ: str) -> bool:
        sts = [r["status"] for r in rows if r["model"] == slug and r["circuit"] == circ]
        return bool(sts) and all(s == "truncated" for s in sts)

    circuits = sorted({r["circuit"] for r in rows})
    # only show circuits at least half the models actually ran — a column
    # with one or two filled cells reads as mystery, not data
    def n_models(c: str) -> int:
        return len({r["model"] for r in rows if r["circuit"] == c})

    hidden = [c for c in circuits if n_models(c) < 5]
    circuits = [c for c in circuits if n_models(c) >= 5]
    if hidden:
        print(f"matrix: hiding {len(hidden)} low-coverage circuits: {', '.join(hidden)}")

    # column difficulty = mean survival over every run of that circuit
    def circ_mean(c: str) -> float:
        vals = [r["survival"] for r in rows if r["circuit"] == c]
        return sum(vals) / len(vals)

    circuits.sort(key=lambda c: -circ_mean(c))

    def hard_mean(m: str) -> float:
        # the visible, stated sort key: mean over every shown circuit
        vals = [v for c in circuits if (v := cell(m, c)) is not None]
        return sum(vals) / len(vals) if vals else 0.0

    models = sorted(ALL_MODELS, key=lambda m: -hard_mean(m))
    fig_w = 3.7 + 0.42 * len(circuits)
    fig_h = 1.6 + 0.38 * len(models)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    for spine in ax.spines.values():
        spine.set_visible(False)
    for yi, m in enumerate(models):
        logo = plt.imread(OUT / "logos" / VENDOR_LOGO[m.split("/")[0]])
        ab = AnnotationBbox(OffsetImage(logo, zoom=0.17), (-0.5, yi), xybox=(-9, 0),
                            boxcoords="offset points", frameon=False,
                            annotation_clip=False)
        ax.add_artist(ab)
        for xi, c in enumerate(circuits):
            v = cell(m, c)
            if v is None:
                if (m, c) in refused:
                    ax.add_patch(Rectangle((xi - 0.5, yi - 0.5), 1, 1,
                                               facecolor=GRID, edgecolor=SURFACE,
                                               linewidth=1.5))
                    ax.text(xi, yi, "✕", ha="center", va="center",
                            color=MUTED, fontsize=8)
                else:
                    ax.text(xi, yi, "·", ha="center", va="center", color=MUTED, fontsize=9)
                continue
            if all_truncated(m, c):
                # every attempt hit the model's output ceiling mid-thought:
                # no answer ever produced. distinct from a scored 0.
                ax.add_patch(Rectangle((xi - 0.5, yi - 0.5), 1, 1, facecolor=SURFACE,
                                           edgecolor=GRID, linewidth=1.2))
                ax.text(xi, yi, "lim", ha="center", va="center", color=MUTED,
                        fontsize=6.5)
                continue
            ax.add_patch(Rectangle((xi - 0.5, yi - 0.5), 1, 1, facecolor=cmap(v),
                                       edgecolor=SURFACE, linewidth=1.5))
            ax.text(xi, yi, f"{round(v * 100)}", ha="center", va="center", fontsize=7.5,
                    color="#ffffff" if v > 0.55 else INK)
        # mirror the logo + name on the right so identity survives a
        # horizontal scroll to the hard columns
        ab_r = AnnotationBbox(OffsetImage(logo, zoom=0.17), (len(circuits) - 0.5, yi),
                              xybox=(12, 0), boxcoords="offset points", frameon=False,
                              annotation_clip=False)
        ax.add_artist(ab_r)
        ax.annotate(ALL_MODELS[m], (len(circuits) - 0.5, yi), xytext=(24, 0),
                    textcoords="offset points", va="center", ha="left",
                    fontsize=8.5, color=INK2, annotation_clip=False)
    ax.set_xlim(-0.5, len(circuits) - 0.4)
    ax.set_ylim(len(models) - 0.5, -0.5)
    ax.set_xticks(range(len(circuits)))
    ax.set_xticklabels(circuits, rotation=45, ha="right", fontsize=7.5, color=INK2)
    ax.set_xlabel("circuit (one test per column)", color=INK2, fontsize=9)
    ax.set_yticks(range(len(models)))
    ax.set_yticklabels([ALL_MODELS[m] for m in models], fontsize=8.5, color=INK2)
    ax.tick_params(length=0)
    ax.tick_params(axis="y", pad=27)  # room for the vendor logo between name and grid
    ax.set_title("models vs circuits: 100 = the whole run bit-for-bit correct; "
                 "anything less = failed, and the number is how far it got "
                 "(darker / higher = better)",
                 color=INK, fontsize=11, loc="left", pad=12)
    fig.tight_layout()
    # fine print top-right, clear of the rotated circuit names at the bottom
    fig.text(0.99, 0.985,
             "rows sorted by each model's mean % over the circuits it was "
             "allowed to attempt (blocked cells excluded); columns sorted "
             "easiest to hardest (each circuit's mean score across all models)\n"
             "every cell is the model's first delivered attempt at its maximum output budget (one shot); "
             "gray ✕ means blocked by the provider safety filter; "
             "lim means still thinking when it hit its output limit (scored 0)",
             ha="right", va="top", fontsize=7.5, color=MUTED, linespacing=1.5)
    fig.savefig(OUT / "matrix.png", dpi=160, facecolor=SURFACE)


VENDOR_LOGO = {
    "anthropic": "anthropic.com.png",
    "openai": "openai.com.png",
    "google": "google.com.png",
    "moonshotai": "moonshot.ai.png",
    "deepseek": "deepseek.com.png",
}








def table(rows: list[dict]) -> None:
    print(f"{'family':10s}", *(f"{lbl:>16s}" for lbl, _ in MODELS.values()))
    for fam in FAMILIES:
        cells = []
        for slug in MODELS:
            vals = [r["survival"] for r in rows if r["model"] == slug and r["family"] == fam]
            cells.append(f"{sum(vals) / len(vals):16.2f}" if vals else f"{'-':>16s}")
        print(f"{fam:10s}", *cells)


if __name__ == "__main__":
    rows = collect()
    refresh_top3(rows)
    print("top 3 by all-circuits mean:", ", ".join(lbl for lbl, _ in MODELS.values()))
    heatmap(rows)
    table(rows)
    print(f"\nwrote matrix.png to {OUT}/ ({len(rows)} records)")
