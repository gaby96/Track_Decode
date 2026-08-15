<template>
  <section class="winner-shell overflow-hidden rounded-[2rem] border border-white/80 bg-[var(--card-strong)] p-4 shadow-pulse backdrop-blur sm:p-6 md:p-8">
    <div class="pointer-events-none absolute inset-0">
      <div class="winner-glow winner-glow-left" />
      <div class="winner-glow winner-glow-right" />
      <div
        v-for="spark in sparks"
        :key="spark.id"
        class="winner-spark"
        :style="spark.style"
      />
    </div>

    <div class="relative z-10">
      <div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div class="min-w-0">
          <p class="text-sm font-medium uppercase tracking-[0.22em] text-amber-700">
            Final Results
          </p>
          <h2 class="mt-2 font-display text-3xl text-ink sm:text-4xl">
            {{ title }}
          </h2>
          <p class="mt-3 max-w-2xl text-sm leading-7 text-slate-600">
            Every team has completed every round. The board is locked and the winners are in.
          </p>
        </div>
      </div>

      <div class="mt-8 grid gap-5 2xl:grid-cols-[minmax(0,1.15fr)_minmax(20rem,0.85fr)]">
        <div class="grid gap-4 xl:grid-cols-2">
          <article
            v-for="(winner, index) in winners"
            :key="winner.id"
            class="winner-card min-w-0 rounded-[1.75rem] border bg-white/90 p-4 sm:p-5"
            :style="winnerCardStyle(winner, index)"
          >
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div class="min-w-0 flex-1">
                <p class="text-xs uppercase tracking-[0.22em] text-slate-500">
                  {{ winners.length === 1 ? "Champion" : `Co-Champion ${index + 1}` }}
                </p>
                <h3 class="mt-2 break-words text-2xl font-bold text-ink sm:text-3xl">{{ winner.name }}</h3>
              </div>
              <div class="winner-badge">
                ★
              </div>
            </div>

            <div class="mt-6 grid gap-3 md:grid-cols-2">
              <div class="rounded-2xl bg-slate-50 px-4 py-3">
                <p class="text-xs uppercase tracking-[0.18em] text-slate-500">Points</p>
                <p class="mt-1 text-2xl font-bold text-ink">{{ winner.total_points }}</p>
              </div>
              <div class="rounded-2xl bg-slate-50 px-4 py-3">
                <p class="text-xs uppercase tracking-[0.18em] text-slate-500">Leader</p>
                <p class="mt-1 break-words text-sm font-semibold text-slate-700">
                  {{ winner.leader?.display_name || "No leader" }}
                </p>
              </div>
            </div>
          </article>
        </div>

        <div class="min-w-0 rounded-[1.75rem] border border-slate-200/80 bg-white/88 p-4 sm:p-5">
          <p class="text-xs uppercase tracking-[0.22em] text-slate-500">Final Ranking</p>

          <div class="mt-6 space-y-3">
            <article
              v-for="(entry, index) in props.standings"
              :key="entry.id"
              class="ranking-card flex items-start gap-3 rounded-[1.35rem] border bg-white px-4 py-4 sm:gap-4"
              :style="rankingCardStyle(entry, index)"
            >
              <div
                class="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-2xl text-lg font-black text-white shadow-sm"
                :style="{ backgroundColor: entry.color }"
              >
                {{ ordinalLabel(index + 1) }}
              </div>
              <div class="min-w-0 flex-1">
                <p class="break-words text-base font-bold leading-6 text-ink sm:text-lg">
                  {{ entry.name }}
                </p>
                <p class="mt-1 text-sm text-slate-500">
                  Rank {{ entry.rank }} · Position {{ entry.position }} · {{ entry.total_points }} points
                </p>
                <p class="mt-1 break-words text-sm text-slate-600">
                  Leader: {{ entry.leader?.display_name || "No leader" }}
                </p>
              </div>
            </article>
          </div>
        </div>
      </div>

      <div
        v-if="$slots.actions"
        class="mt-6 rounded-[1.5rem] border border-slate-200/80 bg-white/88 p-4 sm:p-5"
      >
        <slot name="actions" />
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { StandingsEntry } from "~/types/game";

const props = defineProps<{
  finishedAt: string | null;
  standings: StandingsEntry[];
  winners: StandingsEntry[];
}>();

const title = computed(() => (
  props.winners.length === 1 ? "We Have a Winner" : "Shared Victory"
));

const sparks = [
  {
    id: "left-top",
    style: "left: 7%; top: 14%; animation-delay: 0s;",
  },
  {
    id: "left-mid",
    style: "left: 18%; top: 72%; animation-delay: 1.1s;",
  },
  {
    id: "center-top",
    style: "left: 46%; top: 10%; animation-delay: 0.6s;",
  },
  {
    id: "right-top",
    style: "left: 82%; top: 18%; animation-delay: 1.5s;",
  },
  {
    id: "right-low",
    style: "left: 74%; top: 76%; animation-delay: 0.4s;",
  },
];

