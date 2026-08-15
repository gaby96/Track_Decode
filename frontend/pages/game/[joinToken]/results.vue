<template>
  <div class="space-y-8">
    <section class="results-hero overflow-hidden rounded-[2rem] border border-white/70 p-5 shadow-pulse sm:p-7 md:rounded-[2.5rem] md:p-12">
      <div class="pointer-events-none absolute inset-0">
        <div class="results-beam results-beam-left" />
        <div class="results-beam results-beam-right" />
      </div>

      <div class="relative z-10 flex flex-wrap items-start justify-between gap-6">
        <div>
          <p class="text-sm font-medium uppercase tracking-[0.22em] text-amber-200/90">
            Final Results
          </p>
          <h1 class="mt-3 max-w-3xl font-display text-4xl leading-tight text-white sm:text-5xl md:text-6xl">
            The podium is locked.
          </h1>
          <p class="mt-4 max-w-2xl text-sm leading-7 text-slate-100/85 sm:text-base sm:leading-8">
            Every team has completed its final turn. These are the official
            standings for {{ state?.game.name || "this game" }}.
          </p>
        </div>

        <div class="w-full space-y-3 sm:w-auto">
          <div class="rounded-[1.5rem] border border-white/15 bg-white/10 px-4 py-4 backdrop-blur sm:px-5">
            <p class="text-xs uppercase tracking-[0.18em] text-slate-200/75">Game</p>
            <p class="mt-2 break-words text-base font-semibold text-white sm:text-lg">{{ state?.game.name }}</p>
          </div>

          <div
            v-if="isHostForCurrentGame"
            class="rounded-[1.5rem] border border-white/15 bg-white/10 px-4 py-4 backdrop-blur sm:px-5"
          >
            <p class="text-xs uppercase tracking-[0.18em] text-slate-200/75">Host Actions</p>
            <button
              :disabled="restartingGame || !state"
              class="mt-3 w-full rounded-2xl bg-white px-4 py-3 text-sm font-bold uppercase tracking-[0.18em] text-slate-900 hover:bg-slate-100 disabled:cursor-not-allowed disabled:bg-white/40 disabled:text-slate-500"
              type="button"
              @click="restartGame"
            >
              {{ restartingGame ? "Restarting..." : "Restart Game" }}
            </button>
            <p class="mt-2 text-xs text-slate-100/80">
              Host-only action. This sends everyone back to the lobby.
            </p>
          </div>
        </div>
      </div>
    </section>

    <div
      v-if="restartError"
      class="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-700"
    >
      {{ restartError }}
    </div>

    <div
      v-if="loadError"
      class="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-700"
    >
      {{ loadError }}
    </div>

    <div v-else-if="pending" class="rounded-2xl border border-slate-200 bg-white/80 px-5 py-8 text-sm text-slate-600">
      Loading final standings...
    </div>

    <template v-else-if="state">
      <WinnersShowcase
        :finished-at="state.game.finished_at"
        :standings="state.standings"
        :winners="winningTeams"
      >
        <template v-if="isHostForCurrentGame" #actions>
          <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p class="text-xs uppercase tracking-[0.18em] text-slate-500">Host Actions</p>
              <p class="mt-2 text-sm text-slate-600">
                Restart the room and send everyone back to the lobby for a new round.
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
    </template>
  </div>
</template>

<script setup lang="ts">
import type { GameStateResponse, HostGame } from "~/types/game";

const route = useRoute();
const { apiFetch, getErrorMessage } = useApi();
const { getCsrfToken } = useCsrfToken();
const joinToken = computed(() => String(route.params.joinToken));

const loadError = ref("");
const restartError = ref("");
const restartingGame = ref(false);
const isHostForCurrentGame = ref(false);

useSeoMeta({
  title: `Final Results ${joinToken.value}`,
});

const { data: state, pending, refresh } = await useAsyncData<GameStateResponse>(
  `game-results-${joinToken.value}`,
  async () => {
    try {
      loadError.value = "";
      return await apiFetch(`/games/${joinToken.value}/state/`);
    } catch (error) {
      loadError.value = getErrorMessage(
        error,
        "The final game state could not be loaded.",
      );
      throw error;
    }
  },
);

let refreshIntervalId: ReturnType<typeof window.setInterval> | null = null;

const winningTeams = computed(() => (
  (state.value?.standings || []).filter((entry) => entry.rank === 1)
));

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

async function restartGame() {
  if (!state.value || restartingGame.value || !isHostForCurrentGame.value) {
    return;
  }

  restartError.value = "";
  restartingGame.value = true;

  try {
    await apiFetch(`/games/${state.value.game.id}/restart/`, {
      method: "POST",
      headers: {
        "X-CSRFToken": getCsrfToken(),
      },
    });

    await refresh();
    await navigateTo(`/game/${joinToken.value}`, {
      replace: true,
    });
  } catch (error) {
    restartError.value = getErrorMessage(
      error,
      "The game could not be restarted from the results screen.",
    );
  } finally {
    restartingGame.value = false;
  }
}

watch(
  () => state.value?.game.status,
  (status) => {
    if (status && status !== "FINISHED") {
      void navigateTo(`/game/${joinToken.value}`, {
        replace: true,
      });
    }
  },
  { immediate: true },
);

onMounted(() => {
  void refreshHostAccess();
  refreshIntervalId = window.setInterval(() => {
    void refresh();
  }, 2000);
});

onBeforeUnmount(() => {
  if (refreshIntervalId !== null) {
    window.clearInterval(refreshIntervalId);
    refreshIntervalId = null;
  }
});
</script>

<style scoped>
.results-hero {
  position: relative;
  background:
    radial-gradient(circle at top left, rgba(251, 191, 36, 0.42), transparent 34%),
    radial-gradient(circle at top right, rgba(96, 165, 250, 0.26), transparent 28%),
    linear-gradient(135deg, #0f172a 0%, #172554 52%, #1d4ed8 100%);
}

.results-beam {
  position: absolute;
  width: 18rem;
  height: 18rem;
  border-radius: 9999px;
  filter: blur(26px);
  opacity: 0.55;
  animation: beam-drift 7s ease-in-out infinite;
}

.results-beam-left {
  left: -5rem;
  top: -6rem;
  background: rgba(251, 191, 36, 0.45);
}

.results-beam-right {
  right: -5rem;
  bottom: -6rem;
  background: rgba(59, 130, 246, 0.32);
  animation-delay: 1.2s;
}

@keyframes beam-drift {
  0%, 100% {
    transform: translate3d(0, 0, 0) scale(1);
  }

  50% {
    transform: translate3d(0, 18px, 0) scale(1.08);
  }
}
</style>
