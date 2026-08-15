<template>
  <article class="rounded-[1.75rem] border border-slate-200/80 bg-white/90 p-5 shadow-pulse">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <p class="text-xs uppercase tracking-[0.18em] text-slate-500">Game Room</p>
        <h3 class="mt-2 text-2xl font-bold text-ink">{{ game.name }}</h3>
        <p class="mt-2 text-sm text-slate-600">
          {{ game.number_of_teams }} teams · {{ game.rounds_per_team }} round{{ game.rounds_per_team === 1 ? "" : "s" }} per team · host {{ game.host_username }}
        </p>
      </div>
      <StatusBadge :status="game.status" />
    </div>

    <div class="mt-5 grid gap-5 lg:grid-cols-[220px_1fr]">
      <div class="rounded-[1.5rem] border border-slate-200 bg-slate-50 p-4">
        <div class="flex min-h-[188px] items-center justify-center rounded-[1.25rem] bg-white">
          <img
            v-if="qrCodeDataUrl"
            :src="qrCodeDataUrl"
            :alt="`QR code for ${game.name}`"
            class="h-44 w-44"
          >
          <p v-else class="px-4 text-center text-sm text-slate-500">
            Generating QR code...
          </p>
        </div>
      </div>

      <div class="space-y-4">
        <div class="grid gap-4 lg:grid-cols-[minmax(0,1fr)_220px]">
          <div class="rounded-[1.5rem] border border-slate-200 bg-slate-50 p-4">
            <p class="text-xs uppercase tracking-[0.18em] text-slate-500">Join Link</p>
            <p class="mt-2 break-all text-sm font-medium text-slate-700">{{ joinUrl }}</p>
          </div>

          <div class="rounded-[1.5rem] border border-slate-200 bg-slate-50 p-4">
            <p class="text-xs uppercase tracking-[0.18em] text-slate-500">Game Code</p>
            <p class="mt-2 text-2xl font-black tracking-[0.18em] text-ink">{{ game.join_code }}</p>
            <p class="mt-2 text-xs text-slate-500">Players can type this code on the join screen.</p>
          </div>
        </div>

        <div class="rounded-[1.5rem] border border-slate-200 bg-slate-50 p-4">
          <p class="text-xs uppercase tracking-[0.18em] text-slate-500">Host Controls</p>
          <p class="mt-2 text-sm text-slate-600">{{ hostActionHint }}</p>

          <div class="mt-4 rounded-[1.25rem] border border-slate-200 bg-white/85 p-4">
            <div class="flex flex-wrap items-end gap-3">
              <label class="min-w-0 flex-1 space-y-2">
                <span class="text-xs uppercase tracking-[0.18em] text-slate-500">Rounds Per Team</span>
                <input
                  v-model.number="roundsPerTeamInput"
                  :min="minimumRoundsPerTeam"
                  class="w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm text-ink outline-none focus:border-ink"
                  type="number"
                >
              </label>
              <button
                :disabled="savingRoundsPerTeam || !canSaveRoundsPerTeam"
                class="rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm font-bold uppercase tracking-[0.18em] text-slate-700 hover:border-slate-400 disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-100 disabled:text-slate-400"
                type="button"
                @click="saveRoundsPerTeam"
              >
                {{ savingRoundsPerTeam ? "Saving..." : "Save Rounds" }}
              </button>
            </div>
            <p class="mt-2 text-xs text-slate-500">
              {{
                effectiveGameStatus === "IN_PROGRESS" || effectiveGameStatus === "PAUSED"
                  ? `While the game is live, rounds cannot be reduced below round ${effectiveCurrentRound}.`
                  : "You can change this before the next full run of the game."
              }}
            </p>
          </div>

          <div class="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <button
              :disabled="closingRegistration || !canCloseRegistration"
              class="rounded-2xl bg-ink px-4 py-3 text-sm font-bold uppercase tracking-[0.18em] text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
              type="button"
              @click="closeRegistration"
            >
              {{ closingRegistration ? "Closing..." : "Close Registration" }}
            </button>
            <button
              :disabled="assigningTeams || !canAssignTeams"
              class="rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm font-bold uppercase tracking-[0.18em] text-slate-700 hover:border-slate-400 disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-100 disabled:text-slate-400"
              type="button"
              @click="assignTeams"
            >
              {{ assigningTeams ? "Assigning..." : "Assign Teams" }}
            </button>
            <button
              :disabled="openingVoting || !canOpenVoting"
              class="rounded-2xl bg-amber-500 px-4 py-3 text-sm font-bold uppercase tracking-[0.18em] text-white hover:bg-amber-600 disabled:cursor-not-allowed disabled:bg-amber-300"
              type="button"
              @click="openVoting"
            >
              {{ openingVoting ? "Opening..." : "Open Voting" }}
            </button>
            <button
              :disabled="closingVoting || !canCloseVoting"
              class="rounded-2xl border border-amber-300 bg-white px-4 py-3 text-sm font-bold uppercase tracking-[0.18em] text-amber-700 hover:border-amber-400 disabled:cursor-not-allowed disabled:border-amber-100 disabled:bg-amber-50 disabled:text-amber-300"
              type="button"
              @click="closeVoting"
            >
              {{ closingVoting ? "Closing..." : "Close Voting" }}
            </button>
            <button
              :disabled="startingGame || !canStartGame"
              class="rounded-2xl bg-emerald-600 px-4 py-3 text-sm font-bold uppercase tracking-[0.18em] text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-emerald-300"
              type="button"
              @click="startGame"
            >
              {{ startingGame ? "Starting..." : "Start Game" }}
            </button>
            <button
              :disabled="startingNextRound || !canStartNextRound"
              class="rounded-2xl bg-sky-600 px-4 py-3 text-sm font-bold uppercase tracking-[0.18em] text-white hover:bg-sky-700 disabled:cursor-not-allowed disabled:bg-sky-300"
              type="button"
              @click="startNextRound"
            >
              {{ startingNextRound ? "Starting..." : "Start Next Round" }}
            </button>
            <button
              :disabled="finishingGame || !canFinishGame"
              class="rounded-2xl bg-amber-500 px-4 py-3 text-sm font-bold uppercase tracking-[0.18em] text-white hover:bg-amber-600 disabled:cursor-not-allowed disabled:bg-amber-300"
              type="button"
              @click="finishGame()"
            >
              {{ finishingGame ? "Finishing..." : "Show Final Results" }}
            </button>
            <button
              :disabled="restartingGame || !canRestartGame"
              class="rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm font-bold uppercase tracking-[0.18em] text-slate-700 hover:border-slate-400 disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-100 disabled:text-slate-400"
              type="button"
              @click="restartGame"
            >
              {{ restartingGame ? "Restarting..." : "Restart Game" }}
            </button>
          </div>

          <div
            v-if="currentTurn"
            class="mt-4 rounded-[1.25rem] border border-slate-200 bg-white/80 p-4"
          >
            <p class="text-xs uppercase tracking-[0.18em] text-slate-500">Active Turn</p>
            <p class="mt-2 text-sm font-bold text-ink">
              {{ currentTurn.team.name }} · {{ currentTurn.status.replaceAll("_", " ") }}
            </p>
            <p class="mt-1 text-sm text-slate-600">
              {{ currentTurn.status !== "ACTIVE" && currentTurn.genre?.name ? `Genre: ${currentTurn.genre.name}` : "Genre not selected yet." }}
            </p>

            <div class="mt-4 grid gap-3 sm:grid-cols-3">
              <button
                :disabled="preparingTrack || !canPrepareTrack"
                class="rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm font-bold uppercase tracking-[0.18em] text-slate-700 hover:border-slate-400 disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-100 disabled:text-slate-400"
                type="button"
                @click="prepareTrack"
              >
                {{ preparingTrack ? "Preparing..." : "Prepare Track" }}
              </button>
              <button
                :disabled="startingPlayback || !canStartPlayback"
                class="rounded-2xl bg-emerald-600 px-4 py-3 text-sm font-bold uppercase tracking-[0.18em] text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-emerald-300"
                type="button"
                @click="startPlayback"
              >
                {{ startingPlayback ? "Starting..." : "Start Playback" }}
              </button>
              <button
                :disabled="stoppingPlayback || !canStopPlayback"
                class="rounded-2xl bg-amber-500 px-4 py-3 text-sm font-bold uppercase tracking-[0.18em] text-white hover:bg-amber-600 disabled:cursor-not-allowed disabled:bg-amber-300"
                type="button"
                @click="stopPlayback"
              >
                {{ stoppingPlayback ? "Stopping..." : "Stop Playback" }}
              </button>
            </div>

            <div
              v-if="showAnswerPhasePanel"
              class="mt-4 rounded-[1.25rem] border border-indigo-200 bg-indigo-50/70 p-4"
            >
              <p class="text-xs uppercase tracking-[0.18em] text-indigo-500">Answer Phase</p>
              <p class="mt-2 text-sm text-slate-700">
                {{
                  currentTurn.status === "PLAYING"
                    ? "Replay is in progress. Stop playback or wait for the clip to finish, then reveal the answer."
                    : "Playback has stopped. Reveal the answer before scoring the turn."
                }}
              </p>
              <div class="mt-4 grid gap-3 sm:grid-cols-2">
                <button
                  :disabled="startingPlayback || !canReplayClip"
                  class="rounded-2xl border border-indigo-300 bg-white px-4 py-3 text-sm font-bold uppercase tracking-[0.18em] text-indigo-700 hover:border-indigo-400 disabled:cursor-not-allowed disabled:border-indigo-100 disabled:bg-indigo-50 disabled:text-indigo-300"
                  type="button"
                  @click="replayClip"
                >
                  {{ startingPlayback ? "Replaying..." : "Replay Clip" }}
                </button>
                <button
                  :disabled="revealingAnswer || !canRevealAnswer"
                  class="rounded-2xl bg-indigo-600 px-4 py-3 text-sm font-bold uppercase tracking-[0.18em] text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-indigo-300"
                  type="button"
                  @click="revealAnswer"
                >
                  {{ revealingAnswer ? "Revealing..." : "Reveal Answer" }}
                </button>
              </div>
            </div>

            <div
              v-if="currentTurn.answer"
              class="mt-4 rounded-[1.25rem] border border-indigo-200 bg-white p-4"
            >
              <p class="text-xs uppercase tracking-[0.18em] text-indigo-500">Revealed Answer</p>
              <p class="mt-2 text-base font-bold text-ink">{{ currentTurn.answer.title }}</p>
              <p class="mt-1 text-sm text-slate-700">{{ currentTurn.answer.artist }}</p>
              <p class="mt-1 text-sm text-slate-500">{{ currentTurn.answer.album }}</p>
            </div>

            <div
              v-if="currentTurn.status === 'ANSWER_REVEALED'"
              class="mt-4 rounded-[1.25rem] border border-emerald-200 bg-emerald-50/70 p-4"
            >
              <p class="text-xs uppercase tracking-[0.18em] text-emerald-600">Score Turn</p>
              <p class="mt-2 text-sm text-slate-700">
                Choose the result for {{ currentTurn.team.name }}.
              </p>

              <div class="mt-4 grid gap-3 sm:grid-cols-2">
                <button
                  :disabled="awardingScore"
                  class="rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm font-bold uppercase tracking-[0.18em] text-slate-700 hover:border-slate-400 disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-100 disabled:text-slate-400"
                  type="button"
                  @click="awardScore(false, false)"
                >
                  No Match · 0 pts
                </button>
                <button
                  :disabled="awardingScore"
                  class="rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm font-bold uppercase tracking-[0.18em] text-slate-700 hover:border-slate-400 disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-100 disabled:text-slate-400"
                  type="button"
                  @click="awardScore(true, false)"
                >
                  Title Only · 1 pt
                </button>
                <button
                  :disabled="awardingScore"
                  class="rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm font-bold uppercase tracking-[0.18em] text-slate-700 hover:border-slate-400 disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-100 disabled:text-slate-400"
                  type="button"
                  @click="awardScore(false, true)"
                >
                  Artist Only · 1 pt
                </button>
                <button
                  :disabled="awardingScore"
                  class="rounded-2xl bg-emerald-600 px-4 py-3 text-sm font-bold uppercase tracking-[0.18em] text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-emerald-300"
                  type="button"
                  @click="awardScore(true, true)"
                >
                  Full Match · 3 pts
                </button>
              </div>
            </div>

            <div
              v-if="currentTurn.status === 'COMPLETED'"
              class="mt-4 rounded-[1.25rem] border border-sky-200 bg-sky-50/70 p-4"
            >
              <p class="text-xs uppercase tracking-[0.18em] text-sky-600">Next Turn</p>
              <p class="mt-2 text-sm text-slate-700">
                This turn has been scored. Advance when you are ready.
              </p>
              <button
                :disabled="advancingTurn || !canAdvanceTurn"
                class="mt-4 rounded-2xl bg-sky-600 px-4 py-3 text-sm font-bold uppercase tracking-[0.18em] text-white hover:bg-sky-700 disabled:cursor-not-allowed disabled:bg-sky-300"
                type="button"
                @click="advanceTurn"
              >
                {{ advancingTurn ? "Advancing..." : "Advance Turn" }}
              </button>
            </div>
          </div>

        </div>

        <div class="grid gap-3 sm:grid-cols-3">
          <button
            class="rounded-2xl bg-ink px-4 py-3 text-sm font-bold uppercase tracking-[0.18em] text-white hover:bg-slate-800"
            type="button"
            @click="copyJoinLink"
          >
            Copy Join Link
          </button>
          <button
            class="rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm font-bold uppercase tracking-[0.18em] text-slate-700 hover:border-slate-400"
            type="button"
            @click="copyJoinCode"
          >
            Copy Game Code
          </button>
          <NuxtLink
            :to="`/join/${game.join_token}`"
            class="rounded-2xl border border-slate-300 bg-white px-4 py-3 text-center text-sm font-bold uppercase tracking-[0.18em] text-slate-700 hover:border-slate-400"
          >
            Open Join Page
          </NuxtLink>
        </div>

        <NuxtLink
          v-if="effectiveGameStatus === 'FINISHED'"
          :to="`/game/${game.join_token}/results`"
          class="block rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-center text-sm font-bold uppercase tracking-[0.18em] text-amber-900 hover:border-amber-300"
        >
          Open Results Screen
        </NuxtLink>

        <div
          v-if="copyMessage"
          class="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800"
        >
          {{ copyMessage }}
        </div>

        <div
          v-if="actionMessage"
          class="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800"
        >
          {{ actionMessage }}
        </div>

        <div
          v-if="actionError"
          class="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700"
        >
          {{ actionError }}
        </div>
      </div>
    </div>
  </article>