function winnerCardStyle(entry: StandingsEntry, index: number) {
  return {
    borderColor: `${entry.color}55`,
    boxShadow: `0 18px 40px ${entry.color}1f`,
    animationDelay: `${index * 140}ms`,
  };
}

function rankingCardStyle(entry: StandingsEntry, index: number) {
  return {
    borderColor: `${entry.color}55`,
    boxShadow: `0 14px 30px ${entry.color}18`,
    animationDelay: `${220 + index * 100}ms`,
    background: `linear-gradient(135deg, ${entry.color}12 0%, rgba(255,255,255,0.96) 38%)`,
  };
}

function ordinalLabel(position: number) {
  const mod10 = position % 10;
  const mod100 = position % 100;

  if (mod10 === 1 && mod100 !== 11) {
    return `${position}st`;
  }

  if (mod10 === 2 && mod100 !== 12) {
    return `${position}nd`;
  }

  if (mod10 === 3 && mod100 !== 13) {
    return `${position}rd`;
  }

  return `${position}th`;
}
</script>

<style scoped>
.winner-shell {
  position: relative;
}

.winner-glow {
  position: absolute;
  width: 16rem;
  height: 16rem;
  border-radius: 9999px;
  filter: blur(18px);
  opacity: 0.5;
  animation: glow-shift 7s ease-in-out infinite;
}

.winner-glow-left {
  left: -3rem;
  top: -4rem;
  background: radial-gradient(circle, rgba(251, 191, 36, 0.42), rgba(251, 191, 36, 0));
}

.winner-glow-right {
  right: -4rem;
  bottom: -4rem;
  background: radial-gradient(circle, rgba(59, 130, 246, 0.26), rgba(59, 130, 246, 0));
  animation-delay: 1.4s;
}

.winner-spark {
  position: absolute;
  width: 0.8rem;
  height: 0.8rem;
  border-radius: 9999px;
  background: linear-gradient(135deg, rgba(251, 191, 36, 0.95), rgba(249, 115, 22, 0.85));
  box-shadow: 0 0 18px rgba(251, 191, 36, 0.55);
  animation: float-spark 3.4s ease-in-out infinite;
}

.winner-card {
  position: relative;
  overflow: hidden;
  transform: translateY(18px) scale(0.98);
  opacity: 0;
  animation: card-rise 0.7s cubic-bezier(0.22, 1, 0.36, 1) forwards;
}

.winner-card::after {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(120deg, transparent 22%, rgba(255, 255, 255, 0.65) 50%, transparent 76%);
  transform: translateX(-120%);
  animation: card-shine 4.6s ease-in-out infinite;
}

.winner-badge {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.75rem;
  height: 2.75rem;
  flex-shrink: 0;
  border-radius: 9999px;
  background: linear-gradient(135deg, #fbbf24, #f97316);
  color: white;
  font-size: 1.2rem;
  box-shadow: 0 16px 28px rgba(249, 115, 22, 0.28);
  animation: badge-bob 2.6s ease-in-out infinite;
}

.ranking-card {
  transform: translateY(12px);
  opacity: 0;
  animation: podium-rise 0.6s cubic-bezier(0.22, 1, 0.36, 1) forwards;
}

@keyframes glow-shift {
  0%, 100% {
    transform: translate3d(0, 0, 0) scale(1);
  }

  50% {
    transform: translate3d(0.5rem, 0.8rem, 0) scale(1.08);
  }
}

@keyframes float-spark {
  0%, 100% {
    transform: translate3d(0, 0, 0) scale(0.9);
    opacity: 0.45;
  }

  50% {
    transform: translate3d(0, -12px, 0) scale(1.15);
    opacity: 1;
  }
}

@keyframes card-rise {
  from {
    transform: translateY(18px) scale(0.98);
    opacity: 0;
  }

  to {
    transform: translateY(0) scale(1);
    opacity: 1;
  }
}

@keyframes podium-rise {
  from {
    transform: translateY(12px);
    opacity: 0;
  }

  to {
    transform: translateY(0);
    opacity: 1;
  }
}

@keyframes card-shine {
  0%, 100% {
    transform: translateX(-120%);
  }

  45%, 55% {
    transform: translateX(120%);
  }
}

@keyframes badge-bob {
  0%, 100% {
    transform: translateY(0);
  }

  50% {
    transform: translateY(-5px);
  }
}

@media (min-width: 768px) {
  .winner-badge {
    width: 3rem;
    height: 3rem;
    font-size: 1.35rem;
  }
}
</style>
