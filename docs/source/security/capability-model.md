---
title: Capability model
---
# Capability model

Approved Scripts delegates a small set of explicitly designed operations. It does not infer that a Home Assistant action is safe because the action is not currently administrator-protected. Every action is either implemented in its own `capabilities/library/` module and discovered by the code-defined registry, or unsupported.

## Current capabilities

| Capability | What is fixed in the approval | Permitted dynamic value |
| --- | --- | --- |
| `mqtt.publish.v1` | Topic, QoS, retain flag, encoding, and all other data | `payload`, limited to an exact approved result list |
| `zwave_js.set_lock_usercode.v1` | One `lock.*` target and integer `code_slot` | `usercode`, limited to exact approved non-empty strings |

The Z-Wave JS service is administrator-protected by Home Assistant. Its capability is deliberately narrow: a delegated user cannot select a different lock, code slot, service, or template any of those values.

## Approval scope

The parser walks the top-level script sequence and builds an ordered, canonical snapshot. It records every protected action instance with its sequence position, capability version, fixed fields, template source, and template policy inputs.

An administrator approves the complete snapshot, not selected lines of a live script. A changed, added, removed, or reordered action changes the snapshot hash and pauses the approval. The administrator must explicitly reapprove the new revision; ignoring the resulting Repair intentionally leaves it blocked.

Unknown actions do not become delegated actions. They retain Home Assistant's normal user-context authorization and cannot be included in a snapshot.

## Templates: output is the boundary

An approved action may opt a specific field into template support. Any valid Home Assistant template syntax can be used in that field; security is based on what it renders, not on trying to restrict template syntax.

Before each run, Approved Scripts renders each template separately, validates the result against the administrator's exact allow-list, replaces it with a literal, then validates and runs that fresh snapshot. Raw Jinja is never given to the script runner.

For example, this user-code template is permitted only if it resolves to one of the strings approved for the fixed lock and slot:

```jinja
{{ states("input_text.guest_code") }}
```

A render error, a type mismatch, or a value outside the allow-list stops the run and is recorded as a denied execution. It never falls back to the live script or widens the approval.

## Caller inputs and audit

Caller-supplied service data is not forwarded to delegated snapshots. This prevents a dashboard caller from changing approved data or targets.

Browser-originated approvals record the approving administrator. Config and Repair flows record `SYSTEM`: Home Assistant has applied its normal admin authorization, but custom integrations are not given the initiating user ID in those flows. Each original script trace includes the caller user ID and name, the snapshot execution marker, protected-action descriptors, and template policy.

## Permanent exclusions

The following are not configurable policies and cannot be enabled by an administrator:

- `script.*` and `automation.*` execution or mutation;
- shell commands, command-line integrations, and process execution;
- configuration, authentication, user, permission, update, backup, restart, reload, or supervisor operations;
- generic HTTP or arbitrary network requests;
- dynamic service names, dynamic targets, nested scripts, and raw Jinja in the script runner.

A future exception needs a dedicated capability, threat-matrix row, translation strings, and validation plus runtime tests before it can be released.
