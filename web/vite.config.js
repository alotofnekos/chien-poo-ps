import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api':     'http://localhost:10000',
      '/auth':    'http://localhost:10000',
      '/confirm': 'http://localhost:10000',
      '/me':      'http://localhost:10000',
      '/logout':  'http://localhost:10000',
    }
  }
})