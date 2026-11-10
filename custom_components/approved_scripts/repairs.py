"""Repair flow for explicitly reviewing a stale script approval."""

from __future__ import annotations

from typing import Any

import probatio

from homeassistant.components.repairs import RepairsFlow, RepairsFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.selector import (
    BooleanSelector,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
)

from .canonical import IneligibleScript
from .const import DATA_MANAGER, DOMAIN, SYSTEM_AUTHORIZER
from .manager import ApprovalError, ApprovalManager
from .resolver import ScriptResolutionError


class StaleApprovalRepairFlow(RepairsFlow):
    """Require an explicit administrator review before a new approval."""

    def __init__(self, hass: HomeAssistant, entity_id: str) -> None:
        self._hass = hass
        self._entity_id = entity_id
        self._templates: list[dict[str, Any]] = []

    @property
    def _manager(self) -> ApprovalManager | None:
        manager = self._hass.data.get(DOMAIN, {}).get(DATA_MANAGER)
        return manager if isinstance(manager, ApprovalManager) else None

    def _script_name(self) -> str:
        state = self._hass.states.get(self._entity_id)
        name = state.attributes.get("friendly_name") if state else None
        return str(name) if isinstance(name, str) and name else self._entity_id

    async def _async_show_reapprove_form(
        self, errors: dict[str, str] | None = None
    ) -> RepairsFlowResult:
        if (manager := self._manager) is None:
            return self.async_abort(reason="not_configured")
        status = await manager.async_status(self._entity_id)
        record = status.get("approval")
        if not isinstance(record, dict) or record.get("state") != "stale":
            return self.async_abort(reason="already_repaired")
        eligible_users = await manager.async_eligible_users()
        eligible_ids = {user["id"] for user in eligible_users}
        selected = [
            user_id
            for user_id in record.get("caller_policy", {}).get("allowed_user_ids", [])
            if user_id in eligible_ids
        ]
        try:
            detail = await manager.async_editor_detail(self._entity_id)
        except (ApprovalError, IneligibleScript, ScriptResolutionError):
            return await self._async_show_reapprove_blocked("script_unavailable")
        self._templates = [
            {
                "sequence_index": action["sequence_index"],
                "field": template["field"],
                "source": template["source"],
            }
            for action in detail["protected_actions"]
            for template in action.get("templates", [])
        ]
        existing_rules = record.get("template_policy", {}).get("template_rules", [])
        fields: dict[Any, Any] = {
            probatio.Required("allowed_user_ids", default=selected): SelectSelector(
                SelectSelectorConfig(
                    multiple=True,
                    options=[
                        {"value": user["id"], "label": user["name"]}
                        for user in eligible_users
                    ],
                )
            ),
            probatio.Required("protected_actions_acknowledged", default=False): BooleanSelector(),
        }
        for index, template in enumerate(self._templates):
            saved = next(
                (
                    rule.get("allowed_results", [])
                    for rule in existing_rules
                    if rule.get("sequence_index") == template["sequence_index"]
                    and rule.get("field") == template["field"]
                    and rule.get("source") == template["source"]
                ),
                [],
            )
            fields[probatio.Required(
                f"template_results_{index}", default="\n".join(saved)
            )] = TextSelector(TextSelectorConfig(multiline=True))
        return self.async_show_form(
            step_id="reapprove",
            data_schema=probatio.Schema(fields),
            errors=errors or {},
            description_placeholders={"script_name": self._script_name()},
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> RepairsFlowResult:
        """Offer an explicit choice between reapproval and leaving it paused."""
        if (manager := self._manager) is None:
            return self.async_abort(reason="not_configured")
        status = await manager.async_status(self._entity_id)
        record = status.get("approval")
        if not isinstance(record, dict) or record.get("state") != "stale":
            return self.async_abort(reason="already_repaired")
        return self.async_show_menu(
            step_id="init",
            menu_options=["reapprove", "ignore"],
            description_placeholders={"script_name": self._script_name()},
        )

    async def _async_show_reapprove_blocked(
        self, reason: str
    ) -> RepairsFlowResult:
        """Return a failed reapproval to a menu which can leave it paused.

        A ConfigFlow form error has no secondary action. Returning to this
        menu makes the intentional "Leave unapproved" decision available at
        the point the administrator learns that reapproval cannot succeed.
        """
        return self.async_show_menu(
            step_id="reapprove_blocked",
            menu_options=["reapprove", "ignore"],
            description_placeholders={
                "script_name": self._script_name(),
                "reason": reason,
            },
        )

    async def async_step_reapprove(
        self, user_input: dict[str, Any] | None = None
    ) -> RepairsFlowResult:
        """Reapprove only the current static revision after administrator review."""
        if user_input is None:
            return await self._async_show_reapprove_form()
        if (manager := self._manager) is None:
            return self.async_abort(reason="not_configured")
        try:
            await manager.async_reapprove_current(
                self._entity_id,
                SYSTEM_AUTHORIZER,
                {"allowed_user_ids": user_input["allowed_user_ids"]},
                {
                    "protected_actions_acknowledged": user_input[
                        "protected_actions_acknowledged"
                    ] is True,
                    "template_policy": {
                        "template_rules": [
                            {
                                **template,
                                "allowed_results": [
                                    value.strip()
                                    for value in str(
                                        user_input.get(f"template_results_{index}", "")
                                    ).splitlines()
                                    if value.strip()
                                ],
                            }
                            for index, template in enumerate(self._templates)
                        ]
                    },
                },
            )
        except IneligibleScript:
            return await self._async_show_reapprove_blocked("script_ineligible")
        except ScriptResolutionError:
            return await self._async_show_reapprove_blocked("script_unavailable")
        except ApprovalError as err:
            if err.code in {"script_unavailable", "script_changed"}:
                return await self._async_show_reapprove_blocked(err.code)
            return await self._async_show_reapprove_form({"base": err.code})
        except ValueError:
            return await self._async_show_reapprove_form({"base": "approval_failed"})
        return self.async_create_entry(data={})

    async def async_step_ignore(
        self, user_input: dict[str, Any] | None = None
    ) -> RepairsFlowResult:
        """Keep the approval stale, but stop surfacing this Repair revision."""
        if ir.async_get(self._hass).async_get_issue(DOMAIN, self.issue_id) is not None:
            ir.async_ignore_issue(self._hass, DOMAIN, self.issue_id, ignore=True)
        return self.async_abort(reason="issue_ignored")


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Create the standard Repairs flow for one stale approval."""
    assert issue_id.startswith("stale_approval_")
    assert data and isinstance(entity_id := data.get("entity_id"), str)
    return StaleApprovalRepairFlow(hass, entity_id)
