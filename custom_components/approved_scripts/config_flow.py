"""Config flow for Approved Scripts."""

from __future__ import annotations

from typing import Any

import probatio

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    ObjectSelector,
    ObjectSelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
)

from .canonical import IneligibleScript
from .const import DATA_MANAGER, DOMAIN, NAME, SYSTEM_AUTHORIZER
from .manager import ApprovalError, ApprovalManager
from .resolver import ScriptResolutionError


class ApprovedScriptsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create the singleton Approved Scripts config entry."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Expose approval management from the integration settings cog."""
        return ApprovedScriptsOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Set up Approved Scripts from the integrations UI."""
        if self._async_current_entries() or self.hass.data.get(DOMAIN):
            return self.async_abort(reason="single_instance_allowed")
        return self.async_create_entry(
            title=NAME,
            data={},
            description="refresh_message",
        )


class ApprovedScriptsOptionsFlow(OptionsFlow):
    """Manage persisted script approvals without storing them in entry options."""

    def __init__(self) -> None:
        self._entity_id: str | None = None
        self._adding = False
        self._templates: list[dict[str, Any]] = []
        self._pending_approval_input: dict[str, Any] | None = None
        self._template_rules: list[dict[str, Any]] = []
        self._template_index = 0

    @property
    def _manager(self) -> ApprovalManager | None:
        manager = self.hass.data.get(DOMAIN, {}).get(DATA_MANAGER)
        return manager if isinstance(manager, ApprovalManager) else None

    @staticmethod
    def _approval_error_key(error: Exception) -> str:
        """Map safe backend validation errors to localized form errors."""
        if isinstance(error, IneligibleScript):
            return "script_ineligible"
        if isinstance(error, ScriptResolutionError):
            return "script_unavailable"
        if isinstance(error, ApprovalError):
            return error.code
        return "approval_failed"

    def _script_label(self, entity_id: str) -> str:
        state = self.hass.states.get(entity_id)
        friendly_name = state.attributes.get("friendly_name") if state else None
        if isinstance(friendly_name, str) and friendly_name:
            return f"{friendly_name} ({entity_id})"
        return entity_id

    async def _async_approval_selector(self) -> SelectSelector | None:
        if (manager := self._manager) is None:
            return None
        entity_ids = await manager.async_approval_entity_ids()
        return SelectSelector(
            SelectSelectorConfig(
                options=[
                    {"value": entity_id, "label": self._script_label(entity_id)}
                    for entity_id in entity_ids
                ]
            )
        )

    async def _async_policy_schema(
        self,
        enabled: bool,
        allowed_user_ids: list[str],
        _: dict[str, Any] | None,
    ) -> probatio.Schema:
        """Return the shared approval form used by Add and Edit."""
        assert (manager := self._manager) is not None
        eligible_users = await manager.async_eligible_users()
        eligible_ids = {user["id"] for user in eligible_users}
        fields: dict[Any, Any] = {
                probatio.Required("enabled", default=enabled): BooleanSelector(),
                probatio.Required(
                    "allowed_user_ids",
                    default=[user_id for user_id in allowed_user_ids if user_id in eligible_ids],
                ): SelectSelector(
                    SelectSelectorConfig(
                        multiple=True,
                        options=[
                            {"value": user["id"], "label": user["name"]}
                            for user in eligible_users
                        ],
                    )
                ),
            }
        return probatio.Schema(fields)

    async def _async_save_pending_approval(self) -> ConfigFlowResult:
        """Persist the completed action policies through the same manager path."""
        assert self._entity_id is not None
        assert self._pending_approval_input is not None
        assert (manager := self._manager) is not None
        try:
            detail = await manager.async_editor_detail(self._entity_id)
            await manager.async_approve(
                self._entity_id,
                detail["hash"],
                SYSTEM_AUTHORIZER,
                {"allowed_user_ids": self._pending_approval_input["allowed_user_ids"]},
                {
                    "protected_actions_acknowledged": True,
                    "template_policy": {"template_rules": self._template_rules},
                },
            )
        except (ApprovalError, IneligibleScript, ScriptResolutionError, ValueError) as err:
            return await self._async_show_policy_form({"base": self._approval_error_key(err)})
        return self.async_create_entry(title="", data=self.config_entry.options)

    async def _async_show_policy_form(
        self, errors: dict[str, str] | None = None
    ) -> ConfigFlowResult:
        if self._entity_id is None:
            return self.async_abort(reason="no_script_selected")
        if (manager := self._manager) is None:
            return self.async_abort(reason="not_configured")
        status = await manager.async_status(self._entity_id)
        record = status.get("approval") or {}
        policy = record.get("caller_policy") or {}
        try:
            detail = await manager.async_editor_detail(self._entity_id)
        except (ApprovalError, IneligibleScript, ScriptResolutionError):
            return self.async_abort(reason="script_unavailable")
        self._templates = [
            {
                "sequence_index": action["sequence_index"],
                "action_title": action["action"],
                "field": template["field"],
                "source": template["source"],
            }
            for action in detail["protected_actions"]
            for template in action.get("templates", [])
        ]
        return self.async_show_form(
            step_id="configure_script_approval",
            data_schema=await self._async_policy_schema(
                status.get("approved") is True,
                list(policy.get("allowed_user_ids") or []),
                record.get("template_policy"),
            ),
            errors=errors or {},
            description_placeholders={
                "script_name": self._script_label(self._entity_id)
            },
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Keep Config Flow for setup; management lives in the admin panel."""
        return self.async_abort(reason="manage_in_admin_panel")

    async def async_step_manage_script_approvals(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the approval-management actions."""
        return self.async_show_menu(
            step_id="manage_script_approvals",
            menu_options=[
                "add_script_approval",
                "edit_script_approval",
                "remove_script_approval",
            ],
        )

    async def async_step_add_script_approval(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select one script before configuring its approval policy."""
        if (manager := self._manager) is None:
            return self.async_abort(reason="not_configured")
        existing = await manager.async_approval_entity_ids()
        if user_input is not None:
            entity_id = user_input["entity_id"]
            if entity_id in existing:
                return self.async_show_form(
                    step_id="add_script_approval",
                    data_schema=probatio.Schema(
                        {
                            probatio.Required("entity_id"): EntitySelector(
                                EntitySelectorConfig(
                                    domain="script",
                                    multiple=False,
                                    exclude_entities=existing,
                                )
                            )
                        }
                    ),
                    errors={"base": "already_approved"},
                )
            self._entity_id = entity_id
            self._adding = True
            return await self.async_step_configure_script_approval()
        return self.async_show_form(
            step_id="add_script_approval",
            data_schema=probatio.Schema(
                {
                    probatio.Required("entity_id"): EntitySelector(
                        EntitySelectorConfig(
                            domain="script",
                            multiple=False,
                            exclude_entities=existing,
                        )
                    )
                }
            ),
        )

    async def async_step_edit_script_approval(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select an existing approval to edit."""
        if (selector := await self._async_approval_selector()) is None:
            return self.async_abort(reason="not_configured")
        if not selector.config["options"]:
            return self.async_abort(reason="no_script_approvals")
        if user_input is not None:
            self._entity_id = user_input["entity_id"]
            self._adding = False
            return await self.async_step_configure_script_approval()
        return self.async_show_form(
            step_id="edit_script_approval",
            data_schema=probatio.Schema({probatio.Required("entity_id"): selector}),
        )

    async def async_step_configure_script_approval(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Apply the shared enabled/users approval form."""
        if user_input is None:
            return await self._async_show_policy_form()
        if self._entity_id is None or (manager := self._manager) is None:
            return self.async_abort(reason="not_configured")
        enabled = user_input["enabled"] is True
        if self._adding and not enabled:
            return await self._async_show_policy_form({"base": "new_approval_must_be_enabled"})
        try:
            if enabled:
                self._pending_approval_input = user_input
                self._template_rules = []
                self._template_index = 0
                if self._templates:
                    return await self.async_step_configure_protected_action()
                return await self._async_save_pending_approval()
            else:
                await manager.async_suspend(self._entity_id, SYSTEM_AUTHORIZER)
        except (ApprovalError, IneligibleScript, ScriptResolutionError, ValueError) as err:
            return await self._async_show_policy_form(
                {"base": self._approval_error_key(err)}
            )
        return self.async_create_entry(title="", data=self.config_entry.options)

    async def async_step_configure_protected_action(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the saved template before its result policy is configured."""
        template = self._templates[self._template_index]
        if user_input is None:
            return self.async_show_form(
                step_id="configure_protected_action",
                data_schema=probatio.Schema(
                    {
                        probatio.Optional(
                            "template_source", default=template["source"]
                        ): TextSelector(TextSelectorConfig(multiline=True))
                    }
                ),
                description_placeholders={"action_title": template["action_title"]},
            )
        return await self.async_step_manage_protected_action()

    async def async_step_manage_protected_action(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add typed values for one server-described protected-action input."""
        template = self._templates[self._template_index]
        values = [
            repr(value)
            for rule in self._template_rules
            if rule["sequence_index"] == template["sequence_index"]
            and rule["field"] == template["field"]
            for value in rule["allowed_results"]
        ]
        return self.async_show_menu(
            step_id="manage_protected_action",
            menu_options=["add_scalar_result", "add_object_result", "finish_protected_action"],
            description_placeholders={
                "action_title": template["action_title"],
                "allowed_results": ", ".join(values) or "None yet",
            },
        )

    async def async_step_add_scalar_result(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._add_template_result(user_input["result"])
            return await self.async_step_manage_protected_action()
        return self.async_show_form(
            step_id="add_scalar_result",
            data_schema=probatio.Schema(
                {probatio.Required("result"): TextSelector(TextSelectorConfig())}
            ),
        )

    async def async_step_add_object_result(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._add_template_result(user_input["result"])
            return await self.async_step_manage_protected_action()
        return self.async_show_form(
            step_id="add_object_result",
            data_schema=probatio.Schema(
                {probatio.Required("result"): ObjectSelector(ObjectSelectorConfig())}
            ),
        )

    def _add_template_result(self, result: Any) -> None:
        template = self._templates[self._template_index]
        rule = next(
            (
                item
                for item in self._template_rules
                if item["sequence_index"] == template["sequence_index"]
                and item["field"] == template["field"]
            ),
            None,
        )
        if rule is None:
            rule = {**template, "allowed_results": []}
            rule.pop("action_title", None)
            self._template_rules.append(rule)
        rule["allowed_results"].append(result)

    async def async_step_finish_protected_action(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        template = self._templates[self._template_index]
        if not any(
            rule["sequence_index"] == template["sequence_index"]
            and rule["field"] == template["field"]
            and rule["allowed_results"]
            for rule in self._template_rules
        ):
            return await self.async_step_add_scalar_result()
        self._template_index += 1
        if self._template_index < len(self._templates):
            return await self.async_step_configure_protected_action()
        return await self._async_save_pending_approval()

    async def async_step_remove_script_approval(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Remove one persisted approval record."""
        if (selector := await self._async_approval_selector()) is None:
            return self.async_abort(reason="not_configured")
        if not selector.config["options"]:
            return self.async_abort(reason="no_script_approvals")
        if user_input is not None:
            assert (manager := self._manager) is not None
            try:
                await manager.async_remove(user_input["entity_id"], SYSTEM_AUTHORIZER)
            except ApprovalError:
                return self.async_show_form(
                    step_id="remove_script_approval",
                    data_schema=probatio.Schema({probatio.Required("entity_id"): selector}),
                    errors={"base": "approval_failed"},
                )
            return self.async_create_entry(title="", data=self.config_entry.options)
        return self.async_show_form(
            step_id="remove_script_approval",
            data_schema=probatio.Schema({probatio.Required("entity_id"): selector}),
        )
