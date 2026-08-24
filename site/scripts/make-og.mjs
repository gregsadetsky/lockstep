// regenerate public/figs/og.png from public/figs/matrix.png:
// right portion at 1200x630 with a white fade on the left edge.
// runs as part of `npm run build` so the og image can never go stale;
// skips gracefully where no browser is available (e.g. the disco deploy
// container, which builds with PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 and
// serves the committed og.png instead).
import { readFileSync, writeFileSync } from "node:fs";

let chromium;
try {
  ({ chromium } = await import("playwright"));
} catch {
  console.log("make-og: playwright unavailable, keeping committed og.png");
  process.exit(0);
}

try {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1200, height: 630 } });
  const b64 = readFileSync("public/figs/matrix.png").toString("base64");
  await page.setContent(`<canvas id="c" width="1200" height="630"></canvas>`);
  await page.evaluate(async (b64) => {
    const img = new Image();
    img.src = "data:image/png;base64," + b64;
    await img.decode();
    const c = document.getElementById("c");
    const g = c.getContext("2d");
    const cropW = Math.round((img.height * 1200) / 630);
    g.drawImage(img, img.width - cropW, 0, cropW, img.height, 0, 0, 1200, 630);
    const grad = g.createLinearGradient(0, 0, 170, 0);
    // ease-out fade matching (1 - (x/170)^1.5)
    for (let i = 0; i <= 10; i++) {
      const t = i / 10;
      grad.addColorStop(t, `rgba(252,252,251,${1 - Math.pow(t, 1.5)})`);
    }
    g.fillStyle = grad;
    g.fillRect(0, 0, 170, 630);
  }, b64);
  const buf = await page.locator("#c").screenshot();
  writeFileSync("public/figs/og.png", buf);
  await browser.close();
  console.log("make-og: og.png regenerated from matrix.png");
} catch (err) {
  console.log("make-og: browser launch failed, keeping committed og.png:", err.message);
  process.exit(0);
}
