"""Authenticated WebSocket surface for Approved Scripts."""

from __future__ import annotations

from typing import Any

import probatio

from homeassistant.components import websocket_api
from homeassistant.components.websocket_api import event_message
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.translation import async_get_translations

from .const import DATA_MANAGER, DOMAIN, EVENT_APPROVALS_UPDATED
from .manager import ApprovalError, ApprovalManager


def _error(connection: websocket_api.ActiveConnection, msg_id: int, err: Exception) -> None:
    connection.send_error(msg_id, "approved_scripts_error", str(err))


async def _async_manager_operation(hass: HomeAssistant, operation) -> Any:
    """Run an operation only while the singleton config entry is active."""
    manager = hass.data.get(DOMAIN, {}).get(DATA_MANAGER)
    if not isinstance(manager, ApprovalManager):
        raise ApprovalError("Approved Scripts is not configured")
    return await operation(manager)


async def _async_frontend_translations(
    hass: HomeAssistant, language: str
) -> dict[str, str]:
    """Load the browser strings with Home Assistant's locale fallback."""
    resources = await async_get_translations(
        hass, language, "frontend", integrations={DOMAIN}
    )
    prefix = f"component.{DOMAIN}.frontend."
    return {
        key.removeprefix(prefix): value
        for key, value in resources.items()
        if key.startswith(prefix)
    }


