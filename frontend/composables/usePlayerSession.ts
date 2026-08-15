import type { StoredPlayerSession } from "~/types/game";

export function usePlayerSession(joinToken: string) {
  const storageKey = `spotify-game:player:${joinToken}`;

  function read(): StoredPlayerSession | null {
    if (import.meta.server) {
      return null;
    }

    const rawValue = localStorage.getItem(storageKey);

    if (!rawValue) {
      return null;
    }

    try {
      return JSON.parse(rawValue) as StoredPlayerSession;
    } catch {
      localStorage.removeItem(storageKey);
      return null;
    }
  }

  function write(value: StoredPlayerSession) {
    if (import.meta.server) {
      return;
    }

    localStorage.setItem(storageKey, JSON.stringify(value));
  }

  function clear() {
    if (import.meta.server) {
      return;
    }

    localStorage.removeItem(storageKey);
  }

  return {
    read,
    write,
    clear,
  };
}
