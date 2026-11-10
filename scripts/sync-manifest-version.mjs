import { readFileSync, writeFileSync } from "node:fs";

const packageJson = JSON.parse(readFileSync("package.json"));
const manifestPath = "custom_components/approved_scripts/manifest.json";
const manifest = JSON.parse(readFileSync(manifestPath));
manifest.version = packageJson.version;
writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
