import type { BackendConnectionData, BackendConnectionMessage, Hass } from "./types";

/**
 * Maintain the browser's subscription to the integration, following UIX's
 * connection lifecycle. Home Assistant re-establishes subscribeMessage calls
 * after a WebSocket reconnect, at which point the backend sends fresh data.
 */
export class ApprovedScriptsConnection {
  private connected = false;
  private lifecycleAttached = false;
  private componentSubscriptionAttached = false;

  public constructor(
    private readonly hass: Hass,
    private readonly onData: (data: BackendConnectionData) => void,
    private readonly onDisconnect: () => void,
  ) {}

  public connect(): void {
    this.connectBackend();
    this.observeComponentLoads();
    this.observeConnectionLifecycle();
  }

  private connectBackend(): void {
    const { connection } = this.hass;
    if (!connection.subscribeMessage) {
      console.error("Approved Scripts: WebSocket subscriptions are unavailable.");
      return;
    }
    console.info("Approved Scripts: subscribing to backend connection data.");
    void connection
      .subscribeMessage(
        (message) => this.receiveMessage(message),
        {
          type: "approved_scripts/connect",
          language: this.hass.language || "en",
        },
      )
      .catch((err: unknown) => {
        console.error("Approved Scripts: unable to connect to the backend.", err);
      });
  }

  private observeComponentLoads(): void {
    const { connection } = this.hass;
    if (this.componentSubscriptionAttached || !connection.subscribeEvents) return;
    this.componentSubscriptionAttached = true;
    void connection.subscribeEvents((event) => {
      if (event.data?.component === "approved_scripts") this.connectBackend();
    }, "component_loaded");
  }

  private observeConnectionLifecycle(): void {
    const { connection } = this.hass;
    if (this.lifecycleAttached || !connection.addEventListener) return;
    this.lifecycleAttached = true;
    connection.addEventListener("ready", () => this.onConnected());
    connection.addEventListener("disconnected", () => this.onDisconnected());
  }

  private onConnected(): void {
    this.connected = true;
    console.info("Approved Scripts: WebSocket connected.");
  }

  private onDisconnected(): void {
    this.connected = false;
    console.info("Approved Scripts: WebSocket disconnected.");
    this.onDisconnect();
  }

  private receiveMessage(message: BackendConnectionMessage): void {
    if (!this.connected) this.onConnected();
    this.onData(message.result ?? {});
  }
}
