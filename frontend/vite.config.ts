import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  base: "/overview/",
  plugins: [react()],
  build: {
    outDir: "../server/src/hexgame_server/static/overview",
    emptyOutDir: true
  },
  server: {
    proxy: {
      "/slots": "http://127.0.0.1:8000",
      "/api/statistics": "http://127.0.0.1:8000",
      "/ws": { target: "ws://127.0.0.1:8000", ws: true }
    }
  }
});
