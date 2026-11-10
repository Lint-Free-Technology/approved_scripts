/* Approved Scripts approval UI and execution compatibility layer.
 *
 * This module deliberately has no authority. Python revalidates every
 * approval and execution request; this module only adapts HA UI actions.
 */

import type { Hass, WsResult } from "./types";
import type { ApprovedScriptsTranslations } from "./translations";

type ApprovalEditor = HTMLElement & {
  hass?: Hass;
  entry?: { entity_id?: string };
  disabled?: boolean;
  updateComplete?: Promise<unknown>;
};

type HaForm = HTMLElement & {
  hass?: Hass;
  schema?: unknown[];
  data?: Record<string, unknown>;
  disabled?: boolean;
  narrow?: boolean;
  computeLabel?: (schema: { name?: string }) => string;
  computeHelper?: (schema: { name?: string }) => string | undefined;
  reportValidity?: () => boolean;
};

type AdaptivePopover = HTMLElement & {
  dialogAnchor?: Element;
  headerTitle?: string;
  headerSubtitle?: string;
  width?: "small" | "medium" | "large" | "full";
  hideCloseButton?: boolean;
  preventScrimClose?: boolean;
  open?: boolean;
};

type HaButton = HTMLElement & {
  disabled?: boolean;
  loading?: boolean;
};

type TemplateRequirement = {
  sequence_index: number;
  sequence_path: string;
  field: string;
  source: string;
};

type ProtectedAction = {
  sequence_index: number;
  sequence_path: string;
  action: string;
  title_key: string;
  warning_key: string;
  approved_fields: string[];
  templates?: Array<{ field: string; source: string }>;
  policy_inputs?: Array<{
    id: string;
    kind: string;
    field: string;
    source: string;
    label_key: string;
    description_key: string;
    value_types: string[];
  }>;
};

const MARK = Symbol.for("approved_scripts.call_service_wrapper");
const ROUTES = new Set<string>();
const observedRoots = new WeakSet<Node>();
let installedHass: Hass | undefined;
let originalCallService: Hass["callService"] | undefined;
let routedHass: Hass | undefined;
let routeRetryTimer: number | undefined;
let translations: ApprovedScriptsTranslations | undefined;

function text(key: string, values: Record<string, string | number> = {}): string {
  return translations?.text(key, values) ?? key;
}

const ws = (hass: Hass, message: Record<string, unknown>) =>
  hass.connection.sendMessagePromise(message);

const entityIdFor = (domain: unknown, service: unknown): string | null =>
  domain === "script" && typeof service === "string" && /^[a-z0-9_]+$/.test(service)
    ? `script.${service}`
    : null;

function notify(message: string, detail: Record<string, unknown> = {}): void {
  // Home Assistant registers its notification dialog on the application shell.
  // Dispatching on window does not bubble down into that shell, so use the
  // same target as UIX's version-update toast.
  const base = document.querySelector("home-assistant");
  if (!base) return;
  base.dispatchEvent(
    new CustomEvent("hass-notification", {
      detail: { message, duration: 5000, ...detail },
    }),
  );
}

function openRepairs(): void {
  history.pushState(history.state, "", "/config/repairs");
  const event = new Event("location-changed", { bubbles: true, composed: true });
  (document.querySelector("home-assistant") || window).dispatchEvent(event);
}

function notifyStaleApprovals(entityIds: string[]): void {
  if (!entityIds.length) return;
  const message =
    entityIds.length === 1
      ? text("stale.approval_paused", { script_name: entityIds[0] })
      : text("stale.approvals_paused", { count: entityIds.length });
  notify(message, {
    id: "approved-scripts-stale-approval",
    duration: -1,
    action: {
      text: text("stale.open_repairs"),
      action: openRepairs,
      primary: true,
    },
  });
}

async function refreshRoutes(hass: Hass): Promise<void> {
  const result = await ws(hass, { type: "approved_scripts/routable" });
  const entityIds = Array.isArray(result) ? result : (result.entity_ids as string[] | undefined) || [];
  ROUTES.clear();
  for (const entityId of entityIds) ROUTES.add(entityId);
}

function refreshRoutesWithRetry(hass: Hass, attempt = 0): void {
  window.clearTimeout(routeRetryTimer);
  void refreshRoutes(hass).catch(() => {
    ROUTES.clear();
    // The browser resource can load while integrations are still registering.
    // Retry briefly instead of falling through to an unauthorized direct call.
    if (attempt < 10 && hass === installedHass) {
      routeRetryTimer = window.setTimeout(
        () => refreshRoutesWithRetry(hass, attempt + 1),
        500,
      );
    }
  });
}

