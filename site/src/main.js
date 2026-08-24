import { mountNandSim } from "./nand.js";
import { mountCircuitSim } from "./circuit.js";
// markdown prose blocks are rendered to static html at build time by the
// md-blocks plugin in vite.config.js (dev server included) — nothing to do here

mountNandSim(document.querySelector("#nand-sim .nand-holder"));

// a lone D flip-flop, in the same netlist format as everything else
const dffOnly = {
  name: "dff",
  inputs: ["d"],
  outputs: ["q"],
  gates: [],
  dffs: [{ d: "d", q: "q", init: 0 }],
  trace: { d: [1, 0, 1, 1] },
  cycles: 4,
};
mountCircuitSim(document.querySelector("#dff-sim"), dffOnly, {
  natural: true,
  inputHint: "d",
  rightHint: "q",
  inputCaption: ["click to flip,", "then click 'tick clock'"],
  note: "",
});

// the featured task is a real scored circuit, served from the same json the
// explorer uses
fetch("/circuits/counter_3bit.json")
  .then((r) => r.json())
  .then((c) => mountCircuitSim(document.querySelector("#circuit-sim"), c));

// clicking a figure opens the full image in a new tab (native zoom,
// pinch, 100% resolution) instead of a half-zoom overlay
for (const img of document.querySelectorAll("figure img")) {
  img.style.cursor = "zoom-in";
  img.addEventListener("click", () => {
    window.open(img.src, "_blank", "noopener");
  });
}
