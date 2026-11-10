"""Read current Core script configuration without using its live executor."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from homeassistant.core import HomeAssistant


class ScriptResolutionError(RuntimeError):
    """Core did not expose a current raw script definition."""


def _script_entity(hass: HomeAssistant, entity_id: str) -> Any:
    """Return the current ScriptEntity without using its live executor."""
    if not entity_id.startswith("script."):
        raise ScriptResolutionError("only script entities can be approved")
    component = hass.data.get("script")
    entity = component.get_entity(entity_id) if component is not None else None
    if entity is None:
        raise ScriptResolutionError("current script entity is unavailable")
    return entity


def current_definition(hass: HomeAssistant, entity_id: str) -> dict[str, Any]:
    """Synchronously copy the current ScriptEntity configuration.

    ``raw_config`` is an intentionally pinned internal Core compatibility seam.
    It is configuration data, not ``ScriptEntity.script`` / its mutable Script
    instance.  No await occurs between this copy and validation by the caller.
    """
    entity = _script_entity(hass, entity_id)
    config = getattr(entity, "raw_config", None)
    if not isinstance(config, dict):
        raise ScriptResolutionError("current raw script configuration is unavailable")
    return deepcopy(config)


def original_trace_target(
    hass: HomeAssistant, entity_id: str
) -> tuple[str, dict[str, Any]]:
    """Return the original script's trace key and retention settings.

    This deliberately returns only trace identity/settings.  Callers must still
    execute a separately validated snapshot rather than ``entity.script``.
    """
    entity = _script_entity(hass, entity_id)
    item_id = getattr(entity, "unique_id", None)
    trace_config = getattr(entity, "_trace_config", None)
    if not isinstance(item_id, str) or not item_id or not isinstance(trace_config, dict):
        raise ScriptResolutionError("original script trace configuration is unavailable")
    return item_id, deepcopy(trace_config)
