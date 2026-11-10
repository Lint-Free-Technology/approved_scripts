---
title: Capability threat matrix
---
# Capability threat matrix

Every supported delegated action has a reviewed row here. A proposed action does not ship until its row, implementation, and security tests agree.

| Capability | Delegated operation | Dynamic data | Principal risk | Boundary and evidence |
| --- | --- | --- | --- | --- |
| `mqtt.publish.v1` | A static publish to an administrator-selected topic | `payload` only, exact scalar or JSON-object allow-list | Sending a different MQTT command | Rejects wildcard and `$` topics, targets, service indirection, and dynamic non-payload data. Template output is rendered separately, canonicalized, and matched exactly. Runtime tests prove allowed execution and denied results. |
| `zwave_js.set_lock_usercode.v1` | Set a code on one administrator-selected Z-Wave lock and slot | `usercode` only, exact non-empty string allow-list | Granting physical access or overwriting a credential | Requires exactly one literal `lock.*` target and literal integer slot. Target and slot templates are rejected. Runtime tests prove fixed-target execution and deny an unapproved rendered code. |
| Protected-action discovery | Record each registered action in a script sequence | None | A changed privileged action hiding behind an existing approval | Static registry, canonical snapshot, capability/version/path descriptors, and snapshot hash. Tests cover unsupported actions and changed-script invalidation. |

## Review questions for a new action

1. What administrator-protected or sensitive operation is being delegated?
2. Which service name, target, and data fields must be fixed? Which are necessarily dynamic?
3. For every dynamic field, what result type and finite or otherwise bounded policy is safe?
4. What physical, privacy, financial, network, or configuration impact must the administrator understand before approving it?
5. Which tests prove authorization, successful bounded execution, denied execution, trace metadata, stale invalidation, and resource cleanup?
