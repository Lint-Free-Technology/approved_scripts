export type WsResult = Record<string, unknown>;

export type BackendConnectionData = {
  approvals_changed?: unknown;
  script_index_changed?: unknown;
  stale_entity_ids?: unknown;
  version?: unknown;
  translations?: unknown;
};

export type BackendConnectionMessage = {
  result?: BackendConnectionData;
};

export type Hass = {
  callService: (...args: unknown[]) => Promise<unknown>;
  connection: {
    sendMessagePromise: (message: Record<string, unknown>) => Promise<WsResult>;
    addEventListener?: (
      type: "ready" | "disconnected",
      listener: () => void,
    ) => void;
    subscribeMessage?: (
      callback: (message: BackendConnectionMessage) => void,
      message: Record<string, unknown>,
    ) => Promise<unknown>;
    subscribeEvents?: (
      callback: (event: { data?: Record<string, unknown> }) => void,
      eventType?: string,
    ) => Promise<unknown>;
  };
  user?: { is_admin?: boolean };
  language?: string;
};
