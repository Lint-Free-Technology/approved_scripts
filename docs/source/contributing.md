---
title: Contributing
---
# Contributing

Contributions are welcome. Choose the area that matches the change you want to make, then open a pull request with the relevant checks completed.

## Integration

Approved Scripts treats each delegated capability as a security boundary. A new delegated action is a security-policy change, not a simple service-list addition.

### Adding an action policy

Start by copying [`capabilities/library/_template.py`](https://github.com/Lint-Free-Technology/approved-scripts/blob/main/custom_components/approved_scripts/capabilities/library/_template.py). The library discovers each non-private module's `CAPABILITY` instance, so no registry import needs updating. Shared primitives live alongside it and the registry in `canonical.py` remains responsible for sequence-wide validation.

Every new protected action must include all of the following in the same pull request:

1. A dedicated `ActionCapability` implementation in the code-defined registry. It must accept only the exact service, target forms, and data fields that have been designed for delegation.
2. Canonical snapshot and hash coverage for every value that affects execution, plus clear, specific validation errors for unsupported forms.
3. A defined template contract for each dynamic field: permitted result type, encoding, maximum size, and allowed-result validation. Do not pass raw templates to the script runner.
4. Translation keys for the action title, risk warning, labels, and errors.
5. A row in the [capability threat matrix](security/capability-matrix.md) that documents risk, boundary, and required evidence.
6. Pure validator tests and ha-testcontainer runtime tests for allowed callers, denied callers, bounded success, out-of-policy denial, trace/audit data, stale approval handling, and integration unload or reload behaviour.
7. User documentation explaining the fixed scope, allowed template values, and consequences of approving the action.

Do not introduce a broad allow-list, dynamic service name, dynamic target, or unbounded caller data as a shortcut. If an action cannot be described as a small, reviewable capability, it does not belong in delegated system-context execution.

### Testing

The test suite uses `ha-testcontainer`, following the UIX test shape. It boots a disposable Home Assistant version from `tests/HA_VERSION`, mounts this custom integration, and exercises real REST and WebSocket APIs. No browser or visual test dependency is required for this suite.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-test.txt
pytest tests/
```

Use `pytest tests/test_runtime_security.py -k stale` for one test. The VS Code tasks provide equivalent setup, full-suite, selected-test, and persistent-HA commands.

Each new capability must add tests for its validator, exact user-facing error, authorization, successful bounded execution, denied execution, trace/audit metadata, changed-script invalidation, and every allowed template-result boundary. The suite currently uses local fake MQTT and Z-Wave JS services so the real Home Assistant script and service paths can be tested without a network broker or physical lock.

The implemented registry has validator and runtime assertions for every stored protected-action descriptor and its original-script trace metadata. Protected-action UI acknowledgement still requires tests proving that every instance is presented, and that an added, removed, changed, or unsupported action cannot retain a previous approval.

## Frontend

Write frontend changes in `frontend/src/` using TypeScript targeting ES2017. Keep Home Assistant UIX patterns where they apply, including connection lifecycle handling, version and reload behaviour, backend-provided translations, Home Assistant forms and selectors, and standard dialogs.

Run the frontend checks before opening a pull request:

```sh
npm ci
npm run check:frontend
npm run build
```

The resources in `custom_components/approved_scripts/frontend/` are release artifacts. Rebuild them after changing frontend source or the integration version; do not edit them by hand.

## Documentation

The English documentation in `docs/source/` is canonical. Do not add translated Markdown copies.

Write each prose paragraph on one physical line, with one blank line between paragraphs. Keep line breaks where Markdown structure requires them, including headings, lists, tables, blockquotes, admonitions, and code blocks.

Build the site before opening a pull request:

```sh
cd docs
zensical build --clean --config-file mkdocs.yml
```

`docs/site/` and `docs/.cache/` are generated and must not be committed.
