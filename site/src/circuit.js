// full-circuit widget: auto-laid-out schematic of every gate, live values,
// clock control, and the recorded trace table underneath. inputs are held at
// 0; flip-flop outputs appear once, on the right, with feedback wires routed
// around the bottom back to the left side.

import { createSim } from "./sim.js";
import { el } from "./svg.js";

const ROW_H = 58;
const TOP = 30;
const CHIP_W = 74;
const CHIP_H = 26;
const GATE_W = 34; // body incl. bubble
const COL_GAP = 128;
const GATE_X0 = 170;
const DFF_W = 88;

export function mountCircuitSim(container, circuit, opts = {}) {
  const editable = opts.editableInputs ?? true;
  const sim = createSim(circuit);
  const inputVals = Object.fromEntries(circuit.inputs.map((n) => [n, 0]));
  const recorded = []; // per executed cycle: settled nets (inputs included)

  // ---- layered layout: sources at 0, gate layer = max(input layers) + 1 ----
  const netLayer = new Map();
  for (const n of circuit.inputs) netLayer.set(n, 0);
  for (const f of circuit.dffs) netLayer.set(f.q, 0);
  const gateLayer = new Map();
  {
    const pending = [...circuit.gates];
    while (pending.length > 0) {
      let progressed = false;
      for (let i = 0; i < pending.length; ) {
        const g = pending[i];
        if (netLayer.has(g.a) && netLayer.has(g.b)) {
          const l = Math.max(netLayer.get(g.a), netLayer.get(g.b)) + 1;
          gateLayer.set(g, l);
          netLayer.set(g.y, l);
          pending.splice(i, 1);
          progressed = true;
        } else {
          i += 1;
        }
      }
      if (!progressed) throw new Error("undriven net or combinational loop");
    }
  }
  const maxLayer = circuit.gates.length > 0 ? Math.max(...gateLayer.values()) : 0;

  // feedback loops / left-side taps only exist for q nets something reads
  const consumed = new Set([
    ...circuit.gates.flatMap((g) => [g.a, g.b]),
    ...circuit.dffs.map((f) => f.d),
  ]);
  const fbCount = circuit.dffs.filter((f) => consumed.has(f.q)).length;

  // left column rows: input chips first, then feedback tap points for each
  // q that actually feeds something
  const sources = [
    ...circuit.inputs,
    ...circuit.dffs.map((f) => f.q).filter((q) => consumed.has(q)),
  ];
  const perLayer = new Map(); // layer -> gates in netlist order
  for (const g of circuit.gates) {
    const l = gateLayer.get(g);
    if (!perLayer.has(l)) perLayer.set(l, []);
    perLayer.get(l).push(g);
  }
  const rows = Math.max(
    sources.length,
    circuit.dffs.length,
    ...[...perLayer.values()].map((gs) => gs.length),
  );
  const colY = (count, r) => TOP + ((rows - count) * ROW_H) / 2 + r * ROW_H;

  const outPoint = new Map(); // net -> {x, y} where its fan-out wires start
  sources.forEach((n, r) => outPoint.set(n, { x: 14 + CHIP_W, y: colY(sources.length, r) + CHIP_H / 2 }));
  const gatePos = new Map(); // gate -> {x, y} (left edge, vertical center)
  for (const [l, gs] of perLayer) {
    gs.forEach((g, r) => {
      const x = GATE_X0 + (l - 1) * COL_GAP;
      const y = colY(gs.length, r) + CHIP_H / 2;
      gatePos.set(g, { x, y });
      outPoint.set(g.y, { x: x + GATE_W + 4, y });
    });
  }
  // with no gate columns, keep the dff column close to the input chips
  const dffX = circuit.gates.length > 0 ? GATE_X0 + maxLayer * COL_GAP + 10 : 14 + CHIP_W + 70;
  const width = dffX + DFF_W + 24 + fbCount * 7;
  const trackTop = TOP + rows * ROW_H + 4; // feedback tracks under the schematic
  const height = trackTop + fbCount * 11 + (fbCount > 0 ? 10 : 0) + (opts.inputCaption ? 26 : 0);

  // ---- static svg ----
  const svg = el("svg", { class: "schematic", viewBox: `0 0 ${width} ${height}` });
  if (opts.natural) {
    // big circuits render at natural size inside a horizontal scroller
    svg.setAttribute("width", Math.round(width * 0.85));
    svg.setAttribute("height", Math.round(height * 0.85));
    svg.classList.add("natural");
  } else if (height > width) {
    // tall narrow circuits (e.g. pure-dff perms): don't stretch to full
    // container width — cap the height and center at natural ratio
    svg.classList.add("tall");
  }
  const wires = []; // {path, srcNet}

  function wire(fromNet, to) {
    const from = outPoint.get(fromNet);
    const midX = (from.x + to.x) / 2;
    const path = el("path", {
      d: `M ${from.x} ${from.y} C ${midX} ${from.y}, ${midX} ${to.y}, ${to.x} ${to.y}`,
      class: "wire",
    });
    wires.push({ path, srcNet: fromNet });
    svg.append(path);
  }

  // wires first so everything else draws on top
  for (const g of circuit.gates) {
    const p = gatePos.get(g);
    wire(g.a, { x: p.x, y: p.y - 7 });
    wire(g.b, { x: p.x, y: p.y + 7 });
  }
  circuit.dffs.forEach((f, r) => {
    wire(f.d, { x: dffX, y: colY(circuit.dffs.length, r) + CHIP_H / 2 });
  });

  // feedback: dff output -> right margin -> bottom track -> left -> its tap
  let fbIdx = 0;
  circuit.dffs.forEach((f, i) => {
    if (!consumed.has(f.q)) return;
    const boxY = colY(circuit.dffs.length, i) + CHIP_H / 2;
    const tap = outPoint.get(f.q);
    const xRight = width - 6 - fbIdx * 7;
    const yTrack = trackTop + fbIdx * 11;
    const xLeft = 14 + fbIdx * 5;
    fbIdx += 1;
    const path = el("path", {
      d: `M ${dffX + DFF_W} ${boxY} H ${xRight} V ${yTrack} H ${xLeft} V ${tap.y} H ${tap.x}`,
      class: "wire feedback",
    });
    wires.push({ path, srcNet: f.q });
    svg.append(path);
    svg.append(el("text", { x: tap.x - 4, y: tap.y - 5, "text-anchor": "end", class: "netname" }, f.q));
  });

  // input chips, clickable unless opts.editableInputs is false
  circuit.inputs.forEach((n, r) => {
    const y = colY(sources.length, r);
    const chip = el(
      "g",
      editable ? { class: "pin", tabindex: "0", role: "button" } : {},
      el("rect", { x: 14, y, width: CHIP_W, height: CHIP_H, class: "chip-box input", "data-chip": n }),
      el("text", { x: 14 + CHIP_W / 2, y: y + 18, "text-anchor": "middle", "data-chipval": n }, n),
    );
    if (editable) {
      const flip = () => { inputVals[n] ^= 1; render(); };
      chip.addEventListener("click", flip);
      chip.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); flip(); }
      });
    }
    svg.append(chip);
    // optional caption lines under the chip (used by the lone-dff widget)
    if (r === 0 && opts.inputCaption) {
      opts.inputCaption.forEach((line, i) => {
        svg.append(el("text", {
          x: 14, y: y + CHIP_H + 16 + i * 15, class: "hint under-caption",
        }, line));
      });
    }
  });
  const qSet = new Set(circuit.dffs.map((f) => f.q));
  const dffsAreOutputs =
    circuit.outputs.length === circuit.dffs.length &&
    circuit.outputs.every((o) => qSet.has(o));
  if (circuit.inputs.length > 0) {
    svg.append(el("text", { x: 14, y: TOP - 12, class: "hint" },
      opts.inputHint ?? (editable ? "inputs (click to flip)" : "inputs")));
  }
  if (circuit.dffs.length > 0) {
    svg.append(
      el("text", { x: dffX + DFF_W, y: TOP - 12, "text-anchor": "end", class: "hint" },
        opts.rightHint ?? (dffsAreOutputs ? "the outputs" : "flip-flops")),
    );
  }

  // gates
  for (const g of circuit.gates) {
    const { x, y } = gatePos.get(g);
    svg.append(
      el("path", {
        d: `M ${x} ${y - 12} L ${x + 15} ${y - 12} A 12 12 0 0 1 ${x + 15} ${y + 12} L ${x} ${y + 12} Z`,
        class: "body",
      }),
      el("circle", { cx: x + 31, cy: y, r: 4, class: "body" }),
      el("text", { x: x + 15, y: y + 27, "text-anchor": "middle", class: "netname" }, g.y),
      el("text", { x: x + 42, y: y - 6, class: "netval", "data-netval": g.y }, ""),
    );
  }

  // dff boxes: current output value; the incoming d wire is the next value
  circuit.dffs.forEach((f, r) => {
    const y = colY(circuit.dffs.length, r);
    svg.append(
      el("rect", { x: dffX, y, width: DFF_W, height: CHIP_H, class: "chip-box state", "data-chip": `dff_${f.q}` }),
      el("text", { x: dffX + DFF_W / 2, y: y + 18, "text-anchor": "middle", "data-chipval": `dff_${f.q}` }, ""),
    );
  });

  // ---- dom shell ----
  container.innerHTML = `
    <div class="controls">
      <button data-act="tick">tick clock</button>
      <button data-act="reset">reset</button>
    </div>
    <div class="schematic-holder"></div>
    ${opts.note ? `<p class="simnote">${opts.note}</p>` : ""}
    <div class="trace"></div>
    <details class="netlist">
      <summary>The netlist with its input sequence</summary>
      <pre></pre>
    </details>
  `;
  container.querySelector(".schematic-holder").append(svg);
  container.querySelector("pre").textContent = JSON.stringify(circuit, null, 2);

  // tall circuits are height-capped and can get too small to read: give
  // them zoom buttons. zooming overrides the cap; the holder scrolls.
  if (svg.classList.contains("tall")) {
    let zoom = 1;
    const base = Math.min(620, window.innerHeight * 0.72);
    const bar = document.createElement("div");
    bar.className = "zoom-controls";
    bar.innerHTML = `<button data-z="out" title="zoom out">−</button><button data-z="in" title="zoom in">+</button>`;
    container.querySelector(".schematic-holder").before(bar);
    const apply = () => {
      svg.style.maxHeight = "none";
      svg.style.height = `${Math.round(base * zoom)}px`;
      svg.style.width = "auto";
    };
    bar.addEventListener("click", (e) => {
      const dir = e.target.dataset?.z;
      if (!dir) return;
      zoom = Math.min(6, Math.max(0.5, zoom * (dir === "in" ? 1.4 : 1 / 1.4)));
      apply();
    });
  }

  // ---- live rendering ----
  function render() {
    const nets = sim.settle(inputVals);
    for (const { path, srcNet } of wires) path.classList.toggle("on", nets[srcNet] === 1);
    for (const g of circuit.gates) {
      const t = svg.querySelector(`[data-netval="${g.y}"]`);
      t.textContent = String(nets[g.y]);
      t.classList.toggle("on", nets[g.y] === 1);
    }
    for (const n of circuit.inputs) {
      svg.querySelector(`[data-chipval="${n}"]`).textContent = `${n} = ${nets[n]}`;
      svg.querySelector(`[data-chip="${n}"]`).classList.toggle("on", nets[n] === 1);
    }
    for (const f of circuit.dffs) {
      svg.querySelector(`[data-chipval="dff_${f.q}"]`).textContent = `${f.q} = ${nets[f.q]}`;
      svg.querySelector(`[data-chip="dff_${f.q}"]`).classList.toggle("on", nets[f.q] === 1);
    }

    const header = recorded.map((_, t) => `<th>t${t}</th>`).join("");
    const row = (name) =>
      `<tr><td class="row-name">${name}</td>` +
      recorded.map((r) => `<td class="${r[name] ? "on" : ""}">${r[name]}</td>`).join("") +
      "</tr>";
    const inputRows = circuit.inputs.map(row).join("");
    const outputRows = circuit.outputs.map(row).join("");
    container.querySelector(".trace").innerHTML = `
      <table>
        <tr><th class="row-name">cycle</th>${header}</tr>
        ${inputRows}
        ${outputRows}
      </table>
    `;
  }

  container.querySelector(".controls").addEventListener("click", (e) => {
    const act = e.target.dataset?.act;
    if (!act) return;
    if (act === "reset") {
      sim.reset();
      recorded.length = 0;
      for (const n of circuit.inputs) inputVals[n] = 0;
    } else {
      recorded.push(sim.clock(inputVals));
    }
    render();
  });

  render();
}
