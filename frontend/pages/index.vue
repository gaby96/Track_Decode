<template>
  <div class="grid gap-8 lg:grid-cols-[1.15fr_0.85fr]">
    <section class="space-y-6 rounded-[2.5rem] border border-white/70 bg-[var(--card-strong)] p-8 shadow-pulse backdrop-blur md:p-12">
      <p class="inline-flex rounded-full bg-white px-4 py-2 text-xs font-bold uppercase tracking-[0.22em] text-slate-600">
        Nuxt Frontend
      </p>
      <div class="space-y-4">
        <h1 class="max-w-3xl font-display text-5xl leading-tight text-ink md:text-6xl">
          Run the room. Keep the answer hidden. Let the leaderboard move live.
        </h1>
        <p class="max-w-2xl text-lg leading-8 text-slate-600">
          This frontend is wired for the public and player-facing flow first:
          join a live game, vote inside your team, watch turns update over
          websockets, and reveal song details only when the backend says so.
        </p>
      </div>

      <div class="grid gap-4 md:grid-cols-3">
        <div class="rounded-[1.75rem] border border-slate-200/70 bg-white/85 p-5">
          <p class="text-xs uppercase tracking-[0.18em] text-slate-500">Step 1</p>
          <p class="mt-2 text-lg font-bold text-ink">Join by code</p>
          <p class="mt-2 text-sm text-slate-600">Players can type a short game code or open the QR-based join page.</p>
        </div>
        <div class="rounded-[1.75rem] border border-slate-200/70 bg-white/85 p-5">
          <p class="text-xs uppercase tracking-[0.18em] text-slate-500">Step 2</p>
          <p class="mt-2 text-lg font-bold text-ink">Scan the QR</p>
          <p class="mt-2 text-sm text-slate-600">Hosts can now open a game room card with a scannable player QR code.</p>
        </div>
        <div class="rounded-[1.75rem] border border-slate-200/70 bg-white/85 p-5">
          <p class="text-xs uppercase tracking-[0.18em] text-slate-500">Step 3</p>
          <p class="mt-2 text-lg font-bold text-ink">Protect answers</p>
          <p class="mt-2 text-sm text-slate-600">Title and artist stay hidden until the answer reveal phase.</p>
        </div>
      </div>
    </section>

    <section class="space-y-6">
      <div class="rounded-[2rem] border border-white/70 bg-[var(--card)] p-6 shadow-pulse backdrop-blur md:p-8">
        <p class="text-sm font-medium uppercase tracking-[0.22em] text-slate-500">
          Player Join
        </p>
        <h2 class="mt-2 font-display text-3xl text-ink">Open a room</h2>
        <p class="mt-3 text-sm leading-7 text-slate-600">
          Enter the short <code class="rounded bg-slate-100 px-1 py-0.5 text-xs">game code</code>
          from the host screen, or paste the full <code class="rounded bg-slate-100 px-1 py-0.5 text-xs">join_token</code>
          if you already have it.
        </p>

        <form class="mt-6 space-y-4" @submit.prevent="goToJoinPage">
          <label class="block space-y-2">
            <span class="text-sm font-medium text-slate-700">Game code or join token</span>
            <input
              v-model.trim="joinIdentifier"
              class="w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm text-ink outline-none ring-0 placeholder:text-slate-400 focus:border-ink"
              name="join-identifier"
              placeholder="e.g. 7K9Q2M or 6b37f2af-..."
              type="text"
            >
          </label>
          <div
            v-if="joinError"
            class="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700"
          >
            {{ joinError }}
          </div>
          <button
            :disabled="joining"
            class="w-full rounded-2xl bg-ink px-5 py-3 text-sm font-bold uppercase tracking-[0.18em] text-white hover:bg-slate-800"
            type="submit"
          >
            {{ joining ? "Opening..." : "Enter Game" }}
          </button>
        </form>
      </div>

      <div class="rounded-[2rem] border border-slate-200/70 bg-white/80 p-6 shadow-pulse">
        <p class="text-sm font-medium uppercase tracking-[0.22em] text-slate-500">
          Host Tools
        </p>
        <h2 class="mt-2 font-display text-3xl text-ink">Create a game and show the QR</h2>
        <p class="mt-3 text-sm leading-7 text-slate-600">
          Sign into the backend once, then use the frontend host screen to create a room and display a QR code for players to scan.
        </p>
        <div class="mt-5 flex flex-col gap-3 sm:flex-row">
          <NuxtLink
            to="/host"
            class="rounded-2xl bg-ink px-5 py-3 text-center text-sm font-medium text-white hover:bg-slate-800"
          >
            Open Host Dashboard
          </NuxtLink>
          <a
            :href="`${config.public.backendOrigin}/admin/`"
            class="rounded-2xl border border-slate-300 bg-white px-5 py-3 text-center text-sm font-medium text-slate-700 hover:border-slate-400"
            rel="noreferrer"
            target="_blank"
          >
            Open Admin
          </a>
          <a
            :href="`${config.public.backendOrigin}/api-auth/login/`"
            class="rounded-2xl border border-slate-300 bg-white px-5 py-3 text-center text-sm font-medium text-slate-700 hover:border-slate-400"
            rel="noreferrer"
            target="_blank"
          >
            Open DRF Login
          </a>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import type { PublicGame } from "~/types/game";

const config = useRuntimeConfig();
const { apiFetch, getErrorMessage } = useApi();
const joinIdentifier = ref("");
const joinError = ref("");
const joining = ref(false);
const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

useSeoMeta({
  title: "Spotify Game Frontend",
  description: "Join a live music quiz or open the backend host tools.",
});

async function goToJoinPage() {
  joinError.value = "";

  const identifier = joinIdentifier.value.trim();

  if (!identifier) {
    return;
  }

  if (uuidPattern.test(identifier)) {
    await navigateTo(`/join/${identifier}`);
    return;
  }

  joining.value = true;

  try {
    const game = await apiFetch<PublicGame>(
      `/games/join/code/${identifier.toUpperCase()}/`,
    );

    await navigateTo(`/join/${game.join_token}`);
  } catch (error) {
    joinError.value = getErrorMessage(
      error,
      "That game code could not be found.",
    );
  } finally {
    joining.value = false;
  }
}
</script>
