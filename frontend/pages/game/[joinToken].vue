<template>
  <div class="space-y-8">
    <section class="grid gap-6 rounded-[2rem] border border-white/70 bg-[var(--card-strong)] p-6 shadow-pulse backdrop-blur md:grid-cols-[1.2fr_0.8fr] md:p-8">
      <div>
        <p class="text-sm font-medium uppercase tracking-[0.22em] text-slate-500">
          Live Game View
        </p>
        <h1 class="mt-2 font-display text-4xl text-ink">
          {{ state?.game.name || "Loading room" }}
        </h1>
        <p class="mt-3 max-w-2xl text-sm leading-7 text-slate-600">
          This screen stays in sync with the Django backend through websocket events and refreshed public state snapshots.
        </p>
      </div>

      <div class="grid gap-4 sm:grid-cols-2">
        <div class="rounded-[1.5rem] border border-slate-200/80 bg-white/85 p-4">
          <p class="text-xs uppercase tracking-[0.18em] text-slate-500">Game Status</p>
          <div class="mt-2">
            <StatusBadge v-if="state" :status="state.game.status" />
          </div>
        </div>
        <div class="rounded-[1.5rem] border border-slate-200/80 bg-white/85 p-4">
          <p class="text-xs uppercase tracking-[0.18em] text-slate-500">Socket</p>
          <p class="mt-2 text-sm font-medium text-slate-700">{{ socketLabel }}</p>
        </div>
      </div>
    </section>

    <div v-if="loadError" class="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-700">
      {{ loadError }}
    </div>

    <div class="grid gap-8 xl:grid-cols-[1.1fr_0.9fr]">
      <div class="space-y-8">
        <section
          v-if="storedSession"
          class="rounded-[2rem] border border-white/70 bg-white/90 p-6 shadow-pulse backdrop-blur md:p-8"
        >
          <p class="text-sm font-medium uppercase tracking-[0.22em] text-slate-500">
            Your Seat
          </p>
          <div class="mt-4 flex flex-wrap items-start justify-between gap-4">
            <div>
              <h2 class="font-display text-3xl text-ink">
                {{ storedSession.player.display_name }}
              </h2>
              <p class="mt-2 text-sm text-slate-600">
                {{ playerTeamLabel }}
              </p>
            </div>

            <div
              v-if="playerTeam"
              class="rounded-[1.5rem] border px-4 py-3 text-sm font-bold"
              :style="{
                borderColor: playerTeam.color,
                color: playerTeam.color,
                backgroundColor: `${playerTeam.color}12`,
              }"
            >
              {{ playerTeam.name }}
            </div>
          </div>

          <div
            v-if="playerTeam?.players.length"
            class="mt-5 rounded-[1.5rem] border border-slate-200/80 bg-slate-50/85 p-4"
          >
            <p class="text-xs uppercase tracking-[0.18em] text-slate-500">
              Team Members
            </p>
            <div class="mt-3 flex flex-wrap gap-2">
              <div
                v-for="member in playerTeam.players"
                :key="member.id"
                class="rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700"
              >
                <span class="font-semibold text-ink">{{ member.display_name }}</span>
                <span
                  v-if="playerTeam.leader?.id === member.id"
                  class="ml-2 text-xs font-bold uppercase tracking-[0.14em] text-amber-600"
                >
                  Leader
                </span>
              </div>
            </div>
          </div>
        </section>

        <WinnersShowcase
          v-if="isFinished"
          :finished-at="state?.game.finished_at || null"
          :standings="state?.standings || []"
          :winners="winningTeams"
        >
          <template v-if="isHostForCurrentGame" #actions>
            <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p class="text-xs uppercase tracking-[0.18em] text-slate-500">Host Actions</p>
                <p class="mt-2 text-sm text-slate-600">
                  Restart the room and return everyone to the lobby.
                </p>
              </div>
              <button
                :disabled="restartingGame || !state"
                class="rounded-2xl bg-ink px-5 py-3 text-sm font-bold uppercase tracking-[0.18em] text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
                type="button"
                @click="restartGame"
              >
                {{ restartingGame ? "Restarting..." : "Restart Game" }}
              </button>
            </div>
          </template>
        </WinnersShowcase>

        <CurrentTurnPanel
          v-else
          :turn="state?.current_turn || null"
        />

        <section
          v-if="votingPanelVisible"
          class="rounded-[2rem] border border-white/70 bg-[var(--card)] p-6 shadow-pulse backdrop-blur md:p-8"
        >
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p class="text-sm font-medium uppercase tracking-[0.22em] text-slate-500">
                Leader Voting
              </p>
              <h2 class="font-display text-3xl text-ink">Vote inside your team</h2>
            </div>
            <StatusBadge status="VOTING_OPEN" />
          </div>

          <div v-if="candidatesPending" class="mt-5 text-sm text-slate-600">
            Loading team candidates...
          </div>
          <div v-else-if="candidateError" class="mt-5 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
            {{ candidateError }}
          </div>
          <form v-else-if="candidateData" class="mt-5 space-y-4" @submit.prevent="submitVote">
            <div class="grid gap-3">
              <label
                v-for="candidate in candidateData.candidates"
                :key="candidate.id"
                class="flex items-center justify-between rounded-[1.5rem] border border-slate-200 bg-white/90 px-4 py-4"
                :class="candidateData.has_voted ? 'cursor-not-allowed opacity-70' : 'cursor-pointer hover:border-ink'"
              >
                <div>
                  <p class="text-base font-bold text-ink">{{ candidate.display_name }}</p>
                  <p class="text-sm text-slate-500">{{ candidate.team_name }}</p>
                </div>
                <input
                  v-model="selectedCandidateId"
                  :value="candidate.id"
                  :disabled="candidateData.has_voted"
                  class="h-4 w-4 accent-ink"
                  name="candidate"
                  type="radio"
                >
              </label>
            </div>

            <div
              v-if="candidateData.has_voted"
              class="rounded-2xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-800"
            >
              Your vote has already been recorded and can no longer be changed.
            </div>

            <div
              v-if="voteMessage"
              class="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800"
            >
              {{ voteMessage }}
            </div>

            <button
              :disabled="submittingVote || !selectedCandidateId || candidateData.has_voted"
              class="rounded-2xl bg-ink px-5 py-3 text-sm font-bold uppercase tracking-[0.18em] text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
              type="submit"
            >
              {{
                candidateData.has_voted
                  ? "Vote Submitted"
                  : submittingVote
                    ? "Saving Vote..."
                    : "Submit Vote"
              }}
            </button>
          </form>
        </section>

        <section
          v-if="leaderActionVisible"
          class="rounded-[2rem] border border-amber-200 bg-amber-50 p-6 shadow-pulse md:p-8"
        >
          <p class="text-sm font-medium uppercase tracking-[0.22em] text-amber-700">
            Leader Action
          </p>
          <h2 class="mt-2 font-display text-3xl text-ink">Spin the genre</h2>
          <p class="mt-3 max-w-2xl text-sm leading-7 text-slate-700">
            {{ leaderActionHint }}
          </p>

          <div v-if="spinMessage" class="mt-5 rounded-2xl border border-amber-200 bg-white/70 px-4 py-3 text-sm text-amber-800">
            {{ spinMessage }}
          </div>

          <button
            :disabled="spinningGenre || !canSpinGenre || !state?.current_turn"
            class="mt-5 rounded-2xl bg-amber-500 px-5 py-3 text-sm font-bold uppercase tracking-[0.18em] text-white hover:bg-amber-600 disabled:cursor-not-allowed disabled:bg-amber-300"
            type="button"
            @click="spinGenre"
          >
            {{ spinningGenre ? "Selecting..." : "Spin Genre" }}
          </button>
        </section>
      </div>

      <StandingsTable
        v-if="!isFinished"
        :standings="state?.standings || []"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import type {
  GameStateResponse,
  HostGame,
  PlayerSessionStateResponse,
  StoredPlayerSession,
  VotingCandidatesResponse,
} from "~/types/game";

