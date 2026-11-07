import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
// The site reads ../results/* and the study's markdown at build time, so every number on the page is generated, never typed.
export default defineConfig({
  base: '/data-engineering-scale-lab/',
  plugins: [react()],
  server: { fs: { allow: ['..'] } },
});
