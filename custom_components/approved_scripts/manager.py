"""Authority, immutable snapshot execution, limits, and audit persistence."""

from __future__ import annotations

import asyncio
from collections import deque
from copy import deepcopy
from datetime import UTC, datetime
import json
import logging
from typing import Any
from uuid import uuid4

from homeassistant.components.script.const import DOMAIN as SCRIPT_DOMAIN, ScriptService
from homeassistant.components.script.trace import trace_script
from homeassistant.const import ATTR_DOMAIN, ATTR_SERVICE, EVENT_CALL_SERVICE
from homeassistant.core import Context, Event, HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.script import Script
from homeassistant.helpers.storage import Store
from homeassistant.helpers.template import Template
from homeassistant.helpers.trace import trace_get, trace_path

from .canonical import (
    IneligibleScript,
    canonical_hash,
    canonical_result,
    compile_script,
    executable_snapshot,
    normalize_template_policy,
    requires_approval,
)
from .const import (
    DOMAIN,
    EVENT_APPROVALS_UPDATED,
    MAX_AUDIT_RECORDS,
    MAX_CONCURRENT_RUNS,
    STORAGE_KEY,
    STORAGE_VERSION,
    VALIDATION_VERSION,
)
from .resolver import ScriptResolutionError, current_definition, original_trace_target


_LOGGER = logging.getLogger(__name__)


class ApprovalError(RuntimeError):
    """A request is well-formed but is not authorized or executable."""

    def __init__(self, message: str, *, code: str = "approval_failed") -> None:
        super().__init__(message)
        self.code = code


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


