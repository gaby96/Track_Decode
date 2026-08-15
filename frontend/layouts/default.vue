<template>
  <div class="relative min-h-screen overflow-hidden">
    <div
      class="pointer-events-none absolute inset-0 bg-grid bg-[length:28px_28px] opacity-40"
    />
    <div
      class="pointer-events-none absolute left-[-6rem] top-16 h-48 w-48 rounded-full bg-aurora/20 blur-3xl"
    />
    <div
      class="pointer-events-none absolute right-[-4rem] top-40 h-56 w-56 rounded-full bg-ember/20 blur-3xl"
    />

    <header class="relative z-10 mx-auto flex w-full max-w-7xl items-center justify-between px-6 py-6 md:px-10">
      <NuxtLink to="/" class="inline-flex items-center gap-3">
        <div
          class="flex h-11 w-11 items-center justify-center rounded-2xl bg-ink text-sm font-bold text-white shadow-pulse"
        >
          SQ
        </div>
        <div>
          <p class="font-display text-xl text-ink">Spotify Game</p>
          <p class="text-sm text-slate-600">Live team music quiz frontend</p>
        </div>
      </NuxtLink>

      <div class="hidden items-center gap-3 md:flex">
        <a
          :href="`${config.public.backendOrigin}/admin/`"
          class="rounded-full border border-slate-300/80 bg-white/80 px-4 py-2 text-sm font-medium text-slate-700 hover:border-slate-400 hover:bg-white"
          rel="noreferrer"
          target="_blank"
        >
          Django Admin
        </a>
        <a
          :href="`${config.public.backendOrigin}/api-auth/login/`"
          class="rounded-full bg-ink px-4 py-2 text-sm font-medium text-white hover:bg-slate-800"
          rel="noreferrer"
          target="_blank"
        >
          Backend Login
        </a>
      </div>
    </header>

    <main class="relative z-10 mx-auto w-full max-w-7xl px-6 pb-16 md:px-10">
      <slot />
    </main>
  </div>
</template>

<script setup lang="ts">
const config = useRuntimeConfig();
</script>