def async_register_commands(
    hass: HomeAssistant, frontend_version: str
) -> None:
    """Register the small, authenticated command set."""

    @websocket_api.websocket_command(
        {
            probatio.Required("type"): "approved_scripts/status",
            probatio.Required("entity_id"): str,
        }
    )
    @websocket_api.require_admin
    @callback
    def status(
        _: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        hass.async_create_task(
            _async_reply(
                connection,
                msg,
                _async_manager_operation(
                    hass, lambda manager: manager.async_status(msg["entity_id"])
                ),
            )
        )

    @websocket_api.websocket_command(
        {
            probatio.Required("type"): "approved_scripts/editor_detail",
            probatio.Required("entity_id"): str,
        }
    )
    @websocket_api.require_admin
    @callback
    def editor_detail(
        _: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        hass.async_create_task(
            _async_reply(
                connection,
                msg,
                _async_manager_operation(
                    hass,
                    lambda manager: manager.async_editor_detail(msg["entity_id"]),
                ),
            )
        )

    @websocket_api.websocket_command(
        {probatio.Required("type"): "approved_scripts/eligible_users"}
    )
    @websocket_api.require_admin
    @callback
    def eligible_users(
        _: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        hass.async_create_task(
            _async_reply(
                connection,
                msg,
                _async_manager_operation(
                    hass, lambda manager: manager.async_eligible_users()
                ),
            )
        )

    @websocket_api.websocket_command(
        {probatio.Required("type"): "approved_scripts/admin_script_list"}
    )
    @websocket_api.require_admin
    @callback
    def admin_script_list(
        _: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        hass.async_create_task(
            _async_reply(
                connection,
                msg,
                _async_manager_operation(hass, lambda manager: manager.async_admin_script_list()),
            )
        )

    @websocket_api.websocket_command(
        {
            probatio.Required("type"): "approved_scripts/frontend_translations",
            probatio.Optional("language"): str,
        }
    )
    @websocket_api.require_admin
    @websocket_api.async_response
    async def frontend_translations(
        _: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        connection.send_result(
            msg["id"],
            await _async_frontend_translations(hass, msg.get("language", "en")),
        )

    @websocket_api.websocket_command(
        {
            probatio.Required("type"): "approved_scripts/connect",
            probatio.Optional("language"): str,
        }
    )
    @websocket_api.async_response
    async def connect(
        _: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        """Subscribe a browser to immutable frontend metadata for this process."""

        @callback
        def send_approval_update(event: Any) -> None:
            """Tell connected browsers to refresh their non-authoritative routes."""
            async def push_update() -> None:
                translations = await _async_frontend_translations(
                    hass, msg.get("language", "en")
                )
                result: dict[str, Any] = {
                    "version": frontend_version,
                    "translations": translations,
                    "approvals_changed": True,
                }
                if event.data.get("script_index_changed") is True:
                    result["script_index_changed"] = True
                stale_entity_ids = event.data.get("stale_entity_ids")
                if connection.user.is_admin and isinstance(stale_entity_ids, list):
                    result["stale_entity_ids"] = [
                        entity_id
                        for entity_id in stale_entity_ids
                        if isinstance(entity_id, str)
                    ]
                connection.send_message(
                    event_message(
                        msg["id"],
                        {"result": result},
                    )
                )

            hass.async_create_task(push_update())

        connection.subscriptions[msg["id"]] = hass.bus.async_listen(
            EVENT_APPROVALS_UPDATED, send_approval_update
        )
        connection.send_result(msg["id"])
        translations = await _async_frontend_translations(
            hass, msg.get("language", "en")
        )
        connection.send_message(
            event_message(
                msg["id"],
                {"result": {"version": frontend_version, "translations": translations}},
            )
        )

    @websocket_api.websocket_command(
        {
            probatio.Required("type"): "approved_scripts/suspend",
            probatio.Required("entity_id"): str,
        }
    )
    @websocket_api.require_admin
    @callback
    def suspend(
        _: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        hass.async_create_task(
            _async_reply(
                connection,
                msg,
                _async_manager_operation(
                    hass,
                    lambda manager: manager.async_suspend(
                        msg["entity_id"], connection.user.id
                    ),
                ),
            )
        )

    @websocket_api.websocket_command(
        {
            probatio.Required("type"): "approved_scripts/approve",
            probatio.Required("entity_id"): str,
            probatio.Required("expected_hash"): str,
            probatio.Required("caller_policy"): dict,
            probatio.Required("approval_policy"): dict,
        }
    )
    @websocket_api.require_admin
    @callback
    def approve(
        _: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        hass.async_create_task(
            _async_reply(
                connection,
                msg,
                _async_manager_operation(
                    hass,
                    lambda manager: manager.async_approve(
                        msg["entity_id"],
                        msg["expected_hash"],
                        connection.user.id,
                        msg["caller_policy"],
                        msg["approval_policy"],
                    ),
                ),
            )
        )

    @websocket_api.websocket_command(
        {
            probatio.Required("type"): "approved_scripts/execute",
            probatio.Required("entity_id"): str,
        }
    )
    @callback
    def execute(
        _: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        hass.async_create_task(
            _async_reply(
                connection,
                msg,
                _async_manager_operation(
                    hass,
                    lambda manager: manager.async_execute(
                        msg["entity_id"], connection.user.id
                    ),
                ),
            )
        )

    @websocket_api.websocket_command(
        {probatio.Required("type"): "approved_scripts/routable"}
    )
    @callback
    def routable(
        _: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        hass.async_create_task(
            _async_reply(
                connection,
                msg,
                _async_manager_operation(
                    hass, lambda manager: manager.async_routable(connection.user.id)
                ),
            )
        )

    websocket_api.async_register_command(hass, status)
    websocket_api.async_register_command(hass, editor_detail)
    websocket_api.async_register_command(hass, eligible_users)
    websocket_api.async_register_command(hass, admin_script_list)
    websocket_api.async_register_command(hass, frontend_translations)
    websocket_api.async_register_command(hass, connect)
    websocket_api.async_register_command(hass, suspend)
    websocket_api.async_register_command(hass, approve)
    websocket_api.async_register_command(hass, execute)
    websocket_api.async_register_command(hass, routable)


async def _async_reply(connection: websocket_api.ActiveConnection, msg: dict[str, Any], operation: Any) -> None:
    try:
        result = await operation
    except (ApprovalError, ValueError) as err:
        _error(connection, msg["id"], err)
    except Exception:  # Don't expose Core internals to a browser.
        _error(connection, msg["id"], ApprovalError("request failed"))
        raise
    else:
        connection.send_result(msg["id"], result)
