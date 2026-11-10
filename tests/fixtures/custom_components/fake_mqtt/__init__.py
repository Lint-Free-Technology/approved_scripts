"""Test-only local mqtt.publish service for Approved Scripts runtime tests."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Expose a harmless observable replacement for a broker-backed publish."""

    async def async_publish(call: ServiceCall) -> None:
        hass.states.async_set(
            "sensor.approved_scripts_test_mqtt",
            str(call.data["topic"]),
            {"payload": call.data.get("payload")},
            context=call.context,
        )

    hass.services.async_register("mqtt", "publish", async_publish)
    return True
