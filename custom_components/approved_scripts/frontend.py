"""Versioned in-memory frontend asset snapshot, following the UIX model."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory

from homeassistant.components.frontend import (
    add_extra_js_url,
    async_register_built_in_panel,
    async_remove_panel,
    remove_extra_js_url,
)
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant

from .const import (
    DATA_FRONTEND_SNAPSHOT,
    DOMAIN,
    FRONTEND_SCRIPT,
    FRONTEND_URL,
    PANEL_PATH,
    PANEL_SCRIPT,
    PANEL_URL,
)


@dataclass
class FrontendAssetSnapshot:
    """Built frontend assets copied outside the HACS-managed directory."""

    directory: TemporaryDirectory[str]
    version: str
    script_path: str
    panel_path: str

    def cleanup(self) -> None:
        """Remove the process-local copy when Home Assistant stops."""
        self.directory.cleanup()


def _read_version() -> str:
    manifest = Path(__file__).with_name("manifest.json")
    return str(json.loads(manifest.read_text(encoding="utf-8"))["version"])


def _create_snapshot() -> FrontendAssetSnapshot:
    """Copy JS and its pre-compressed sibling into a stable temporary location."""
    directory = TemporaryDirectory(prefix=f"{DOMAIN}-frontend-")
    try:
        paths: dict[str, str] = {}
        for script in (FRONTEND_SCRIPT, PANEL_SCRIPT):
            source = Path(__file__).parent / "frontend" / script
            destination = Path(directory.name) / script
            copyfile(source, destination)
            compressed_source = source.with_suffix(f"{source.suffix}.gz")
            if compressed_source.is_file():
                copyfile(
                    compressed_source,
                    destination.with_suffix(f"{destination.suffix}.gz"),
                )
            paths[script] = str(destination)
    except Exception:
        directory.cleanup()
        raise
    return FrontendAssetSnapshot(
        directory=directory,
        version=_read_version(),
        script_path=paths[FRONTEND_SCRIPT],
        panel_path=paths[PANEL_SCRIPT],
    )


async def async_get_frontend_snapshot(hass: HomeAssistant) -> FrontendAssetSnapshot:
    """Return the immutable frontend snapshot for this HA process."""
    if snapshot := hass.data.get(DATA_FRONTEND_SNAPSHOT):
        return snapshot

    snapshot = await hass.async_add_executor_job(_create_snapshot)
    hass.data[DATA_FRONTEND_SNAPSHOT] = snapshot

    async def _async_cleanup(_event) -> None:
        await hass.async_add_executor_job(snapshot.cleanup)

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_cleanup)
    return snapshot


async def async_register_static_path(hass: HomeAssistant) -> FrontendAssetSnapshot:
    """Serve the process-local frontend snapshot from a stable static path."""
    snapshot = await async_get_frontend_snapshot(hass)
    try:
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(FRONTEND_URL, snapshot.script_path, cache_headers=True),
                StaticPathConfig(PANEL_URL, snapshot.panel_path, cache_headers=True),
            ]
        )
    except RuntimeError:
        # Static paths intentionally survive config-entry removal/re-addition.
        pass
    return snapshot


async def async_register_frontend_script_resource(
    hass: HomeAssistant,
) -> FrontendAssetSnapshot:
    """Add the versioned frontend module while the config entry is active."""
    snapshot = await async_get_frontend_snapshot(hass)
    add_extra_js_url(hass, f"{FRONTEND_URL}?v={snapshot.version}")
    return snapshot


async def async_remove_frontend_script_resource(hass: HomeAssistant) -> None:
    """Remove the extra frontend module when the config entry is removed."""
    snapshot = hass.data.get(DATA_FRONTEND_SNAPSHOT)
    if snapshot is not None:
        remove_extra_js_url(hass, f"{FRONTEND_URL}?v={snapshot.version}")


async def async_register_admin_panel(hass: HomeAssistant) -> None:
    """Register the Browser Mod-shaped admin page while the entry is active."""
    snapshot = await async_get_frontend_snapshot(hass)
    async_remove_panel(hass, PANEL_PATH, warn_if_unknown=False)
    async_register_built_in_panel(
        hass=hass,
        component_name="custom",
        frontend_url_path=PANEL_PATH,
        require_admin=True,
        config_panel_domain=DOMAIN,
        config={
            "_panel_custom": {
                "name": "approved-scripts-panel",
                "module_url": f"{PANEL_URL}?v={snapshot.version}",
            }
        },
    )


async def async_remove_admin_panel(hass: HomeAssistant) -> None:
    """Remove the entry-owned admin page."""
    async_remove_panel(hass, PANEL_PATH, warn_if_unknown=False)
