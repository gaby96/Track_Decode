<template>
  <section class="rounded-[2rem] border border-white/70 bg-[var(--card)] p-4 shadow-pulse backdrop-blur sm:p-6 md:p-8">
    <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div class="min-w-0">
        <p class="text-sm font-medium uppercase tracking-[0.22em] text-slate-500">
          Standings
        </p>
        <h2 class="font-display text-2xl text-ink sm:text-3xl">Leaderboard</h2>
      </div>
      <p class="text-sm text-slate-500">{{ standings.length }} teams</p>
    </div>

    <div class="mt-6 space-y-3">
      <div
        v-for="entry in standings"
        :key="entry.id"
        class="grid items-start gap-4 rounded-[1.5rem] border border-slate-200/70 bg-white/85 p-4 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_minmax(0,0.8fr)_72px] lg:items-center"
      >
        <div class="flex min-w-0 items-center gap-3">
          <div
            class="flex h-12 w-12 items-center justify-center rounded-2xl text-lg font-bold text-white"
            :style="{ backgroundColor: entry.color }"
          >
            {{ entry.rank }}
          </div>
          <div class="min-w-0">
            <p class="break-words text-base font-bold text-ink sm:text-lg">{{ entry.name }}</p>
            <p class="text-sm text-slate-500">Position {{ entry.position }}</p>
          </div>
        </div>

        <div class="min-w-0">
          <p class="text-xs uppercase tracking-[0.18em] text-slate-500">Leader</p>
          <p class="mt-1 break-words text-sm font-medium text-slate-700">
            {{ entry.leader?.display_name || "Pending vote" }}
          </p>
        </div>

        <div>
          <p class="text-xs uppercase tracking-[0.18em] text-slate-500">Points</p>
          <p class="mt-1 text-2xl font-bold text-ink">{{ entry.total_points }}</p>
        </div>

        <div class="text-left text-sm text-slate-500 lg:text-right">
          Rank {{ entry.rank }}
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { StandingsEntry } from "~/types/game";

defineProps<{
  standings: StandingsEntry[];
}>();
</script>
