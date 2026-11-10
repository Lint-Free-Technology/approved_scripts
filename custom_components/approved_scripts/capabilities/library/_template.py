"""Copy this library file when designing a new delegated action capability.

The leading underscore keeps this scaffold out of the registry. Do not add a
capability to ``capabilities/__init__.py`` until its threat-matrix row,
translations, and pure plus runtime security tests are ready in the same
change.
"""

from __future__ import annotations

from typing import Any

from ..base import ActionCapability
from ..common import ineligible


class ExampleActionCapability(ActionCapability):
    """Example only: replace every value with a deliberately bounded design."""

    action = "example.action"
    capability_id = "example.action.v1"
    title_key = "protected_action.example.title"
    warning_key = "protected_action.example.warning"

    def compile(
        self, action: dict[str, Any], path: str, sequence_index: int
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Validate every execution-relevant field and return a literal snapshot."""
        # 1. Require the exact target shape and use ``reject_dynamic`` for all
        # static values. Do not accept wildcard or generic service targets.
        # 2. Allow-list data keys and validate types, ranges, and fixed scope.
        # 3. For an intentionally dynamic field, create a policy input below;
        #    raw templates must never reach Home Assistant's Script runner.
        raise ineligible(
            "not_implemented",
            "This is a capability template and cannot be used",
            path=path,
            capability=self.capability_id,
        )

    def template_policy_input(
        self, field: str, source: str, sequence_index: int
    ) -> dict[str, Any]:
        """Example shape for a separately rendered, bounded template field."""
        return {
            "id": f"template_{sequence_index}_{field}",
            "kind": "allowed_results",
            "field": field,
            "source": source,
            "label_key": "protected_action.allowed_results.label",
            "description_key": "protected_action.example_results.description",
            "value_types": ["scalar"],
            "result_encoding": "string",
            "result_type": "string",
        }