async function execute(
  hass: Hass,
  entityId: string,
  notifyOnError: unknown,
  returnResponse: unknown,
): Promise<unknown> {
  try {
    const result = await ws(hass, {
      type: "approved_scripts/execute",
      entity_id: entityId,
    });
    const answer: Record<string, unknown> = { context: result.context };
    if (returnResponse && result.response !== undefined) answer.response = result.response;
    return answer;
  } catch (err) {
    if (notifyOnError) {
      notify(text("error.execution_failed", { error: String(err) }));
    }
    throw err; // Never fall through to the normal service call.
  }
}

function wrapCallService(hass: Hass): void {
  const markedCall = hass.callService as Hass["callService"] & {
    [MARK]?: { original: Hass["callService"] };
  };
  if (!hass || (hass === installedHass && markedCall[MARK])) return;
  installedHass = hass;
  const current = hass.callService;
  if (typeof current !== "function") return;
  originalCallService = markedCall[MARK]?.original || current;
  const approvedCallService = function (
    this: Hass,
    domain: unknown,
    service: unknown,
    _data?: unknown,
    _target?: unknown,
    notifyOnError?: unknown,
    returnResponse?: unknown,
  ): Promise<unknown> {
    const entityId = entityIdFor(domain, service);
    if (entityId && ROUTES.has(entityId)) {
      return execute(this || hass, entityId, notifyOnError, returnResponse);
    }
    return originalCallService!.call(
      this,
      domain,
      service,
      _data,
      _target,
      notifyOnError,
      returnResponse,
    );
  } as Hass["callService"];
  Object.defineProperty(approvedCallService, MARK, {
    value: { original: originalCallService },
  });
  hass.callService = approvedCallService;
}

function hassFromEvent(event: Event): Hass | undefined {
  for (const node of event.composedPath()) {
    const candidate = node as unknown as { hass?: Hass };
    if (candidate.hass) return candidate.hass;
  }
  return (document.querySelector("home-assistant") as { hass?: Hass } | null)?.hass;
}

function installActionInterceptor(): void {
  document.addEventListener(
    "hass-action",
    async (event) => {
      const detail = (event as CustomEvent<Record<string, unknown>>).detail || {};
      const service =
        detail.action === "perform-action"
          ? detail.perform_action
          : detail.action === "call-service"
            ? detail.service
            : undefined;
      if (typeof service !== "string" || !service.startsWith("script.")) return;
      if (!ROUTES.has(service)) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      const hass = hassFromEvent(event);
      if (hass) await execute(hass, service, true, false);
    },
    true,
  );
}

async function ensureHaForm(): Promise<void> {
  if (customElements.get("ha-form")) return;
  // This is the same lazy-load path used by UIX: creating a card editor asks
  // Home Assistant to import its ha-form implementation for the current UI.
  const helpers = await (window as unknown as {
    loadCardHelpers?: () => Promise<{ createCardElement: (config: unknown) => Promise<unknown> }>;
  }).loadCardHelpers?.();
  const card = await helpers?.createCardElement({ type: "button" });
  const constructor = (card as { constructor?: { getConfigElement?: () => Promise<unknown> } })?.constructor;
  await constructor?.getConfigElement?.();
  await customElements.whenDefined("ha-form");
}

