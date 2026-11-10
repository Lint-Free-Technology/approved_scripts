---
title: Using Approved Scripts
---
# Using Approved Scripts

An approval lets selected non-admin users run one reviewed script snapshot in system context. The system context is parented to the caller, and the original script trace records the delegated execution and caller identity.

## The admin page

The **Approved Scripts** admin page lists every script. Its Approval column is ordered by capability state, not translated display text:

1. **Approved**;
2. actionable states: **Not approved**, **Needs review**, and **Suspended**;
3. **Approval not supported**;
4. **Approval not required**.

Only an actionable row has **Configure approval**. This avoids a table row that appears interactive but cannot do anything.

## What an administrator reviews

The approval form presents every protected action in the script. It shows the fixed action data and target, then asks for explicit policy only where a capability permits dynamic template output.

The form can be dismissed with Escape or the header close button when clean. After an edit, Home Assistant guards dismissal and **Cancel** asks whether to discard the unsaved approval changes.

## Current protected actions

### MQTT publish

`mqtt.publish` requires a literal non-system, non-wildcard topic. Its payload may be literal, or an administrator-authored template with an exact list of allowed rendered results.

### Z-Wave JS set lock user code

`zwave_js.set_lock_usercode` requires exactly one literal `lock.*` entity target and one literal integer `code_slot`. Its `usercode` may be literal, or a template whose final string is exactly one of the administrator-approved user-code values. Neither the lock target nor code slot can be templated.

!!! warning
    A lock user code grants physical access. Approve only a purpose-specific script, fixed lock, fixed slot, and a small known set of code values.

## Next up

- [Template result policies](templates.md)
- [Repairs and changed scripts](repairs.md)
