"""End-to-end security tests against a real Home Assistant test container."""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import urlencode

import pytest
import requests
import websocket


SCRIPT_PREFIX = "approved_security"


def _ws_call(url: str, token: str, command: dict[str, Any]) -> dict[str, Any]:
    """Send one authenticated WebSocket command and return its matching reply."""
    ws = websocket.create_connection(url.replace("http://", "ws://") + "/api/websocket", timeout=20)
    try:
        assert json.loads(ws.recv())["type"] == "auth_required"
        ws.send(json.dumps({"type": "auth", "access_token": token}))
        assert json.loads(ws.recv())["type"] == "auth_ok"
        ws.send(json.dumps(command))
        while True:
            reply = json.loads(ws.recv())
            if reply.get("id") == command["id"]:
                return reply
    finally:
        ws.close()


def _admin_call(ha: Any, command_type: str, **data: Any) -> dict[str, Any]:
    return _ws_call(ha.get_url(), ha.get_token(), {"id": 1, "type": command_type, **data})


def _create_user_token(ha: Any, username: str) -> tuple[str, str]:
    """Create a real non-admin user and exchange credentials for an API token."""
    password = f"{username}-password"
    created = _admin_call(ha, "config/auth/create", name=username)
    assert created["success"] is True
    user_id = created["result"]["user"]["id"]
    credentials = _admin_call(
        ha,
        "config/auth_provider/homeassistant/create",
        user_id=user_id,
        username=username,
        password=password,
    )
    assert credentials["success"] is True

    client_id = f"{ha.get_url()}/"
    flow = requests.post(
        f"{ha.get_url()}/auth/login_flow",
        json={"client_id": client_id, "handler": ["homeassistant", None], "redirect_uri": client_id},
        timeout=20,
    )
    flow.raise_for_status()
    complete = requests.post(
        f"{ha.get_url()}/auth/login_flow/{flow.json()['flow_id']}",
        json={"client_id": client_id, "username": username, "password": password},
        timeout=20,
    )
    complete.raise_for_status()
    code = complete.json()["result"]
    token = requests.post(
        f"{ha.get_url()}/auth/token",
        data=urlencode({"client_id": client_id, "grant_type": "authorization_code", "code": code}),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=20,
    )
    token.raise_for_status()
    return user_id, token.json()["access_token"]


def _write_script(ha: Any, object_id: str, payload: str = "on") -> str:
    response = ha.api(
        "POST",
        f"/api/config/script/config/{object_id}",
        json={
            "alias": object_id.replace("_", " ").title(),
            "sequence": [
                {
                    "action": "mqtt.publish",
                    "data": {"topic": f"approved-scripts/{object_id}", "payload": payload},
                }
            ],
        },
    )
    response.raise_for_status()
    entity_id = f"script.{object_id}"
    _wait_for(lambda: ha.api("GET", f"/api/states/{entity_id}").status_code == 200)
    return entity_id


def _write_unsupported_script(ha: Any, object_id: str) -> str:
    """Save a Core-valid script that the delegated registry must reject."""
    response = ha.api(
        "POST",
        f"/api/config/script/config/{object_id}",
        json={
            "alias": object_id.replace("_", " ").title(),
            "sequence": [{"action": "light.turn_on", "data": {}}],
        },
    )
    response.raise_for_status()
    entity_id = f"script.{object_id}"
    _wait_for(lambda: ha.api("GET", f"/api/states/{entity_id}").status_code == 200)
    return entity_id


def _write_ineligible_mqtt_script(ha: Any, object_id: str) -> str:
    """Save an MQTT-shaped script whose target policy is intentionally unsupported."""
    response = ha.api(
        "POST",
        f"/api/config/script/config/{object_id}",
        json={
            "alias": object_id.replace("_", " ").title(),
            "sequence": [
                {
                    "action": "mqtt.publish",
                    "target": {"entity_id": "mqtt.ignored"},
                    "data": {"topic": "approved-scripts/ineligible", "payload": "on"},
                }
            ],
        },
    )
    response.raise_for_status()
    entity_id = f"script.{object_id}"
    _wait_for(lambda: ha.api("GET", f"/api/states/{entity_id}").status_code == 200)
    return entity_id