async function ensureAdaptivePopover(): Promise<void> {
  if (customElements.get("ha-adaptive-popover")) return;
  // Adaptive popovers are lazy-loaded by Core. Reuse UIX's supported lazy
  // import trigger instead of assuming this entity-settings route loaded it.
  const helpers = await (window as unknown as {
    loadCardHelpers?: () => Promise<{ createCardElement: (config: unknown) => Promise<unknown> }>;
  }).loadCardHelpers?.();
  await helpers?.createCardElement({ type: "calendar" });
  await customElements.whenDefined("ha-full-calendar");
  const base = document.querySelector("home-assistant") as { hass?: Hass; shadowRoot?: ShadowRoot | null } | null;
  if (!base?.shadowRoot) throw new Error(text("error.application_shell_unavailable"));
  type CalendarLoader = HTMLElement & {
    hass?: Hass;
    _activeView?: unknown;
    _createEvent?: () => void;
  };
  let calendar = base.shadowRoot.getElementById(
    "approved-scripts-popover-loader",
  ) as CalendarLoader | null;
  if (!calendar) {
    const loader = document.createElement("ha-full-calendar") as unknown as CalendarLoader;
    loader.id = "approved-scripts-popover-loader";
    loader.style.display = "none";
    base.shadowRoot.append(loader);
    calendar = loader;
  }
  // This is UIX's lazy-load path. _createEvent() emits a dialog event while it
  // imports its editor, so consume that event before it reaches HA's dialog
  // manager. The import still completes; no calendar-event dialog is shown.
  const calendarDialogHandler = (event: Event) => {
    const detail = (event as CustomEvent<{
      dialogTag?: string;
      dialogImport?: () => Promise<unknown>;
    }>).detail;
    if (detail?.dialogTag === "dialog-calendar-event-editor") {
      event.stopPropagation();
      Promise.resolve(detail.dialogImport?.()).finally(() => calendar?.remove());
    }
    window.removeEventListener("show-dialog", calendarDialogHandler, { capture: true });
  };
  window.addEventListener("show-dialog", calendarDialogHandler, { capture: true });
  calendar.hass = base.hass;
  calendar._activeView = undefined;
  calendar._createEvent?.();
  await customElements.whenDefined("ha-date-input");
  type DateInputLoader = HTMLElement & {
    locale?: unknown;
    _openDialog?: () => void;
  };
  let dateInput = base.shadowRoot.getElementById(
    "approved-scripts-date-input-loader",
  ) as DateInputLoader | null;
  if (!dateInput) {
    dateInput = document.createElement("ha-date-input") as unknown as DateInputLoader;
    dateInput.id = "approved-scripts-date-input-loader";
    dateInput.style.display = "none";
    base.shadowRoot.append(dateInput);
  }
  await new Promise<void>((resolve, reject) => {
    const timeout = window.setTimeout(() => {
      cleanup();
      reject(new Error(text("error.popover_load_timeout")));
    }, 2_000);
    const cleanup = () => {
      window.clearTimeout(timeout);
      window.removeEventListener("show-dialog", handleDialog, { capture: true });
    };
    const handleDialog = (event: Event) => {
      const detail = (event as CustomEvent<{
        dialogTag?: string;
        dialogImport?: () => Promise<unknown>;
      }>).detail;
      if (detail?.dialogTag !== "ha-dialog-date-picker") return;
      event.stopPropagation();
      cleanup();
      Promise.resolve(detail.dialogImport?.()).then(
        () => resolve(),
        (err) => reject(err),
      );
    };
    window.addEventListener("show-dialog", handleDialog, { capture: true });
    dateInput!.locale = (base.hass as unknown as { locale?: unknown } | undefined)?.locale;
    dateInput!._openDialog?.();
  });
  await customElements.whenDefined("ha-adaptive-popover");
  calendar.remove();
  dateInput.remove();
}