const route = useRoute();
const config = useRuntimeConfig();
const { apiFetch, getErrorMessage } = useApi();
const { getCsrfToken } = useCsrfToken();
const joinToken = computed(() => String(route.params.joinToken));
const resultsRoute = computed(() => `/game/${joinToken.value}/results`);
const playerSession = usePlayerSession(joinToken.value);

const loadError = ref("");
const socketState = ref<"connecting" | "live" | "offline">("connecting");
const storedSession = ref<StoredPlayerSession | null>(null);
const candidateData = ref<VotingCandidatesResponse | null>(null);
const candidateError = ref("");
const candidatesPending = ref(false);
const selectedCandidateId = ref("");
const submittingVote = ref(false);
const voteMessage = ref("");
const spinningGenre = ref(false);
const spinMessage = ref("");
const restartingGame = ref(false);
const isHostForCurrentGame = ref(false);
let socket: WebSocket | null = null;
let reconnectTimeoutId: ReturnType<typeof window.setTimeout> | null = null;
let statePollIntervalId: ReturnType<typeof window.setInterval> | null = null;
let latestVotingRequestId = 0;

useSeoMeta({
  title: `Game ${joinToken.value}`,
});

const { data: state, refresh } = await useAsyncData<GameStateResponse>(
  `game-state-${joinToken.value}`,
  async () => {
    try {
      loadError.value = "";
      return await apiFetch(`/games/${joinToken.value}/state/`);
    } catch (error) {
      loadError.value = getErrorMessage(
        error,
        "The public game state could not be loaded.",
      );
      throw error;
    }
  },
);

