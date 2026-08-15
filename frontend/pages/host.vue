<template>
  <div class="space-y-8">
    <section class="grid gap-6 rounded-[2rem] border border-white/70 bg-[var(--card-strong)] p-6 shadow-pulse backdrop-blur lg:grid-cols-[1.05fr_0.95fr] md:p-8">
      <div>
        <p class="text-sm font-medium uppercase tracking-[0.22em] text-slate-500">
          Host Dashboard
        </p>
        <h1 class="mt-2 font-display text-4xl text-ink">Create rooms and hand players a QR code</h1>
        <p class="mt-3 max-w-2xl text-sm leading-7 text-slate-600">
          After logging into Django or DRF on this machine, you can create a game here and immediately show a scannable join code on the screen.
        </p>
      </div>

      <form class="rounded-[1.75rem] border border-slate-200/80 bg-white/90 p-5" @submit.prevent="createGame">
        <div class="space-y-4">
          <label class="block space-y-2">
            <span class="text-sm font-medium text-slate-700">Game name</span>
            <input
              v-model.trim="createForm.name"
              class="w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm text-ink outline-none placeholder:text-slate-400 focus:border-ink"
              maxlength="100"
              placeholder="Track Decode"
              type="text"
            >
          </label>

          <label class="block space-y-2">
            <span class="text-sm font-medium text-slate-700">Number of teams</span>
            <input
              v-model.number="createForm.numberOfTeams"
              class="w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm text-ink outline-none focus:border-ink"
              max="8"
              min="2"
              type="number"
            >
          </label>

          <label class="block space-y-2">
            <span class="text-sm font-medium text-slate-700">Rounds per team</span>
            <input
              v-model.number="createForm.roundsPerTeam"
              class="w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm text-ink outline-none focus:border-ink"
              min="1"
              type="number"
            >
          </label>

          <div
            v-if="createError"
            class="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700"
          >
            {{ createError }}
          </div>

          <button
            :disabled="creating"
            class="w-full rounded-2xl bg-ink px-5 py-3 text-sm font-bold uppercase tracking-[0.18em] text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
            type="submit"
          >
            {{ creating ? "Creating..." : "Create Game" }}
          </button>
        </div>
      </form>
    </section>

    <div
      v-if="loadError"
      class="rounded-2xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm text-amber-900"
    >
      {{ loadError }}
    </div>

    <section class="space-y-5">
      <div class="flex items-center justify-between gap-4">
        <div>
          <p class="text-sm font-medium uppercase tracking-[0.22em] text-slate-500">
            Your Games
          </p>
          <h2 class="font-display text-3xl text-ink">QR-ready rooms</h2>
        </div>
        <button
          :disabled="pending"
          class="rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm font-medium text-slate-700 hover:border-slate-400 disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-100 disabled:text-slate-400"
          type="button"
          @click="refreshGames"
        >
          {{ pending && games?.length ? "Refreshing..." : "Refresh" }}
        </button>
      </div>

      <div v-if="pending && !games?.length" class="rounded-2xl border border-slate-200 bg-white/80 px-5 py-4 text-sm text-slate-600">
        Loading hosted games...
      </div>

      <div
        v-else-if="!games?.length"
        class="rounded-2xl border border-dashed border-slate-300 bg-white/80 px-5 py-8 text-sm text-slate-600"
      >
        No hosted games yet. Create one above, then put its QR code on the shared screen for players to scan.
      </div>

      <div v-else class="grid gap-6">
        <JoinQrCard
          v-for="game in games"
          :key="game.id"
          :game="game"
          @refresh-requested="refreshGames"
        />
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import type { HostGame } from "~/types/game";

const { apiFetch, getErrorMessage } = useApi();
const { getCsrfToken } = useCsrfToken();

const createForm = reactive({
  name: "Track Decode",
  numberOfTeams: 2,
  roundsPerTeam: 1,
});
const creating = ref(false);
const createError = ref("");
const loadError = ref("");

useSeoMeta({
  title: "Host Dashboard",
  description: "Create quiz rooms and display QR codes for player join.",
});

const { data: games, pending, refresh } = await useAsyncData<HostGame[]>(
  "host-games",
  async () => {
    try {
      loadError.value = "";
      return await apiFetch<HostGame[]>("/games/");
    } catch (error) {
      loadError.value = getErrorMessage(
        error,
        "Host games could not be loaded. Log into the backend first.",
      );
      return [];
    }
  },
);

async function refreshGames() {
  await refresh();
}

onMounted(() => {
  void refreshGames();
});

function insertHostedGame(game: HostGame) {
  const existingGames = games.value ?? [];
  const remainingGames = existingGames.filter((entry) => entry.id !== game.id);

  games.value = [game, ...remainingGames];
  loadError.value = "";
}

async function createGame() {
  createError.value = "";
  creating.value = true;

  try {
    const createdGame = await apiFetch<HostGame>("/games/", {
      method: "POST",
      headers: {
        "X-CSRFToken": getCsrfToken(),
      },
      body: {
        name: createForm.name || "Track Decode",
        number_of_teams: createForm.numberOfTeams,
        rounds_per_team: createForm.roundsPerTeam,
      },
    });

    insertHostedGame(createdGame);
  } catch (error) {
    createError.value = getErrorMessage(
      error,
      "The game could not be created. Make sure you are logged into the backend.",
    );
  } finally {
    creating.value = false;
  }
}
</script>
