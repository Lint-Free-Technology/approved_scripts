import type { BackendConnectionData } from "./types";
import type { ApprovedScriptsTranslations } from "./translations";

const TOAST_ID = "approved-scripts-reload";
const RELOAD_DELAY_SECONDS = 60;

type HomeAssistantShell = HTMLElement & { shadowRoot: ShadowRoot };

/** Version mismatch handling, following UIX's controlled reload countdown. */
export class ApprovedScriptsVersion {
  private notificationPending = false;
  private reloadIntervalId?: number;

  public constructor(
    private readonly frontendVersion: string,
    private readonly translations: ApprovedScriptsTranslations,
  ) {}

  public receive(data: BackendConnectionData): void {
    const backendVersion = data.version;
    if (typeof backendVersion !== "string") {
      console.error("Approved Scripts: backend connection did not include a version.");
      return;
    }
    console.info("Approved Scripts connection data:", {
      frontend: this.frontendVersion,
      backend: backendVersion,
    });
    if (backendVersion !== this.frontendVersion && !this.notificationPending) {
      this.notificationPending = true;
      void this.showReloadNotification(backendVersion);
    }
  }

  public disconnected(): void {
    this.notificationPending = false;
    this.clearReloadTimer();
  }

  private async waitForNoToast(): Promise<void> {
    while (this.findToast()) {
      await new Promise((resolve) => window.setTimeout(resolve, 1_000));
    }
  }

  private async showReloadNotification(backendVersion: string): Promise<void> {
    await this.waitForNoToast();
    this.clearReloadTimer();
    let seconds = RELOAD_DELAY_SECONDS;
    const base = this.hassBaseElement();
    if (!base) {
      this.notificationPending = false;
      return;
    }

    const activateReload = () => {
      this.clearReloadTimer();
      void this.clearCachesAndReload();
    };
    const dismiss = () => this.clearReloadTimer();
    const messageBase = this.translations.text("version.updated", {
      version: backendVersion,
      frontend_version: this.frontendVersion,
    });
    const showToast = () => {
      const message = `${messageBase}${seconds === RELOAD_DELAY_SECONDS ? "" : `${seconds}s`}`;
      base.dispatchEvent(
        new CustomEvent("hass-notification", {
          detail: {
            id: TOAST_ID,
            message,
            action: {
              text: this.translations.text("button.reload_now"),
              action: activateReload,
              primary: true,
            },
            secondaryAction: { text: this.translations.text("button.cancel"), action: dismiss },
            duration: -1,
            dismiss,
          },
        }),
      );
    };

    showToast();
    let reloadTickRunning = false;
    this.reloadIntervalId = window.setInterval(async () => {
      if (reloadTickRunning) return;
      reloadTickRunning = true;
      try {
        const first = seconds === RELOAD_DELAY_SECONDS;
        seconds -= 1;
        if (seconds <= 0) {
          activateReload();
          return;
        }
        const toastRoot = this.findReloadToast();
        if (toastRoot) {
          let style = toastRoot.querySelector("style[data-approved-scripts-style]");
          if (!style && first) {
            style = document.createElement("style");
            style.setAttribute("data-approved-scripts-style", "");
            toastRoot.prepend(style);
          }
          if (style) {
            style.textContent = `span.message::after { content: "${seconds}s"; }`;
            return;
          }
        }
        showToast();
      } finally {
        reloadTickRunning = false;
      }
    }, 1_000);
  }

  private clearReloadTimer(): void {
    if (this.reloadIntervalId === undefined) return;
    window.clearInterval(this.reloadIntervalId);
    this.reloadIntervalId = undefined;
  }

  private hassBaseElement(): HomeAssistantShell | null {
    return document.querySelector("home-assistant") as HomeAssistantShell | null;
  }

  private findToast(): HTMLElement | null {
    const base = this.hassBaseElement();
    const manager = base?.shadowRoot?.querySelector("notification-manager");
    return (manager?.shadowRoot?.querySelector("ha-toast") as HTMLElement | null) ?? null;
  }

  private findReloadToast(): ShadowRoot | null {
    const base = this.hassBaseElement();
    const manager = base?.shadowRoot?.querySelector("notification-manager");
    const toast = manager?.shadowRoot?.querySelector(
      `ha-toast[data-notification-key="identified-${TOAST_ID}"]`,
    ) as HTMLElement | null;
    return toast?.shadowRoot ?? null;
  }

  private async clearCachesAndReload(): Promise<void> {
    try {
      if ("caches" in window) {
        await Promise.all((await window.caches.keys()).map((name) => window.caches.delete(name)));
      }
    } catch (err) {
      console.error("Approved Scripts: failed to clear caches before reload.", err);
    }
    window.location.reload();
  }
}
