export default defineNuxtConfig({
  compatibilityDate: "2025-07-15",
  devtools: { enabled: true },
  modules: ["@nuxtjs/tailwindcss"],
  css: ["~/assets/css/main.css"],
  runtimeConfig: {
    backendOrigin: process.env.NUXT_BACKEND_ORIGIN || "http://127.0.0.1:8000",
    public: {
      appOrigin:
        process.env.NUXT_PUBLIC_APP_ORIGIN || "http://127.0.0.1:3000",
      backendOrigin:
        process.env.NUXT_PUBLIC_BACKEND_ORIGIN || "http://127.0.0.1:8000",
      wsOrigin: process.env.NUXT_PUBLIC_WS_ORIGIN || "ws://127.0.0.1:8000",
    },
  },
  app: {
    head: {
      title: "Spotify Game",
      meta: [
        {
          name: "viewport",
          content: "width=device-width, initial-scale=1",
        },
        {
          name: "description",
          content:
            "A live team music quiz with lobby, voting, genre spins, playback control, and a live leaderboard.",
        },
      ],
    },
  },
});
