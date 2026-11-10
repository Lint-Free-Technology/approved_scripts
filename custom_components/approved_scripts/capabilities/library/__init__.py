"""Self-registering library of reviewed delegated action capabilities.

Every non-private module must expose exactly one ``CAPABILITY`` instance. The
loader rejects malformed or duplicate registrations during integration setup;
an action is never selected from user configuration or a broad allow-list.
"""

from __future__ import annotations

from importlib import import_module
from pkgutil import iter_modules

from ..base import ActionCapability


def load_capabilities() -> tuple[ActionCapability, ...]:
    """Load every reviewed capability module in deterministic filename order."""
    capabilities: list[ActionCapability] = []
    for module_info in sorted(iter_modules(__path__), key=lambda item: item.name):
        if module_info.ispkg or module_info.name.startswith("_"):
            continue
        module = import_module(f"{__name__}.{module_info.name}")
        capability = getattr(module, "CAPABILITY", None)
        if not isinstance(capability, ActionCapability):
            raise RuntimeError(
                f"Capability library module {module_info.name!r} must expose CAPABILITY"
            )
        capabilities.append(capability)

    actions = [capability.action for capability in capabilities]
    capability_ids = [capability.capability_id for capability in capabilities]
    if len(set(actions)) != len(actions) or len(set(capability_ids)) != len(capability_ids):
        raise RuntimeError("Capability library contains duplicate action registrations")
    return tuple(capabilities)
