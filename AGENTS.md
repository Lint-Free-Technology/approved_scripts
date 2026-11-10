# Approved Scripts

Approved Scripts is a Home Assistant custom integration for delegating narrowly bounded, administrator-approved script actions to named non-admin users.

## Repository

- `custom_components/approved_scripts/` — integration backend, frontend resources, translations, brand assets, and the code-defined capability registry.
- `custom_components/approved_scripts/capabilities/library/` — one self-registering module for each reviewed delegated capability. Copy `_template.py` when adding one.
- `frontend/src/` — TypeScript source for the frontend resource and management panel.
- `tests/` — pure validator tests and ha-testcontainer runtime security tests.
- `docs/` — Zensical documentation source and site configuration.

## Markdown and documentation

Write each prose paragraph on one physical line, with one blank line between paragraphs. Do not manually wrap prose. Keep line breaks where Markdown structure requires them, including headings, lists, tables, blockquotes, admonitions, and code blocks.

The English documentation in `docs/source/` is canonical. Do not add translated Markdown copies. Update the relevant documentation, threat matrix, and contribution guidance with every user-facing feature or capability change.

Build the documentation site with `zensical build --clean --config-file mkdocs.yml` from `docs/`. `docs/site/` and `docs/.cache/` are generated and must not be committed.

## Capability security model

- A new protected action is a security-policy change, not a service-list addition.
- Add it as a non-private module exposing one `CAPABILITY` instance in `capabilities/library/`; the library discovers it automatically. Do not register actions from YAML, UI input, or a broad allow-list.
- Every capability must have a bounded target and data model, canonical snapshot coverage, translated title and warning, a threat-matrix row, and pure plus runtime security tests.
- Templates may be supported only for explicitly designed fields. Render them outside Home Assistant's Script runner and validate their result against the exact approved policy before execution.
- Never introduce dynamic service names, dynamic targets, raw Jinja in the Script runner, generic HTTP, shell/configuration/authentication operations, `script.*`, or `automation.*` without an explicitly approved new security model.

## Frontend and generated assets

Use TypeScript in `frontend/src/` and target ES2017. Keep UIX-shaped frontend patterns where applicable: connection lifecycle handling, version/reload behaviour, translations served by the backend, Home Assistant forms/selectors, and standard dialogs.

Run `npm run check:frontend` before frontend changes are handed over. Run `npm run build` after changing frontend source or integration version; it rebuilds both JavaScript bundles and their `.gz` variants. The frontend resources in `custom_components/approved_scripts/frontend/` are release artifacts and must be rebuilt, not edited by hand. Versioning is workflow-controlled: never manually set the version.

## Testing

Use the VS Code tasks for virtual-environment setup, individual tests, the full suite, and the persistent Home Assistant server. The test environment is ha-testcontainer, not visual/browser snapshots.

Set up the environment with `python3 -m venv .venv && source .venv/bin/activate && python -m pip install -r requirements-test.txt`.

For repeated runtime tests, start the `HA: Start persistent server` VS Code task. For a focused test, run `pytest tests/test_runtime_security.py -k '<expression>'`. Run `pytest tests/` for capability, authorization, snapshot, template-policy, trace, reload, or unload changes. Bug fixes should include a regression test where practical.

## Releases and pull requests

Follow the existing release and validation workflows. The release workflow owns the version and release recovery; do not make a manual version bump. HACS compatibility and documentation publishing are validated by their workflows.