</template>

<script setup lang="ts">
import QRCode from "qrcode";
import type { GameStateResponse, HostGame } from "~/types/game";

const props = defineProps<{
  game: HostGame;
}>();
const emit = defineEmits<{
  refreshRequested: [];
}>();

const config = useRuntimeConfig();
const { apiFetch, getErrorMessage } = useApi();
const { getCsrfToken } = useCsrfToken();
const qrCodeDataUrl = ref("");
const copyMessage = ref("");
const actionMessage = ref("");
const actionError = ref("");
const closingRegistration = ref(false);
const assigningTeams = ref(false);
const openingVoting = ref(false);
const closingVoting = ref(false);
const currentState = ref<GameStateResponse | null>(null);
const preparingTrack = ref(false);
const startingPlayback = ref(false);
const stoppingPlayback = ref(false);
const revealingAnswer = ref(false);
const awardingScore = ref(false);
const advancingTurn = ref(false);
const startingGame = ref(false);
const startingNextRound = ref(false);
const finishingGame = ref(false);
const restartingGame = ref(false);
const savingRoundsPerTeam = ref(false);
const replayingAnswerPhase = ref(false);
let latestStateRequestId = 0;
let statePollIntervalId: ReturnType<typeof window.setInterval> | null = null;
const roundsPerTeamInput = ref(props.game.rounds_per_team);

