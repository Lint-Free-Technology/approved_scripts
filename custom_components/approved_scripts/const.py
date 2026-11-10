"""Constants for Approved Scripts."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "approved_scripts"
NAME: Final = "Approved Scripts"
STORAGE_KEY: Final = f"{DOMAIN}.approvals"
STORAGE_VERSION: Final = 1
VALIDATION_VERSION: Final = 1
DATA_MANAGER: Final = "manager"
DATA_COORDINATOR: Final = "coordinator"
DATA_FRONTEND_SNAPSHOT: Final = f"{DOMAIN}_frontend_snapshot"
EVENT_APPROVALS_UPDATED: Final = f"{DOMAIN}_approvals_updated"
FRONTEND_SCRIPT: Final = "approved-scripts.js"
FRONTEND_URL: Final = f"/{DOMAIN}/{FRONTEND_SCRIPT}"
PANEL_SCRIPT: Final = "approved-scripts-panel.js"
PANEL_URL: Final = f"/{DOMAIN}/{PANEL_SCRIPT}"
PANEL_PATH: Final = "approved-scripts"

# Snapshot instances deliberately have their own limit.  Do not inherit a live
# ScriptEntity's mode/max: that would require executing the mutable entity.
MAX_CONCURRENT_RUNS: Final = 4
MAX_AUDIT_RECORDS: Final = 200

# Home Assistant's Options and Repairs APIs authorize the flow before invoking
# a custom integration, but do not expose the initiating administrator to it.
SYSTEM_AUTHORIZER: Final = "SYSTEM"