def _write_lock_usercode_script(ha: Any, object_id: str, usercode: str) -> str:
    """Save a static-target lock code action for the delegated-capability test."""
    response = ha.api(
        "POST",
        f"/api/config/script/config/{object_id}",
        json={
            "alias": object_id.replace("_", " ").title(),
            "sequence": [
                {
                    "action": "zwave_js.set_lock_usercode",
                    "target": {"entity_id": "lock.approved_scripts_test_lock"},
                    "data": {"code_slot": 3, "usercode": usercode},
                }
            ],
        },
    )
    response.raise_for_status()
    entity_id = f"script.{object_id}"
    _wait_for(lambda: ha.api("GET", f"/api/states/{entity_id}").status_code == 200)
    return entity_id


def _wait_for(predicate: Any, timeout: float = 15) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.25)
    raise AssertionError("condition was not met before timeout")


def _approve(
    ha: Any,
    entity_id: str,
    user_id: str,
    template_rules: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    detail = _admin_call(ha, "approved_scripts/editor_detail", entity_id=entity_id)
    assert detail["success"] is True, detail
    approval = _admin_call(
        ha,
        "approved_scripts/approve",
        entity_id=entity_id,
        expected_hash=detail["result"]["hash"],
        caller_policy={"allowed_user_ids": [user_id]},
        approval_policy={
            "protected_actions_acknowledged": True,
            "template_policy": {"template_rules": template_rules or []},
        },
    )
    assert approval["success"] is True
    return approval["result"]


def test_only_allowed_user_executes_snapshot_with_original_trace(ha: Any) -> None:
    """A non-admin allow-list user executes a snapshot, not the live entity."""
    entity_id = _write_script(ha, f"{SCRIPT_PREFIX}_execute")
    allowed_id, allowed_token = _create_user_token(ha, "approved-allowed")
    _, denied_token = _create_user_token(ha, "approved-denied")
    approval = _approve(ha, entity_id, allowed_id)
    assert approval["protected_actions"] == [
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
        }
    ]

    allowed_routes = _ws_call(
        ha.get_url(), allowed_token, {"id": 2, "type": "approved_scripts/routable"}
    )
    assert allowed_routes["success"] is True
    assert entity_id in allowed_routes["result"]["entity_ids"]

    denied_routes = _ws_call(
        ha.get_url(), denied_token, {"id": 3, "type": "approved_scripts/routable"}
    )
    assert denied_routes["success"] is True
    assert entity_id not in denied_routes["result"]["entity_ids"]

    forbidden = _ws_call(
        ha.get_url(), denied_token, {"id": 4, "type": "approved_scripts/execute", "entity_id": entity_id}
    )
    assert forbidden["success"] is False

    executed = _ws_call(
        ha.get_url(), allowed_token, {"id": 5, "type": "approved_scripts/execute", "entity_id": entity_id}
    )
    assert executed["success"] is True, executed
    state = _wait_for(lambda: ha.api("GET", "/api/states/sensor.approved_scripts_test_mqtt").json())
    assert state["state"] == f"approved-scripts/{SCRIPT_PREFIX}_execute"
    assert state["context"]["user_id"] is None
    assert state["context"]["parent_id"] == executed["result"]["context"]["id"]

    traces = _admin_call(ha, "trace/list", domain="script", item_id=f"{SCRIPT_PREFIX}_execute")
    assert traces["success"] is True
    trace = _admin_call(
        ha,
        "trace/get",
        domain="script",
        item_id=f"{SCRIPT_PREFIX}_execute",
        run_id=traces["result"][0]["run_id"],
    )
    approved_metadata = trace["result"]["config"]["approved_scripts"]
    assert approved_metadata["entity_id"] == entity_id
    assert approved_metadata["caller_user_id"] == allowed_id
    assert approved_metadata["execution"] == "approved_snapshot"
    assert approved_metadata["protected_actions"] == approval["protected_actions"]


def test_script_reload_pauses_approval_and_ignore_keeps_it_blocked(ha: Any) -> None:
    """A changed script becomes stale; ignoring its Repair never restores it."""
    entity_id = _write_script(ha, f"{SCRIPT_PREFIX}_stale", payload="before")
    user_id, token = _create_user_token(ha, "approved-stale-user")
    _approve(ha, entity_id, user_id)
    _write_script(ha, f"{SCRIPT_PREFIX}_stale", payload="after")

    def stale() -> dict[str, Any] | None:
        status = _admin_call(ha, "approved_scripts/status", entity_id=entity_id)
        record = status.get("result", {}).get("approval")
        return record if isinstance(record, dict) and record.get("state") == "stale" else None

    assert _wait_for(stale, timeout=12)["invalidated_reason"] == "script_changed"
    blocked = _ws_call(
        ha.get_url(), token, {"id": 6, "type": "approved_scripts/execute", "entity_id": entity_id}
    )
    assert blocked["success"] is False

    issues = _admin_call(ha, "repairs/list_issues")["result"]["issues"]
    issue = next(issue for issue in issues if issue["domain"] == "approved_scripts")
    ignored = _admin_call(
        ha,
        "repairs/ignore_issue",
        domain="approved_scripts",
        issue_id=issue["issue_id"],
        ignore=True,
    )
    assert ignored["success"] is True
    assert _admin_call(ha, "approved_scripts/status", entity_id=entity_id)["result"]["approved"] is False