async function openApprovalPopover(
  editor: ApprovalEditor,
  anchor?: Element,
): Promise<void> {
  const entityId = editor.entry?.entity_id;
  const hass = editor.hass;
  if (!entityId || !hass) return;
  await Promise.all([ensureHaForm(), ensureAdaptivePopover()]);

  const [eligible, status, detail] = await Promise.all([
    ws(hass, { type: "approved_scripts/eligible_users" }),
    ws(hass, { type: "approved_scripts/status", entity_id: entityId }),
    ws(hass, { type: "approved_scripts/editor_detail", entity_id: entityId }),
  ]);
  const eligibleUsers = eligible as unknown as Array<{ id: string; name: string }>;
  const approval = status.approval as
    | {
        caller_policy?: { allowed_user_ids?: string[] };
        template_policy?: { template_rules?: Array<TemplateRequirement & { allowed_results?: string[] }> };
      }
    | undefined;
  const selectedIds = (approval?.caller_policy?.allowed_user_ids || []).filter((userId) =>
    eligibleUsers.some((user) => user.id === userId),
  );
  const protectedActions = (detail.protected_actions || []) as ProtectedAction[];
  const policyInputs = protectedActions.flatMap((action) =>
    (action.policy_inputs || []).map((input) => ({ ...input, action })),
  );
  const existingTemplateRules = approval?.template_policy?.template_rules || [];
  const savedResults = (input: TemplateRequirement): unknown[] =>
    existingTemplateRules.find(
      (rule) =>
        rule.sequence_index === input.sequence_index &&
        rule.field === input.field &&
        rule.source === input.source,
    )?.allowed_results || [];
  const policyValues = new Map<string, unknown[]>(
    policyInputs.map((input) => [
      input.id,
      savedResults({
        sequence_index: input.action.sequence_index,
        sequence_path: input.action.sequence_path,
        field: input.field,
        source: input.source,
      }),
    ]),
  );

  const popover = document.createElement("ha-adaptive-popover") as AdaptivePopover;
  if (anchor) popover.dialogAnchor = anchor;
  popover.headerTitle = text("popover.title");
  popover.width = "medium";
  popover.hideCloseButton = false;
  popover.preventScrimClose = false;

  // HA dialog-header subtitles intentionally stay on a single line. Keep the
  // heading native, but render the longer description in the popover body so
  // it wraps at every responsive width and has deliberate spacing.
  const description = document.createElement("div");
  description.textContent = text("popover.description");
  description.style.cssText = [
    "color: var(--secondary-text-color)",
    "line-height: var(--ha-line-height-normal)",
    "padding: 8px 24px 24px",
  ].join(";");
  popover.append(description);

  const policyEditor = document.createElement("div");
  policyEditor.style.cssText = "padding: 0 24px 16px;";
  const policyStyles = document.createElement("style");
  policyStyles.textContent = `
    .approved-scripts-results-table {
      border-collapse: collapse;
      margin-top: 8px;
      width: 100%;
    }
    .approved-scripts-results-table th,
    .approved-scripts-results-table td {
      border-bottom: 1px solid var(--divider-color);
      padding: var(--ha-space-2);
      text-align: start;
      vertical-align: middle;
    }
    .approved-scripts-results-table th {
      color: var(--secondary-text-color);
      font-size: var(--ha-font-size-s);
      font-weight: var(--ha-font-weight-medium);
    }
    .approved-scripts-results-table th:last-child,
    .approved-scripts-results-table td:last-child {
      text-align: end;
      white-space: nowrap;
      width: 1%;
    }
    .approved-scripts-results-value {
      display: block;
      font-family: var(--code-font-family, monospace);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .approved-scripts-result-actions {
      display: flex;
      justify-content: flex-end;
    }
  `;
  policyEditor.append(policyStyles);
  const renderPolicyInput = (input: (typeof policyInputs)[number], container: HTMLElement) => {
    const valueTable = document.createElement("table");
    valueTable.className = "approved-scripts-results-table";
    const tableHeader = document.createElement("thead");
    const headerRow = document.createElement("tr");
    for (const heading of [text("form.result_value"), text("form.actions")]) {
      const cell = document.createElement("th");
      cell.scope = "col";
      cell.textContent = heading;
      headerRow.append(cell);
    }
    tableHeader.append(headerRow);
    const valueList = document.createElement("tbody");
    valueTable.append(tableHeader, valueList);
    const previewValue = (value: unknown): string => {
      const serialized = typeof value === "string" ? value : JSON.stringify(value);
      return serialized.length > 120 ? `${serialized.slice(0, 117)}…` : serialized;
    };
    const confirmRemoval = async (): Promise<boolean> => {
      const helpers = await (window as unknown as {
        loadCardHelpers?: () => Promise<{
          showConfirmationDialog?: (
            target: Element,
            config: { title: string; text: string; confirmText: string; destructive: boolean },
          ) => Promise<unknown>;
        }>;
      }).loadCardHelpers?.();
      return await helpers?.showConfirmationDialog?.(popover, {
        title: text("confirmation.delete_allowed_result_title"),
        text: text("confirmation.delete_allowed_result_text"),
        confirmText: text("button.delete"),
        destructive: true,
      }) === true;
    };
    const openResultEditor = (kind: "scalar" | "object", index?: number) => {
      const values = policyValues.get(input.id) || [];
      const current = index === undefined ? (kind === "object" ? {} : "") : values[index];
      const resultEditor = document.createElement("ha-adaptive-popover") as AdaptivePopover;
      resultEditor.headerTitle = text(
        index === undefined
          ? kind === "object" ? "form.add_object_result" : "form.add_scalar_result"
          : "form.edit_allowed_result",
      );
      // Object selectors need enough horizontal space to expose their YAML/JSON
      // editor. Keep scalar editing in the same consistent dialog width.
      resultEditor.width = "medium";
      const body = document.createElement("div");
      body.style.cssText = "padding: 0 24px 16px;";
      const resultForm = document.createElement("ha-form") as HaForm;
      resultForm.hass = hass;
      resultForm.narrow = false;
      resultForm.schema = [{
        name: "value",
        selector: kind === "object" ? { object: {} } : { text: {} },
        required: true,
      }];
      resultForm.data = { value: current };
      resultForm.computeLabel = () => text("form.result_value");
      resultForm.computeHelper = () =>
        kind === "object" ? text("form.object_result_helper") : undefined;
      body.append(resultForm);
      const footer = document.createElement("ha-dialog-footer");
      footer.slot = "footer";
      const cancel = document.createElement("ha-button") as HaButton;
      cancel.slot = "secondaryAction";
      cancel.setAttribute("appearance", "plain");
      cancel.setAttribute("variant", "neutral");
      cancel.textContent = text("button.cancel");
      cancel.addEventListener("click", (event) => {
        // In the entity-settings route the nested adaptive dialog's close
        // event can otherwise reach the approval editor's close handler.
        event.preventDefault();
        event.stopImmediatePropagation();
        resultEditor.open = false;
      });
      const save = document.createElement("ha-button") as HaButton;
      save.slot = "primaryAction";
      save.setAttribute("appearance", "accent");
      save.setAttribute("variant", "brand");
      save.textContent = text(index === undefined ? "button.add" : "button.update");
      save.addEventListener("click", () => {
        const next = resultForm.data?.value;
        if (resultForm.reportValidity?.() === false) return;
        if (kind === "object" && (next === null || typeof next !== "object")) return;
        if (index === undefined) values.push(next);
        else values[index] = next;
        policyValues.set(input.id, values);
        markDirty();
        renderValues();
        resultEditor.open = false;
      });
      footer.append(cancel, save);
      resultEditor.append(body, footer);
      resultEditor.addEventListener("closed", (event) => {
        event.stopPropagation();
        resultEditor.remove();
      }, { once: true });
      const base = document.querySelector("home-assistant") as { shadowRoot?: ShadowRoot | null } | null;
      if (!base?.shadowRoot) return;
      base.shadowRoot.append(resultEditor);
      resultEditor.open = true;
    };
    const renderValues = () => {
      valueList.replaceChildren();
      for (const [index, value] of (policyValues.get(input.id) || []).entries()) {
        const row = document.createElement("tr");
        const valueCell = document.createElement("td");
        const valuePreview = document.createElement("code");
        valuePreview.className = "approved-scripts-results-value";
        valuePreview.textContent = previewValue(value);
        valuePreview.title = typeof value === "string" ? value : JSON.stringify(value);
        valueCell.append(valuePreview);
        const actionCell = document.createElement("td");
        const actions = document.createElement("div");
        actions.className = "approved-scripts-result-actions";
        const iconAction = (icon: string, labelText: string, handler: () => void | Promise<void>) => {
          const button = document.createElement("ha-icon-button") as HTMLElement & { label?: string };
          button.label = labelText;
          button.setAttribute("title", labelText);
          const actionIcon = document.createElement("ha-icon") as HTMLElement & { icon?: string };
          actionIcon.icon = icon;
          button.append(actionIcon);
          button.addEventListener("click", () => void handler());
          return button;
        };
        actions.append(
          iconAction("mdi:pencil", text("button.edit_allowed_result"), () =>
            openResultEditor(value !== null && typeof value === "object" ? "object" : "scalar", index),
          ),
          iconAction("mdi:close", text("button.delete_allowed_result"), async () => {
            if (!await confirmRemoval()) return;
            const values = policyValues.get(input.id) || [];
            values.splice(index, 1);
            markDirty();
            renderValues();
          }),
        );
        actionCell.append(actions);
        row.append(valueCell, actionCell);
        valueList.append(row);
      }
    };
    const templateLabel = document.createElement("div");
    templateLabel.textContent = text("form.template");
    templateLabel.style.cssText = "font-weight: var(--ha-font-weight-medium); margin-top: 16px;";
    const source = document.createElement("code");
    source.textContent = input.source;
    source.style.cssText = "display:block; white-space:pre-wrap; margin:8px 0; padding:8px; background:var(--code-editor-background-color, #f5f5f5);";
    const helper = document.createElement("div");
    helper.textContent = text(input.description_key);
    helper.style.cssText = "color:var(--secondary-text-color);";
    const label = document.createElement("div");
    label.textContent = text(input.label_key);
    label.style.cssText = "font-weight: var(--ha-font-weight-medium); margin-top: 16px;";
    const controls = document.createElement("div");
    controls.style.cssText = "display:flex; gap:var(--ha-space-2); justify-content:flex-end; margin-top:var(--ha-space-2);";
    const add = (kind: "scalar" | "object") => openResultEditor(kind);
    if (input.value_types.includes("scalar")) {
      const button = document.createElement("ha-button") as HaButton;
      button.setAttribute("appearance", "filled");
      button.setAttribute("variant", "brand");
      button.textContent = text("button.add_scalar");
      button.addEventListener("click", () => add("scalar"));
      controls.append(button);
    }
    if (input.value_types.includes("object")) {
      const button = document.createElement("ha-button") as HaButton;
      button.setAttribute("appearance", "filled");
      button.setAttribute("variant", "brand");
      button.textContent = text("button.add_object");
      button.addEventListener("click", () => add("object"));
      controls.append(button);
    }
    container.append(templateLabel, source, label, helper, valueTable, controls);
    renderValues();
  };
  for (const action of protectedActions) {
    const section = document.createElement("section");
    section.style.cssText = "border-top: 1px solid var(--divider-color); border-bottom: 1px solid var(--divider-color); padding:16px 0;";
    const title = document.createElement("div");
    title.textContent = text(action.title_key || action.action);
    title.style.cssText = "font-weight:var(--ha-font-weight-bold); font-size:var(--ha-font-size-l);";
    const details = document.createElement("div");
    details.textContent = `${action.sequence_path}: ${action.approved_fields.join(", ")}`;
    details.style.cssText = "color:var(--secondary-text-color); margin-top:4px;";
    const warning = document.createElement("div");
    warning.textContent = text(action.warning_key);
    warning.style.cssText = "color:var(--secondary-text-color); margin-top:8px;";
    section.append(title, details, warning);
    for (const input of policyInputs.filter((item) => item.action === action)) renderPolicyInput(input, section);
    policyEditor.append(section);
  }
  const form = document.createElement("ha-form") as HaForm;
  form.hass = hass;
  form.narrow = true;
  form.disabled = Boolean(editor.disabled);
  form.computeLabel = (field) => {
    if (field.name === "enabled") return text("form.approve_for_non_admin_users");
    if (field.name === "allowed_user_ids") return text("form.allowed_users");
    return field.name || "";
  };
  form.computeHelper = (field) =>
    field.name === "allowed_user_ids"
      ? text("form.allowed_users_helper")
      : undefined;
  const schema = (enabled: boolean) => [
    {
      name: "enabled",
      selector: { boolean: {} },
    },
    {
      name: "allowed_user_ids",
      selector: {
        select: {
          multiple: true,
          options: eligibleUsers.map((user) => ({ value: user.id, label: user.name })),
        },
      },
      required: true,
      disabled: !enabled || Boolean(editor.disabled),
    },
  ];
  form.schema = schema(status.approved === true);
  form.data = {
    enabled: status.approved === true,
    allowed_user_ids: selectedIds,
  };
  form.addEventListener("value-changed", () => {
    form.schema = schema(form.data?.enabled === true);
    markDirty();
  });
  form.style.cssText = "display: block; padding: 0 24px 16px;";
  popover.append(form);
  popover.append(policyEditor);

  const acknowledgement = document.createElement("label");
  acknowledgement.style.cssText = "display:flex; gap:12px; align-items:center; padding:0 24px 16px;";
  const acknowledgementInput = document.createElement("input");
  acknowledgementInput.type = "checkbox";
  acknowledgementInput.disabled = Boolean(editor.disabled);
  acknowledgementInput.addEventListener("change", () => markDirty());
  const acknowledgementText = document.createElement("span");
  acknowledgementText.textContent = text("form.protected_actions_acknowledged");
  acknowledgement.append(acknowledgementInput, acknowledgementText);
  popover.append(acknowledgement);

  let initialState = "";
  const currentState = () => JSON.stringify({
    form: form.data,
    policy_values: Array.from(policyValues.entries()),
    protected_actions_acknowledged: acknowledgementInput.checked,
  });
  const markDirty = () => {
    // HA's adaptive dialog uses this flag for the close button, scrim, and
    // Escape. Clean forms remain easy to inspect and dismiss.
    popover.preventScrimClose = currentState() !== initialState;
  };
  initialState = currentState();

  const requestClose = async () => {
    if (!popover.preventScrimClose) {
      popover.open = false;
      return;
    }
    const helpers = await (window as unknown as {
      loadCardHelpers?: () => Promise<{
        showConfirmationDialog?: (
          target: Element,
          config: { title: string; text: string; confirmText: string; destructive: boolean },
        ) => Promise<unknown>;
      }>;
    }).loadCardHelpers?.();
    const discard = await helpers?.showConfirmationDialog?.(popover, {
      title: text("confirmation.discard_approval_title"),
      text: text("confirmation.discard_approval_text"),
      confirmText: text("button.discard"),
      destructive: true,
    });
    if (discard === true) popover.open = false;
  };
  // In anchored-popover mode Home Assistant's header close control bypasses
  // `preventScrimClose`, so guard it explicitly. This also gives Escape the
  // same discard choice in either adaptive mode.
  popover.addEventListener("click", (event) => {
    if (!popover.preventScrimClose) return;
    const closesDialog = event.composedPath().some(
      (node) =>
        node instanceof HTMLElement &&
        (node.getAttribute("data-dialog") === "close" || node.getAttribute("data-popover") === "close"),
    );
    if (!closesDialog) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    void requestClose();
  }, true);
  popover.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || !popover.preventScrimClose) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    void requestClose();
  }, true);

  const error = document.createElement("div");
  error.hidden = true;
  error.style.cssText = "color: var(--error-color); padding: 0 24px 16px;";
  popover.append(error);

  const footer = document.createElement("ha-dialog-footer");
  footer.slot = "footer";
  const cancel = document.createElement("ha-button") as HaButton;
  cancel.slot = "secondaryAction";
  cancel.setAttribute("variant", "neutral");
  cancel.setAttribute("appearance", "plain");
  cancel.textContent = text("button.cancel");
  cancel.addEventListener("click", () => void requestClose());
  const save = document.createElement("ha-button") as HaButton;
  save.slot = "primaryAction";
  save.setAttribute("variant", "brand");
  save.setAttribute("appearance", "accent");
  save.textContent = text("button.save");
  save.disabled = Boolean(editor.disabled);
  save.addEventListener("click", async () => {
    const data = form.data || {};
    const enabled = data.enabled === true;
    const userIds = Array.isArray(data.allowed_user_ids)
      ? data.allowed_user_ids.filter((value): value is string => typeof value === "string")
      : [];
    if (enabled && (!userIds.length || form.reportValidity?.() === false)) {
      error.textContent = text("form.select_non_admin_user");
      error.hidden = false;
      return;
    }
    if (enabled && !acknowledgementInput.checked) {
      error.textContent = text("form.acknowledge_protected_actions");
      error.hidden = false;
      return;
    }
    const templateRules = policyInputs
      .filter((input) => input.kind === "allowed_results")
      .map((input) => ({
        sequence_index: input.action.sequence_index,
        field: input.field,
        source: input.source,
        allowed_results: policyValues.get(input.id) || [],
      }));
    if (enabled && templateRules.some((rule) => !rule.allowed_results.length)) {
      error.textContent = text("form.template_results_required");
      error.hidden = false;
      return;
    }
    if (enabled && policyEditor.querySelector("textarea:invalid, input:invalid")) {
      error.textContent = text("form.correct_policy_fields");
      error.hidden = false;
      return;
    }
    save.loading = true;
    save.disabled = true;
    form.disabled = true;
    error.hidden = true;
    try {
      if (!enabled) {
        await ws(hass, { type: "approved_scripts/suspend", entity_id: entityId });
      } else {
        const detail = await ws(hass, {
          type: "approved_scripts/editor_detail",
          entity_id: entityId,
        });
        await ws(hass, {
          type: "approved_scripts/approve",
          entity_id: entityId,
          expected_hash: detail.hash,
          caller_policy: { allowed_user_ids: userIds },
          approval_policy: {
            protected_actions_acknowledged: true,
            template_policy: { template_rules: templateRules },
          },
        });
      }
      refreshRoutesWithRetry(hass);
      initialState = currentState();
      popover.preventScrimClose = false;
      popover.open = false;
    } catch (err) {
      error.textContent = text("error.save_approval", { error: String(err) });
      error.hidden = false;
    } finally {
      save.loading = false;
      save.disabled = Boolean(editor.disabled);
      form.disabled = Boolean(editor.disabled);
    }
  });
  footer.append(cancel, save);
  popover.append(footer);

  const removeApprovalPopover = (event: Event) => {
    // A nested result editor may emit the same bubbling event. Only the
    // approval editor's own lifecycle event is allowed to remove it.
    if (event.target !== popover) return;
    popover.removeEventListener("closed", removeApprovalPopover);
    popover.remove();
  };
  popover.addEventListener("closed", removeApprovalPopover);
  const base = document.querySelector("home-assistant") as { shadowRoot?: ShadowRoot | null } | null;
  if (!base?.shadowRoot) throw new Error(text("error.application_shell_unavailable"));
  base.shadowRoot.append(popover);
  popover.open = true;
}