const joinUrl = computed(
  () => `${config.public.appOrigin}/join/${props.game.join_token}`,
);
const currentTurn = computed(() => currentState.value?.current_turn || null);
const effectiveRegistrationOpen = computed(
  () => currentState.value?.game.registration_open ?? props.game.registration_open,
);
const effectiveGameStatus = computed(
  () => currentState.value?.game.status || props.game.status,
);
const effectiveCurrentRound = computed(
  () => currentState.value?.game.current_round ?? props.game.current_round,
);
const effectiveRoundsPerTeam = computed(
  () => currentState.value?.game.rounds_per_team ?? props.game.rounds_per_team,
);
const minimumRoundsPerTeam = computed(() => (
  effectiveGameStatus.value === "IN_PROGRESS"
  || effectiveGameStatus.value === "PAUSED"
    ? Math.max(1, effectiveCurrentRound.value)
    : 1
));
const isRoundCompleted = computed(() => (
  effectiveGameStatus.value === "IN_PROGRESS"
  && currentTurn.value?.status === "COMPLETED"
  && currentTurn.value.turn_position === (
    currentState.value?.game.number_of_teams ?? props.game.number_of_teams
  )
));
const canCloseRegistration = computed(
  () => effectiveRegistrationOpen.value && effectiveGameStatus.value === "LOBBY_OPEN",
);
const canAssignTeams = computed(
  () => !effectiveRegistrationOpen.value && effectiveGameStatus.value === "LOBBY_CLOSED",
);
const canOpenVoting = computed(
  () => effectiveGameStatus.value === "TEAMS_ASSIGNED",
);
const canCloseVoting = computed(
  () => effectiveGameStatus.value === "VOTING_OPEN",
);
const canPrepareTrack = computed(() => (
  effectiveGameStatus.value === "IN_PROGRESS"
  && currentTurn.value?.status === "GENRE_SELECTED"
));
const canStartPlayback = computed(() => (
  effectiveGameStatus.value === "IN_PROGRESS"
  && currentTurn.value?.status === "TRACK_READY"
));
const canStopPlayback = computed(() => (
  effectiveGameStatus.value === "IN_PROGRESS"
  && currentTurn.value?.status === "PLAYING"
));
const canRevealAnswer = computed(() => (
  effectiveGameStatus.value === "IN_PROGRESS"
  && currentTurn.value?.status === "AWAITING_ANSWER"
));
const canReplayClip = computed(() => (
  effectiveGameStatus.value === "IN_PROGRESS"
  && currentTurn.value?.status === "AWAITING_ANSWER"
));
const canAdvanceTurn = computed(() => (
  effectiveGameStatus.value === "IN_PROGRESS"
  && currentTurn.value?.status === "COMPLETED"
));
const canStartGame = computed(() => (
  effectiveGameStatus.value === "VOTING_CLOSED"
  && !currentTurn.value
));
const canStartNextRound = computed(() => (
  isRoundCompleted.value
  && effectiveCurrentRound.value < effectiveRoundsPerTeam.value
));
const canSaveRoundsPerTeam = computed(() => (
  Number.isInteger(roundsPerTeamInput.value)
  && roundsPerTeamInput.value >= minimumRoundsPerTeam.value
  && roundsPerTeamInput.value !== effectiveRoundsPerTeam.value
));
const canFinishGame = computed(() => (
  (effectiveGameStatus.value === "IN_PROGRESS"
    || effectiveGameStatus.value === "PAUSED")
  && currentTurn.value?.status !== "PLAYING"
));
const canRestartGame = computed(() => (
  effectiveGameStatus.value !== "LOBBY_OPEN"
  && currentTurn.value?.status !== "PLAYING"
));
const showAnswerPhasePanel = computed(() => (
  currentTurn.value?.status === "AWAITING_ANSWER"
  || (
    replayingAnswerPhase.value
    && currentTurn.value?.status === "PLAYING"
  )
));
const hostActionHint = computed(() => {
  if (canCloseRegistration.value) {
    return "Close registration when everyone has joined. Team assignment unlocks after that.";
  }

  if (canAssignTeams.value) {
    return "Registration is closed. Assign teams now to randomize players into balanced groups.";
  }

  if (canOpenVoting.value) {
    return "Teams are already assigned. The next step is opening leader voting.";
  }

  if (canCloseVoting.value) {
    return "Leader voting is live. Close voting after each multi-player team has cast all votes.";
  }

  if (effectiveGameStatus.value === "VOTING_CLOSED") {
    return "Every team has a leader. Start the game to create the first turn.";
  }

  if (effectiveGameStatus.value === "FINISHED") {
    return "The game is finished. Show final results or restart the room for another round.";
  }

  if (
    effectiveGameStatus.value === "IN_PROGRESS"
    && currentTurn.value
  ) {
    if (canStartNextRound.value) {
      return `Round ${effectiveCurrentRound.value} is complete. Start round ${effectiveCurrentRound.value + 1} when you are ready.`;
    }

    if (
      isRoundCompleted.value
      && effectiveCurrentRound.value >= effectiveRoundsPerTeam.value
    ) {
      return `Round ${effectiveCurrentRound.value} is complete and the configured limit has been reached. Show the final results when you are ready.`;
    }

    const teamName = currentTurn.value.team.name;
    const turnStatus = currentTurn.value.status.replaceAll("_", " ").toLowerCase();
    const genreName = currentTurn.value.status === "ACTIVE"
      ? null
      : currentTurn.value.genre?.name;

    if (genreName) {
      return `${teamName} is active. Current turn status: ${turnStatus}. Genre: ${genreName}.`;
    }

    return `${teamName} is active. Current turn status: ${turnStatus}.`;
  }

  return `Current status: ${effectiveGameStatus.value.replaceAll("_", " ").toLowerCase()}.`;
});

