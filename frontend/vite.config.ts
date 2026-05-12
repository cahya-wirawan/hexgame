import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  base: "/overview/",
  plugins: [react()],
  build: {
    outDir: "../src/hexgame/server/static/overview",
    emptyOutDir: true
  },
  server: {
    proxy: {
      "/slots": "http://127.0.0.1:8000",
      "/api/statistics": "http://127.0.0.1:8000"
    }
  }
});
