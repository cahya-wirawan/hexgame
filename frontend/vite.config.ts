import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  base: "/overview/",
  plugins: [react()],
  build: {
    outDir: "../app/static/overview",
    emptyOutDir: true
  },
  server: {
    proxy: {
      "/slots": "http://127.0.0.1:8000"
    }
  }
});
