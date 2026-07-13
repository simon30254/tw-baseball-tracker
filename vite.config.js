import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// GitHub Pages 專案站服務於子路徑 /tw-baseball-tracker/,由 deploy workflow 設 BASE_PATH。
// 本機開發與(未來)根網域自訂網域則用預設 "/"。
export default defineConfig({
  base: process.env.BASE_PATH || "/",
  plugins: [react()],
});
