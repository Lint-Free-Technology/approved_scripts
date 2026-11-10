"""Approved Scripts config-entry lifecycle."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import DATA_COORDINATOR, DATA_MANAGER, DOMAIN
from .coordinator import ApprovedScriptsCoordinator
from .frontend import (
    async_register_frontend_script_resource,
    async_register_admin_panel,
    async_remove_admin_panel,
    async_register_static_path,
    async_remove_frontend_script_resource,
)
from .websocket import async_register_commands

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Prepare the stable static asset and global WebSocket command surface."""
    snapshot = await async_register_static_path(hass)
    async_register_commands(hass, snapshot.version)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Activate the singleton integration from its UI-created config entry."""
    if hass.data.get(DOMAIN):
        return False

    coordinator = ApprovedScriptsCoordinator(hass, entry.entry_id)
    await coordinator.async_setup()
    hass.data[DOMAIN] = {
        DATA_COORDINATOR: coordinator,
        DATA_MANAGER: coordinator.manager,
    }
    try:
        await async_register_frontend_script_resource(hass)
        await async_register_admin_panel(hass)
    except Exception:
        hass.data.pop(DOMAIN, None)
        await coordinator.async_shutdown()
        raise
    return True


async def _async_deactivate_entry(hass: HomeAssistant) -> bool:
    """Remove entry-owned authority and browser resource registration."""
    data = hass.data.pop(DOMAIN, None)
    if isinstance(data, dict) and isinstance(
        coordinator := data.get(DATA_COORDINATOR), ApprovedScriptsCoordinator
    ):
        await coordinator.async_shutdown()
    await async_remove_frontend_script_resource(hass)
    await async_remove_admin_panel(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the active config entry without removing its persisted data."""
    return await _async_deactivate_entry(hass)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Remove the browser resource and authority state for this config entry."""
    return await _async_deactivate_entry(hass)