class ApprovalManager:
    """Own all delegated authority.  Browser data is never an authority input."""

    def __init__(self, hass: HomeAssistant, config_entry_id: str | None = None) -> None:
        self.hass = hass
        self._config_entry_id = config_entry_id
        self._store = Store[dict[str, Any]](hass, STORAGE_VERSION, STORAGE_KEY)
        self._approvals: dict[str, dict[str, Any]] = {}
        self._audits: deque[dict[str, Any]] = deque(maxlen=MAX_AUDIT_RECORDS)
        self._runs = asyncio.Semaphore(MAX_CONCURRENT_RUNS)
        self._remove_script_reload_listener: Any | None = None
        self._reconcile_task: asyncio.Task[None] | None = None
        self._script_reload_generation = 0

    async def async_load(self) -> None:
        """Load persisted approvals and audit records."""
        data = await self._store.async_load() or {}
        self._approvals = dict(data.get("approvals", {}))
        self._audits = deque(data.get("audits", []), maxlen=MAX_AUDIT_RECORDS)

    async def _async_save(self) -> None:
        await self._store.async_save({"approvals": self._approvals, "audits": list(self._audits)})

    @staticmethod
    def _stale_issue_id(record: dict[str, Any]) -> str | None:
        approval_id = record.get("id")
        return f"stale_approval_{approval_id}" if isinstance(approval_id, str) else None

    def _async_delete_stale_issue(self, record: dict[str, Any]) -> None:
        if issue_id := self._stale_issue_id(record):
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)

    def _async_create_stale_issue(self, record: dict[str, Any], entity_id: str) -> None:
        if not (issue_id := self._stale_issue_id(record)):
            return
        state = self.hass.states.get(entity_id)
        script_name = state.attributes.get("friendly_name", entity_id) if state else entity_id
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            issue_id,
            config_entry_id=self._config_entry_id,
            data={"entity_id": entity_id},
            is_fixable=True,
            is_persistent=True,
            severity=ir.IssueSeverity.WARNING,
            translation_key="stale_approval",
            translation_placeholders={"script_name": str(script_name)},
        )

    async def async_start_monitoring(self) -> None:
        """Reconcile approvals now and after every Core script reload."""
        await self.async_reconcile_approvals()

        @callback
        def on_call_service(event: Event) -> None:
            if (
                event.data.get(ATTR_DOMAIN) != SCRIPT_DOMAIN
                or event.data.get(ATTR_SERVICE) != ScriptService.RELOAD
            ):
                return
            self._script_reload_generation += 1
            if self._reconcile_task is None or self._reconcile_task.done():
                self._reconcile_task = self.hass.async_create_task(
                    self._async_reconcile_after_script_reload()
                )

        self._remove_script_reload_listener = self.hass.bus.async_listen(
            EVENT_CALL_SERVICE, on_call_service
        )

    async def async_stop_monitoring(self) -> None:
        """Detach the reload observer when the config entry unloads."""
        if self._remove_script_reload_listener is not None:
            self._remove_script_reload_listener()
            self._remove_script_reload_listener = None
        if self._reconcile_task is not None:
            self._reconcile_task.cancel()
            self._reconcile_task = None

    async def _async_reconcile_after_script_reload(self) -> None:
        """Wait for Core's asynchronous reload to settle, then reconcile once."""
        while True:
            generation = self._script_reload_generation
            # A config-editor save emits EVENT_CALL_SERVICE before its asynchronous
            # reload has completed.  Do not inspect a transient state: an entity
            # briefly absent during reload must not invalidate its approval.
            await asyncio.sleep(5)
            if generation == self._script_reload_generation:
                await self.async_reconcile_approvals(script_index_changed=True)
                return

    async def async_reconcile_approvals(
        self, *, script_index_changed: bool = False
    ) -> None:
        """Reconcile approvals and notify when the admin script index changed."""
        changed: list[str] = []
        for entity_id, record in self._approvals.items():
            if record.get("state") != "approved":
                continue
            reason: str | None = None
            try:
                snapshot = executable_snapshot(current_definition(self.hass, entity_id))
            except ScriptResolutionError:
                reason = "script_unavailable"
            except IneligibleScript:
                reason = "script_ineligible"
            else:
                if canonical_hash(snapshot) != record.get("hash"):
                    reason = "script_changed"
            if reason is None:
                continue
            record["state"] = "stale"
            record["invalidated_at"] = _timestamp()
            record["invalidated_reason"] = reason
            self._async_create_stale_issue(record, entity_id)
            changed.append(entity_id)
        if changed:
            await self._async_save()
        if changed or script_index_changed:
            event_data: dict[str, Any] = {"script_index_changed": script_index_changed}
            if changed:
                event_data["stale_entity_ids"] = changed
            self.hass.bus.async_fire(EVENT_APPROVALS_UPDATED, event_data)

    async def async_status(self, entity_id: str) -> dict[str, Any]:
        record = self._approvals.get(entity_id)
        return {"entity_id": entity_id, "approved": bool(record and record["state"] == "approved"), "approval": record}

    async def async_approval_entity_ids(self) -> list[str]:
        """Return every script with an approval record, including suspended ones."""
        return sorted(self._approvals)

    async def async_admin_script_list(self) -> list[dict[str, Any]]:
        """Return the server-owned script index for the admin management page."""
        scripts: list[dict[str, Any]] = []
        for state in self.hass.states.async_all(SCRIPT_DOMAIN):
            entity_id = state.entity_id
            record = self._approvals.get(entity_id)
            name = state.attributes.get("friendly_name")
            approval_state = "not_required"
            try:
                definition = current_definition(self.hass, entity_id)
                if requires_approval(definition):
                    try:
                        compile_script(definition)
                    except IneligibleScript:
                        approval_state = "not_supported"
                    else:
                        approval_state = record.get("state") if record else "unapproved"
            except ScriptResolutionError:
                approval_state = "not_supported" if record else "not_required"
            scripts.append(
                {
                    "entity_id": entity_id,
                    "name": name if isinstance(name, str) and name else entity_id,
                    "approval_state": approval_state,
                    "approval_available": approval_state
                    not in {"not_required", "not_supported"},
                }
            )
        return sorted(scripts, key=lambda script: (script["name"].lower(), script["entity_id"]))

    async def async_editor_detail(self, entity_id: str) -> dict[str, Any]:
        """Return the current server-derived revision for the admin settings row.

        The browser only passes this value straight back as a stale-editor guard;
        ``async_approve`` resolves and hashes the definition independently.
        """
        try:
            snapshot, protected_actions = compile_script(
                current_definition(self.hass, entity_id)
            )
        except ScriptResolutionError as err:
            raise ApprovalError("script is unavailable", code="script_unavailable") from err
        record = self._approvals.get(entity_id)
        return {
            "entity_id": entity_id,
            "hash": canonical_hash(snapshot),
            "approved": bool(record and record["state"] == "approved"),
            "caller_policy": record.get("caller_policy") if record else None,
            "protected_actions": protected_actions,
            "template_policy": record.get("template_policy") if record else None,
        }

    async def async_eligible_users(self) -> list[dict[str, str]]:
        """Return active non-admin human users for the admin-only settings UI."""
        return [
            {"id": user.id, "name": user.name or user.id}
            for user in await self.hass.auth.async_get_users()
            if (
                user.is_active
                and not user.is_admin
                and not user.is_owner
                and not user.system_generated
            )
        ]

    async def _async_validate_caller_policy(
        self, caller_policy: dict[str, Any]
    ) -> list[str]:
        """Require canonical, active non-admin Home Assistant user IDs."""
        allowed_users = caller_policy.get("allowed_user_ids")
        if (
            set(caller_policy) != {"allowed_user_ids"}
            or not isinstance(allowed_users, list)
            or not allowed_users
            or not all(isinstance(value, str) and value for value in allowed_users)
        ):
            raise ApprovalError(
                "select at least one non-admin user", code="selected_users_required"
            )
        users = {user.id: user for user in await self.hass.auth.async_get_users()}
        invalid = [
            user_id
            for user_id in allowed_users
            if (
                (user := users.get(user_id)) is None
                or not user.is_active
                or user.is_admin
                or user.is_owner
                or user.system_generated
            )
        ]
        if invalid:
            raise ApprovalError(
                "one or more selected users are no longer active non-admin users",
                code="selected_users_invalid",
            )
        return sorted(set(allowed_users))

    async def async_routable(self, user_id: str | None) -> dict[str, list[str]]:
        """Return only entity IDs this authenticated caller may attempt to run.

        This is UI routing data, not authorization.  It intentionally exposes no
        hash, policy, audit, or approval metadata to non-admin users.
        """
        return {
            "entity_ids": [
                entity_id
                for entity_id, record in self._approvals.items()
                if record.get("state") == "approved"
                and record.get("validation_version") == VALIDATION_VERSION
                and self._allow_caller(record, user_id)
            ]
        }

    async def async_suspend(self, entity_id: str, authorizer_id: str | None) -> None:
        """Immediately block future executions, retaining the record for audit."""
        record = self._approvals.get(entity_id)
        if record is not None:
            record["state"] = "suspended"
            record["suspended_at"] = _timestamp()
            record["suspended_by"] = authorizer_id
            await self._async_save()
            self._async_delete_stale_issue(record)
            self.hass.bus.async_fire(EVENT_APPROVALS_UPDATED)

    async def async_remove(self, entity_id: str, authorizer_id: str | None) -> None:
        """Permanently remove an approval record while retaining an audit event."""
        record = self._approvals.pop(entity_id, None)
        if record is None:
            raise ApprovalError("script approval does not exist")
        self._audits.append(
            {
                "at": _timestamp(),
                "outcome": "removed",
                "approval_id": record.get("id"),
                "entity_id": entity_id,
                "hash": record.get("hash"),
                "authorizer_id": authorizer_id,
            }
        )
        await self._async_save()
        self._async_delete_stale_issue(record)
        self.hass.bus.async_fire(EVENT_APPROVALS_UPDATED)

    async def async_approve(
        self,
        entity_id: str,
        expected_hash: str,
        authorizer_id: str | None,
        caller_policy: dict[str, Any],
        approval_policy: dict[str, Any],
    ) -> dict[str, Any]:
        """Approve exactly the current static executable revision.

        ``expected_hash`` is merely a stale-editor guard.  The backend resolves,
        copies, validates and hashes the current Core definition itself.
        """
        allowed_users = await self._async_validate_caller_policy(caller_policy)
        if (
            set(approval_policy) != {"protected_actions_acknowledged", "template_policy"}
            or approval_policy.get("protected_actions_acknowledged") is not True
            or not isinstance(approval_policy.get("template_policy"), dict)
        ):
            raise ApprovalError(
                "review and acknowledge the protected actions before approving",
                code="protected_actions_not_acknowledged",
            )
        try:
            snapshot, protected_actions = compile_script(
                current_definition(self.hass, entity_id)
            )
        except ScriptResolutionError as err:
            raise ApprovalError("script is unavailable", code="script_unavailable") from err
        actual_hash = canonical_hash(snapshot)
        if expected_hash != actual_hash:
            raise ApprovalError(
                "script changed before approval; reload and approve the visible revision",
                code="script_changed",
            )
        template_policy = normalize_template_policy(
            protected_actions, approval_policy["template_policy"]
        )
        previous = self._approvals.get(entity_id)
        record = {
            "id": str(uuid4()),
            "entity_id": entity_id,
            "hash": actual_hash,
            "state": "approved",
            "authorized_by": authorizer_id,
            "approved_at": _timestamp(),
            "caller_policy": {"allowed_user_ids": allowed_users},
            "validation_version": VALIDATION_VERSION,
            "snapshot": snapshot,
            "protected_actions": protected_actions,
            "template_policy": {"template_rules": template_policy},
        }
        self._approvals[entity_id] = record
        await self._async_save()
        if previous is not None:
            self._async_delete_stale_issue(previous)
        self.hass.bus.async_fire(EVENT_APPROVALS_UPDATED)
        return record

    async def async_reapprove_current(
        self,
        entity_id: str,
        authorizer_id: str | None,
        caller_policy: dict[str, Any],
        approval_policy: dict[str, Any],
    ) -> dict[str, Any]:
        """Approve the revision presently loaded by Core after an explicit review."""
        detail = await self.async_editor_detail(entity_id)
        return await self.async_approve(
            entity_id, detail["hash"], authorizer_id, caller_policy, approval_policy
        )

    def _render_template_snapshot(
        self, snapshot: dict[str, Any], template_policy: dict[str, Any]
    ) -> dict[str, Any]:
        """Render approved templates outside the Script runner and bound results."""
        rendered_snapshot = deepcopy(snapshot)
        for rule in template_policy.get("template_rules", []):
            try:
                rendered = Template(rule["source"], self.hass).async_render(
                    parse_result=True
                )
            except Exception as err:
                raise ApprovalError(
                    "an approved template could not be rendered",
                    code="template_render_failed",
                ) from err
            if rule.get("result_encoding") == "string":
                if not isinstance(rendered, (str, int, float, bool)):
                    raise ApprovalError(
                        "an approved template did not render a scalar user code",
                        code="template_result_type_not_allowed",
                    )
                rendered = str(rendered)
            if canonical_result(rendered) not in {
                canonical_result(value) for value in rule["allowed_results"]
            }:
                raise ApprovalError(
                    "template result is not in this approval's allowed results",
                    code="template_result_not_allowed",
                )
            if rule.get("result_encoding") == "json_text" and not isinstance(
                rendered, str
            ):
                rendered = json.dumps(
                    rendered, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                )
            rendered_snapshot["sequence"][rule["sequence_index"]]["data"][rule["field"]] = rendered
        return rendered_snapshot

    def _allow_caller(self, record: dict[str, Any], user_id: str | None) -> bool:
        return user_id is not None and user_id in record["caller_policy"]["allowed_user_ids"]

    @staticmethod
    def _trace_config(
        snapshot: dict[str, Any],
        record: dict[str, Any],
        entity_id: str,
        caller_context: Context,
        caller_username: str | None,
        system_context: Context,
    ) -> dict[str, Any]:
        """Describe the immutable snapshot that produced an original-script trace."""
        return {
            "sequence": snapshot["sequence"],
            "approved_scripts": {
                "execution": "approved_snapshot",
                "entity_id": entity_id,
                "approval_id": record["id"],
                "approved_hash": record["hash"],
                "caller_user_id": caller_context.user_id,
                "caller_username": caller_username,
                "caller_context_id": caller_context.id,
                "system_context_id": system_context.id,
                "protected_actions": record.get("protected_actions", []),
                "template_policy": record.get("template_policy", {"template_rules": []}),
            },
        }

    async def _async_audit(self, record: dict[str, Any] | None, entity_id: str, caller_context: Context, system_context: Context | None, outcome: str, reason: str | None = None) -> None:
        self._audits.append(
            {
                "at": _timestamp(),
                "outcome": outcome,
                "reason": reason,
                "approval_id": record.get("id") if record else None,
                "entity_id": entity_id,
                "hash": record.get("hash") if record else None,
                "caller_user_id": caller_context.user_id,
                "caller_context_id": caller_context.id,
                "system_context_id": system_context.id if system_context else None,
            }
        )
        await self._async_save()

    async def async_execute(self, entity_id: str, user_id: str | None) -> dict[str, Any]:
        """Execute a freshly compiled snapshot under explicit delegated authority."""
        caller_context = Context(user_id=user_id)
        record = self._approvals.get(entity_id)
        if record is None or record.get("state") != "approved" or record.get("validation_version") != VALIDATION_VERSION:
            await self._async_audit(record, entity_id, caller_context, None, "denied", "not approved")
            raise ApprovalError("script is not approved")
        if not self._allow_caller(record, user_id):
            await self._async_audit(record, entity_id, caller_context, None, "denied", "caller policy")
            raise ApprovalError("you are not allowed to run this script")
        caller = await self.hass.auth.async_get_user(user_id)
        caller_username = next(
            (
                credential.data["username"]
                for credential in caller.credentials
                if isinstance(credential.data.get("username"), str)
            ),
            None,
        ) if caller is not None else None

        # This read/copy/validate/hash sequence has no await.  It never invokes
        # script.<id>, script.turn_on, or the live entity's Script instance.
        try:
            snapshot, protected_actions = compile_script(
                current_definition(self.hass, entity_id)
            )
            template_rules = normalize_template_policy(
                protected_actions,
                record.get("template_policy"),
            )
        except (ScriptResolutionError, IneligibleScript) as err:
            await self._async_audit(record, entity_id, caller_context, None, "denied", str(err))
            raise ApprovalError("approved revision is no longer executable") from err
        if canonical_hash(snapshot) != record["hash"]:
            await self._async_audit(record, entity_id, caller_context, None, "denied", "stale revision")
            raise ApprovalError("script revision changed and must be approved again")
        try:
            snapshot = self._render_template_snapshot(
                snapshot, {"template_rules": template_rules}
            )
        except ApprovalError as err:
            await self._async_audit(record, entity_id, caller_context, None, "denied", str(err))
            raise

        system_context = Context(user_id=None, parent_id=caller_context.id)
        try:
            trace_item_id, trace_settings = original_trace_target(
                self.hass, entity_id
            )
        except ScriptResolutionError as err:
            await self._async_audit(
                record,
                entity_id,
                caller_context,
                system_context,
                "denied",
                str(err),
            )
            raise ApprovalError("original script trace is unavailable") from err
        async with self._runs:
            # A request may have waited for capacity while an administrator
            # suspended/re-approved it.  Revocation blocks this not-yet-started
            # snapshot run; in-flight snapshots are deliberately not cancelled.
            active = self._approvals.get(entity_id)
            if active is not record or active.get("state") != "approved" or active.get("hash") != record["hash"]:
                await self._async_audit(record, entity_id, caller_context, system_context, "denied", "revoked while queued")
                raise ApprovalError("approval was revoked before execution started")
            # Script is an internal API: this invocation is compatibility-tested
            # against each supported HA minor.  It is constructed from our copied
            # validated snapshot, never from ScriptEntity.script.
            script = Script(
                self.hass,
                snapshot["sequence"],
                f"approved snapshot {entity_id}",
                domain="approved_scripts",
                script_mode="parallel",
                max_runs=MAX_CONCURRENT_RUNS,
            )
            # Store this run in the original script's trace history, but record
            # the immutable snapshot—not the mutable live script—as its config.
            # ``trace_script`` is an internal Core seam pinned by compatibility
            # tests; it does not execute the ScriptEntity.
            with trace_script(
                self.hass,
                trace_item_id,
                self._trace_config(
                    snapshot,
                    record,
                    entity_id,
                    caller_context,
                    caller_username,
                    system_context,
                ),
                None,
                system_context,
                trace_settings,
            ) as original_trace:
                original_trace.set_trace(trace_get())
                try:
                    with trace_path("sequence"):
                        result = await script.async_run({}, system_context)
                except Exception as err:  # Auditing must include execution failures.
                    _LOGGER.exception(
                        "Approved snapshot execution failed for %s", entity_id
                    )
                    await self._async_audit(record, entity_id, caller_context, system_context, "error", str(err))
                    raise ApprovalError("approved script execution failed") from err
                finally:
                    await script.async_stop()
        await self._async_audit(record, entity_id, caller_context, system_context, "success")
        response = getattr(result, "service_response", None) if result is not None else None
        return {"context": {"id": caller_context.id, "parent_id": caller_context.parent_id, "user_id": caller_context.user_id}, "response": response}
