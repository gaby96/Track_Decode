<template>
  <section
    class="rounded-[2rem] border border-white/70 bg-[var(--card-strong)] p-6 shadow-pulse backdrop-blur md:p-8"
  >
    <div v-if="turn" class="space-y-6">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p class="text-sm font-medium uppercase tracking-[0.22em] text-slate-500">
            Current Turn
          </p>
          <h2 class="font-display text-3xl text-ink">
            {{ turn.team.name }}
          </h2>
        </div>
        <StatusBadge :status="turn.status" />
      </div>

      <div class="grid gap-4 md:grid-cols-3">
        <div class="rounded-3xl border border-slate-200/80 bg-white/80 p-4">
          <p class="text-xs uppercase tracking-[0.18em] text-slate-500">Round</p>
          <p class="mt-2 text-2xl font-bold text-ink">{{ turn.round_number }}</p>
        </div>
        <div class="rounded-3xl border border-slate-200/80 bg-white/80 p-4">
          <p class="text-xs uppercase tracking-[0.18em] text-slate-500">Position</p>
          <p class="mt-2 text-2xl font-bold text-ink">{{ turn.turn_position }}</p>
        </div>
        <div class="rounded-3xl border border-slate-200/80 bg-white/80 p-4">
          <p class="text-xs uppercase tracking-[0.18em] text-slate-500">Genre</p>
          <p class="mt-2 text-2xl font-bold text-ink">
            {{ turn.status === "ACTIVE" ? "Waiting" : (turn.genre?.name || "Waiting") }}
          </p>
        </div>
      </div>

      <div class="rounded-[1.75rem] p-5 text-white" :style="{ backgroundColor: turn.team.color }">
        <p class="text-sm uppercase tracking-[0.2em] text-white/80">Team On Deck</p>
        <p class="mt-2 text-2xl font-bold">{{ turn.team.name }}</p>
      </div>

      <div
        v-if="turn.answer"
        class="grid gap-4 rounded-[1.75rem] border border-indigo-200 bg-indigo-50 p-5 md:grid-cols-[120px_1fr]"
      >
        <img
          v-if="turn.answer.artwork_url"
          :src="turn.answer.artwork_url"
          :alt="`${turn.answer.title} artwork`"
          class="h-28 w-28 rounded-2xl object-cover shadow-md"
        >
        <div>
          <p class="text-xs uppercase tracking-[0.2em] text-indigo-500">Answer Revealed</p>
          <h3 class="mt-2 text-2xl font-bold text-ink">{{ turn.answer.title }}</h3>
          <p class="mt-1 text-base text-slate-700">{{ turn.answer.artist }}</p>
          <p class="mt-2 text-sm text-slate-500">{{ turn.answer.album }}</p>
        </div>
      </div>
      <div
        v-else
        class="rounded-[1.75rem] border border-dashed border-slate-300 bg-white/70 p-5 text-slate-600"
      >
        Song title and artist stay hidden until the admin reveals the answer.
      </div>
    </div>

    <div v-else class="rounded-[1.75rem] border border-dashed border-slate-300 bg-white/80 p-6 text-slate-600">
      The game has no active turn yet.
    </div>
  </section>
</template>

<script setup lang="ts">
import type { CurrentTurn } from "~/types/game";

defineProps<{
  turn: CurrentTurn | null;
}>();
</script>
