import { defineConfig } from "vite";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { marked } from "marked";

const root = dirname(fileURLToPath(import.meta.url));


// prose is authored as markdown in <script type="text/markdown"> blocks;
// render them to static html at build time so the deployed page carries the
// real text (seo/scrapers/curl), no client-side conversion needed
const mdBlocks = {
  name: "md-blocks",
  transformIndexHtml(html) {
    return html.replace(
      /<script type="text\/markdown">([\s\S]*?)<\/script>/g,
      (_, md) => {
        const lines = md.replace(/^\n+|\s+$/g, "").split("\n");
        const nonEmpty = lines.filter((l) => l.trim());
        const indent = nonEmpty.length
          ? Math.min(...nonEmpty.map((l) => l.match(/^\s*/)[0].length))
          : 0;
        const src = lines.map((l) => l.slice(indent)).join("\n");
        const out = marked.parse(src).replace(
          /<a href="([^"]+)"/g,
          '<a href="$1" target="_blank" rel="noopener"',
        );
        return `<div class="md">\n${out}</div>`;
      },
    );
  },
};

export default defineConfig({
  plugins: [mdBlocks],
  build: {
    rollupOptions: {
      input: {
        main: resolve(root, "index.html"),
        c: resolve(root, "c/index.html"),
        r: resolve(root, "r/index.html"),
      },
    },
  },
});
