import { gzipSync } from "node:zlib";
import { readFileSync, writeFileSync } from "node:fs";

for (const artifact of [
  "custom_components/approved_scripts/frontend/approved-scripts.js",
  "custom_components/approved_scripts/frontend/approved-scripts-panel.js",
]) {
  writeFileSync(`${artifact}.gz`, gzipSync(readFileSync(artifact)));
}
