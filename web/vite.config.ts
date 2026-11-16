import react from "@vitejs/plugin-react"
import { defineConfig } from "vitest/config"

const api = process.env.FLAKEGUARD_API_URL ?? "http://127.0.0.1:8000"

export default defineConfig({
  plugins: [react()],
  build: {
    // The FastAPI app serves this directory, so no separate web server is needed.
    outDir: "../src/flakeguard/web",
    emptyOutDir: true,
    sourcemap: false,
  },
  server: { port: 5173, proxy: { "/api": api, "/config": api, "/health": api } },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
})
