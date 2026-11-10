"""Shared validation primitives for delegated action capabilities."""

from __future__ import annotations

from typing import Any


class IneligibleScript(ValueError):
    """A definition falls outside a registered delegated capability."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "ineligible_script",
        path: str | None = None,
        capability: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.path = path
        self.capability = capability


def ineligible(
    code: str,
    message: str,
    *,
    path: str | None = None,
    capability: str | None = None,
) -> IneligibleScript:
    """Build a consistent, administrator-facing validation error."""
    location = f" at {path}" if path else ""
    capability_name = f" by the {capability} capability" if capability else ""
    return IneligibleScript(
        f"{message}{location}{capability_name}",
        code=code,
        path=path,
        capability=capability,
    )


def reject_dynamic(value: Any, path: str, capability: str) -> None:
    """Reject templates and non-JSON values in a static capability field."""
    if isinstance(value, str):
        if "{{" in value or "{%" in value:
            raise ineligible(
                "template_not_allowed",
                "Templates are not allowed",
                path=path,
                capability=capability,
            )
        return
    if value is None or isinstance(value, (bool, int, float)):
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            reject_dynamic(item, f"{path}[{index}]", capability)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ineligible(
                    "non_string_key",
                    "Data keys must be strings",
                    path=path,
                    capability=capability,
                )
            reject_dynamic(item, f"{path}.{key}", capability)
        return
    raise ineligible(
        "non_literal_value",
        "Only literal JSON values are allowed",
        path=path,
        capability=capability,
    )