async function buildQrCode() {
  qrCodeDataUrl.value = await QRCode.toDataURL(joinUrl.value, {
    width: 320,
    margin: 1,
    color: {
      dark: "#101828",
      light: "#FFFFFFFF",
    },
  });
}

async function copyJoinLink() {
  await navigator.clipboard.writeText(joinUrl.value);
  copyMessage.value = "Join link copied.";

  window.setTimeout(() => {
    copyMessage.value = "";
  }, 2200);
}

async function copyJoinCode() {
  await navigator.clipboard.writeText(props.game.join_code);
  copyMessage.value = "Game code copied.";

  window.setTimeout(() => {
    copyMessage.value = "";
  }, 2200);
}

async function loadGameState() {
  const requestId = ++latestStateRequestId;
  try {
    const nextState = await apiFetch<GameStateResponse>(
      `/games/${props.game.join_token}/state/`,
    );
    if (requestId === latestStateRequestId) {
      currentState.value = nextState;
    }
  } catch {
    // Keep the last known state so transient proxy/backend failures do
    // not knock the host controls into an unusable state.
  }
}

function setCurrentTurnStatus(status: string) {
  if (!currentState.value?.current_turn) {
    return;
  }

  currentState.value = {
    ...currentState.value,
    current_turn: {
      ...currentState.value.current_turn,
      status,
    },
  };
}