export async function openApprovalEditor(
  hass: Hass,
  entityId: string,
  anchor?: Element,
): Promise<void> {
  // Open the single shared approval editor from any admin surface.
  await openApprovalPopover(
    { hass, entry: { entity_id: entityId } } as ApprovalEditor,
    anchor,
  );
}

(window as unknown as { approvedScriptsOpenApproval?: typeof openApprovalEditor }).approvedScriptsOpenApproval = openApprovalEditor;

function installApprovalRow(editor: ApprovalEditor): void {
  const entityId = editor.entry?.entity_id;
  const hass = editor.hass;
  const root = editor.shadowRoot;
  if (!entityId?.startsWith("script.") || !hass?.user?.is_admin || !root) return;
  if (root.querySelector("[data-approved-scripts-settings]")) return;

  if (!editor.dataset.approvedScriptsSettingsAvailable) {
    if (editor.dataset.approvedScriptsSettingsUnavailable) return;
    if (!editor.dataset.approvedScriptsSettingsChecking) {
      editor.dataset.approvedScriptsSettingsChecking = "";
      void ws(hass, { type: "approved_scripts/editor_detail", entity_id: entityId }).then(
        () => {
          delete editor.dataset.approvedScriptsSettingsChecking;
          editor.dataset.approvedScriptsSettingsAvailable = "true";
          installApprovalRow(editor);
        },
        () => {
          delete editor.dataset.approvedScriptsSettingsChecking;
          editor.dataset.approvedScriptsSettingsUnavailable = "true";
        },
      );
    }
    return;
  }

  // Lit may not yet have rendered the editor when the shadow-root observer
  // first sees it. Wait for its native settings list, otherwise our row would
  // be inserted first and Core's rendered controls would follow it.
  if (!root.querySelector("ha-list-base")) {
    if (!editor.dataset.approvedScriptsSettingsPending) {
      editor.dataset.approvedScriptsSettingsPending = "";
      void (editor.updateComplete ?? Promise.resolve()).then(() => {
        requestAnimationFrame(() => {
          delete editor.dataset.approvedScriptsSettingsPending;
          installApprovalRow(editor);
        });
      });
    }
    return;
  }

  const row = document.createElement("ha-row-item");
  row.dataset.approvedScriptsSettings = "";
  row.style.marginTop = "16px";
  const headline = document.createElement("span");
  headline.slot = "headline";
  headline.textContent = text("row.headline");
  const supportingText = document.createElement("span");
  supportingText.slot = "supporting-text";
  supportingText.textContent = text("row.supporting_text");
  const button = document.createElement("ha-button") as HaButton;
  button.slot = "end";
  button.setAttribute("variant", "brand");
  button.setAttribute("appearance", "filled");
  button.textContent = text("row.configure");
  button.disabled = Boolean(editor.disabled);
  button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      await openApprovalPopover(editor, button);
    } catch (err) {
      notify(text("error.open_popover", { error: String(err) }));
    } finally {
      button.disabled = Boolean(editor.disabled);
    }
  });
  row.append(headline, supportingText, button);
  root.append(row);
}

