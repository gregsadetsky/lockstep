# lockstep

article page for the lockstep eval. vite + plain html/js/css, no framework.

```
npm install
npm run dev
```

the page lives under a secret uuid path (see vite.config.js), / is blank on purpose.

- `<uuid>/` — the article
- `<uuid>/c/?id=<circuit>` — interactive viewer for any circuit json in `public/circuits/`
- `src/sim.js` — js port of the netlist semantics (nand + dff), runs in the page
- `npm run build` also checks links (no FIXME hrefs, no broken local paths, external links need target=_blank); `npm run check` adds live http checks
- figures are exports from the eval repo's `analysis/`