async function closeRegistration() {
  if (!canCloseRegistration.value) {
    return;
  }

  actionError.value = "";
  actionMessage.value = "";
  closingRegistration.value = true;

  try {
    await apiFetch(`/games/${props.game.id}/close-registration/`, {
      method: "POST",
      headers: {
        "X-CSRFToken": await getCsrfToken(),
      },
    });

    actionMessage.value = "Registration closed.";
    await loadGameState();
    emit("refreshRequested");
  } catch (error) {
    actionError.value = getErrorMessage(
      error,
      "Registration could not be closed.",
    );
  } finally {
    closingRegistration.value = false;
  }
}

async function assignTeams() {
  if (!canAssignTeams.value) {
    return;
  }

  actionError.value = "";
  actionMessage.value = "";
  assigningTeams.value = true;

  try {
    await apiFetch(`/games/${props.game.id}/assign-teams/`, {
      method: "POST",
      headers: {
        "X-CSRFToken": await getCsrfToken(),
      },
    });

    actionMessage.value = "Teams assigned.";
    await loadGameState();
    emit("refreshRequested");
  } catch (error) {
    actionError.value = getErrorMessage(
      error,
      "Teams could not be assigned.",
    );
  } finally {
    assigningTeams.value = false;
  }
}

async function openVoting() {
  if (!canOpenVoting.value) {
    return;
  }

  actionError.value = "";
  actionMessage.value = "";
  openingVoting.value = true;

  try {
    const response = await apiFetch<{
      game: {
        status: string;
      };
      leaders?: Array<{
        team: {
          name: string;
        };
        leader: {
          display_name: string;
        };
      }>;
    }>(`/games/${props.game.id}/voting/open/`, {
      method: "POST",
      headers: {
        "X-CSRFToken": await getCsrfToken(),
      },
    });

    actionMessage.value = response.game.status === "VOTING_CLOSED"
      ? "Voting resolved immediately. Solo-player teams were auto-assigned leaders."
      : "Leader voting opened.";
    await loadGameState();
    emit("refreshRequested");
  } catch (error) {
    actionError.value = getErrorMessage(
      error,
      "Leader voting could not be opened.",
    );
  } finally {
    openingVoting.value = false;
  }
}