const observer = new MutationObserver(() => scan());

function observe(root: Node): void {
  if (observedRoots.has(root)) return;
  observedRoots.add(root);
  observer.observe(root, { childList: true, subtree: true });
}

function visit(root: Document | ShadowRoot): void {
  observe(root);
  root.querySelectorAll("*").forEach((element) => {
    if (element.localName === "entity-registry-settings-editor") {
      installApprovalRow(element as ApprovalEditor);
    }
    if (element.shadowRoot) visit(element.shadowRoot);
  });
}

function scan(): void {
  const hass = (document.querySelector("home-assistant") as { hass?: Hass } | null)?.hass;
  if (hass) {
    wrapCallService(hass);
    if (hass !== routedHass) {
      routedHass = hass;
      refreshRoutesWithRetry(hass);
    }
  }
  visit(document);
}

let started = false;

export function startApprovedScripts(
  frontendTranslations: ApprovedScriptsTranslations,
  approvalsChanged = false,
  staleEntityIds: string[] = [],
): void {
  if (started) {
    if (approvalsChanged && routedHass) refreshRoutesWithRetry(routedHass);
    notifyStaleApprovals(staleEntityIds);
    return;
  }
  started = true;
  translations = frontendTranslations;
  installActionInterceptor();
  scan();
}
