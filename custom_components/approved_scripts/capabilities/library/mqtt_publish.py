"""Library capability for a bounded MQTT publish."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..base import ActionCapability
from ..common import ineligible, reject_dynamic


_DATA_KEYS = {"topic", "payload", "qos", "retain", "encoding", "evaluate_payload"}


class MqttPublishCapability(ActionCapability):
    """A literal MQTT publish with an optional bounded payload template."""

    action = "mqtt.publish"
    capability_id = "mqtt.publish.v1"
    title_key = "protected_action.mqtt_publish.title"
    warning_key = "protected_action.mqtt_publish.warning"

    def compile(
        self, action: dict[str, Any], path: str, sequence_index: int
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if action.get("target") not in (None, {}):
            raise ineligible(
                "target_not_allowed",
                "MQTT publish does not support a service target",
                path=f"{path}.target",
                capability=self.capability_id,
            )
        if action.get("metadata", {}) not in ({}, None):
            raise ineligible(
                "action_metadata_not_allowed",
                "Action metadata must be empty",
                path=path,
                capability=self.capability_id,
            )
        data = action.get("data")
        if not isinstance(data, dict) or not data:
            raise ineligible(
                "data_required",
                "Literal MQTT data is required",
                path=path,
                capability=self.capability_id,
            )
        unsupported = sorted(set(data) - _DATA_KEYS)
        if unsupported:
            raise ineligible(
                "unsupported_data_field",
                f"Unsupported MQTT data fields: {', '.join(unsupported)}",
                path=f"{path}.data",
                capability=self.capability_id,
            )
        topic = data.get("topic")
        if not isinstance(topic, str) or not topic:
            raise ineligible(
                "topic_required",
                "A literal MQTT topic is required",
                path=f"{path}.data.topic",
                capability=self.capability_id,
            )
        if topic.startswith("$") or "+" in topic or "#" in topic:
            raise ineligible(
                "privileged_or_wildcard_topic",
                "MQTT system and wildcard topics are not allowed",
                path=f"{path}.data.topic",
                capability=self.capability_id,
            )

        templates: list[dict[str, str]] = []
        for field, value in data.items():
            field_path = f"{path}.data.{field}"
            if isinstance(value, str) and ("{{" in value or "{%" in value):
                if field != "payload":
                    raise ineligible(
                        "template_field_not_supported",
                        "Templates are supported only for MQTT payload",
                        path=field_path,
                        capability=self.capability_id,
                    )
                templates.append({"field": field, "source": value})
                continue
            reject_dynamic(value, field_path, self.capability_id)
        if data.get("evaluate_payload", False) is not False:
            raise ineligible(
                "payload_evaluation_not_allowed",
                "MQTT payload evaluation is not allowed",
                path=f"{path}.data.evaluate_payload",
                capability=self.capability_id,
            )

        clean_data = deepcopy(data)
        clean_data.pop("evaluate_payload", None)
        clean: dict[str, Any] = {"action": self.action, "data": clean_data}
        if isinstance(action.get("alias"), str):
            clean["alias"] = action["alias"]
        descriptor = self.descriptor(path, sequence_index, sorted(clean_data), templates)
        descriptor["policy_inputs"] = [
            {
                "id": f"template_{sequence_index}_{template['field']}",
                "kind": "allowed_results",
                "field": template["field"],
                "source": template["source"],
                "label_key": "protected_action.allowed_results.label",
                "description_key": "protected_action.allowed_results.description",
                "value_types": ["scalar", "object"],
                "result_encoding": "json_text",
            }
            for template in templates
        ]
        return clean, descriptor


CAPABILITY = MqttPublishCapability()