const socketLabel = computed(() => {
  if (socketState.value === "live") {
    return "Live";
  }

  if (socketState.value === "connecting") {
    return "Connecting";
  }

  return "Offline";
});

const playerTeam = computed(() => {
  if (!storedSession.value?.player.team || !state.value) {
    return null;
  }

  return state.value.standings.find(
    (entry) => entry.id === String(storedSession.value?.player.team),
  ) || null;
});
const playerTeamLabel = computed(() => {
  if (!storedSession.value) {
    return "";
  }

  if (!storedSession.value.player.team_name) {
    return "You have not been assigned to a team yet.";
  }

  if (
    playerTeam.value?.leader?.id
    && playerTeam.value.leader.id === storedSession.value.player.id
  ) {
    return `You are on ${storedSession.value.player.team_name} and you are the elected leader.`;
  }

  return `You are on ${storedSession.value.player.team_name}.`;
});

const isFinished = computed(() => (
  state.value?.game.status === "FINISHED"
));

const winningTeams = computed(() => (
  (state.value?.standings || []).filter((entry) => entry.rank === 1)
));

const votingPanelVisible = computed(() => (
  !!storedSession.value
  && state.value?.game.status === "VOTING_OPEN"
  && (
    candidatesPending.value
    || !!candidateError.value
    || candidateData.value?.requires_vote === true
  )
));

const canSpinGenre = computed(() => {
  const currentTurn = state.value?.current_turn;
  const session = storedSession.value;
  const leader = playerTeam.value?.leader;

  return !!(
    currentTurn
    && session
    && state.value?.game.status === "IN_PROGRESS"
    && currentTurn.status === "ACTIVE"
    && String(session.player.team) === currentTurn.team.id
    && leader?.id === session.player.id
  );
});
const leaderActionVisible = computed(() => {
  const currentTurn = state.value?.current_turn;
  const session = storedSession.value;

  return !!(
    currentTurn
    && session
    && state.value?.game.status === "IN_PROGRESS"
    && currentTurn.status === "ACTIVE"
    && String(session.player.team) === currentTurn.team.id
  );
});
const leaderActionHint = computed(() => {
  const currentTurn = state.value?.current_turn;
  const session = storedSession.value;

  if (!currentTurn) {
    return "Waiting for the next active turn.";
  }

  if (canSpinGenre.value) {
    return "You are the elected leader for the active team. This action asks the backend to select the genre.";
  }

  if (!session) {
    return "Join the room to see who can select the genre for this turn.";
  }

  if (String(session.player.team) !== currentTurn.team.id) {
    return `${currentTurn.team.name} is up now. Their leader will select the genre.`;
  }

  if (playerTeam.value?.leader?.id) {
    return `${playerTeam.value.leader.display_name} is your team's leader and must select the genre for this turn.`;
  }

  return "Waiting for the active team's leader to select the genre.";
});

async function refreshHostAccess() {
  try {
    const hostGames = await apiFetch<HostGame[]>("/games/");
    isHostForCurrentGame.value = hostGames.some(
      (game) => game.join_token === joinToken.value,
    );
  } catch {
    isHostForCurrentGame.value = false;
  }
}

onMounted(async () => {
  storedSession.value = playerSession.read();
  await refreshHostAccess();
  await refreshPlayerSession();
  await refreshVotingPanel();
  connectSocket();

  statePollIntervalId = window.setInterval(() => {
    void refreshRealtimeState();
  }, 2000);
});

