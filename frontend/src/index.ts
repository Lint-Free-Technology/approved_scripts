import { ApprovedScriptsConnection } from "./connection";
import { startApprovedScripts } from "./approved-scripts";
import { ApprovedScriptsTranslations } from "./translations";
import type { Hass } from "./types";
import { ApprovedScriptsVersion } from "./version";

declare const __APPROVED_SCRIPTS_VERSION__: string;

const FRONTEND_VERSION = __APPROVED_SCRIPTS_VERSION__;
const COORDINATOR_KEY = "approvedScriptsCoordinator";

class ApprovedScriptsCoordinator {
  public async start(): Promise<void> {
    const hass = await this.waitForHass();
    const translations = new ApprovedScriptsTranslations();
    const version = new ApprovedScriptsVersion(FRONTEND_VERSION, translations);
    new ApprovedScriptsConnection(
      hass,
      (data) => {
        translations.receive(data);
        version.receive(data);
        if (data.approvals_changed === true || data.script_index_changed === true) {
          window.dispatchEvent(
            new CustomEvent("approved-scripts-data-changed"),
          );
        }
        startApprovedScripts(
          translations,
          data.approvals_changed === true,
          Array.isArray(data.stale_entity_ids)
            ? data.stale_entity_ids.filter((entityId): entityId is string => typeof entityId === "string")
            : [],
        );
      },
      () => version.disconnected(),
    ).connect();
  }

  private async waitForHass(): Promise<Hass> {
    while (true) {
      const hass = (document.querySelector("home-assistant") as { hass?: Hass } | null)?.hass;
      if (hass) return hass;
      await new Promise((resolve) => window.setTimeout(resolve, 100));
    }
  }
}

const windowWithCoordinator = window as Window & {
  [COORDINATOR_KEY]?: ApprovedScriptsCoordinator;
};

console.groupCollapsed(
  `%c💡 Approved Scripts ${FRONTEND_VERSION} IS INSTALLED 💡`,
  "color: white; background-color: #CE3226; padding: 2px 5px; font-weight: bold; border-radius: 5px;",
);
console.log("Frontend bundle version:", FRONTEND_VERSION);
console.groupEnd();

if (!windowWithCoordinator[COORDINATOR_KEY]) {
  windowWithCoordinator[COORDINATOR_KEY] = new ApprovedScriptsCoordinator();
  void windowWithCoordinator[COORDINATOR_KEY]!.start();
}