async function closeVoting() {
  if (!canCloseVoting.value) {
    return;
  }

  actionError.value = "";
  actionMessage.value = "";
  closingVoting.value = true;

  try {
    await apiFetch(`/games/${props.game.id}/voting/close/`, {
      method: "POST",
      headers: {
        "X-CSRFToken": await getCsrfToken(),
      },
    });

    actionMessage.value = "Leader voting closed.";
    await loadGameState();
    emit("refreshRequested");
  } catch (error) {
    actionError.value = getErrorMessage(
      error,
      "Leader voting could not be closed.",
    );
  } finally {
    closingVoting.value = false;
  }
}

async function prepareTrack() {
  if (!canPrepareTrack.value || !currentTurn.value) {
    return;
  }

  actionError.value = "";
  actionMessage.value = "";
  preparingTrack.value = true;

  try {
    const response = await apiFetch<{
      track: {
        title: string;
        artist: string;
      };
    }>(
      `/games/${props.game.id}/turns/${currentTurn.value.id}/track/prepare/`,
      {
        method: "POST",
        headers: {
          "X-CSRFToken": await getCsrfToken(),
        },
      },
    );

    actionMessage.value = `Track prepared: ${response.track.title} by ${response.track.artist}.`;
    await loadGameState();
  } catch (error) {
    actionError.value = getErrorMessage(
      error,
      "Track preparation failed.",
    );
  } finally {
    preparingTrack.value = false;
  }
}

async function startGame() {
  if (!canStartGame.value) {
    return;
  }

  actionError.value = "";
  actionMessage.value = "";
  startingGame.value = true;

  try {
    const response = await apiFetch<{
      active_turn: {
        team_name: string;
      };
    }>(`/games/${props.game.id}/start/`, {
      method: "POST",
      headers: {
        "X-CSRFToken": await getCsrfToken(),
      },
    });

    actionMessage.value = `Game started. ${response.active_turn.team_name} is up first.`;
    await loadGameState();
    emit("refreshRequested");
  } catch (error) {
    actionError.value = getErrorMessage(
      error,
      "The game could not be started.",
    );
  } finally {
    startingGame.value = false;
  }
}

