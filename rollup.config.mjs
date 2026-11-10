import { readFileSync } from "node:fs";
import esbuild from "rollup-plugin-esbuild";

const packageJson = JSON.parse(readFileSync(new URL("./package.json", import.meta.url)));
const dev = Boolean(process.env.ROLLUP_WATCH);

const bundle = (input, file, name) => ({
  input,
  output: { file, format: "iife", name, sourcemap: dev },
  plugins: [
    esbuild({
      minify: !dev,
      target: "es2017",
      tsconfig: "./tsconfig.json",
      define: { __APPROVED_SCRIPTS_VERSION__: JSON.stringify(packageJson.version) },
    }),
  ],
});

export default [
  bundle("frontend/src/index.ts", "custom_components/approved_scripts/frontend/approved-scripts.js", "ApprovedScriptsFrontend"),
  bundle("frontend/src/panel.ts", "custom_components/approved_scripts/frontend/approved-scripts-panel.js", "ApprovedScriptsPanel"),
];
