/* Admin management page. It only lists scripts and opens the shared editor. */

type Hass = {
  language?: string;
  connection: {
    sendMessagePromise: (message: Record<string, unknown>) => Promise<unknown>;
  };
};

type ScriptRow = {
  entity_id: string;
  name: string;
  approval_state: "approved" | "stale" | "suspended" | "unapproved" | "not_required" | "not_supported";
  approval_available: boolean;
};

type ApprovalWindow = Window & {
  approvedScriptsOpenApproval?: (hass: Hass, entityId: string, anchor?: Element) => Promise<void>;
};

// These are capability states, not display strings.  Sorting therefore remains
// meaningful in every translated frontend.  The server's name ordering is
// preserved within each rank.
const APPROVAL_RANK: Record<ScriptRow["approval_state"], number> = {
  approved: 0,
  unapproved: 1,
  stale: 1,
  suspended: 1,
  not_supported: 2,
  not_required: 3,
};

class ApprovedScriptsPanel extends HTMLElement {
  private _hass?: Hass;
  private _translations: Record<string, string> = {};
  private _scripts: ScriptRow[] = [];
  private _narrow = false;
  private _loading?: Promise<void>;
  private _loadedConnection?: Hass["connection"];
  private _loadedLanguage?: string;
  private _refreshRequested = false;
  private readonly _handleDataChanged = () => this.refresh();

  set hass(value: Hass | undefined) {
    this._hass = value;
    // HA replaces this state object whenever state changes. `load()` decides
    // whether its stable connection or language actually needs new data.
    this.load();
  }

  get hass(): Hass | undefined {
    return this._hass;
  }

  set narrow(value: boolean) {
    if (value === this._narrow) return;
    this._narrow = value;
    this.render();
  }

  get narrow(): boolean {
    return this._narrow;
  }

  connectedCallback(): void {
    window.addEventListener("approved-scripts-data-changed", this._handleDataChanged);
    this.render();
    this.load();
  }

  disconnectedCallback(): void {
    window.removeEventListener("approved-scripts-data-changed", this._handleDataChanged);
  }

  private text(key: string, values: Record<string, string> = {}): string {
    return (this._translations[key] || key).replace(/\{(\w+)\}/g, (_, name: string) => values[name] || "");
  }

  private load(): void {
    const hass = this._hass;
    const language = hass?.language || "en";
    if (
      !hass ||
      this._loading ||
      (this._loadedConnection === hass.connection && this._loadedLanguage === language)
    ) return;
    this._loading = (async () => {
      try {
        const [translations, scripts] = await Promise.all([
          hass.connection.sendMessagePromise({
            type: "approved_scripts/frontend_translations",
            language,
          }),
          hass.connection.sendMessagePromise({ type: "approved_scripts/admin_script_list" }),
        ]);
        // A state update changes the hass object, but not its connection.
        // Discard only a response from an actual reconnect or locale change.
        if (
          hass.connection !== this._hass?.connection ||
          language !== (this._hass?.language || "en")
        ) return;
        if (translations && typeof translations === "object" && !Array.isArray(translations)) {
          this._translations = translations as Record<string, string>;
        }
        this._scripts = Array.isArray(scripts) ? scripts as ScriptRow[] : [];
        this._loadedConnection = hass.connection;
        this._loadedLanguage = language;
        this.render();
      } catch (err) {
        console.error("Approved Scripts: could not load the admin panel", err);
      } finally {
        this._loading = undefined;
        if (this._refreshRequested) {
          this._refreshRequested = false;
          this._loadedConnection = undefined;
          this._loadedLanguage = undefined;
          this.load();
          return;
        }
        // A reconnect can occur while a request is in flight.
        if (
          hass.connection !== this._hass?.connection ||
          language !== (this._hass?.language || "en")
        ) this.load();
      }
    })();
  }

  private refresh(): void {
    // The backend has confirmed a script reload or approval-state change.
    // Invalidate only this data cache; normal Home Assistant state updates do
    // not reach this path.
    if (this._loading) {
      this._refreshRequested = true;
      return;
    }
    this._loadedConnection = undefined;
    this._loadedLanguage = undefined;
    this.load();
  }

  private notify(key: string, values: Record<string, string> = {}): void {
    const shell = document.querySelector("home-assistant");
    shell?.dispatchEvent(
      new CustomEvent("hass-notification", {
        detail: { message: this.text(key, values), duration: 5000 },
      }),
    );
  }