async function startPlayback() {
  if (!currentTurn.value) {
    return;
  }

  const isReplay = currentTurn.value.status === "AWAITING_ANSWER";

  if (!canStartPlayback.value && !isReplay) {
    return;
  }

  actionError.value = "";
  actionMessage.value = "";
  startingPlayback.value = true;

  try {
    const response = await apiFetch<{
      turn: {
        status: string;
      };
    }>(
      `/games/${props.game.id}/turns/${currentTurn.value.id}/playback/start/`,
      {
        method: "POST",
        headers: {
          "X-CSRFToken": await getCsrfToken(),
        },
      },
    );

    setCurrentTurnStatus(response.turn.status);
    actionMessage.value = `${isReplay ? "Clip replaying" : "Playback started"} on ${props.game.spotify_device_name || "the selected Spotify device"}.`;
    await loadGameState();
  } catch (error) {
    await loadGameState();
    actionError.value = getErrorMessage(
      error,
      isReplay
        ? "Clip replay could not be started."
        : "Playback could not be started.",
    );
  } finally {
    startingPlayback.value = false;
  }
}

async function replayClip() {
  if (!canReplayClip.value) {
    return;
  }

  replayingAnswerPhase.value = true;
  await startPlayback();
}

async function stopPlayback() {
  if (!canStopPlayback.value || !currentTurn.value) {
    return;
  }

  actionError.value = "";
  actionMessage.value = "";
  stoppingPlayback.value = true;

  try {
    const response = await apiFetch<{
      turn: {
        status: string;
      };
    }>(
      `/games/${props.game.id}/turns/${currentTurn.value.id}/playback/stop/`,
      {
        method: "POST",
        headers: {
          "X-CSRFToken": await getCsrfToken(),
        },
      },
    );

    setCurrentTurnStatus(response.turn.status);
    actionMessage.value = "Playback stopped.";
    await loadGameState();
  } catch (error) {
    await loadGameState();
    actionError.value = getErrorMessage(
      error,
      "Playback could not be stopped.",
    );
  } finally {
    stoppingPlayback.value = false;
  }
}

async function revealAnswer() {
  if (!canRevealAnswer.value || !currentTurn.value) {
    return;
  }

  actionError.value = "";
  actionMessage.value = "";
  revealingAnswer.value = true;

  try {
    const response = await apiFetch<{
      answer: {
        title: string;
        artist: string;
      };
    }>(
      `/games/${props.game.id}/turns/${currentTurn.value.id}/answer/reveal/`,
      {
        method: "POST",
        headers: {
          "X-CSRFToken": await getCsrfToken(),
        },
      },
    );

    actionMessage.value = `Answer revealed: ${response.answer.title} by ${response.answer.artist}.`;
    await loadGameState();
  } catch (error) {
    actionError.value = getErrorMessage(
      error,
      "Answer could not be revealed.",
    );
  } finally {
    revealingAnswer.value = false;
  }
}

async function awardScore(
  songTitleCorrect: boolean,
  artistCorrect: boolean,
) {
  if (currentTurn.value?.status !== "ANSWER_REVEALED" || !currentTurn.value) {
    return;
  }

  actionError.value = "";
  actionMessage.value = "";
  awardingScore.value = true;

  try {
    const response = await apiFetch<{
      result: {
        points_awarded: number;
      };
    }>(
      `/games/${props.game.id}/turns/${currentTurn.value.id}/score/`,
      {
        method: "POST",
        headers: {
          "X-CSRFToken": await getCsrfToken(),
        },
        body: {
          song_title_correct: songTitleCorrect,
          artist_correct: artistCorrect,
        },
      },
    );

    actionMessage.value = `${currentTurn.value.team.name} awarded ${response.result.points_awarded} point${response.result.points_awarded === 1 ? "" : "s"}.`;
    await loadGameState();
  } catch (error) {
    actionError.value = getErrorMessage(
      error,
      "Score could not be recorded.",
    );
  } finally {
    awardingScore.value = false;
  }
}

async function advanceTurn() {
  if (!canAdvanceTurn.value || !currentTurn.value) {
    return;
  }

  actionError.value = "";
  actionMessage.value = "";
  advancingTurn.value = true;

  try {
    const response = await apiFetch<{
      advanced: boolean;
      round_completed: boolean;
      detail?: string;
    }>(
      `/games/${props.game.id}/turns/${currentTurn.value.id}/advance/`,
      {
        method: "POST",
        headers: {
          "X-CSRFToken": await getCsrfToken(),
        },
      },
    );

    if (response.advanced) {
      actionMessage.value = "Advanced to the next turn.";
    } else if (response.round_completed) {
      const reachedRoundLimit = effectiveCurrentRound.value >= effectiveRoundsPerTeam.value;

      if (reachedRoundLimit) {
        actionMessage.value = response.detail || "This round is complete.";
        await finishGame({
          automatic: true,
        });
      } else {
        actionMessage.value = `Round ${effectiveCurrentRound.value} is complete. Start round ${effectiveCurrentRound.value + 1} when you are ready.`;
      }
    } else {
      actionMessage.value = "Turn advance processed.";
    }

    await loadGameState();
  } catch (error) {
    actionError.value = getErrorMessage(
      error,
      "Turn could not be advanced.",
    );
  } finally {
    advancingTurn.value = false;
  }
}

