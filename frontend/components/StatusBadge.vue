<template>
  <span
    class="inline-flex items-center rounded-full px-3 py-1 text-xs font-bold uppercase tracking-[0.18em]"
    :class="tone"
  >
    {{ label }}
  </span>
</template>

<script setup lang="ts">
const props = defineProps<{
  status: string;
}>();

const label = computed(() => props.status.replaceAll("_", " "));

const tone = computed(() => {
  const tones: Record<string, string> = {
    LOBBY_OPEN: "bg-emerald-100 text-emerald-800",
    LOBBY_CLOSED: "bg-slate-200 text-slate-700",
    TEAMS_ASSIGNED: "bg-sky-100 text-sky-800",
    VOTING_OPEN: "bg-amber-100 text-amber-800",
    VOTING_CLOSED: "bg-orange-100 text-orange-800",
    IN_PROGRESS: "bg-violet-100 text-violet-800",
    TRACK_READY: "bg-cyan-100 text-cyan-800",
    PLAYING: "bg-fuchsia-100 text-fuchsia-800",
    AWAITING_ANSWER: "bg-yellow-100 text-yellow-800",
    ANSWER_REVEALED: "bg-indigo-100 text-indigo-800",
    COMPLETED: "bg-slate-900 text-white",
    FINISHED: "bg-ink text-white",
    ACTIVE: "bg-violet-100 text-violet-800",
  };

  return tones[props.status] || "bg-slate-200 text-slate-700";
});
</script>
