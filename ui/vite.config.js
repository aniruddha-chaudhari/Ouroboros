import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The trigger + timeline API runs on :8090. In dev we proxy the API paths to it,
// so the app can fetch relative URLs ('/timeline', '/diagnose') that also work
// in production when FastAPI serves the built app from the same origin.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/timeline': 'http://localhost:8090',
      '/diagnose': 'http://localhost:8090',
      '/webhook': 'http://localhost:8090',
    },
  },
  build: { outDir: 'dist', emptyOutDir: true },
})
