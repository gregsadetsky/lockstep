// one interactive NAND gate: click either input value to flip it

import { el } from "./svg.js";

export function mountNandSim(container) {
  const state = { a: 0, b: 1 };

  const svg = el("svg", {
    class: "nand-svg",
    viewBox: "0 0 420 170",
    width: "420",
    height: "170",
  });

  function valueBox(x, y, name, clickable) {
    const g = el("g", clickable ? { class: "pin", tabindex: "0", role: "button" } : {});
    const rect = el("rect", {
      x, y, width: 32, height: 32, class: "val-box", "data-net": name,
    });
    const text = el("text", {
      x: x + 16, y: y + 22, "text-anchor": "middle", "data-val": name,
    }, "0");
    g.append(rect, text);
    if (clickable) {
      const flip = () => { state[name] ^= 1; render(); };
      g.addEventListener("click", flip);
      g.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); flip(); }
      });
    }
    return g;
  }

  svg.append(
    // input wires
    el("line", { x1: 92, y1: 66, x2: 170, y2: 66, class: "wire", "data-wire": "a" }),
    el("line", { x1: 92, y1: 104, x2: 170, y2: 104, class: "wire", "data-wire": "b" }),
    // nand body: flat left edge, round right edge, inversion bubble
    el("path", { d: "M 170 40 L 218 40 A 45 45 0 0 1 218 130 L 170 130 Z", class: "body" }),
    el("circle", { cx: 270, cy: 85, r: 7, class: "body" }),
    // output wire
    el("line", { x1: 277, y1: 85, x2: 340, y2: 85, class: "wire", "data-wire": "y" }),
    // labels
    el("text", { x: 56, y: 42, class: "hint" }, "a (click to flip)"),
    el("text", { x: 56, y: 136, class: "hint" }, "b (click to flip)"),
    el("text", { x: 344, y: 61, class: "hint" }, "y"),
    // value boxes
    valueBox(56, 50, "a", true),
    valueBox(56, 88, "b", true),
    valueBox(344, 69, "y", false),
  );

  function render() {
    const y = 1 - (state.a & state.b);
    const vals = { ...state, y };
    for (const [name, v] of Object.entries(vals)) {
      svg.querySelector(`[data-val="${name}"]`).textContent = String(v);
      svg.querySelector(`[data-net="${name}"]`).classList.toggle("on", v === 1);
      const wire = svg.querySelector(`[data-wire="${name}"]`);
      if (wire) wire.classList.toggle("on", v === 1);
    }
  }

  container.append(svg);
  render();
}
