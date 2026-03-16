import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  build: {
    // Output gets overridden per-build by the render script
    outDir: path.resolve(__dirname, "../static"),
    emptyOutDir: false,
    rollupOptions: {
      input: path.resolve(__dirname, "entry.html"),
    },
  },
  resolve: {
    alias: {
      "@theme": path.resolve(__dirname, "../themes/default/react"),
    },
  },
});
