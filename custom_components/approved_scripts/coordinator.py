"""Integration lifecycle coordinator, mirroring UIX's asset ownership model."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from .frontend import FrontendAssetSnapshot, async_get_frontend_snapshot
from .manager import ApprovalManager


class ApprovedScriptsCoordinator:
    """Own the backend manager and immutable frontend snapshot for one process."""

    def __init__(self, hass: HomeAssistant, config_entry_id: str) -> None:
        self.hass = hass
        self.manager = ApprovalManager(hass, config_entry_id)
        self.frontend: FrontendAssetSnapshot | None = None

    async def async_setup(self) -> None:
        """Load authority state and capture the process-local frontend version."""
        await self.manager.async_load()
        self.frontend = await async_get_frontend_snapshot(self.hass)
        await self.manager.async_start_monitoring()

    async def async_shutdown(self) -> None:
        """Stop background approval reconciliation before unloading."""
        await self.manager.async_stop_monitoring()

    @property
    def frontend_version(self) -> str:
        if self.frontend is None:
            raise RuntimeError("frontend snapshot has not been initialized")
        return self.frontend.version
