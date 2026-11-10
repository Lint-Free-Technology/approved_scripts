---
title: Template result policies
---
# Template result policies

Templates are useful when an administrator wants a script to react to current Home Assistant state. They are not an unrestricted input channel for the person running the script.

When a protected action has an approved template field, the approval form shows the original template as read-only and asks for the specific rendered results it may use. The approved values are part of the immutable approval.

## MQTT payloads

An `mqtt.publish` payload can allow scalar values or JSON objects/arrays. For example, a dashboard script may permit `on` and `off`, but not every value a sensor could emit.

## Lock user codes

`zwave_js.set_lock_usercode` permits a template only for `usercode`. The selected lock and `code_slot` remain fixed. Its policy accepts non-empty text values only, so each entry is one exact code that may be set.

## At run time

The integration renders templates before starting the cloned script. It checks the result against the saved policy and substitutes a literal value only when there is an exact match. A mismatch denies that run without changing the approval.