  private async configure(entityId: string): Promise<void> {
    if (!this._hass) return;
    let opener = (window as ApprovalWindow).approvedScriptsOpenApproval;
    // The panel and extra module can arrive in either order after a frontend
    // reload. Wait for the single shared editor rather than dropping a click.
    for (let attempt = 0; !opener && attempt < 40; attempt += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 50));
      opener = (window as ApprovalWindow).approvedScriptsOpenApproval;
    }
    if (!opener) {
      this.notify("panel.editor_unavailable");
      return;
    }
    try {
      // An entity-settings button supplies an anchor. The panel deliberately
      // does not: HA's adaptive popover then uses its centred dialog mode.
      await opener(this._hass, entityId);
    } catch (err) {
      console.error("Approved Scripts: could not open the approval editor", err);
      this.notify("panel.editor_failed");
    }
  }

  private centreActionColumnHeader(table: HTMLElement): void {
    // `ha-data-table` renders its column headers in its shadow root. Add a
    // table-local style after its first render so this only affects Actions.
    requestAnimationFrame(() => {
      const tableRoot = table.shadowRoot;
      if (
        !tableRoot ||
        tableRoot.querySelector("style[data-approved-scripts-actions-header]")
      ) return;
      const style = document.createElement("style");
      style.dataset.approvedScriptsActionsHeader = "";
      style.textContent = ".mdc-data-table__header-cell:last-child { text-align:center; }";
      tableRoot.append(style);
    });
  }

  private render(): void {
    const root = this.shadowRoot || this.attachShadow({ mode: "open" });
    root.replaceChildren();
    const style = document.createElement("style");
    style.textContent = `
      :host {
        display:block;
        height:100%;
        color:var(--primary-text-color);
        --app-header-background-color:var(--sidebar-background-color);
        --app-header-text-color:var(--sidebar-text-color);
        --app-header-border-bottom:1px solid var(--divider-color);
        --ha-card-border-radius:var(--ha-config-card-border-radius, 8px);
      }
      /* Keep the inset on our own stable wrapper. ha-config-section changes its
         internal padding as Core changes width modes, which made this appear
         and disappear between panel renders. */
      .content {
        box-sizing: border-box;
        padding: var(--ha-space-2);
      }
      ha-config-section {
        box-sizing:border-box;
        direction:ltr;
        padding:0;
      }
      ha-data-table { display:block; }
    `;
    const appBar = document.createElement("ha-top-app-bar-fixed") as HTMLElement & {
      backButton?: boolean;
    };
    appBar.backButton = true;
    const title = document.createElement("div");
    title.slot = "title";
    title.textContent = this.text("panel.title");
    const content = document.createElement("div");
    content.className = "content ha-scrollbar";
    const section = document.createElement("ha-config-section") as HTMLElement & { isWide?: boolean };
    // Core's config section is 640px in narrow mode and 1040px when wide.
    // Use the panel's responsive signal rather than leaving it narrow always.
    section.isWide = !this._narrow;
    section.setAttribute("full-width", "");
    const table = document.createElement("ha-data-table") as HTMLElement & {
      columns?: unknown;
      data?: unknown[];
      id?: string;
      autoHeight?: boolean;
      noDataText?: string;
    };
    table.id = "entity_id";
    table.autoHeight = true;
    table.noDataText = this.text("panel.empty");
    table.columns = {
      name: { title: this.text("panel.column.name"), main: true, sortable: true, filterable: true },
      entity_id: { title: this.text("panel.column.entity_id"), sortable: true, filterable: true },
      approval_state: {
        title: this.text("panel.column.state"),
        sortable: true,
        filterable: true,
        valueColumn: "approval_rank",
        direction: "asc",
      },
      action: {
        title: this.text("panel.column.actions"),
        type: "flex",
        showNarrow: true,
        lastFixed: true,
        minWidth: "176px",
        maxWidth: "176px",
        flex: 0.001,
        template: (script: ScriptRow) => {
          if (!script.approval_available) return "";
          const button = document.createElement("ha-button") as HTMLElement;
          button.setAttribute("appearance", "plain");
          button.setAttribute("variant", "brand");
          button.setAttribute("size", "s");
          button.textContent = this.text("panel.configure");
          button.addEventListener("click", () => void this.configure(script.entity_id));
          // Lit accepts DOM nodes as a rendered child. The cast keeps this
          // vanilla panel independent of a bundled Lit runtime.
          return button as unknown as string;
        },
      },
    };
    table.data = this._scripts.map((script) => ({
      ...script,
      approval_rank: APPROVAL_RANK[script.approval_state],
      approval_state: this.text(`panel.state.${script.approval_state}`),
    }));
    section.append(table);
    content.append(section);
    appBar.append(title, content);
    root.append(style, appBar);
    this.centreActionColumnHeader(table);
  }
}

if (!customElements.get("approved-scripts-panel")) {
  customElements.define("approved-scripts-panel", ApprovedScriptsPanel);
}
