"""Capability registry and canonical snapshots for delegated scripts.

This module owns sequence-wide validation, hashing, and template-policy
normalization. Individual protected action implementations live in
``capabilities/`` so each can be maintained and reviewed independently.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any

from .capabilities import ActionCapability, load_capabilities
from .capabilities.common import IneligibleScript, ineligible as _ineligible


_SAFE_TOP_LEVEL = {
    "alias",
    "description",
    "icon",
    "mode",
    "max",
    "max_exceeded",
    "trace",
    "sequence",
}
_ACTION_KEYS = {"alias", "service", "action", "target", "data", "metadata"}


class CapabilityRegistry:
    """Immutable action lookup used for every approval and execution check."""

    def __init__(self, capabilities: tuple[ActionCapability, ...]) -> None:
        self._by_action = {
            capability.action: capability for capability in capabilities
        }

    def has_action(self, action: object) -> bool:
        """Return whether an action has a registered delegated capability."""
        return isinstance(action, str) and action in self._by_action

    @property
    def actions(self) -> frozenset[str]:
        """Return the action names currently discovered from the library."""
        return frozenset(self._by_action)

    def compile_action(
        self, action: dict[str, Any], path: str, sequence_index: int
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Compile one action with the capability registered for its service."""
        if "action" in action and "service" in action:
            raise _ineligible(
                "ambiguous_action", "Use either action or service, not both", path=path
            )
        service = action.get("action", action.get("service"))
        if not isinstance(service, str) or not service:
            raise _ineligible("action_required", "An action is required", path=path)
        capability = self._by_action.get(service)
        if capability is None:
            registered = ", ".join(sorted(self._by_action))
            raise _ineligible(
                "unsupported_action",
                f"Unsupported action '{service}'. Registered delegated actions: {registered}",
                path=path,
            )
        return capability.compile(action, path, sequence_index)


# The library discovers reviewed modules. Adding a module is still a security
# change and must include its matrix entry, translations, and security tests.
CAPABILITY_REGISTRY = CapabilityRegistry(load_capabilities())


def requires_approval(definition: dict[str, Any]) -> bool:
    """Return whether a script contains a registered protected action."""
    sequence = definition.get("sequence") if isinstance(definition, dict) else None
    if not isinstance(sequence, list):
        return False
    return any(
        isinstance(action, dict)
        and CAPABILITY_REGISTRY.has_action(action.get("action", action.get("service")))
        for action in sequence
    )


