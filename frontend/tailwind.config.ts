import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: { 50: "#eef4ff", 100: "#dbe7ff", 500: "#3b6cf6", 600: "#2f56d9", 700: "#2644ad", 900: "#172554" },
      },
    },
  },
  plugins: [],
} satisfies Config;
