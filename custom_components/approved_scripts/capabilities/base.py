"""Base type shared by all code-defined action capabilities."""

from __future__ import annotations

from typing import Any


class ActionCapability:
    """Base class for one explicitly registered protected action."""

    action = ""
    capability_id = ""
    version = 1
    title_key = ""
    warning_key = ""

    def compile(
        self, action: dict[str, Any], path: str, sequence_index: int
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Validate one action and return its snapshot form and descriptor."""
        raise NotImplementedError

    def descriptor(
        self,
        path: str,
        sequence_index: int,
        approved_fields: list[str],
        templates: list[dict[str, str]],
    ) -> dict[str, Any]:
        """Build the common persisted descriptor for an approved action."""
        return {
            "sequence_path": path,
            "sequence_index": sequence_index,
            "capability": self.capability_id,
            "capability_version": self.version,
            "action": self.action,
            "title_key": self.title_key,
            "warning_key": self.warning_key,
            "approved_fields": approved_fields,
            "templates": templates,
            "policy_inputs": [],
        }
