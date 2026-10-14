import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/calculate": `http://localhost:${process.env.BACKEND_PORT ?? "8000"}`,
      "/health": `http://localhost:${process.env.BACKEND_PORT ?? "8000"}`,
    },
  },
});