def test_template_payload_is_rendered_outside_script_and_bound_to_allow_list(ha: Any) -> None:
    """A payload template can produce only administrator-approved literals."""
    source = "{{ states('sensor.approved_scripts_command') }}"
    state = ha.api(
        "POST", "/api/states/sensor.approved_scripts_command", json={"state": "on"}
    )
    state.raise_for_status()
    entity_id = _write_script(ha, f"{SCRIPT_PREFIX}_template", payload=source)
    user_id, token = _create_user_token(ha, "approved-template-user")
    approval = _approve(
        ha,
        entity_id,
        user_id,
        [
            {
                "sequence_index": 0,
                "field": "payload",
                "source": source,
                "allowed_results": ["on", "off"],
            }
        ],
    )
    assert approval["template_policy"]["template_rules"][0]["allowed_results"] == ["off", "on"]

    executed = _ws_call(
        ha.get_url(), token, {"id": 8, "type": "approved_scripts/execute", "entity_id": entity_id}
    )
    assert executed["success"] is True, executed
    mqtt_state = _wait_for(
        lambda: ha.api("GET", "/api/states/sensor.approved_scripts_test_mqtt").json()
    )
    assert mqtt_state["attributes"]["payload"] == "on"
    traces = _admin_call(
        ha, "trace/list", domain="script", item_id=f"{SCRIPT_PREFIX}_template"
    )
    trace = _admin_call(
        ha,
        "trace/get",
        domain="script",
        item_id=f"{SCRIPT_PREFIX}_template",
        run_id=traces["result"][0]["run_id"],
    )
    assert trace["result"]["config"]["approved_scripts"]["template_policy"] == approval[
        "template_policy"
    ]

    state = ha.api(
        "POST", "/api/states/sensor.approved_scripts_command", json={"state": "unexpected"}
    )
    state.raise_for_status()
    blocked = _ws_call(
        ha.get_url(), token, {"id": 9, "type": "approved_scripts/execute", "entity_id": entity_id}
    )
    assert blocked["success"] is False
    assert "allowed results" in blocked["error"]["message"]


def test_template_object_result_is_canonical_json_payload(ha: Any) -> None:
    """Object allow-list entries become deterministic JSON text for MQTT."""
    source = "{{ {'command': 'on', 'level': 1} }}"
    entity_id = _write_script(ha, f"{SCRIPT_PREFIX}_template_object", payload=source)
    user_id, token = _create_user_token(ha, "approved-template-object-user")
    _approve(
        ha,
        entity_id,
        user_id,
        [
            {
                "sequence_index": 0,
                "field": "payload",
                "source": source,
                "allowed_results": [{"level": 1, "command": "on"}],
            }
        ],
    )
    executed = _ws_call(
        ha.get_url(), token, {"id": 10, "type": "approved_scripts/execute", "entity_id": entity_id}
    )
    assert executed["success"] is True, executed
    mqtt_state = _wait_for(
        lambda: ha.api("GET", "/api/states/sensor.approved_scripts_test_mqtt").json()
    )
    assert mqtt_state["attributes"]["payload"] == '{"command":"on","level":1}'