async function startNextRound() {
  if (!canStartNextRound.value) {
    return;
  }

  actionError.value = "";
  actionMessage.value = "";
  startingNextRound.value = true;

  try {
    const response = await apiFetch<{
      started: boolean;
      round_number: number;
    }>(`/games/${props.game.id}/rounds/next/`, {
      method: "POST",
      headers: {
        "X-CSRFToken": await getCsrfToken(),
      },
    });

    if (response.started) {
      actionMessage.value = `Round ${response.round_number} started.`;
    }

    await loadGameState();
    emit("refreshRequested");
  } catch (error) {
    actionError.value = getErrorMessage(
      error,
      "The next round could not be started.",
    );
  } finally {
    startingNextRound.value = false;
  }
}

async function saveRoundsPerTeam() {
  if (!canSaveRoundsPerTeam.value) {
    return;
  }

  actionError.value = "";
  actionMessage.value = "";
  savingRoundsPerTeam.value = true;

  try {
    const updatedGame = await apiFetch<HostGame>(`/games/${props.game.id}/settings/`, {
      method: "PATCH",
      headers: {
        "X-CSRFToken": await getCsrfToken(),
      },
      body: {
        rounds_per_team: roundsPerTeamInput.value,
      },
    });

    roundsPerTeamInput.value = updatedGame.rounds_per_team;
    actionMessage.value = `Rounds per team updated to ${updatedGame.rounds_per_team}.`;
    await loadGameState();
    emit("refreshRequested");
  } catch (error) {
    actionError.value = getErrorMessage(
      error,
      "Rounds per team could not be updated.",
    );
  } finally {
    savingRoundsPerTeam.value = false;
  }
}

async function finishGame(options?: {
  automatic?: boolean;
}) {
  if (!canFinishGame.value) {
    return;
  }

  actionError.value = "";

  if (!options?.automatic) {
    actionMessage.value = "";
  }

  finishingGame.value = true;

  try {
    const response = await apiFetch<{
      finished: boolean;
    }>(`/games/${props.game.id}/finish/`, {
      method: "POST",
      headers: {
        "X-CSRFToken": await getCsrfToken(),
      },
    });

    if (response.finished) {
      actionMessage.value = options?.automatic
        ? "All teams have completed the round. Final results are now live."
        : "Final results are now live.";
    }

    await loadGameState();
    emit("refreshRequested");
  } catch (error) {
    actionError.value = getErrorMessage(
      error,
      options?.automatic
        ? "The game could not be finished automatically."
        : "The game could not be finished.",
    );
  } finally {
    finishingGame.value = false;
  }
}

async function restartGame() {
  if (!canRestartGame.value) {
    return;
  }

  actionError.value = "";
  actionMessage.value = "";
  restartingGame.value = true;

  try {
    const response = await apiFetch<{
      restarted: boolean;
      player_count: number;
    }>(`/games/${props.game.id}/restart/`, {
      method: "POST",
      headers: {
        "X-CSRFToken": await getCsrfToken(),
      },
    });

    if (response.restarted) {
      actionMessage.value = `Game restarted. ${response.player_count} player${response.player_count === 1 ? "" : "s"} remain in the room.`;
    }

    await loadGameState();
    emit("refreshRequested");
  } catch (error) {
    actionError.value = getErrorMessage(
      error,
      "The game could not be restarted.",
    );
  } finally {
    restartingGame.value = false;
  }
}

watch(
  () => props.game.join_token,
  () => {
    void buildQrCode();
    void loadGameState();
  },
  { immediate: true },
);

watch(
  () => effectiveRoundsPerTeam.value,
  (nextValue) => {
    roundsPerTeamInput.value = nextValue;
  },
  { immediate: true },
);

watch(
  () => currentTurn.value?.status,
  (status) => {
    if (
      !status
      || status === "AWAITING_ANSWER"
      || status === "ANSWER_REVEALED"
      || status === "COMPLETED"
    ) {
      replayingAnswerPhase.value = false;
    }
  },
);

onMounted(() => {
  statePollIntervalId = window.setInterval(() => {
    void loadGameState();
  }, 2000);
});

onBeforeUnmount(() => {
  if (statePollIntervalId !== null) {
    window.clearInterval(statePollIntervalId);
    statePollIntervalId = null;
  }
});
</script>
