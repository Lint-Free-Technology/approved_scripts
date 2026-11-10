"""Library capability for a fixed Z-Wave JS lock code slot."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..base import ActionCapability
from ..common import ineligible, reject_dynamic


_DATA_KEYS = {"code_slot", "usercode"}


class ZWaveJSSetLockUsercodeCapability(ActionCapability):
    """A fixed Z-Wave lock slot with an exact approved user-code value."""

    action = "zwave_js.set_lock_usercode"
    capability_id = "zwave_js.set_lock_usercode.v1"
    title_key = "protected_action.zwave_js_set_lock_usercode.title"
    warning_key = "protected_action.zwave_js_set_lock_usercode.warning"

    def compile(
        self, action: dict[str, Any], path: str, sequence_index: int
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if action.get("metadata", {}) not in ({}, None):
            raise ineligible(
                "action_metadata_not_allowed",
                "Action metadata must be empty",
                path=path,
                capability=self.capability_id,
            )
        target = action.get("target")
        if not isinstance(target, dict) or set(target) != {"entity_id"}:
            raise ineligible(
                "fixed_lock_target_required",
                "One fixed Z-Wave lock entity target is required",
                path=f"{path}.target",
                capability=self.capability_id,
            )
        entity_id = target.get("entity_id")
        if not isinstance(entity_id, str):
            raise ineligible(
                "lock_target_required",
                "The target must be one literal lock entity ID",
                path=f"{path}.target.entity_id",
                capability=self.capability_id,
            )
        reject_dynamic(entity_id, f"{path}.target.entity_id", self.capability_id)
        if not entity_id.startswith("lock."):
            raise ineligible(
                "lock_target_required",
                "The target must be one literal lock entity ID",
                path=f"{path}.target.entity_id",
                capability=self.capability_id,
            )

        data = action.get("data")
        if not isinstance(data, dict):
            raise ineligible(
                "data_required",
                "Lock user-code data is required",
                path=f"{path}.data",
                capability=self.capability_id,
            )
        unsupported = sorted(set(data) - _DATA_KEYS)
        if unsupported:
            raise ineligible(
                "unsupported_data_field",
                f"Unsupported lock user-code data fields: {', '.join(unsupported)}",
                path=f"{path}.data",
                capability=self.capability_id,
            )
        code_slot = data.get("code_slot")
        if isinstance(code_slot, bool) or not isinstance(code_slot, int):
            raise ineligible(
                "code_slot_required",
                "A literal integer code slot is required",
                path=f"{path}.data.code_slot",
                capability=self.capability_id,
            )
        usercode = data.get("usercode")
        if not isinstance(usercode, str) or not usercode:
            raise ineligible(
                "usercode_required",
                "A literal or approved-template user code is required",
                path=f"{path}.data.usercode",
                capability=self.capability_id,
            )

        templates: list[dict[str, str]] = []
        for field, value in data.items():
            field_path = f"{path}.data.{field}"
            if isinstance(value, str) and ("{{" in value or "{%" in value):
                if field != "usercode":
                    raise ineligible(
                        "template_field_not_supported",
                        "Templates are supported only for the lock user code",
                        path=field_path,
                        capability=self.capability_id,
                    )
                templates.append({"field": field, "source": value})
                continue
            reject_dynamic(value, field_path, self.capability_id)

        clean: dict[str, Any] = {
            "action": self.action,
            "target": {"entity_id": entity_id},
            "data": deepcopy(data),
        }
        if isinstance(action.get("alias"), str):
            clean["alias"] = action["alias"]
        descriptor = self.descriptor(
            path, sequence_index, ["code_slot", "usercode"], templates
        )
        descriptor["policy_inputs"] = [
            {
                "id": f"template_{sequence_index}_{template['field']}",
                "kind": "allowed_results",
                "field": template["field"],
                "source": template["source"],
                "label_key": "protected_action.allowed_results.label",
                "description_key": "protected_action.lock_usercode_results.description",
                "value_types": ["scalar"],
                "result_encoding": "string",
                "result_type": "string",
            }
            for template in templates
        ]
        return clean, descriptor


CAPABILITY = ZWaveJSSetLockUsercodeCapability()