def test_lock_usercode_template_is_bound_to_the_approved_code(ha: Any) -> None:
    """A delegated lock-code update retains its fixed lock, slot, and code policy."""
    source = "{{ states('input_text.approved_security_lock_code') }}"
    entity_id = _write_lock_usercode_script(ha, f"{SCRIPT_PREFIX}_lock_code", source)
    allowed_id, allowed_token = _create_user_token(ha, "approved-lock-code-user")
    state = ha.api(
        "POST", "/api/states/input_text.approved_security_lock_code", json={"state": "1234"}
    )
    state.raise_for_status()
    approval = _approve(
        ha,
        entity_id,
        allowed_id,
        [
            {
                "sequence_index": 0,
                "field": "usercode",
                "source": source,
                "allowed_results": ["1234"],
            }
        ],
    )
    assert approval["protected_actions"][0]["capability"] == "zwave_js.set_lock_usercode.v1"

    executed = _ws_call(
        ha.get_url(), allowed_token, {"id": 12, "type": "approved_scripts/execute", "entity_id": entity_id}
    )
    assert executed["success"] is True, executed
    lock_state = _wait_for(
        lambda: ha.api("GET", "/api/states/sensor.approved_scripts_test_lock_usercode").json()
    )
    assert lock_state["state"] == "1234"
    assert lock_state["attributes"] == {
        "code_slot": 3,
        "entity_id": ["lock.approved_scripts_test_lock"],
    }

    state = ha.api(
        "POST", "/api/states/input_text.approved_security_lock_code", json={"state": "5678"}
    )
    state.raise_for_status()
    blocked = _ws_call(
        ha.get_url(), allowed_token, {"id": 13, "type": "approved_scripts/execute", "entity_id": entity_id}
    )
    assert blocked["success"] is False
    assert "allowed results" in blocked["error"]["message"]


def test_non_admin_cannot_read_or_modify_admin_approval_data(ha: Any) -> None:
    """Admin-only management commands stay unavailable to an allowed caller."""
    entity_id = _write_script(ha, f"{SCRIPT_PREFIX}_admin")
    user_id, token = _create_user_token(ha, "approved-management-denied")
    _approve(ha, entity_id, user_id)

    for message_type in (
        "approved_scripts/status",
        "approved_scripts/editor_detail",
        "approved_scripts/eligible_users",
        "approved_scripts/admin_script_list",
    ):
        message: dict[str, Any] = {"id": 7, "type": message_type}
        if message_type in {"approved_scripts/status", "approved_scripts/editor_detail"}:
            message["entity_id"] = entity_id
        reply = _ws_call(ha.get_url(), token, message)
        assert reply["success"] is False


def test_admin_script_index_lists_scripts_for_the_management_panel(ha: Any) -> None:
    """The panel index is server-derived and does not expose it to callers."""
    entity_id = _write_script(ha, f"{SCRIPT_PREFIX}_panel")
    scripts = _admin_call(ha, "approved_scripts/admin_script_list")
    assert scripts["success"] is True
    row = next(item for item in scripts["result"] if item["entity_id"] == entity_id)
    assert row == {
        "entity_id": entity_id,
        "name": f"{SCRIPT_PREFIX}_panel".replace("_", " ").title(),
        "approval_state": "unapproved",
        "approval_available": True,
    }


def test_admin_script_index_distinguishes_not_required_and_not_supported(ha: Any) -> None:
    """Only registered, eligible protected actions are editable in the panel."""
    normal = _write_unsupported_script(ha, f"{SCRIPT_PREFIX}_normal")
    ineligible = _write_ineligible_mqtt_script(ha, f"{SCRIPT_PREFIX}_ineligible")
    rows = {
        item["entity_id"]: item
        for item in _admin_call(ha, "approved_scripts/admin_script_list")["result"]
    }
    assert rows[normal]["approval_state"] == "not_required"
    assert rows[normal]["approval_available"] is False
    assert rows[ineligible]["approval_state"] == "not_supported"
    assert rows[ineligible]["approval_available"] is False


def test_admin_sees_the_specific_unsupported_action_error(ha: Any) -> None:
    """Eligibility errors identify the rejected action and sequence location."""
    entity_id = _write_unsupported_script(ha, f"{SCRIPT_PREFIX}_unsupported")
    detail = _admin_call(ha, "approved_scripts/editor_detail", entity_id=entity_id)
    assert detail["success"] is False
    assert detail["error"]["code"] == "approved_scripts_error"
    assert "light.turn_on" in detail["error"]["message"]
    assert "sequence[0]" in detail["error"]["message"]


def test_z_config_entry_reload_and_removal_close_the_authority_surface(ha: Any) -> None:
    """Reload keeps the authority available; removal closes it for every caller."""
    entries = ha.api("GET", "/api/config/config_entries/entry?domain=approved_scripts")
    entries.raise_for_status()
    entry_id = entries.json()[0]["entry_id"]

    reloaded = ha.api("POST", f"/api/config/config_entries/entry/{entry_id}/reload")
    reloaded.raise_for_status()
    assert _wait_for(
        lambda: _admin_call(ha, "approved_scripts/routable").get("success") is True
    )

    removed = ha.api("DELETE", f"/api/config/config_entries/entry/{entry_id}")
    removed.raise_for_status()
    assert _wait_for(
        lambda: _admin_call(ha, "approved_scripts/routable").get("success") is False
    )
