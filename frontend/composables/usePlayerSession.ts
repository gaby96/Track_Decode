import type { StoredPlayerSession } from "~/types/game";

export function usePlayerSession(joinToken: string) {
  const session = useState<StoredPlayerSession | null>(
    `player-session:${joinToken}`,
    () => null,
  );

  function read(): StoredPlayerSession | null {
    return session.value;
  }

  function write(value: StoredPlayerSession) {
    session.value = value;
  }

  function clear() {
    session.value = null;
  }

  return {
    session,
    read,
    write,
    clear,
  };
}