onBeforeUnmount(() => {
  if (statePollIntervalId !== null) {
    window.clearInterval(statePollIntervalId);
    statePollIntervalId = null;
  }
  if (reconnectTimeoutId !== null) {
    window.clearTimeout(reconnectTimeoutId);
    reconnectTimeoutId = null;
  }
  socket?.close();
});

watch(
  () => state.value?.game.status,
  async (status, previousStatus) => {
    if (
      status === "FINISHED"
      && route.path !== resultsRoute.value
    ) {
      void navigateTo(resultsRoute.value, {
        replace: true,
      });
    }

    if (status !== previousStatus) {
      await refreshVotingPanel();
    }
  },
  { immediate: true },
);

watch(
  () => storedSession.value?.sessionToken,
  async (sessionToken, previousSessionToken) => {
    if (sessionToken && sessionToken !== previousSessionToken) {
      await refreshPlayerSession();
      await refreshVotingPanel();
    }
  },
);

async function refreshVotingPanel() {
  if (!storedSession.value || state.value?.game.status !== "VOTING_OPEN") {
    candidateData.value = null;
    candidateError.value = "";
    candidatesPending.value = false;
    selectedCandidateId.value = "";
    voteMessage.value = "";
    return;
  }

  const requestId = ++latestVotingRequestId;
  const hasCandidateData = candidateData.value !== null;

  if (!hasCandidateData) {
    candidatesPending.value = true;
  }

  try {
    const response = await apiFetch<VotingCandidatesResponse>(
      `/games/join/${joinToken.value}/voting/candidates/`,
      {
        method: "POST",
        body: {
          session_token: storedSession.value.sessionToken,
        },
      },
    );

    if (requestId !== latestVotingRequestId) {
      return;
    }

    candidateData.value = response;
    candidateError.value = "";

    if (!response.candidates.some((candidate) => candidate.id === selectedCandidateId.value)) {
      selectedCandidateId.value = "";
    }
  } catch (error) {
    if (requestId !== latestVotingRequestId) {
      return;
    }

    candidateError.value = getErrorMessage(
      error,
      "Your voting panel could not be loaded.",
    );
  } finally {
    if (requestId === latestVotingRequestId) {
      candidatesPending.value = false;
    }
  }
}

async function refreshPlayerSession() {
  if (!storedSession.value) {
    return;
  }

  try {
    const response = await apiFetch<PlayerSessionStateResponse>(
      `/games/join/${joinToken.value}/session/`,
      {
        method: "POST",
        body: {
          session_token: storedSession.value.sessionToken,
        },
      },
    );

    const updatedSession = {
      ...storedSession.value,
      player: response.player,
    };

    storedSession.value = updatedSession;
    playerSession.write(updatedSession);
  } catch {
    // Keep the local session if the hydration call fails.
  }
}

function connectSocket() {
  if (reconnectTimeoutId !== null) {
    window.clearTimeout(reconnectTimeoutId);
    reconnectTimeoutId = null;
  }

  socketState.value = "connecting";
  socket = new WebSocket(
    `${config.public.wsOrigin}/ws/games/${joinToken.value}/`,
  );

  socket.addEventListener("open", () => {
    socketState.value = "live";
  });

  socket.addEventListener("close", () => {
    socketState.value = "offline";
    scheduleSocketReconnect();
  });

  socket.addEventListener("error", () => {
    socketState.value = "offline";
  });

  socket.addEventListener("message", async (event) => {
    const payload = JSON.parse(event.data) as {
      type?: string;
      data?: Record<string, unknown>;
    };

    if (payload.type === "connection.ready") {
      return;
    }

    applyRealtimeEvent(payload);
    await refreshRealtimeState();
  });
}

function scheduleSocketReconnect() {
  if (reconnectTimeoutId !== null) {
    return;
  }

  reconnectTimeoutId = window.setTimeout(() => {
    reconnectTimeoutId = null;
    connectSocket();
  }, 1500);
}

