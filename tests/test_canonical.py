"""Security boundary tests that do not require a running Home Assistant."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType

import unittest


_PACKAGE_ROOT = Path(__file__).parents[1] / "custom_components/approved_scripts"
_PACKAGE_NAME = "approved_scripts_canonical_test"
package = ModuleType(_PACKAGE_NAME)
package.__path__ = [str(_PACKAGE_ROOT)]
sys.modules[_PACKAGE_NAME] = package
SPEC = importlib.util.spec_from_file_location(
    f"{_PACKAGE_NAME}.canonical", _PACKAGE_ROOT / "canonical.py"
)
assert SPEC and SPEC.loader
canonical = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(canonical)


class CanonicalSubsetTest(unittest.TestCase):
    def test_library_discovers_each_reviewed_capability(self) -> None:
        self.assertEqual(
            canonical.CAPABILITY_REGISTRY.actions,
            frozenset({"mqtt.publish", "zwave_js.set_lock_usercode"}),
        )

    def test_static_mqtt_snapshot_has_stable_identity(self) -> None:
        definition = {
            "alias": "Publish lounge command",
            "sequence": [{"action": "mqtt.publish", "data": {"payload": "on", "topic": "lounge/command", "qos": 1}}],
        }
        snapshot = canonical.executable_snapshot(definition)
        self.assertEqual(snapshot, {"sequence": [{"action": "mqtt.publish", "data": {"payload": "on", "topic": "lounge/command", "qos": 1}}]})
        self.assertEqual(canonical.canonical_hash(snapshot), canonical.canonical_hash(canonical.executable_snapshot(definition)))

    def test_accepts_inert_defaults_written_by_the_script_editor(self) -> None:
        definition = {
            "sequence": [
                {
                    "action": "mqtt.publish",
                    "metadata": {},
                    "data": {
                        "evaluate_payload": False,
                        "payload": "ON",
                        "qos": "0",
                        "retain": False,
                        "topic": "publish_test",
                    },
                }
            ]
        }
        self.assertEqual(
            canonical.executable_snapshot(definition),
            {
                "sequence": [
                    {
                        "action": "mqtt.publish",
                        "data": {
                            "payload": "ON",
                            "qos": "0",
                            "retain": False,
                            "topic": "publish_test",
                        },
                    }
                ]
            },
        )

    def test_registry_records_each_protected_action_instance(self) -> None:
        snapshot, protected_actions = canonical.compile_script(
            {
                "sequence": [
                    {
                        "action": "mqtt.publish",
                        "data": {"topic": "lounge/command", "payload": "on"},
                    },
                    {
                        "action": "mqtt.publish",
                        "data": {"topic": "kitchen/command", "retain": True},
                    },
                ]
            }
        )
        self.assertEqual(len(snapshot["sequence"]), 2)
        self.assertEqual(
            protected_actions,
            [
                {
                    "sequence_path": "sequence[0]",
                    "sequence_index": 0,
                    "capability": "mqtt.publish.v1",
                    "capability_version": 1,
                    "action": "mqtt.publish",
                    "title_key": "protected_action.mqtt_publish.title",
                    "warning_key": "protected_action.mqtt_publish.warning",
                    "approved_fields": ["payload", "topic"],
                    "templates": [],
                    "policy_inputs": [],
                },
                {
                    "sequence_path": "sequence[1]",
                    "sequence_index": 1,
                    "capability": "mqtt.publish.v1",
                    "capability_version": 1,
                    "action": "mqtt.publish",
                    "title_key": "protected_action.mqtt_publish.title",
                    "warning_key": "protected_action.mqtt_publish.warning",
                    "approved_fields": ["retain", "topic"],
                    "templates": [],
                    "policy_inputs": [],
                },
            ],
        )

    def test_lock_usercode_has_a_fixed_target_slot_and_template_policy(self) -> None:
        source = "{{ states('input_text.guest_code') }}"
        snapshot, actions = canonical.compile_script(
            {
                "sequence": [
                    {
                        "action": "zwave_js.set_lock_usercode",
                        "target": {"entity_id": "lock.front_door"},
                        "data": {"code_slot": 4, "usercode": source},
                    }
                ]
            }
        )
        self.assertEqual(
            snapshot["sequence"][0],
            {
                "action": "zwave_js.set_lock_usercode",
                "target": {"entity_id": "lock.front_door"},
                "data": {"code_slot": 4, "usercode": source},
            },
        )
        self.assertEqual(actions[0]["capability"], "zwave_js.set_lock_usercode.v1")
        self.assertEqual(actions[0]["templates"], [{"field": "usercode", "source": source}])
        rules = canonical.normalize_template_policy(
            actions,
            {
                "template_rules": [
                    {
                        "sequence_index": 0,
                        "field": "usercode",
                        "source": source,
                        "allowed_results": ["1234", "5678"],
                    }
                ]
            },
        )
        self.assertEqual(rules[0]["result_encoding"], "string")
        with self.assertRaises(canonical.IneligibleScript) as context:
            canonical.normalize_template_policy(
                actions,
                {
                    "template_rules": [
                        {
                            "sequence_index": 0,
                            "field": "usercode",
                            "source": source,
                            "allowed_results": [1234],
                        }
                    ]
                },
            )
        self.assertEqual(context.exception.code, "invalid_template_policy")

    def test_lock_usercode_rejects_dynamic_target_and_slot(self) -> None:
        invalid_definitions = (
            {
                "sequence": [
                    {
                        "action": "zwave_js.set_lock_usercode",
                        "target": {"entity_id": "lock.{{ states('input_text.lock') }}"},
                        "data": {"code_slot": 1, "usercode": "1234"},
                    }
                ]
            },
            {
                "sequence": [
                    {
                        "action": "zwave_js.set_lock_usercode",
                        "target": {"entity_id": "lock.front_door"},
                        "data": {"code_slot": "{{ 1 }}", "usercode": "1234"},
                    }
                ]
            },
        )
        for definition in invalid_definitions:
            with self.subTest(definition=definition), self.assertRaises(canonical.IneligibleScript):
                canonical.compile_script(definition)

    def test_unsupported_action_has_a_specific_reason(self) -> None:
        with self.assertRaises(canonical.IneligibleScript) as context:
            canonical.executable_snapshot(
                {"sequence": [{"service": "light.turn_on", "data": {}}]}
            )
        self.assertEqual(context.exception.code, "unsupported_action")
        self.assertEqual(context.exception.path, "sequence[0]")
        self.assertIn("light.turn_on", str(context.exception))

    def test_payload_template_requires_an_exact_result_allow_list(self) -> None:
        snapshot, actions = canonical.compile_script(
            {
                "sequence": [
                    {
                        "action": "mqtt.publish",
                        "data": {
                            "topic": "lounge/command",
                            "payload": "{{ states('sensor.command') }}",
                        },
                    }
                ]
            }
        )
        self.assertEqual(
            actions[0]["templates"],
            [{"field": "payload", "source": "{{ states('sensor.command') }}"}],
        )
        rules = canonical.normalize_template_policy(
            actions,
            {
                "template_rules": [
                    {
                        "sequence_index": 0,
                        "field": "payload",
                        "source": "{{ states('sensor.command') }}",
                        "allowed_results": ["off", "on"],
                    }
                ]
            },
        )
        self.assertEqual(rules[0]["allowed_results"], ["off", "on"])
        with self.assertRaises(canonical.IneligibleScript) as context:
            canonical.normalize_template_policy(actions, {"template_rules": []})
        self.assertEqual(context.exception.code, "template_policy_incomplete")
        self.assertIn("{{", snapshot["sequence"][0]["data"]["payload"])

    def test_multiple_protected_action_inputs_each_need_a_policy_rule(self) -> None:
        """A future action may expose many inputs; none can be implicitly allowed."""
        first = "{{ states('sensor.first_command') }}"
        second = "{{ states('sensor.second_command') }}"
        _, actions = canonical.compile_script(
            {
                "sequence": [
                    {
                        "action": "mqtt.publish",
                        "data": {"topic": "first/command", "payload": first},
                    },
                    {
                        "action": "mqtt.publish",
                        "data": {"topic": "second/command", "payload": second},
                    },
                ]
            }
        )
        with self.assertRaises(canonical.IneligibleScript) as context:
            canonical.normalize_template_policy(
                actions,
                {
                    "template_rules": [
                        {
                            "sequence_index": 0,
                            "field": "payload",
                            "source": first,
                            "allowed_results": ["on"],
                        }
                    ]
                },
            )
        self.assertEqual(context.exception.code, "template_policy_incomplete")
        rules = canonical.normalize_template_policy(
            actions,
            {
                "template_rules": [
                    {
                        "sequence_index": 0,
                        "field": "payload",
                        "source": first,
                        "allowed_results": ["on"],
                    },
                    {
                        "sequence_index": 1,
                        "field": "payload",
                        "source": second,
                        "allowed_results": ["off"],
                    },
                ]
            },
        )
        self.assertEqual(len(rules), 2)

    def test_v1_rejects_dynamic_or_privileged_constructs(self) -> None:
        definitions = [
        {"sequence": [{"service": "light.turn_on", "data": {}}]},
        {"sequence": [{"service": "mqtt.publish", "data": {"topic": "{{ states('input_text.topic') }}", "payload": "x"}}]},
        {"sequence": [{"service": "mqtt.publish", "data": {"topic": "$SYS/broker", "payload": "x"}}]},
        {"sequence": [{"service": "mqtt.publish", "data": {"topic": "lounge/command", "payload": "x"}, "target": {"entity_id": "x"}}]},
        {"sequence": [{"choose": []}]},
        {"sequence": [{"service": "mqtt.publish", "metadata": {"ui": "value"}, "data": {"topic": "lounge/command", "payload": "x"}}]},
        {"sequence": [{"service": "mqtt.publish", "data": {"topic": "lounge/command", "payload": "x", "evaluate_payload": True}}]},
        {"fields": {"payload": {}}, "sequence": [{"service": "mqtt.publish", "data": {"topic": "lounge/command", "payload": "x"}}]},
        ]
        for definition in definitions:
            with self.assertRaises(canonical.IneligibleScript):
                canonical.executable_snapshot(definition)
