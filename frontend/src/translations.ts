import type { BackendConnectionData } from "./types";

type TranslationValues = Record<string, string | number>;

/**
 * Frontend strings are supplied by Home Assistant's backend translation
 * loader. Keeping this small stateful adapter means reconnects can refresh
 * the locale without coupling UI code to the WebSocket payload shape.
 */
export class ApprovedScriptsTranslations {
  private resources: Record<string, string> = {};

  public receive(data: BackendConnectionData): void {
    const resources = data.translations;
    if (!resources || typeof resources !== "object" || Array.isArray(resources)) return;
    const translatedResources: Record<string, string> = {};
    for (const [key, value] of Object.entries(resources)) {
      if (typeof value === "string") translatedResources[key] = value;
    }
    this.resources = translatedResources;
  }

  public text(key: string, values: TranslationValues = {}): string {
    const template = this.resources[key];
    if (!template) {
      console.error(`Approved Scripts: missing frontend translation "${key}".`);
      return key;
    }
    return template.replace(/\{([\w_]+)\}/g, (placeholder, name: string) =>
      name in values ? String(values[name]) : placeholder,
    );
  }
}