function applyRealtimeEvent(payload: {
  type?: string;
  data?: Record<string, unknown>;
}) {
  if (!state.value || !payload.type) {
    return;
  }

  const applyActiveTurnSnapshot = (activeTurn: Record<string, unknown>) => {
    const activeTeam = activeTurn.team;

    state.value = {
      ...state.value,
      game: {
        ...state.value.game,
        status: "IN_PROGRESS",
        current_round: Number(payload.data?.current_round || activeTurn.round_number || state.value.game.current_round || 1),
      },
      current_turn: {
        id: String(activeTurn.id || ""),
        round_number: Number(activeTurn.round_number || 1),
        turn_position: Number(activeTurn.turn_position || 1),
        status: String(activeTurn.status || "ACTIVE"),
        team: {
          id: String((activeTeam as Record<string, unknown> | undefined)?.id || ""),
          name: String((activeTeam as Record<string, unknown> | undefined)?.name || ""),
          color: String((activeTeam as Record<string, unknown> | undefined)?.color || ""),
        },
        genre: null,
        track_ready: false,
      },
    };
  };

  if (payload.type === "answer.revealed") {
    const answer = payload.data?.answer;

    if (
      state.value.current_turn
      && typeof answer === "object"
      && answer !== null
    ) {
      state.value = {
        ...state.value,
        current_turn: {
          ...state.value.current_turn,
          status: "ANSWER_REVEALED",
          answer: {
            title: String((answer as Record<string, unknown>).title || ""),
            artist: String((answer as Record<string, unknown>).artist || ""),
            album: String((answer as Record<string, unknown>).album || ""),
            artwork_url: String((answer as Record<string, unknown>).artwork_url || ""),
          },
        },
      };
    }

    return;
  }

  if (payload.type === "game.started") {
    const activeTurn = payload.data?.active_turn;

    if (
      typeof activeTurn === "object"
      && activeTurn !== null
    ) {
      applyActiveTurnSnapshot(activeTurn as Record<string, unknown>);
    }

    return;
  }

  if (payload.type === "turn.advanced" || payload.type === "round.started") {
    const activeTurn = payload.data?.active_turn;

    if (
      typeof activeTurn === "object"
      && activeTurn !== null
    ) {
      applyActiveTurnSnapshot(activeTurn as Record<string, unknown>);
    }
  }
}

async function refreshRealtimeState() {
  await refresh();
  await refreshPlayerSession();
  await refreshVotingPanel();
}

async function submitVote() {
  if (!storedSession.value || !selectedCandidateId.value) {
    return;
  }

  submittingVote.value = true;
  voteMessage.value = "";
  candidateError.value = "";

  try {
    const response = await apiFetch<{
      detail: string;
    }>(`/games/join/${joinToken.value}/voting/`, {
      method: "POST",
      headers: {
        "X-Player-Token": storedSession.value.sessionToken,
      },
      body: {
        candidate_id: selectedCandidateId.value,
      },
    });

    voteMessage.value = response.detail;
    await refreshVotingPanel();
  } catch (error) {
    candidateError.value = getErrorMessage(
      error,
      "Your vote could not be saved.",
    );
  } finally {
    submittingVote.value = false;
  }
}

async function restartGame() {
  if (!state.value || restartingGame.value || !isHostForCurrentGame.value) {
    return;
  }

  restartingGame.value = true;

  try {
    await apiFetch(`/games/${state.value.game.id}/restart/`, {
      method: "POST",
      headers: {
        "X-CSRFToken": getCsrfToken(),
      },
    });

    await refresh();
    await refreshPlayerSession();
    await refreshVotingPanel();
    await navigateTo(`/game/${joinToken.value}`, {
      replace: true,
    });
  } catch (error) {
    loadError.value = getErrorMessage(
      error,
      "The game could not be restarted.",
    );
  } finally {
    restartingGame.value = false;
  }
}

async function spinGenre() {
  if (!storedSession.value || !state.value?.current_turn) {
    return;
  }

  spinningGenre.value = true;
  spinMessage.value = "";

  try {
    const response = await apiFetch<{
      genre: {
        name: string;
      };
    }>(
      `/games/join/${joinToken.value}/turns/${state.value.current_turn.id}/genre/`,
      {
        method: "POST",
        body: {
          session_token: storedSession.value.sessionToken,
        },
      },
    );

    spinMessage.value = `Genre selected: ${response.genre.name}`;
    await refresh();
  } catch (error) {
    spinMessage.value = getErrorMessage(
      error,
      "The backend rejected the genre selection.",
    );
  } finally {
    spinningGenre.value = false;
  }
}
</script>
