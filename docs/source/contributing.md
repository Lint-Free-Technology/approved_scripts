---
title: Contributing action policies
---
# Contributing

Contributions are welcome. A new delegated action is a security-policy change, not a simple service-list addition.

## Documentation and test changes

Run the frontend and security checks before opening a pull request:

```sh
npm ci
npm run check:frontend
npm run build
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-test.txt
pytest tests/
```

The VS Code tasks provide matching virtual-environment, full-suite, single-test, and persistent-server commands.

## Adding an action policy

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
