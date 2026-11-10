"""Test-only local zwave_js.set_lock_usercode service for runtime coverage."""

from __future__ import annotations

from homeassistant.core import HomeAssistant, ServiceCall


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register a bounded observable stand-in for the Core admin-only service."""

    async def async_set_lock_usercode(call: ServiceCall) -> None:
        hass.states.async_set(
            "sensor.approved_scripts_test_lock_usercode",
            str(call.data["usercode"]),
            {
                "code_slot": call.data["code_slot"],
                "entity_id": call.data["entity_id"],
            },
            context=call.context,
        )

    hass.services.async_register("zwave_js", "set_lock_usercode", async_set_lock_usercode)
    return True
