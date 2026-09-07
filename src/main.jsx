import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import "./styles.css";

// 純靜態的索引頁(/mlb/ /npb/ /kbo/)由 prerender 產生完整 HTML,內容只是連結
// 清單,不需要互動。App 不認得這些路徑,掛載後會把它們洗成首頁 —— 所以這裡
// 直接跳過掛載,讓預渲染的 HTML 留在畫面上(導覽列是真的 <a>,沒有 JS 也能用)。
// 新增這類靜態頁時記得把路徑加進來。
const STATIC_PAGES = /^\/(mlb|npb|kbo)\/?$/;

if (!STATIC_PAGES.test(window.location.pathname.replace(import.meta.env.BASE_URL, "/"))) {
  createRoot(document.getElementById("root")).render(<App />);
}
