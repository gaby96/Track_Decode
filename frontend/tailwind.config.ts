import type { Config } from "tailwindcss";

export default <Partial<Config>>{
  theme: {
    extend: {
      colors: {
        ink: "#101828",
        mist: "#F4F7FB",
        aurora: "#14B8A6",
        ember: "#F97316",
        voltage: "#2563EB",
        plum: "#7C3AED",
      },
      fontFamily: {
        display: ["Fraunces", "serif"],
        sans: ["Space Grotesk", "sans-serif"],
      },
      boxShadow: {
        pulse: "0 20px 60px rgba(16, 24, 40, 0.14)",
      },
      backgroundImage: {
        grid: "linear-gradient(rgba(16,24,40,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(16,24,40,0.05) 1px, transparent 1px)",
      },
    },
  },
};
