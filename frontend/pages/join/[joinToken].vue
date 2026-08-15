<template>
  <div class="grid gap-8 lg:grid-cols-[0.95fr_1.05fr]">
    <section class="rounded-[2rem] border border-white/70 bg-[var(--card-strong)] p-6 shadow-pulse backdrop-blur md:p-8">
      <p class="text-sm font-medium uppercase tracking-[0.22em] text-slate-500">
        Room Check
      </p>
      <div v-if="pending" class="mt-4 text-slate-600">
        Loading game details...
      </div>
      <div v-else-if="error" class="mt-4 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-rose-700">
        This game could not be loaded. The join token may be invalid or the backend is unavailable.
      </div>
      <div v-else-if="game" class="mt-4 space-y-5">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 class="font-display text-4xl text-ink">{{ game.name }}</h1>
            <p class="mt-2 text-sm text-slate-600">
              {{ game.player_count }} players queued · {{ game.number_of_teams }} teams planned
            </p>
          </div>
          <StatusBadge :status="game.status" />
        </div>

        <div class="grid gap-4 sm:grid-cols-2">
          <div class="rounded-[1.5rem] border border-slate-200/80 bg-white/85 p-4">
            <p class="text-xs uppercase tracking-[0.18em] text-slate-500">Registration</p>
            <p class="mt-2 text-lg font-bold text-ink">
              {{ game.registration_open ? "Open" : "Closed" }}
            </p>
          </div>
          <div class="rounded-[1.5rem] border border-slate-200/80 bg-white/85 p-4">
            <p class="text-xs uppercase tracking-[0.18em] text-slate-500">Game Code</p>
            <p class="mt-2 text-2xl font-black tracking-[0.18em] text-ink">{{ game.join_code }}</p>
          </div>
        </div>

        <div
          v-if="existingSession"
          class="rounded-[1.5rem] border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800"
        >
          This browser already has a player session for this room as
          <strong>{{ existingSession.player.display_name }}</strong>.
          <button
            class="ml-2 font-bold underline underline-offset-4"
            type="button"
            @click="continueToGame"
          >
            Continue instead
          </button>
        </div>

        <div
          v-if="game?.status === 'FINISHED'"
          class="rounded-[1.5rem] border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"
        >
          This game has finished. You can still open the podium and final
          standings.
          <button
            class="ml-2 font-bold underline underline-offset-4"
            type="button"
            @click="continueToGame"
          >
            View results
          </button>
        </div>
      </div>
    </section>

    <section class="rounded-[2rem] border border-slate-200/70 bg-white/85 p-6 shadow-pulse md:p-8">
      <p class="text-sm font-medium uppercase tracking-[0.22em] text-slate-500">
        Join Game
      </p>
      <h2 class="mt-2 font-display text-3xl text-ink">Pick a display name</h2>
      <p class="mt-3 text-sm leading-7 text-slate-600">
        Your player session is stored locally in this browser so you can reconnect after a refresh.
      </p>

      <form class="mt-6 space-y-4" @submit.prevent="submitJoin">
        <label class="block space-y-2">
          <span class="text-sm font-medium text-slate-700">Display name</span>
          <input
            v-model.trim="displayName"
            class="w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm text-ink outline-none placeholder:text-slate-400 focus:border-ink"
            maxlength="50"
            name="display-name"
            placeholder="Your team will see this"
            type="text"
          >
        </label>

        <div
          v-if="submitError"
          class="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700"
        >
          {{ submitError }}
        </div>

        <button
          :disabled="submitting || !game?.registration_open || game?.status === 'FINISHED'"
          class="w-full rounded-2xl bg-ink px-5 py-3 text-sm font-bold uppercase tracking-[0.18em] text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
          type="submit"
        >
          {{ submitting ? "Joining..." : "Join Room" }}
        </button>
      </form>
    </section>
  </div>
</template>

<script setup lang="ts">
import type { PlayerJoinResponse, PublicGame, StoredPlayerSession } from "~/types/game";

const route = useRoute();
const { apiFetch, getErrorMessage } = useApi();
const joinToken = computed(() => String(route.params.joinToken));
const playerSession = usePlayerSession(joinToken.value);
const continueRoute = computed(() => (
  game.value?.status === "FINISHED"
    ? `/game/${joinToken.value}/results`
    : `/game/${joinToken.value}`
));

const displayName = ref("");
const submitError = ref("");
const submitting = ref(false);
const existingSession = ref<StoredPlayerSession | null>(null);

useSeoMeta({
  title: `Join Game ${joinToken.value}`,
});

const { data: game, pending, error } = await useAsyncData<PublicGame>(
  `public-game-${joinToken.value}`,
  () => apiFetch(`/games/join/${joinToken.value}/`),
);

onMounted(() => {
  existingSession.value = playerSession.read();
});

async function submitJoin() {
  submitError.value = "";

  if (!displayName.value) {
    submitError.value = "Enter a display name.";
    return;
  }

  submitting.value = true;

  try {
    const response = await apiFetch<PlayerJoinResponse>(
      `/games/join/${joinToken.value}/players/`,
      {
        method: "POST",
        body: {
          display_name: displayName.value,
        },
      },
    );

    playerSession.write({
      sessionToken: response.session_token,
      player: response.player,
    });

    await navigateTo(continueRoute.value);
  } catch (error) {
    submitError.value = getErrorMessage(
      error,
      "The player could not be added to this game.",
    );
  } finally {
    submitting.value = false;
  }
}

function continueToGame() {
  navigateTo(continueRoute.value);
}
</script>