def compile_script(
    definition: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Compile a definition into a literal snapshot and protected descriptors."""
    if not isinstance(definition, dict):
        raise _ineligible("definition_not_mapping", "Script definition must be a mapping")
    copied = deepcopy(definition)
    unknown = sorted(set(copied) - _SAFE_TOP_LEVEL)
    if unknown:
        raise _ineligible(
            "unsupported_script_field",
            f"Unsupported script fields: {', '.join(unknown)}",
        )
    sequence = copied.get("sequence")
    if not isinstance(sequence, list) or not sequence:
        raise _ineligible(
            "sequence_required", "A non-empty static top-level sequence is required"
        )

    clean_sequence: list[dict[str, Any]] = []
    protected_actions: list[dict[str, Any]] = []
    for index, action in enumerate(sequence):
        path = f"sequence[{index}]"
        if not isinstance(action, dict):
            raise _ineligible("action_not_mapping", "Action must be a mapping", path=path)
        unsupported = sorted(set(action) - _ACTION_KEYS)
        if unsupported:
            raise _ineligible(
                "unsupported_action_construct",
                f"Unsupported action fields: {', '.join(unsupported)}",
                path=path,
            )
        clean, descriptor = CAPABILITY_REGISTRY.compile_action(action, path, index)
        clean_sequence.append(clean)
        protected_actions.append(descriptor)
    return {"sequence": clean_sequence}, protected_actions


def executable_snapshot(definition: dict[str, Any]) -> dict[str, Any]:
    """Return only the executable portion of a registered static script."""
    snapshot, _ = compile_script(definition)
    return snapshot


def normalize_template_policy(
    protected_actions: list[dict[str, Any]], policy: dict[str, Any] | None
) -> list[dict[str, Any]]:
    """Validate the exact finite result allow-list for every template."""
    if policy is None:
        policy = {"template_rules": []}
    if set(policy) != {"template_rules"} or not isinstance(
        policy.get("template_rules"), list
    ):
        raise _ineligible("invalid_template_policy", "Template policy is malformed")
    expected = {
        (action["sequence_index"], template["field"], template["source"]): next(
            (
                policy_input
                for policy_input in action.get("policy_inputs", [])
                if policy_input.get("field") == template["field"]
                and policy_input.get("source") == template["source"]
            ),
            {},
        )
        for action in protected_actions
        for template in action.get("templates", [])
    }
    normalized: list[dict[str, Any]] = []
    for rule in policy["template_rules"]:
        required_rule_keys = {
            "sequence_index",
            "field",
            "source",
            "allowed_results",
        }
        if (
            not isinstance(rule, dict)
            or not required_rule_keys <= set(rule)
            or set(rule) - (required_rule_keys | {"result_encoding"})
        ):
            raise _ineligible(
                "invalid_template_policy", "Template policy contains an invalid rule"
            )
        key = (rule["sequence_index"], rule["field"], rule["source"])
        results = rule["allowed_results"]
        if (
            key not in expected
            or not isinstance(results, list)
            or not 1 <= len(results) <= 32
        ):
            raise _ineligible(
                "invalid_template_policy",
                "Each template needs one allow-list of up to 32 scalar or object results",
            )
        try:
            result_keys = [canonical_result(result) for result in results]
        except ValueError as err:
            raise _ineligible("invalid_template_policy", str(err)) from err
        if expected[key].get("result_type") == "string" and not all(
            isinstance(result, str) and result for result in results
        ):
            raise _ineligible(
                "invalid_template_policy",
                "This template may allow only non-empty string results",
            )
        if len(set(result_keys)) != len(results):
            raise _ineligible(
                "invalid_template_policy", "Template allowed results must be unique"
            )
        expected_encoding = expected[key].get("result_encoding", "native")
        if rule.get("result_encoding", expected_encoding) != expected_encoding:
            raise _ineligible(
                "invalid_template_policy",
                "Template result encoding does not match this action",
            )
        normalized.append(
            {
                "sequence_index": rule["sequence_index"],
                "field": rule["field"],
                "source": rule["source"],
                "allowed_results": [
                    result
                    for _, result in sorted(zip(result_keys, results, strict=True))
                ],
                "result_encoding": expected_encoding,
            }
        )
    found = {
        (rule["sequence_index"], rule["field"], rule["source"])
        for rule in normalized
    }
    if found != set(expected) or len(found) != len(normalized):
        raise _ineligible(
            "template_policy_incomplete",
            "Approve an allow-list for every template in the script",
        )
    return sorted(normalized, key=lambda rule: (rule["sequence_index"], rule["field"]))


def canonical_result(value: Any) -> str:
    """Return a bounded canonical identity for a permitted template result."""

    def validate(item: Any, depth: int = 0) -> None:
        if depth > 8:
            raise ValueError("Template result objects may be at most eight levels deep")
        if item is None or isinstance(item, (str, bool, int, float)):
            if isinstance(item, str) and (not item or len(item) > 256):
                raise ValueError(
                    "Template scalar results must be non-empty and at most 256 characters"
                )
            return
        if isinstance(item, list):
            for nested_value in item:
                validate(nested_value, depth + 1)
            return
        if isinstance(item, dict):
            for key, nested_value in item.items():
                if not isinstance(key, str):
                    raise ValueError("Template result object keys must be strings")
                validate(nested_value, depth + 1)
            return
        raise ValueError("Template results must be JSON scalars, arrays, or objects")

    validate(value)
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as err:
        raise ValueError("Template results must be finite JSON values") from err
    if len(encoded.encode()) > 2048:
        raise ValueError("Template result values may be at most 2048 bytes")
    return encoded


def canonical_hash(snapshot: dict[str, Any]) -> str:
    """Return a stable SHA-256 over a validated executable snapshot."""
    encoded = json.dumps(
        snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(encoded.encode()).hexdigest()
