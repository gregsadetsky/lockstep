// link check over the built site.
// default: fail if any href/src contains FIXME (placeholder never ships).
// with --network: also HEAD/GET every external http(s) link, fail on >= 400.

import { readFileSync, readdirSync, statSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { parse } from "node-html-parser";

const dist = join(dirname(fileURLToPath(import.meta.url)), "..", "dist");
const network = process.argv.includes("--network");

function htmlFiles(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...htmlFiles(p));
    else if (name.endsWith(".html")) out.push(p);
  }
  return out;
}

if (!existsSync(dist)) {
  console.error("check-links: dist/ not found, run vite build first");
  process.exit(1);
}

const urls = new Map(); // url -> file it appears in
let failed = false;
for (const file of htmlFiles(dist)) {
  const root = parse(readFileSync(file, "utf8"));
  for (const node of root.querySelectorAll("[href], [src]")) {
    const url = node.getAttribute("href") ?? node.getAttribute("src");
    if (url) urls.set(url, file);
    // external anchors must open in a new tab
    if (
      node.tagName === "A" &&
      /^https?:\/\//.test(node.getAttribute("href") ?? "") &&
      node.getAttribute("target") !== "_blank"
    ) {
      console.error(`external link missing target=_blank in ${file}: ${url}`);
      failed = true;
    }
  }
}

for (const [url, file] of urls) {
  if (url.toUpperCase().includes("FIXME")) {
    console.error(`FIXME link left in ${file}: ${url}`);
    failed = true;
  }
}

// local references (/figs/..., /assets/...) must exist in dist
for (const [url, file] of urls) {
  if (url.startsWith("/") && !url.startsWith("//")) {
    const target = join(dist, url.split("#")[0].split("?")[0]);
    if (!existsSync(target)) {
      console.error(`broken local link in ${file}: ${url}`);
      failed = true;
    }
  }
}

if (network) {
  for (const [url] of urls) {
    if (!/^https?:\/\//.test(url)) continue;
    let status;
    try {
      let res = await fetch(url, { method: "HEAD", redirect: "follow" });
      if (res.status >= 400) res = await fetch(url, { method: "GET", redirect: "follow" });
      status = res.status;
    } catch (err) {
      status = `error: ${err.message}`;
    }
    const bad = typeof status !== "number" || status >= 400;
    console.log(`${bad ? "FAIL" : "ok  "} ${status} ${url}`);
    if (bad) failed = true;
  }
}

if (failed) process.exit(1);
console.log(`check-links: ${urls.size} urls checked${network ? " (incl. network)" : ""}, all good`);
