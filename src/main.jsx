import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import "./styles.css";

// 純靜態的索引頁(/mlb/ /npb/ /kbo/)由 prerender 產生完整 HTML,內容只是連結
// 清單,不需要互動。App 不認得這些路徑,掛載後會把它們洗成首頁 —— 所以這裡
// 直接跳過掛載,讓預渲染的 HTML 留在畫面上(導覽列是真的 <a>,沒有 JS 也能用)。
// 新增這類靜態頁時記得把路徑加進來。
// 純靜態頁:三個聯盟索引、排行榜,以及球季逐場頁 /player/{slug}/{年}/
// 球員頁也在內。預渲染的球員頁本來就是完整的靜態文件 —— 實測靜態版可見文字
// 2094 字 vs 掛載後 1830 字(靜態還多一段介紹),導覽是真的 <a>,連結都有 href。
// 掛載只是把同樣的內容重畫一次,代價是 65KB JS + 35KB players.json ≈ 100KB,
// 而 GSC 顯示有曝光的 37 個頁面裡 36 個是球員頁 —— 搜尋流量幾乎全部直接落在
// 這種頁。從首頁點進去時仍然是 SPA 導覽(App 已經載入),不受影響。
const STATIC_PAGES =
  /^\/(mlb|npb|kbo|leaders|players|news|media)\/?$|^\/news\/[^/]+\/$|^\/player\/[^/]+\/(\d{4}\/?)?$/;

if (!STATIC_PAGES.test(window.location.pathname.replace(import.meta.env.BASE_URL, "/"))) {
  createRoot(document.getElementById("root")).render(<App />);
}
