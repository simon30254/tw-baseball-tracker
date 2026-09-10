/**
 * 靜態預渲染:在 vite build 之後,為每位球員產生 /player/{slug}/index.html
 * ============================================================================
 * 目的:GitHub Pages 是純 CSR SPA,爬蟲/LLM(GPTBot、PerplexityBot 多半不執行 JS)
 * 只會拿到空的 #root。這支腳本把每位球員的中文名、個人資料、球季數據、最近出賽
 * 直接寫進靜態 HTML,並附上 JSON-LD(Person/SportsTeam),讓搜尋引擎與 LLM 可讀、可引用。
 * React 載入後會依網址接管同一頁(見 App.jsx 的 player 路由),內容一致故閃動極小。
 *
 * 另外產出:sitemap.xml、robots.txt,並把首頁 #root 填入可爬取的球員索引與 meta。
 *
 * 執行(build 後):BASE_PATH=/tw-baseball-tracker/ node scripts/prerender.mjs
 */

import { readFileSync, writeFileSync, mkdirSync, readdirSync } from "node:fs";
import { buildFeed, recentForm, seasonLine } from "../src/lib/recap.js";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");
const DIST = resolve(ROOT, "dist");

const BASE = (process.env.BASE_PATH || "/").replace(/\/*$/, "/"); // 保證結尾斜線
const ORIGIN = (process.env.SITE_ORIGIN || "https://simon30254.github.io").replace(/\/$/, "");
const SITE = ORIGIN + BASE; // 例:https://simon30254.github.io/tw-baseball-tracker/

const data = JSON.parse(readFileSync(resolve(ROOT, "public/data/players.json"), "utf-8"));
// 有哪些球員的哪些年份有逐場頁(public/data/gamelogs/{slug}.json)。
// 讀一次就好,讓球員頁的年份標題可以連過去。
const seasonLogIndex = new Map();
try {
  for (const f of readdirSync(resolve(ROOT, "public/data/gamelogs"))) {
    if (!f.endsWith(".json")) continue;
    const slug = f.slice(0, -5);
    const store = JSON.parse(readFileSync(resolve(ROOT, "public/data/gamelogs", f), "utf-8"));
    seasonLogIndex.set(slug, new Set(Object.keys(store)));
  }
} catch {
  /* 還沒抓過逐場就是空的,不影響其他頁 */
}

// clutchgtime.com 上有專文的球員。兩個站同屬 clutchgtime.com,同一位球員若兩邊
// 都主打「{名} 成績」會跨站互搶,所以這裡分工:文章站主打「成績/最新動態」,
// 追蹤站改主打「逐場紀錄/數據」。沒有專文的球員不受此限,照常主打成績。
let wpArticleNames = new Set();
try {
  wpArticleNames = new Set(
    JSON.parse(readFileSync(resolve(ROOT, "scripts/wp_articles.json"), "utf-8")).articles.map((a) => a.name)
  );
} catch {
  wpArticleNames = new Set();
}

// MLB 官方異動(scripts/fetch_transactions.py)。消息頁的事實主要來自這裡。
let transactions = [];
try {
  transactions = JSON.parse(readFileSync(resolve(ROOT, "public/data/transactions.json"), "utf-8")).items || [];
} catch {
  transactions = [];
}

// 媒體新聞(scripts/fetch_news.py)。抓不到就是空的,不擋 build —— 新聞是加值,
// 不是這個站的核心資料。
let news = [];
try {
  news = JSON.parse(readFileSync(resolve(ROOT, "public/data/news.json"), "utf-8")).items || [];
} catch {
  news = [];
}

// 歷代球員(已離開大聯盟體系)。檔案不存在時視為空,不擋 build。
// alumniLastmod:歷史資料很少變動,sitemap 用它而不是「今天」
let alumni = [];
try {
  alumni = JSON.parse(readFileSync(resolve(ROOT, "public/data/alumni.json"), "utf-8")).players || [];
} catch {
  alumni = [];
}
let alumniLastmod = "";
try {
  alumniLastmod = (JSON.parse(readFileSync(resolve(ROOT, "public/data/alumni.json"), "utf-8")).updated_at || "").slice(0, 10);
} catch {
  alumniLastmod = "";
}
const template = readFileSync(resolve(DIST, "index.html"), "utf-8");
const season = data.season;

const LEVEL_LABEL = {
  MLB: "大聯盟", AAA: "3A", AA: "2A", "High-A": "高階1A", A: "1A", Rookie: "新人聯盟",
  一軍: "一軍", 二軍: "二軍",
};
const LEAGUE_LABEL = { mlb: "旅美", milb: "旅美", npb: "旅日", kbo: "旅韓" };
const LEAGUE_ORG = { mlb: "MLB 大聯盟", milb: "MLB 小聯盟", npb: "日本職棒 NPB", kbo: "韓國職棒 KBO" };

const esc = (s) =>
  String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");

const roleZh = (p) => (p.role === "pitcher" ? "投手" : "野手");

// 英文/羅馬名:旅美球員 name_en 本就是英文;旅日/旅韓的 name_en 是中文,改用 slug 還原羅馬拼音
const romanName = (p) =>
  /[a-z]/i.test(p.name_en || "")
    ? p.name_en
    : (p.slug || "").split("-").map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");

// 靜態頁首導覽列(與 React SiteHeader 一致;React 掛載後會取代 #root,此為首次載入/爬蟲用)
function topbarHtml() {
  const nav = [
    // 累積數據/地圖/評比是 SPA 內的分頁、沒有自己的網址,靜態版只能連回首頁;
    // 最新表現與歷代球員有真實網址,直接連過去。
    ["", "每日戰報"], ["news/", "最新消息"], ["latest/", "最新表現"], ["", "累積數據"],
    ["", "地圖"], ["", "評比"], ["alumni/", "歷代球員"],
  ]
    .map(([path, label]) => `<a class="topnav-btn" href="${BASE}${path}">${label}</a>`)
    .join("");
  return (
    `<header class="topbar"><div class="topbar-in wrap">` +
    `<a class="brand" href="${BASE}"><img class="brand-mark" src="${BASE}logo.svg" alt="" width="26" height="34" />旅外球員情報站<span class="brand-sub">台灣旅外棒球員即時數據</span></a>` +
    `<nav class="topnav" aria-label="主導覽">${nav}</nav>` +
    `</div></header>`
  );
}
// 把內容包成與 React 相同的版型:頁首導覽 + 置中內容區
const siteWrap = (inner) => `${topbarHtml()}<div class="wrap page">${inner}</div>`;

// 出賽最多的主層(答案優先摘要用)
function pickMainLevel(p) {
  const ss = p.season_stats || {};
  const keys = Object.keys(ss);
  if (!keys.length) return null;
  const lv = keys.reduce((a, b) => ((ss[b].g || 0) > (ss[a].g || 0) ? b : a));
  return { level: lv, s: ss[lv] };
}

// JSON-LD 一律走這裡輸出。JSON.stringify 不會轉義 "<",若資料裡出現 "</script>"
// (影片標題來自 YouTube,是外部不可信來源)整頁就被截斷。把 < 轉成 \u003c,
// 在 JSON 裡等價、在 HTML 裡則不再是標籤起頭。
const ldScript = (obj) =>
  `<script type="application/ld+json">${JSON.stringify(obj).replace(/</g, "\\u003c")}</script>`;

// 當季戰績一句話摘要(全用既有數據,不編造)
function seasonSummary(p) {
  const ml = pickMainLevel(p);
  if (!ml) return null;
  const s = ml.s;
  const lv = LEVEL_LABEL[ml.level] || ml.level;
  let parts;
  if (p.role === "pitcher") {
    parts = [`${s.g} 場`, `${s.w}勝${s.l}敗`];
    if (s.sv > 0) parts.push(`${s.sv} 救援`);
    parts.push(`${s.ip} 局`, `${s.so} 次三振`);
    // 空值不要印(NPB 資料源沒有 WHIP,照印會變成結尾一句「WHIP 。」)
    if (s.era) parts.push(`防禦率 ${s.era}`);
    if (s.whip) parts.push(`WHIP ${s.whip}`);
  } else {
    parts = [`${s.g} 場`];
    if (s.avg) parts.push(`打擊率 ${s.avg}`);
    if (s.hr) parts.push(`${s.hr} 轟`);
    if (s.rbi) parts.push(`${s.rbi} 打點`);
    if (s.ops) parts.push(`OPS ${s.ops}`);
  }
  return `${season} 球季在${lv}出賽 ${parts.join("、")}。`;
}

// 戰績摘要後面接的「最新表現」一句話(與 App.jsx 的 latestGameText 同一套,兩份要同步)。
// 只用在球員頁的戰績摘要;FAQ 的「球季成績如何」問的是累積,維持原樣。
function latestGameLine(p) {
  const logs = p.game_logs || [];
  const g = logs.reduce((a, x) => (!a || x.date > a.date ? x : a), null);
  if (!g) return null;
  const ml = pickMainLevel(p);
  // 最近一場若不在主要層級(如大聯盟球員被下放打 3A),標出來才不會誤導
  const lvNote = ml && g.level && g.level !== ml.level ? `在${LEVEL_LABEL[g.level] || g.level}` : "";
  const opp = g.opponent ? `對${g.opponent}` : "";
  const d = fmtDateZh(g.date);
  if (g.type === "pitching") {
    const decision = g.win ? "拿下勝投" : g.loss ? "吞下敗投" : g.save ? "拿下救援成功" : "";
    const line = [`投 ${g.ip} 局`, `被 ${g.h} 支安打`, `失 ${g.r} 分`, `${g.so} 次三振`];
    return `最近一場出賽是 ${d}${lvNote}${g.started ? "先發" : "後援"}${opp}${decision},${line.join("、")}。`;
  }
  const line = [g.ab > 0 ? `${g.ab} 打數 ${g.h} 安` : "未有打數"];
  if (g.hr) line.push(`${g.hr} 轟`);
  if (g.rbi) line.push(`${g.rbi} 打點`);
  if (g.bb) line.push(`${g.bb} 次保送`);
  if (g.sb) line.push(`${g.sb} 次盜壘`);
  return `最近一場出賽是 ${d}${lvNote}${opp},${line.join("、")}。`;
}

// 常見問答(FAQPage schema + 頁面顯示;答案皆由資料生成)
function faqItems(p) {
  const items = [];
  const sum = seasonSummary(p);
  if (sum) items.push({ q: `${p.name} ${season} 球季成績如何?`, a: sum });
  items.push({
    q: `${p.name} 目前效力哪一隊?`,
    a: `${p.name} 目前效力於 ${p.org}（${LEAGUE_LABEL[p.league]}${LEVEL_LABEL[p.level] || p.level}）。`,
  });
  const b = p.bio || {};
  if (b.velo && p.role === "pitcher")
    items.push({ q: `${p.name} 最快球速多少?`, a: `${p.name} 最快球速為 ${b.velo}。` });
  const arse = (b.pitches || []).filter((x) => x.pct >= 5);
  if (arse.length && p.role === "pitcher")
    items.push({
      q: `${p.name} 會投哪些球種?`,
      a: `${p.name} ${season} 球季主要使用 ${arse.map((x) => `${x.name}（使用率 ${x.pct}%${x.kmh ? `、平均 ${x.kmh} km/h` : ""}）`).join("、")}。` +
         `球種與球速為該季實際投球追蹤資料。`,
    });
  if (b.debut)
    items.push({
      q: `${p.name} 何時在大聯盟初登場?`,
      a: `${p.name} 於 ${b.debut.replaceAll("-", "/")} 完成 MLB 初登場。`,
    });
  return items;
}

// 同聯盟其他球員(內鏈用);以自身在排序中的位置取後 n 位(環繞)→ 連結分散不集中
// 全站統一層級排序:大聯盟>日職一軍>韓職一軍>3A>2A>日/韓二軍>高階1A>1A>新人聯盟
function rankLevel(lgZh, level) {
  if (level === "MLB") return 0;
  if (level === "一軍") return lgZh === "旅日" ? 1 : 2;
  if (level === "AAA") return 3;
  if (level === "AA") return 4;
  if (level === "二軍") return 5;
  if (level === "High-A") return 6;
  if (level === "A") return 7;
  if (level === "Rookie") return 8;
  return 9;
}
const levelRankP = (p) => rankLevel(LEAGUE_LABEL[p.league], p.level);
function relatedPlayers(p, all, n = 6) {
  const lg = LEAGUE_LABEL[p.league];
  const group = all
    .filter((x) => x.slug && LEAGUE_LABEL[x.league] === lg)
    .sort((a, b) => levelRankP(a) - levelRankP(b) || a.slug.localeCompare(b.slug));
  const others = group.filter((x) => x.id !== p.id);
  let picked = [];
  if (others.length <= n) {
    picked = others;
  } else {
    const i = group.findIndex((x) => x.id === p.id);
    for (let k = 1; picked.length < n; k++) {
      const g = group[(i + k) % group.length];
      if (g.id !== p.id) picked.push(g);
    }
  }
  if (picked.length < n) {
    const extra = all
      .filter((x) => x.slug && x.id !== p.id && !picked.includes(x) && LEAGUE_LABEL[x.league] !== lg)
      .sort((a, b) => levelRankP(a) - levelRankP(b));
    picked = picked.concat(extra.slice(0, n - picked.length));
  }
  return picked;
}

function bioLine(p) {
  const b = p.bio || {};
  // LEAGUE_ORG 是「MLB 大聯盟」、LEVEL_LABEL 是「大聯盟」,兩者字串不同但語意重複,
  // 直接串會寫成「MLB 大聯盟・大聯盟・太空人」。層級已包含在聯盟字串裡就略過。
  const lg = LEAGUE_ORG[p.league] || "";
  const lv = LEVEL_LABEL[p.level] || p.level || "";
  const parts = [lg, lg.includes(lv) ? "" : lv, p.org].filter(Boolean);
  const sub = [];
  if (b.age) sub.push(`${b.age}歲`);
  if (b.pos_zh) sub.push(b.pos_zh);
  if (b.throws && b.bats) sub.push(`${b.throws}投${b.bats}打`);
  if (b.ht && b.wt) sub.push(`${b.ht}cm / ${b.wt}kg`);
  if (b.velo) sub.push(`最快 ${b.velo}`);
  // 主要球種:只列使用率 5% 以上的前四種,零星球種對讀者沒意義
  const arsenal = (b.pitches || []).filter((x) => x.pct >= 5).slice(0, 4);
  if (arsenal.length)
    sub.push(`主要球種 ${arsenal.map((x) => `${x.name} ${x.pct}%${x.kmh ? `(平均 ${x.kmh} km/h)` : ""}`).join("、")}`);
  return parts.concat(sub).join("・");
}

function introText(p) {
  const b = p.bio || {};
  const league = LEAGUE_LABEL[p.league];
  const role = roleZh(p);
  let s = p.heritage
    ? `${p.name}（${romanName(p)}）是效力於${p.org}${LEVEL_LABEL[p.level] || p.level}、具台灣血統的台裔旅美${role}`
    : `${p.name}（${romanName(p)}）是效力於${p.org}${LEVEL_LABEL[p.level] || p.level}的台灣${league}${role}`;
  if (b.velo && p.role === "pitcher") s += `，最快球速 ${b.velo}`;
  if (b.debut) s += `，${b.debut.replaceAll("-", "/")} 完成大聯盟初登場`;
  // 原本這裡是固定句「以下為 X 球季累積數據與最近出賽紀錄」,39 頁一字不差,
  // 造成這些頁在「旅外球員 數據」這類泛用詞上互搶。改成用該球員自己的數字
  // 收尾:每頁都不同,也順便讓摘要在搜尋結果裡就有實質內容。
  const ml = pickMainLevel(p);
  if (ml) {
    const st = ml.s;
    const lv = LEVEL_LABEL[ml.level] || ml.level;
    s += p.role === "pitcher"
      ? `。${season} 球季在${lv}出賽 ${st.g} 場、${st.w}勝${st.l}敗、防禦率 ${st.era}。`
      : `。${season} 球季在${lv}出賽 ${st.g} 場、打擊率 ${st.avg}、${st.hr} 轟。`;
  } else {
    s += `。${season} 球季尚無出賽紀錄。`;
  }
  const gl = (p.game_logs || [])[0];
  if (gl) s += `最近一場出賽在 ${fmtDateZh(gl.date)}。`;
  return s;
}

function statTable(levels, isP) {
  const head = isP
    ? ["層級", "出賽", "勝敗", "救援", "局數", "被安", "保送", "K", "ERA", "WHIP"]
    : ["層級", "出賽", "打數", "安打", "轟", "打點", "得分", "盜", "保送", "K", "打率", "OPS"];
  const rows = levels.map(([lv, s]) => {
    const cells = isP
      ? [LEVEL_LABEL[lv] || lv, s.g, `${s.w}-${s.l}`, s.sv, s.ip, s.h ?? "—", s.bb, s.so, s.era, s.whip]
      : [LEVEL_LABEL[lv] || lv, s.g, s.ab, s.h, s.hr, s.rbi, s.r ?? "—", s.sb, s.bb ?? "—", s.so ?? "—", s.avg, s.ops];
    return `<tr>${cells.map((c) => `<td>${esc(c)}</td>`).join("")}</tr>`;
  });
  return `<table><thead><tr>${head.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table>`;
}

function seasonTable(p) {
  const levels = Object.entries(p.season_stats || {});
  if (!levels.length) return `<p>本季尚無累積數據。</p>`;
  return statTable(levels, p.role === "pitcher");
}

// 生涯逐年一張表(Baseball Reference 的作法)。原本每個球季各一張只有一列的小表、
// 每張都重複一次表頭 —— 四個球季就有四行「層級 出賽 打數…」,右側三分之二空白,
// 看起來像沒有內容,而且完全無法跨年比較。改成年份當列、生涯合計放最後。
// App.jsx 的 CareerYearTable 是等效實作,兩份要同步。
function careerYearTable(p) {
  const hist = p.prev_season || {};
  const years = Object.keys(hist).sort((a, b) => Number(b) - Number(a));
  const career = Object.entries(p.career || {});
  if (!years.length && !career.length) return "";
  const isP = p.role === "pitcher";
  const head = isP
    ? ["年份", "球隊", "層級", "出賽", "勝敗", "救援", "局數", "被安", "保送", "K", "ERA", "WHIP"]
    : ["年份", "球隊", "層級", "出賽", "打數", "安打", "轟", "打點", "得分", "盜", "保送", "K", "打率", "OPS"];
  const cells = (s) => isP
    ? [s.g, `${s.w}-${s.l}`, s.sv, s.ip, s.h ?? "—", s.bb, s.so, s.era || "—", s.whip || "—"]
    : [s.g, s.ab, s.h, s.hr, s.rbi, s.r ?? "—", s.sb, s.bb ?? "—", s.so ?? "—", s.avg || "—", s.ops || "—"];
  const rows = [];
  for (const y of years) {
    const levels = Object.entries(hist[y] || {});
    levels.forEach(([lv, st], i) => {
      rows.push(`<tr>` +
        // 同一年有多個層級時,年份只寫在第一列,視覺上才分得出是同一年
        `<td>${i === 0 ? y : ""}</td>` +
        // 小聯盟長隊名會被 CSS 截斷,補 title 讓滑過看得到完整名稱
        `<td title="${esc(st.team || "")}">${esc(st.team || "—")}</td>` +
        `<td>${esc(LEVEL_LABEL[lv] || lv)}</td>` +
        cells(st).map((c) => `<td>${esc(c)}</td>`).join("") + `</tr>`);
    });
  }
  const totalRows = career.map(([lv, st], i) =>
    `<tr class="yr-total">` +
    `<td>${i === 0 ? "生涯" : ""}</td><td>—</td><td>${esc(LEVEL_LABEL[lv] || lv)}</td>` +
    cells(st).map((c) => `<td>${esc(c)}</td>`).join("") + `</tr>`).join("");
  return `<h2>生涯逐年數據</h2><div class="table-scroll">` +
    `<table class="stat-table yr-table"><thead><tr>${head.map((h) => `<th>${h}</th>`).join("")}</tr></thead>` +
    `<tbody>${rows.join("")}${totalRows}</tbody></table></div>`;
}

function recentGames(p) {
  const games = (p.game_logs || []).slice(0, 10);
  if (!games.length) return "";
  const isP = p.role === "pitcher";
  const head = isP
    ? ["日期", "對手", "局", "安", "失", "K", "BB", "HR"]
    : ["日期", "對手", "打數", "安", "轟", "打點", "得", "盜", "BB"];
  const rows = games.map((g) => {
    const date = g.date.slice(5).replace("-", "/");
    const opp = (g.level ? `[${LEVEL_LABEL[g.level] || g.level}] ` : "") + (g.opponent || "");
    const cells = isP
      ? [date, opp, g.ip, g.h, g.r, g.so, g.bb, g.hr]
      : [date, opp, g.ab, g.h, g.hr, g.rbi, g.r, g.sb, g.bb];
    return `<tr>${cells
      .map((c, i) => `<td${i === 1 ? ' class="rc-opp"' : ""}>${esc(c)}</td>`)
      .join("")}</tr>`;
  });
  return `<h2>最近出賽</h2><div class="table-scroll"><table class="stat-table rc-table"><thead><tr>${head
    .map((h) => `<th>${h}</th>`)
    .join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>`;
}

// ---- 球員頁「最新動態」時間軸 ----
// 與 App.jsx 的 buildTimeline/Timeline 同一套邏輯,兩份要一起改。
// 視窗從「最新一筆動態」往回算 30 天(不是從今天),長期未出賽的球員才不會空白。
function buildTimeline(p, days = 30, max = 10) {
  const items = [];
  (p.moves || []).forEach((m) => items.push({ date: m.date, kind: "move", moveType: m.type, text: m.text }));
  // 亮點出賽 +「最近一場」(即使表現平平也收,否則「最新動態」會漏掉最新消息)
  const logs = p.game_logs || [];
  const newest = logs.reduce((a, g) => (!a || g.date > a.date ? g : a), null);
  logs.forEach((g) => {
    if (isHot(g) || g === newest) items.push({ date: g.date, kind: "game", game: g });
  });
  ((p.content || {}).articles || []).forEach((a) => {
    if (a.date) items.push({ date: a.date, kind: "article", article: a });
  });
  if (!items.length) return [];
  const rank = (it) => (it.kind === "move" ? 0 : it.kind === "game" ? 1 : 2);
  items.sort((a, b) => (a.date === b.date ? rank(a) - rank(b) : a.date < b.date ? 1 : -1));
  const cut = new Date(items[0].date + "T00:00:00").getTime() - days * 86400000;
  return items.filter((it) => new Date(it.date + "T00:00:00").getTime() >= cut).slice(0, max);
}

// 與 App.jsx 首頁「近期異動」同一組圖示
const MOVE_ICON = { promote: "↑", demote: "↓", il: "🏥", return: "↩" };

function timelineHtml(p, items) {
  if (!items.length) return "";
  const li = items
    .map((it) => {
      const d = `<span class="tl-date">${it.date.slice(5).replace("-", "/")}</span>`;
      if (it.kind === "move")
        return `<li class="tl-item tl-move-${esc(it.moveType)}">${d}<span class="tl-body">` +
          `<span class="tl-icon">${MOVE_ICON[it.moveType] || "・"}</span>` +
          `<span class="tl-line">${esc(it.text)}</span></span></li>`;
      if (it.kind === "game" && !hasPerfPage(p.slug, it.game.date))
        // 該場沒有表現頁(在視窗外)→ 顯示但不連結,免得連到 404
        return `<li class="tl-item">${d}<span class="tl-body">` +
          `<span class="badge">${esc(badgeText(it.game))}</span>` +
          `<span class="tl-line">${esc(perfLineTxt(it.game))}</span>` +
          (it.game.opponent ? `<span class="tl-opp">對${esc(it.game.opponent)}</span>` : "") +
          `</span></li>`;
      if (it.kind === "game")
        return `<li class="tl-item">${d}<a class="tl-body tl-link" href="${BASE}performance/${p.slug}/${it.game.date}/">` +
          `<span class="badge">${esc(badgeText(it.game))}</span>` +
          `<span class="tl-line">${esc(perfLineTxt(it.game))}</span>` +
          (it.game.opponent ? `<span class="tl-opp">對${esc(it.game.opponent)}</span>` : "") +
          (it.game.video ? `<span class="tl-video" title="有精華影片">▶</span>` : "") +
          `</a></li>`;
      return `<li class="tl-item">${d}<a class="tl-body tl-link" href="${esc(it.article.url)}">` +
        `<span class="tl-icon">📰</span><span class="tl-line">${esc(it.article.title)}</span></a></li>`;
    })
    .join("");
  return `<section class="tl"><h2 class="tl-title">📌 最新動態</h2><ol class="tl-list">${li}</ol></section>`;
}

// 球員頁的「近況與消息」。內容由本站資料寫成:近況出自 game_logs(src/lib/recap.js
// 計算)、異動出自 MLB 官方紀錄;官方推不出來的才引用媒體原標題並註明出處。
// 這裡刻意不列一串外站標題 —— 球員頁的價值是「看完就知道他最近怎麼樣」,
// 而不是把讀者送去別的網站看別人寫的。
const NEWS_PER_PLAYER = 4;
const txByPlayer = new Map();
for (const t of transactions) {
  const k = String(t.id);
  if (!txByPlayer.has(k)) txByPlayer.set(k, []);
  txByPlayer.get(k).push(t);
}
const quotesByPlayer = new Map();   // 官方推不出來、只能引用的媒體消息

function buildPlayerQuotes() {
  const feed = buildFeed({ players: data.players, transactions, moves: data.moves || [], news, days: 30 });
  for (const day of feed) {
    for (const e of day.entries) {
      if (!e.quote) continue;
      const k = String(e.player.id);
      if (!quotesByPlayer.has(k)) quotesByPlayer.set(k, []);
      quotesByPlayer.get(k).push({ ...e.quote, date: e.date, others: e.others, sources: e.sources });
    }
  }
}
buildPlayerQuotes();

function recapHtml(p) {
  const form = recentForm(p);
  const txs = (txByPlayer.get(String(p.id)) || []).filter((t) => t.big).slice(0, NEWS_PER_PLAYER);
  const quotes = (quotesByPlayer.get(String(p.id)) || []).slice(0, NEWS_PER_PLAYER);
  if (!form && !txs.length && !quotes.length) return "";

  const md = (d) => `${Number(d.split("-")[1])}/${Number(d.split("-")[2])}`;
  let out = `<section class="related"><div class="related-block">` +
    `<h2 class="related-title">📋 ${esc(p.name)}的近況</h2>`;
  if (form) out += `<p class="rc-form">${esc(form)}</p>`;
  if (txs.length) {
    out += `<ul class="rc-list">` + txs.map((t) =>
      `<li><span class="rc-d">${esc(md(t.date))}</span><span class="rc-t">${esc(t.text || t.official)}</span></li>`
    ).join("") + `</ul><p class="rc-src">異動來源：MLB 官方異動紀錄</p>`;
  }
  if (quotes.length) {
    out += `<p class="rc-sub">其他消息（本站資料無法取得，引用媒體報導）</p><ul class="rc-list rc-list-q">` +
      quotes.map((q) =>
        `<li><span class="rc-d">${esc(md(q.date))}</span><span class="rc-t">「${esc(q.title)}」` +
        `<span class="rc-attr">據《${esc(q.source || "媒體")}》報導` +
        (q.url ? ` <a href="${esc(q.url)}" target="_blank" rel="noopener nofollow">原文</a>` : "") +
        `</span></span></li>`
      ).join("") + `</ul>`;
  }
  out += `<p class="related-more"><a href="${BASE}news/">看全部旅外球員消息 →</a></p>` +
    `</div></section>`;
  return out;
}

// hideUrls:已經在「最新動態」列過的報導不再重複(這裡只留較舊的那些)
function relatedHtml(p, hideUrls) {
  const c = p.content || {};
  const articles = (c.articles || []).filter((a) => !(hideUrls && hideUrls.has(a.url)));
  const qa = c.qa || [];
  let out = "";
  if (articles.length) {
    const li = articles
      .map(
        (a) =>
          `<li><a href="${esc(a.url)}">${esc(a.title)}</a>${
            a.date ? ` <span class="related-date">${a.date.slice(5).replace("-", "/")}</span>` : ""
          }</li>`
      )
      .join("");
    out += `<h2>相關報導</h2><ul>${li}</ul>`;
  }
  if (qa.length) {
    const li = qa.map((q) => `<li><a href="${esc(q.url)}">${esc(q.q)}</a></li>`).join("");
    out += `<h2>延伸問答</h2><ul>${li}</ul>`;
  }
  return out;
}

// 該球員在 clutchgtime 最新的一篇報導(導流回 The Clutch Time)
function newestArticle(p) {
  const arts = (p.content && p.content.articles) || [];
  if (!arts.length) return null;
  return arts.slice().sort((a, b) => (b.date || "").localeCompare(a.date || ""))[0];
}

function faqHtml(p) {
  const items = faqItems(p);
  if (!items.length) return "";
  const blocks = items
    .map((it) => `<h3 class="faq-q">${esc(it.q)}</h3><p class="faq-a">${esc(it.a)}</p>`)
    .join("");
  const a = newestArticle(p);
  const HUB = {
    旅美: { url: "https://clutchgtime.com/taiwan-mlb-players/", title: "台灣旅美球員全整理" },
    旅日: { url: "https://clutchgtime.com/npb-taiwan-players/", title: "台灣旅日球員全整理" },
    旅韓: { url: "https://clutchgtime.com/kbo-to-mlb-stars/", title: "韓職 KBO 焦點" },
  };
  const link = a ? { url: a.url, title: a.title } : HUB[LEAGUE_LABEL[p.league]];
  const more = link
    ? `<p class="faq-more">延伸閱讀:<a href="${esc(link.url)}">The Clutch Time —《${esc(link.title)}》</a></p>`
    : "";
  return `<section class="faq"><h2>常見問題</h2>${blocks}${more}</section>`;
}

function morePlayersHtml(p) {
  const rel = relatedPlayers(p, data.players, 6);
  if (!rel.length) return "";
  const li = rel
    .map(
      (x) =>
        `<a href="${BASE}player/${x.slug}/">${esc(x.name)}<span>${esc(LEVEL_LABEL[x.level] || x.level)}・${esc(x.org)}</span></a>`
    )
    .join("");
  return `<section class="morep"><h2>其他旅外球員</h2><nav class="morep-list">${li}</nav></section>`;
}

function faqJsonLd(p) {
  const items = faqItems(p);
  if (!items.length) return "";
  const schema = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: items.map((it) => ({
      "@type": "Question",
      name: it.q,
      acceptedAnswer: { "@type": "Answer", text: it.a },
    })),
  };
  return ldScript(schema);
}

function jsonLd(p) {
  const b = p.bio || {};
  const url = `${SITE}player/${p.slug}/`;
  const person = {
    "@context": "https://schema.org",
    "@type": "Person",
    name: p.name,
    alternateName: romanName(p),
    url,
    nationality: { "@type": "Country", name: "Taiwan" },
    jobTitle: `職業棒球${roleZh(p)}`,
    affiliation: { "@type": "SportsTeam", name: p.org, sport: "Baseball" },
  };
  if (b.ht) person.height = { "@type": "QuantitativeValue", value: b.ht, unitCode: "CMT" };
  if (b.wt) person.weight = { "@type": "QuantitativeValue", value: b.wt, unitCode: "KGM" };
  // 評比條目(人工核實過才會進 accolades.json)當作 award
  const awards = ((p.accolades || {}).list || []).map((a) => `${a.y} ${a.t}`).filter(Boolean);
  if (awards.length) person.award = awards;
  // 官方球員頁,幫搜尋引擎把這個人跟既有實體對上。
  // 只放能穩定組出網址的:旅美用 MLB 球員 id、旅韓用 KBO playerId;
  // 旅日的 npb.jp 需要另一組 id(名冊裡多半是空的)→ 不放,寧缺勿錯。
  const sameAs = [];
  if (typeof p.id === "number" || /^\d+$/.test(String(p.id))) {
    sameAs.push(`https://www.mlb.com/player/${p.id}`);
  } else if (String(p.id).startsWith("kbo")) {
    const kid = String(p.id).slice(3);
    const kind = p.role === "pitcher" ? "Pitcher" : "Hitter";
    sameAs.push(`https://www.koreabaseball.com/Record/Player/${kind}Detail/Basic.aspx?playerId=${kid}`);
  }
  if (sameAs.length) person.sameAs = sameAs;
  const breadcrumb = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "首頁", item: SITE },
      { "@type": "ListItem", position: 2, name: p.name, item: url },
    ],
  };
  return (
    ldScript(person) +
    ldScript(breadcrumb)
  );
}

// ---- 最新表現(亮點)helpers(與 App.jsx 同邏輯,須同步)----
const LEVEL_CLASS = { MLB: "MLB", AAA: "AAA", AA: "AA", "High-A": "HighA", A: "A", Rookie: "Rookie", 一軍: "ichigun", 二軍: "nigun" };
const levelClassMjs = (lv) => LEVEL_CLASS[lv] || "other";
const HUB_FALLBACK = {
  旅美: { url: "https://clutchgtime.com/taiwan-mlb-players/", title: "台灣旅美球員全整理" },
  旅日: { url: "https://clutchgtime.com/npb-taiwan-players/", title: "台灣旅日球員全整理" },
  旅韓: { url: "https://clutchgtime.com/kbo-to-mlb-stars/", title: "韓職 KBO 焦點" },
};
function pitchLineTxt(g) {
  const parts = [`${g.ip}局`, `${g.h}安`, `失${g.r}分`, `${g.so}K`];
  if (g.bb > 0) parts.push(`${g.bb}BB`);
  if (g.hr > 0) parts.push(`被${g.hr}轟`);
  return parts.join("　");
}
function hitLineTxt(g) {
  const parts = [`${g.ab}打數${g.h}安`];
  if (g.hr > 0) parts.push(`${g.hr}轟`);
  if (g.rbi > 0) parts.push(`${g.rbi}打點`);
  if (g.r > 0) parts.push(`得${g.r}分`);
  if (g.bb > 0) parts.push(`${g.bb}保送`);
  if (g.sb > 0) parts.push(`${g.sb}盜`);
  return parts.join("　");
}
const perfLineTxt = (g) => (g.type === "pitching" ? pitchLineTxt(g) : hitLineTxt(g));
function isHot(g) {
  if (!g) return false;
  if (g.type === "pitching") {
    if (g.win || g.save) return true;
    if (g.started && parseFloat(g.ip) >= 6 && (g.er ?? g.r) <= 2) return true;
    return g.so >= 7;
  }
  return g.hr > 0 || g.h >= 2 || g.rbi >= 2;
}
function badgeText(g) {
  if (g.type === "pitching") {
    if (g.win) return "勝投";
    if (g.save) return "救援";
    if (g.loss) return "敗投";
    return g.started ? "先發" : "後援";
  }
  return g.hr > 0 ? "開轟" : "出賽";
}
const WD = "日一二三四五六";
const fmtDateZh = (iso) => { const [, m, d] = iso.split("-"); return `${Number(m)}月${Number(d)}日`; };
const weekdayZh = (iso) => "週" + WD[new Date(iso + "T00:00:00").getDay()];
const ytSearchUrl = (p, g) =>
  `https://www.youtube.com/results?search_query=${encodeURIComponent(`${p.name} ${g.date.slice(0, 4)} 精華`)}`;

function perfBody(p, g) {
  const arts = (p.content && p.content.articles) || [];
  const oppLevel = (g.level ? `[${LEVEL_LABEL[g.level] || g.level}] ` : "") + (g.opponent || "");
  const hub = HUB_FALLBACK[LEAGUE_LABEL[p.league]];
  const video =
    g.video && g.video.id
      ? `<div class="perf-video-frame"><iframe src="https://www.youtube-nocookie.com/embed/${esc(g.video.id)}" title="${esc(p.name)} 精華" loading="lazy" allowfullscreen></iframe></div>${g.video.title ? `<p class="perf-video-cap">${esc(g.video.title)}</p>` : ""}`
      : `<a class="perf-video-search" href="${esc(ytSearchUrl(p, g))}" target="_blank" rel="noopener">▶ 在 YouTube 搜尋「${esc(p.name)} 精華」</a>`;
  const newsList = arts.length
    ? `<ul class="related-list">${arts.map((a) => `<li><a href="${esc(a.url)}">${esc(a.title)}</a>${a.date ? ` <span class="related-date">${a.date.slice(5).replace("-", "/")}</span>` : ""}</li>`).join("")}</ul>`
    : `<p class="perf-muted">暫無站內收錄的相關報導。</p>`;
  const hubLink = hub ? `<p class="faq-more">延伸閱讀:<a href="${esc(hub.url)}">The Clutch Time —《${esc(hub.title)}》</a></p>` : "";
  const others = (p.game_logs || []).filter((x) => x !== g && isHot(x) && hasPerfPage(p.slug, x.date)).slice(0, 6);
  const othersHtml = others.length
    ? `<section class="perf-sec"><h2 class="perf-sec-t">${esc(p.name)} 其他亮點</h2><nav class="perf-more-grid">${others.map((x) => `<a class="perf-mini" href="${BASE}performance/${p.slug}/${x.date}/"><span class="perf-mini-d">${esc(fmtDateZh(x.date))} ${esc(badgeText(x))}</span><span class="perf-mini-l">${esc(perfLineTxt(x))}</span></a>`).join("")}</nav></section>`
    : "";
  return (
    `<article class="pd">` +
    `<nav class="crumb" aria-label="breadcrumb"><a href="${BASE}">首頁</a><span class="crumb-sep">›</span><a href="${BASE}player/${p.slug}/">${esc(p.name)}</a><span class="crumb-sep">›</span><span class="crumb-cur">${esc(fmtDateZh(g.date))}表現</span></nav>` +
    `<div class="perf-hero level-${levelClassMjs(p.level)}"><div class="perf-hero-top"><span class="badge">${esc(badgeText(g))}</span><span class="perf-date">${esc(fmtDateZh(g.date))}（${esc(weekdayZh(g.date))}）</span></div>` +
    `<h1 class="perf-h1"><a class="perf-h1-link plink" href="${BASE}player/${p.slug}/">${esc(p.name)}</a><span class="perf-h1-sub"> ${esc(fmtDateZh(g.date))} ${esc(badgeText(g))}</span></h1>` +
    `<p class="perf-opp">對戰 ${esc(oppLevel)}</p><p class="perf-stat">${esc(perfLineTxt(g))}</p></div>` +
    `<section class="perf-sec"><h2 class="perf-sec-t">🎬 比賽影片</h2><div class="perf-video">${video}</div></section>` +
    `<section class="perf-sec"><h2 class="perf-sec-t">📰 消息來源</h2>${newsList}${hubLink}</section>` +
    `<section class="perf-sec"><h2 class="perf-sec-t">關於 ${esc(p.name)}</h2>${seasonSummary(p) ? `<p class="perf-about">${esc(seasonSummary(p))}</p>` : ""}<a class="perf-btn" href="${BASE}player/${p.slug}/">看 ${esc(p.name)} 完整數據與近況 →</a></section>` +
    othersHtml +
    `<p class="perf-back"><a class="perf-btn ghost" href="${BASE}latest/">← 看更多最新表現</a></p>` +
    `</article>`
  );
}
function perfBreadcrumbLd(p, g) {
  const url = `${SITE}performance/${p.slug}/${g.date}/`;
  const schema = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "首頁", item: SITE },
      { "@type": "ListItem", position: 2, name: p.name, item: `${SITE}player/${p.slug}/` },
      { "@type": "ListItem", position: 3, name: `${fmtDateZh(g.date)}表現`, item: url },
    ],
  };
  return ldScript(schema);
}

// 表現頁的主體是「某場比賽裡的某位球員」→ SportsEvent,球員掛 performer、
// 兩隊掛 competitor(對手若還是英文原名就照原樣寫,不硬湊中文)。
// 有精華影片且知道上傳日時再加 VideoObject —— uploadDate 是必要欄位,
// 不知道就不發這段,寧可少一個結構化資料也不要餵錯資訊給搜尋引擎。
function perfEventLd(p, g) {
  const url = `${SITE}performance/${p.slug}/${g.date}/`;
  const teams = [p.org, g.opponent].filter(Boolean)
    .map((n) => ({ "@type": "SportsTeam", name: n, sport: "Baseball" }));
  const event = {
    "@context": "https://schema.org",
    "@type": "SportsEvent",
    "@id": `${url}#event`,
    name: `${p.name} ${fmtDateZh(g.date)}${g.opponent ? ` 對${g.opponent}` : ""}`,
    description: perfLineTxt(g),
    startDate: g.date,
    sport: "Baseball",
    url,
    performer: { "@type": "Person", name: p.name, url: `${SITE}player/${p.slug}/` },
  };
  if (teams.length) event.competitor = teams;
  const out = [event];
  const v = g.video;
  if (v && v.id && v.published) {
    out.push({
      "@context": "https://schema.org",
      "@type": "VideoObject",
      name: v.title || `${p.name} ${fmtDateZh(g.date)} 精華`,
      description: `${p.name} ${fmtDateZh(g.date)}${g.opponent ? `對${g.opponent}` : ""}的表現:${perfLineTxt(g)}`,
      thumbnailUrl: [`https://i.ytimg.com/vi/${v.id}/hqdefault.jpg`],
      uploadDate: v.published,
      embedUrl: `https://www.youtube.com/embed/${v.id}`,
      contentUrl: `https://www.youtube.com/watch?v=${v.id}`,
    });
  }
  return out.map((x) => ldScript(x)).join("");
}

// ---- AdSense 版位 ----
// 設定在 scripts/adsense.json;slot 留空或 enabled=false 就完全不輸出任何程式碼
// (連 <script> 都不會有),所以預設狀態與現在完全相同。
// 刻意用手動單元而非 Auto Ads:Auto Ads 自行決定插入位置(含錨定/插頁),
// 無法保證不動版面。這裡固定版位 + 預留高度避免位移。
// 腳本延遲到捲近版位才載入 —— 球員頁靜態化後只有 12KB,不該為廣告在首屏付 100KB。
let adsConf = { enabled: false, client: "", slot: "" };
try {
  adsConf = JSON.parse(readFileSync(resolve(ROOT, "scripts/adsense.json"), "utf-8"));
} catch {
  /* 沒有設定檔就是不放廣告 */
}
const adsOn = !!(adsConf.enabled && adsConf.client && adsConf.slot);

function adSlotHtml() {
  if (!adsOn) return "";
  return (
    `<div class="adbox"><span class="adbox-label">贊助廣告</span>` +
    `<ins class="adsbygoogle" style="display:block" data-ad-client="${adsConf.client}"` +
    ` data-ad-slot="${adsConf.slot}" data-ad-format="auto" data-full-width-responsive="true"></ins></div>`
  );
}

// 只在頁面真的有版位時輸出;IntersectionObserver 讓腳本延到捲近才載入
function adLoaderScript() {
  if (!adsOn) return "";
  return `<script>(function(){var b=document.querySelector('.adbox');if(!b||!('IntersectionObserver' in window))return;` +
    `var done=false;var io=new IntersectionObserver(function(es){es.forEach(function(e){if(!e.isIntersecting||done)return;done=true;io.disconnect();` +
    `var s=document.createElement('script');s.async=true;s.crossOrigin='anonymous';` +
    `s.src='https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=${adsConf.client}';` +
    `s.onload=function(){(window.adsbygoogle=window.adsbygoogle||[]).push({});};document.head.appendChild(s);});},` +
    `{rootMargin:'300px'});io.observe(b);})();</script>`;
}

// 網站頁尾。放在 renderPage 裡,所以每一個預渲染頁面都有(首頁與 /latest/ 沒走
// siteWrap,若把頁尾綁在 siteWrap 會漏掉那兩頁)。
// 這裡是全站唯一每頁都出現的位置,所以把幾個索引頁放進來傳遞權重 —— 原本靜態頁
// 完全沒有頁尾,爬蟲與不掛 React 的索引頁一個頁尾連結都看不到。
// App.jsx 的 SiteFooter 是等效實作,改這裡要同步。
function footerHtml(updatedAt) {
  const col = (title, links) =>
    `<div class="ft-col"><h3>${title}</h3><ul>` +
    links.map(([href, text, ext]) =>
      `<li><a href="${href}"${ext ? ' target="_blank" rel="noopener"' : ""}>${esc(text)}</a></li>`).join("") +
    `</ul></div>`;
  const stamp = updatedAt ? `資料更新於 ${esc(String(updatedAt).slice(0, 16).replace("T", " "))}・` : "";
  return (
    `<footer class="foot"><div class="wrap">` +
    `<div class="ft-grid">` +
    col("球員", [
      [`${BASE}players/`, "全部球員索引"],
      [`${BASE}alumni/`, "歷代旅外球員"],
      [`${BASE}mlb/`, "台灣大聯盟球員"],
      [`${BASE}npb/`, "台灣旅日球員"],
      [`${BASE}kbo/`, "台灣旅韓球員"],
    ]) +
    col("數據", [
      [BASE, "每日戰報"],
      [`${BASE}news/`, "最新消息"],
      [`${BASE}latest/`, "最新表現"],
      [`${BASE}leaders/`, "生涯紀錄排行榜"],
    ]) +
    col("延伸閱讀", [
      ["https://clutchgtime.com/taiwan-mlb-players/", "台灣旅美球員全整理", 1],
      ["https://clutchgtime.com/npb-taiwan-players/", "台灣旅日球員全整理", 1],
      ["https://clutchgtime.com/kbo-to-mlb-stars/", "韓職 KBO 焦點", 1],
    ]) +
    `</div>` +
    `<p class="ft-note">資料來源:MLB Stats API、npb.jp（日本野球機構）、koreabaseball.com（KBO）` +
    `官方公開資料,每日台灣時間清晨 6:00 自動更新。數據僅供參考,以各聯盟官方紀錄為準。</p>` +
    `<p class="ft-copy">${stamp}© ${season} 旅外球員情報站</p>` +
    `</div></footer>`
  );
}

// 把 head 的 title/description/canonical/OG 換掉,並在 #root 注入內容
function renderPage(html, { title, description, canonical, bodyHtml, headExtra = "", image, noJs = false }) {
  // noJs:這一頁的預渲染內容本來就完整,不需要 React 接手 —— 直接把 bundle 的
  // <script> 拿掉。實測球員頁靜態內容比掛載後還多(2094 vs 1830 字),導覽是真的
  // <a>、連結都有 href,掛載只是把同樣的東西重畫一次。省下 64KB JS + 33KB
  // players.json ≈ 97KB;而 GSC 顯示有曝光的 37 頁裡 36 頁是球員頁,搜尋流量
  // 幾乎全部直接落在這種頁。(main.jsx 的 STATIC_PAGES 仍留著當保險。)
  // 每位球員有自己的分享圖(scripts/make_og.py 產生);其餘頁面沿用全站那張
  const ogImage = image ? `${SITE}${image}` : `${SITE}og.png`;
  let out = html.replace(/<title>[\s\S]*?<\/title>/, `<title>${esc(title)}</title>`);
  out = out.replace(
    /<meta name="description"[^>]*>/,
    `<meta name="description" content="${esc(description)}" />`
  );
  const meta = [
    `<link rel="canonical" href="${canonical}" />`,
    `<meta property="og:type" content="website" />`,
    `<meta property="og:locale" content="zh_TW" />`,
    `<meta property="og:title" content="${esc(title)}" />`,
    `<meta property="og:description" content="${esc(description)}" />`,
    `<meta property="og:url" content="${canonical}" />`,
    `<meta property="og:site_name" content="旅外球員情報站" />`,
    `<meta property="og:image" content="${ogImage}" />`,
    `<meta property="og:image:width" content="1200" />`,
    `<meta property="og:image:height" content="630" />`,
    `<meta name="twitter:card" content="summary_large_image" />`,
    `<meta name="twitter:image" content="${ogImage}" />`,
    headExtra,
  ].join("\n    ");
  out = out.replace("</head>", `    ${meta}\n  </head>`);
  out = out.replace('<div id="root"></div>', `<div id="root">${bodyHtml}${footerHtml(data.updated_at)}</div>`);
  if (noJs) out = out.replace(/<script type="module"[^>]*><\/script>\s*/g, "");
  out = out.replace("</body>", `  ${adLoaderScript()}\n  </body>`);
  return out;
}

// 進階數據一行。只有大聯盟層級有(sabermetrics endpoint 不含小聯盟與日韓職)。
// ERA-/FIP- 是相對聯盟平均的指標,100 是平均、越低越好,所以標註出來免得被誤讀。
function advLine(st, isPitcher) {
  const a = (st || {}).adv;
  if (!a) return "";
  const parts = isPitcher
    ? [a.fip != null ? `FIP ${a.fip}` : "", a.xfip != null ? `xFIP ${a.xfip}` : "",
       a.eraMinus != null ? `ERA- ${a.eraMinus}` : "", a.war != null ? `WAR ${a.war}` : ""]
    : [a.woba != null ? `wOBA ${String(a.woba).replace(/^0/, "")}` : "",
       a.wrcPlus != null ? `wRC+ ${a.wrcPlus}` : "", a.war != null ? `WAR ${a.war}` : ""];
  const body = parts.filter(Boolean).join("・");
  if (!body) return "";
  return `<p class="adv-line"><span class="adv-t">進階數據</span>${esc(body)}` +
    `<span class="adv-note">${isPitcher ? "ERA-／FIP- 以 100 為聯盟平均,越低越好" : "wRC+ 以 100 為聯盟平均"}</span></p>`;
}

// 分項數據表(對左/右、主/客)。只顯示主要層級那組,列出全部層級會太雜。
// 投手的 avg 是「被打擊率」、野手的是自己的打擊率 —— 同欄位在投打意思不同,
// 欄名要跟著換,否則會讀成投手自己打擊率兩成六。
const SPLIT_COLS = [["vl", "對左"], ["vr", "對右"], ["h", "主場"], ["a", "客場"]];

function splitsTable(p) {
  const ml = pickMainLevel(p);
  const sp = ml && (ml.s.splits || null);
  if (!sp) return "";
  const isP = p.role === "pitcher";
  const rows = isP
    ? [["防禦率", "era"], ["被打擊率", "avg"], ["WHIP", "whip"], ["投球局數", "ip"],
       ["奪三振", "so"], ["被全壘打", "hr"]]
    : [["打擊率", "avg"], ["OPS", "ops"], ["打數", "ab"], ["全壘打", "hr"], ["三振", "so"]];
  const cols = SPLIT_COLS.filter(([code]) => sp[code]);
  if (!cols.length) return "";
  const head = `<tr><th>${isP ? "對戰／場地" : "對戰／場地"}</th>` +
    cols.map(([, label]) => `<th>${label}${isP ? (label.startsWith("對") ? "打" : "") : (label.startsWith("對") ? "投" : "")}</th>`).join("") + "</tr>";
  const body = rows.map(([label, key]) => {
    const cells = cols.map(([code]) => sp[code][key]);
    if (cells.every((c) => c === undefined || c === null || c === "")) return "";
    return `<tr><td>${label}</td>` +
      cells.map((c) => `<td>${esc(String(c ?? "—"))}</td>`).join("") + "</tr>";
  }).join("");
  if (!body) return "";
  return `<h2>${season} 分項數據（${esc(LEVEL_LABEL[ml.level] || ml.level)}）</h2>` +
    `<div class="table-scroll"><table class="stat-table split-table"><thead>${head}</thead>` +
    `<tbody>${body}</tbody></table></div>`;
}

// ---- 歷代球員(alumni)----
// 已離開大聯盟體系的前輩,只有季級資料(逐年 + 生涯合計),沒有本季與逐場。
// 沿用 /player/{slug}/ 網址空間 —— 他們就是球員,沒有理由另開一套網址。
function alumniBio(p) {
  const b = p.bio || {};
  const sub = [];
  if (b.pos_zh) sub.push(b.pos_zh);
  if (b.throws && b.bats) sub.push(`${b.throws}投${b.bats}打`);
  if (b.ht && b.wt) sub.push(`${b.ht}cm / ${b.wt}kg`);
  if (b.birth) sub.push(`${b.birth.replaceAll("-", "/")} 生`);
  return sub.join("・");
}

function alumniIntro(p) {
  const b = p.bio || {};
  const m = alumniMain(p);
  const c = m && m.c;
  const isNpb = p.league === "npb";
  // 旅日前輩的 name_en 就是中文名,寫成「郭源治（郭源治）」很蠢
  const en = p.name_en && p.name_en !== p.name ? `（${p.name_en}）` : "";
  let s = `${p.name}${en}是台灣${isNpb ? "旅日" : "旅美"}${roleZh(p)}`;
  const span = alumniSpan(p).trim();
  if (span) s += `，${span}間效力${isNpb ? "日本職棒" : "大聯盟"}`;
  if (b.debut) s += `，${b.debut.replaceAll("-", "/")} 完成大聯盟初登場`;
  s += "。";
  if (c) {
    s += p.role === "pitcher"
      ? `${m.where}生涯出賽 ${c.g} 場、${c.w}勝${c.l}敗、${c.ip} 局、${c.so} 次三振、防禦率 ${c.era}。`
      : `${m.where}生涯出賽 ${c.g} 場、打擊率 ${c.avg}、${c.hr} 轟、${c.rbi} 打點。`;
  }
  // 橫跨多聯盟的球員(陳偉殷美日、王維中美韓)每一段都要交代,
  // 那正是這站能提供而別處沒有的東西。
  for (const [lvKey, label] of [["一軍", "旅日期間在日職一軍"], ["韓職一軍", "旅韓期間在韓職一軍"]]) {
    const other = (p.career || {})[lvKey];
    if (isNpb || !other) continue;
    s += p.role === "pitcher"
      ? `${label}出賽 ${other.g} 場、${other.w}勝${other.l}敗、${other.ip} 局、防禦率 ${other.era}。`
      : `${label}出賽 ${other.g} 場、打擊率 ${other.avg}、${other.hr} 轟。`;
  }
  s += isNpb ? "以下為完整生涯逐年數據。" : "以下為完整生涯逐年數據（含小聯盟各層級）。";
  return s;
}

function alumniLd(p) {
  const url = `${SITE}player/${p.slug}/`;
  const b = p.bio || {};
  const person = {
    "@context": "https://schema.org",
    "@type": "Person",
    name: p.name,
    alternateName: p.name_en,
    url,
    nationality: { "@type": "Country", name: "Taiwan" },
    jobTitle: `職業棒球${roleZh(p)}`,
    sameAs: [p.league === "npb"
      ? `https://npb.jp/bis/players/${String(p.id).replace(/^npba/, "")}.html`
      : `https://www.mlb.com/player/${p.id}`],
  };
  if (b.birth) person.birthDate = b.birth;
  if (b.ht) person.height = { "@type": "QuantitativeValue", value: b.ht, unitCode: "CMT" };
  if (b.wt) person.weight = { "@type": "QuantitativeValue", value: b.wt, unitCode: "KGM" };
  return (
    ldScript(person) +
    ldScript({
      "@context": "https://schema.org",
      "@type": "BreadcrumbList",
      itemListElement: [
        { "@type": "ListItem", position: 1, name: "首頁", item: SITE },
        { "@type": "ListItem", position: 2, name: "歷代球員", item: `${SITE}alumni/` },
        { "@type": "ListItem", position: 3, name: p.name, item: url },
      ],
    })
  );
}

// 標題裡的核心數字:有數字的標題點擊率較好,也更容易命中長尾查詢
function titleStats(p, st) {
  if (!st) return "";
  return p.role === "pitcher"
    ? `${st.g} 場 ${st.w}勝${st.l}敗、防禦率 ${st.era}`
    : `${st.g} 場、打擊率 ${st.avg}、${st.hr} 轟`;
}

function playerTitle(p) {
  const ml = pickMainLevel(p);
  const core = ml ? titleStats(p, ml.s) : "";
  const hasWp = wpArticleNames.has(p.name);
  // 層級放進標題,**但只放旅日二軍**。GSC 近 28 天含層級字眼的查詢共 12 個,
  // 全部是日職一/二軍(「林家正 二軍成績」排名 2.3 CTR 31%、「陽柏翔 二軍成績」
  // 排名 2.0 CTR 22%),**沒有任何一個是 3A/2A/1A** —— 旅美小聯盟的使用者是打
  // 「{名} 成績」,硬加 3A 反而稀釋完全比對。有需求證據才加。
  const lvTag = p.league === "npb" && ml && ml.level === "二軍" ? "二軍" : "";
  const head = hasWp ? `${p.name}逐場紀錄與數據` : `${p.name} ${season} ${lvTag}成績`;
  // 沒有專文的那組標題開頭已經有年份了,中段就別再寫一次「2026 賽季」
  const mid = hasWp ? `${season} 賽季 ${core}` : core;
  return core ? `${head}｜${mid}｜旅外球員情報站` : `${head}｜旅外球員情報站`;
}

const allPerf = [];
for (const p of data.players) {
  if (!p.slug) continue;
  for (const g of p.game_logs || []) allPerf.push({ p, g });
}
allPerf.sort((a, b) => (a.g.date !== b.g.date ? (a.g.date < b.g.date ? 1 : -1) : levelRankP(a.p) - levelRankP(b.p)));
const latestGameDate = allPerf.length ? allPerf[0].g.date : null;
const windowMs = 30 * 86400000;
const inWindow = (d) =>
  latestGameDate ? new Date(d + "T00:00:00").getTime() >= new Date(latestGameDate + "T00:00:00").getTime() - windowMs : false;


// 哪些場次真的會有表現頁 —— 只有視窗內的會產生。先算好,讓球員頁的「最新動態」
// 與表現頁的「其他亮點」都只連到真的存在的頁,不要製造 404。
// (稽核發現 66 個斷掉的站內連結,全是連到視窗外的表現頁,其中一個被連了 25 次。)
const perfPageKeys = new Set(
  allPerf.filter(({ g }) => inWindow(g.date)).map(({ p, g }) => `${p.slug}/${g.date}`)
);
const hasPerfPage = (slug, date) => perfPageKeys.has(`${slug}/${date}`);

// ---- 每位球員頁 ----
let count = 0;
for (const p of data.players) {
  const title = playerTitle(p);
  const description = introText(p).slice(0, 150);
  const canonical = `${SITE}player/${p.slug}/`;
  const timeline = buildTimeline(p);
  const timelineUrls = new Set(timeline.filter((it) => it.kind === "article").map((it) => it.article.url));
  const bodyHtml =
    `<article class="pd">` +
    `<nav class="crumb" aria-label="breadcrumb"><a href="${BASE}">首頁</a><span class="crumb-sep">›</span><span class="crumb-cur">${esc(p.name)}</span></nav>` +
    `<h1>${esc(p.name)} <span class="pd-en">${esc(romanName(p))}</span></h1>` +
    `<p class="pd-bio">${esc(bioLine(p))}</p>` +
    (p.heritage ? `<p class="pd-heritage">🇹🇼 台裔球員 · 具台灣血統</p>` : "") +
    `<p class="pd-intro">${esc(introText(p))}</p>` +
    (seasonSummary(p)
      ? `<p class="pd-summary"><b>戰績摘要</b>：${esc(seasonSummary(p))}` +
        (latestGameLine(p) ? `<span class="pd-latest">${esc(latestGameLine(p))}</span>` : "") +
        `</p>`
      : "") +
    `<h2>${season} 球季累積數據</h2>${seasonTable(p)}` +
    advLine((p.season_stats || {}).MLB, p.role === "pitcher") +
    splitsTable(p) +
    careerYearTable(p) +
    recentGames(p) +
    timelineHtml(p, timeline) +
    recapHtml(p) +
    relatedHtml(p, timelineUrls) +
    faqHtml(p) +
    adSlotHtml() +
    morePlayersHtml(p) +
    `</article>`;
  const html = renderPage(template, {
    title, description, canonical, bodyHtml: siteWrap(bodyHtml), headExtra: jsonLd(p) + faqJsonLd(p),
    image: `og/${p.slug}.png`,
    noJs: true,   // 球員頁靜態內容已完整
  });
  const dir = resolve(DIST, "player", p.slug);
  mkdirSync(dir, { recursive: true });
  writeFileSync(resolve(dir, "index.html"), html);
  count++;
}

// ---- 表現頁 /performance/{slug}/{date}/ 與 最新表現總覽 /latest/ ----
// 蒐集所有場次,取「最新場次日期往前 30 天」為視窗(控制頁數、保持新鮮)
const perfSitemapUrls = [];
let perfCount = 0;
let perfNoindex = 0;
for (const { p, g } of allPerf) {
  if (!inWindow(g.date)) continue;
  const hot = isHot(g);
  const bt = badgeText(g);
  const canonical = `${SITE}performance/${p.slug}/${g.date}/`;
  const title = `${p.name} ${fmtDateZh(g.date)} ${bt}｜${perfLineTxt(g)}｜旅外球員情報站`;
  const description = `${p.name}（${romanName(p)}）${season} 球季 ${fmtDateZh(g.date)} 對 ${g.opponent || "對手"} 的表現:${perfLineTxt(g)}。含數據、消息來源與精華影片。`.slice(0, 155);
  // 亮點頁 → 收錄 + 進 sitemap;普通(非亮點)頁 → noindex、不進 sitemap(避免薄頁灌水)
  const headExtra = perfBreadcrumbLd(p, g) + perfEventLd(p, g) + (hot ? "" : `\n    <meta name="robots" content="noindex,follow" />`);
  const html = renderPage(template, { title, description, canonical, bodyHtml: siteWrap(perfBody(p, g)), headExtra });
  const dir = resolve(DIST, "performance", p.slug, g.date);
  mkdirSync(dir, { recursive: true });
  writeFileSync(resolve(dir, "index.html"), html);
  perfCount++;
  if (hot) perfSitemapUrls.push([canonical, g.date]);   // 過去的比賽不會再變
  else perfNoindex++;
}

// 最新表現總覽(亮點,近 21 天,依日期分組)
const hlWindowMs = 21 * 86400000;
const highlights = allPerf.filter(
  ({ g }) => isHot(g) && (latestGameDate ? new Date(g.date + "T00:00:00").getTime() >= new Date(latestGameDate + "T00:00:00").getTime() - hlWindowMs : false)
);
const hlGroups = [];
{
  let cur = null;
  for (const it of highlights) {
    if (!cur || cur.date !== it.g.date) { cur = { date: it.g.date, list: [] }; hlGroups.push(cur); }
    cur.list.push(it);
  }
}
const latestBody =
  `<article class="pd"><nav class="crumb" aria-label="breadcrumb"><a href="${BASE}">首頁</a><span class="crumb-sep">›</span><span class="crumb-cur">最新表現</span></nav>` +
  `<h1>最新表現・旅外台將亮點</h1>` +
  `<p class="latest-lead">近三週旅美、旅日、旅韓台灣旅外球員的亮點表現(開轟・勝投・救援・優質先發・多安打),點進看數據、消息來源與精華影片。</p>` +
  hlGroups
    .map(
      (grp) =>
        `<section class="latest-day"><h2 class="latest-date">${esc(fmtDateZh(grp.date))}<span class="latest-wd">${esc(weekdayZh(grp.date))}</span></h2><div class="latest-grid">` +
        grp.list
          .map(
            ({ p, g }) =>
              `<div class="perf-card level-${levelClassMjs(p.level)}"><div class="perf-card-top"><a class="perf-card-name plink" href="${BASE}player/${p.slug}/">${esc(p.name)}</a><span class="badge">${esc(badgeText(g))}</span></div><a class="perf-card-body" href="${BASE}performance/${p.slug}/${g.date}/"><span class="perf-card-meta">${esc((g.level ? `${LEVEL_LABEL[g.level] || g.level}・` : "") + LEAGUE_LABEL[p.league])}</span><span class="perf-card-line">${esc(perfLineTxt(g))}</span></a></div>`
          )
          .join("") +
        `</div></section>`
    )
    .join("") +
  `</article>`;
const latestLd = {
  "@context": "https://schema.org",
  "@type": "ItemList",
  name: `旅外台將最新亮點表現（${season}）`,
  numberOfItems: highlights.length,
  itemListElement: highlights.slice(0, 50).map((it, i) => ({
    "@type": "ListItem",
    position: i + 1,
    url: `${SITE}performance/${it.p.slug}/${it.g.date}/`,
    name: `${it.p.name} ${fmtDateZh(it.g.date)} ${badgeText(it.g)}`,
  })),
};
const latestHtml = renderPage(template, {
  title: "最新表現｜旅外台將亮點 開轟・勝投・救援・好投｜旅外球員情報站",
  description: `近三週旅美、旅日、旅韓台灣旅外球員的亮點表現彙整,含逐場數據、消息來源與精華影片。共 ${highlights.length} 場亮點。`,
  canonical: `${SITE}latest/`,
  bodyHtml: latestBody,
  headExtra:
    ldScript(latestLd) +
    ldScript({
      "@context": "https://schema.org",
      "@type": "BreadcrumbList",
      itemListElement: [
        { "@type": "ListItem", position: 1, name: "首頁", item: SITE },
        { "@type": "ListItem", position: 2, name: "最新表現", item: `${SITE}latest/` },
      ],
    }),
});
mkdirSync(resolve(DIST, "latest"), { recursive: true });
writeFileSync(resolve(DIST, "latest", "index.html"), latestHtml);
console.log(`表現頁:${perfCount} 頁(亮點收錄 ${perfSitemapUrls.length}、noindex ${perfNoindex})+ 最新表現總覽(${highlights.length} 場)`);

// ---- 首頁:填 #root 讓爬蟲有內容,並列出所有球員連結供發現 ----
const byLeague = { mlb: [], npb: [], kbo: [] };
for (const p of data.players) {
  const key = p.league === "milb" ? "mlb" : p.league;
  (byLeague[key] || byLeague.mlb).push(p);
}
const leagueBlock = (key, label) =>
  byLeague[key].length
    ? `<section><h2>${label}</h2><ul>${byLeague[key]
        .map((p) => `<li><a href="${BASE}player/${p.slug}/">${esc(p.name)}</a>（${esc(LEVEL_LABEL[p.level] || p.level)}・${esc(p.org)}）</li>`)
        .join("")}</ul></section>`
    : "";
const homeHighlights = highlights.slice(0, 10);
const homeHlBlock = homeHighlights.length
  ? `<section><h2><a href="${BASE}latest/">最新亮點</a></h2><ul>${homeHighlights
      .map(({ p, g }) => `<li><a href="${BASE}performance/${p.slug}/${g.date}/">${esc(p.name)} ${esc(fmtDateZh(g.date))} ${esc(badgeText(g))}</a>（${esc(perfLineTxt(g))}）</li>`)
      .join("")}</ul></section>`
  : "";
// 歷代球員區塊:先前首頁只有 39 個現役球員連結、0 個歷代 —— 35 個新頁除了
// 導覽列以外拿不到首頁的權重傳遞,也讓「歷代旅外球員」這個查詢沒有入口。
const alumniHomeBlock = alumni.length
  ? `<section><h2><a href="${BASE}alumni/">歷代旅外球員</a></h2>` +
    `<p>從 ${Math.min(...alumni.map((x) => x.first_year || 9999))} 年至今、已退役或離開美日韓職棒的 ${alumni.length} 位台灣前輩,完整生涯逐年數據。</p>` +
    `<ul>${[...alumni]
      .sort((a, b) => (a.first_year || 0) - (b.first_year || 0))
      .map((p) => `<li><a href="${BASE}player/${p.slug}/">${esc(p.name)}</a>（${p.league === "npb" ? "旅日" : "旅美"} ${p.first_year}–${p.last_year}）</li>`)
      .join("")}</ul></section>`
  : "";
const activeMlb = data.players.filter((x) => (x.season_stats || {}).MLB).length;
const homeBody =
  `<div class="prerender-home">` +
  `<h1>台灣旅外球員數據｜旅美・旅日・旅韓即時戰報</h1>` +
  `<p>每日追蹤旅美、旅日、旅韓共 ${data.players.length} 位現役台灣旅外棒球員的出賽表現與 ${season} 球季數據,` +
  `另收錄 ${alumni.length} 位歷代前輩的完整生涯逐年成績,最早回溯至 ${alumni.length ? Math.min(...alumni.map((x) => x.first_year || 9999)) : season} 年。</p>` +
  homeHlBlock +
  `<section><h2>各聯盟球員一覽</h2><ul>` +
  `<li><a href="${BASE}mlb/">台灣大聯盟球員一覽（歷代＋現役）</a></li>` +
  `<li><a href="${BASE}npb/">台灣旅日球員一覽（歷代＋現役）</a></li>` +
  `<li><a href="${BASE}kbo/">台灣旅韓球員一覽</a></li>` +
  `<li><a href="${BASE}leaders/">台灣旅外生涯紀錄排行榜</a></li>` +
  `<li><a href="${BASE}players/">全部球員索引（可搜尋）</a></li>` +
  `</ul></section>` +
  leagueBlock("mlb", "旅美（MLB / 小聯盟）") +
  leagueBlock("npb", "旅日（NPB）") +
  leagueBlock("kbo", "旅韓（KBO）") +
  alumniHomeBlock +
  `</div>`;
// 首頁是全站權重最高的頁,原本 title 只有 19 字、H1 是品牌名,等於沒有經營
// 任何查詢。改成主打「台灣旅外球員數據」,並用人數與年份當信任訊號。
const homeDesc = `台灣旅外棒球員完整數據庫:每日追蹤旅美、旅日、旅韓 ${data.players.length} 位現役球員的逐場表現與 ${season} 球季成績,` +
  `另收錄王建民、陳偉殷、郭源治等 ${alumni.length} 位歷代前輩的生涯逐年數據。`;
// 首頁結構化資料:網站實體 + 發行組織(關聯 logo) + 球員名冊 ItemList
// WebSite 與 Organization 用 @id 互指,搜尋引擎才知道是同一個發布者而非兩個實體
const homeSchemas = [
  {
    "@context": "https://schema.org",
    "@type": "WebSite",
    "@id": `${SITE}#website`,
    name: "旅外球員情報站",
    alternateName: "台灣旅外棒球員即時數據",
    url: SITE,
    inLanguage: "zh-Hant",
    publisher: { "@id": `${SITE}#org` },
  },
  {
    "@context": "https://schema.org",
    "@type": "Organization",
    "@id": `${SITE}#org`,
    name: "旅外球員情報站",
    url: SITE,
    logo: `${SITE}apple-touch-icon.png`,
  },
  {
    "@context": "https://schema.org",
    "@type": "ItemList",
    name: `台灣旅外棒球員名冊（${season}）`,
    numberOfItems: data.players.length,
    itemListElement: data.players.map((p, i) => ({
      "@type": "ListItem",
      position: i + 1,
      url: `${SITE}player/${p.slug}/`,
      name: p.name,
    })),
  },
];
const homeJsonLd = homeSchemas
  .map((s) => ldScript(s))
  .join("\n    ");
const homeHtml = renderPage(template, {
  title: `台灣旅外球員數據｜${data.players.length} 位現役、${alumni.length} 位歷代生涯成績｜旅外球員情報站`,
  description: homeDesc,
  canonical: SITE,
  bodyHtml: homeBody,
  headExtra: homeJsonLd,
});
writeFileSync(resolve(DIST, "index.html"), homeHtml);

// ---- 自訂 404(GitHub Pages 對未匹配路徑會服務此檔;自帶樣式、不依賴 SPA)----
const quick = data.players
  .filter((p) => p.slug)
  .sort((a, b) => levelRankP(a) - levelRankP(b))
  .slice(0, 6);
const quickLinks = quick
  .map((p) => `<a href="${BASE}player/${p.slug}/">${esc(p.name)}</a>`)
  .join("");
const notFound = `<!doctype html>
<html lang="zh-Hant-TW">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>找不到頁面｜旅外球員情報站</title>
<meta name="robots" content="noindex" />
<link rel="icon" type="image/svg+xml" href="${BASE}logo.svg" />
<style>
:root{--ink:#182420;--ink3:#8b968f;--paper:#f6f8f6;--card:#fff;--line:#e3e8e4;--green:#0f5138}
@media(prefers-color-scheme:dark){:root{--ink:#e7ece9;--ink3:#71807a;--paper:#121513;--card:#1b201d;--line:#2b322d;--green:#52c194}}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
background:var(--paper);color:var(--ink);
font-family:system-ui,-apple-system,"PingFang TC","Microsoft JhengHei","Noto Sans TC",sans-serif;
line-height:1.6;padding:24px;text-align:center}
.box{max-width:440px}
img{width:60px;height:auto;margin-bottom:8px}
.code{font-size:56px;font-weight:800;color:var(--green);margin:0;letter-spacing:.04em}
h1{font-size:22px;margin:4px 0 8px}
p{color:var(--ink3);margin:0 0 20px;font-size:14.5px}
.btn{display:inline-block;background:var(--green);color:#fff;text-decoration:none;
padding:11px 22px;border-radius:10px;font-size:15px;font-weight:500}
.q{margin-top:24px}
.q-t{font-size:12px;color:var(--ink3);margin-bottom:8px}
.q-list{display:flex;flex-wrap:wrap;gap:8px;justify-content:center}
.q-list a{border:1px solid var(--line);border-radius:999px;padding:5px 13px;
text-decoration:none;color:var(--ink);font-size:13px;background:var(--card)}
</style>
</head>
<body>
<main class="box">
<img src="${BASE}logo.svg" alt="旅外球員情報站" />
<p class="code">404</p>
<h1>找不到這個頁面</h1>
<p>這個網址可能不存在,或球員頁尚未建立。</p>
<a class="btn" href="${BASE}">← 回首頁</a>
<div class="q">
<div class="q-t">熱門球員</div>
<div class="q-list">${quickLinks}</div>
</div>
</main>
</body>
</html>
`;
writeFileSync(resolve(DIST, "404.html"), notFound);

// 歷代球員的答案優先摘要與問答。全部由生涯/逐年資料算出,不做主觀評價
// (所以問的是「單季最多勝的一年」這種事實,而不是「最好的一季」)。
// 主舞台:旅美看大聯盟、旅日看一軍。回傳 {c, 場域名稱, 該層級 key}
function alumniMain(p) {
  const car = p.career || {};
  if (car.MLB) return { c: car.MLB, where: "大聯盟", level: "MLB" };
  if (car["一軍"]) return { c: car["一軍"], where: "日職一軍", level: "一軍" };
  return null;
}

function alumniSpan(p) {
  const y = p.mlb_seasons || p.npb_seasons || [];
  if (y.length) return ` ${y[0]}–${y[y.length - 1]} 年`;
  return p.first_year ? ` ${p.first_year}–${p.last_year} 年` : "";
}

function alumniSummary(p) {
  const m = alumniMain(p);
  if (!m) return "";
  const { c, where } = m;
  return p.role === "pitcher"
    ? `${p.name}${alumniSpan(p)}在${where}出賽 ${c.g} 場、${c.w}勝${c.l}敗、${c.ip} 局、${c.so} 次三振、防禦率 ${c.era}、WHIP ${c.whip}。`
    : `${p.name}${alumniSpan(p)}在${where}出賽 ${c.g} 場、打擊率 ${c.avg}、${c.hr} 轟、${c.rbi} 打點、OPS ${c.ops}。`;
}

// 代表作那一季。指標:投手看勝場、野手看全壘打;但生涯 0 勝或 0 轟的人
// (陳金鋒大聯盟 0 轟、倪福德 0 勝)問「單季最多全壘打」會得到「0 轟」,
// 讀起來像壞掉 → 這種情況改問出賽數最多的一季,一樣是事實陳述。
function alumniBestSeason(p) {
  const isP = p.role === "pitcher";
  const lv = (alumniMain(p) || {}).level || "MLB";
  const pick = (metric) => {
    let best = null;
    for (const [yr, byLevel] of Object.entries(p.prev_season || {})) {
      const s = byLevel[lv];
      if (!s) continue;
      const key = metric(s);
      const tie = isP ? -parseFloat(s.era || "99") : parseFloat(s.avg || "0");
      if (!best || key > best.key || (key === best.key && tie > best.tie)) best = { yr, s, key, tie };
    }
    return best;
  };
  const main = pick(isP ? ((s) => s.w) : ((s) => s.hr));
  if (main && main.key > 0) return { ...main, by: isP ? "win" : "hr" };
  const byGames = pick((s) => s.g);
  return byGames ? { ...byGames, by: "g" } : null;
}

function alumniTeams(p) {
  const out = [];
  const lv = (alumniMain(p) || {}).level || "MLB";
  for (const byLevel of Object.values(p.prev_season || {})) {
    const t = (byLevel[lv] || {}).team;
    if (t) t.split("、").forEach((x) => out.push(x));
  }
  return [...new Set(out)];
}

// 生涯亮點。**全部由資料算出,不編造** —— 受傷、轉隊原因、名場面那種需要外部
// 來源的敘事一律不寫。這裡只講數字本身就能證明的事:里程碑、連續球季、生涯跨度、
// 跨聯盟。目的是讓純數字的歷代球員頁讀起來像有內容,而不是一張表。
// App.jsx 的 careerHighlights 是等效實作,兩份要同步。
function careerHighlights(p) {
  const m = alumniMain(p);
  if (!m) return [];
  const c = m.c;
  const isP = p.role === "pitcher";
  const lv = m.level;
  const out = [];

  // 生涯跨度與效力球隊(球隊數由逐年表的 team 欄去重)
  const yearsAtLevel = Object.keys(p.prev_season || {})
    .filter((y) => (p.prev_season[y] || {})[lv]).sort();
  const teams = [...new Set(Object.values(p.prev_season || {})
    .flatMap((by) => ((by[lv] || {}).team || "").split("、")).filter(Boolean))];
  if (yearsAtLevel.length) {
    let t = `${m.where}生涯橫跨 ${yearsAtLevel.length} 個球季（${yearsAtLevel[0]}–${yearsAtLevel[yearsAtLevel.length - 1]}）`;
    if (teams.length > 1) t += `,效力過 ${teams.length} 支球隊：${teams.join("、")}`;
    else if (teams.length === 1) t += `,生涯僅效力${teams[0]}`;
    out.push(t + "。");
  }

  // 整數里程碑:只列真的達到的
  const marks = isP
    ? [["w", 100, "勝"], ["so", 1000, "次三振"], ["sv", 100, "次救援成功"], ["hld", 100, "次中繼成功"]]
    : [["hr", 100, "支全壘打"], ["h", 1000, "支安打"], ["rbi", 500, "分打點"]];
  const hit = marks.filter(([k, n]) => (c[k] || 0) >= n)
    .map(([k, n, unit]) => `${n} ${unit}（生涯 ${c[k]}）`);
  if (hit.length) out.push(`達成${m.where}生涯 ${hit.join("、")}。`);

  // 連續兩季同樣的成績:數字自己會說話(王建民 2006、2007 連兩季 19 勝)
  const key = isP ? "w" : "hr";
  const floor = isP ? 10 : 15;
  for (let i = 0; i < yearsAtLevel.length - 1; i++) {
    const a = yearsAtLevel[i], b = yearsAtLevel[i + 1];
    if (Number(b) - Number(a) !== 1) continue;
    const va = (p.prev_season[a][lv] || {})[key], vb = (p.prev_season[b][lv] || {})[key];
    if (va != null && va === vb && va >= floor) {
      out.push(`${a}、${b} 連兩季${isP ? `拿下 ${va} 勝` : `擊出 ${va} 支全壘打`}。`);
      break;
    }
  }

  // 跨聯盟(陳偉殷美日、王維中美韓)
  const others = [["一軍", "日職一軍"], ["韓職一軍", "韓職一軍"]]
    .filter(([k]) => k !== lv && (p.career || {})[k]);
  if (others.length) {
    out.push(`除了${m.where}之外,也有${others.map(([, l]) => l).join("、")}的出賽紀錄,` +
      `是少數橫跨多國職棒的台灣球員。`);
  }
  return out.slice(0, 4);
}

function highlightsHtml(p) {
  const items = careerHighlights(p);
  if (!items.length) return "";
  return `<section class="hl"><h2>生涯亮點</h2><ul class="hl-list">` +
    items.map((t) => `<li>${esc(t)}</li>`).join("") + `</ul>` +
    `<p class="hl-note">以上皆由官方逐年紀錄計算,不含未經查證的敘述。</p></section>`;
}

function alumniFaqItems(p) {
  const items = [];
  const where = (alumniMain(p) || {}).where || "大聯盟";
  const sum = alumniSummary(p);
  if (sum) items.push({ q: `${p.name} ${where} 生涯成績如何?`, a: sum });
  const teams = alumniTeams(p);
  if (teams.length) {
    items.push({ q: `${p.name} 在${where}效力過哪些球隊?`, a: `${p.name} ${where}時期效力過 ${teams.join("、")}。` });
  }
  const b = p.bio || {};
  if (b.debut) {
    items.push({ q: `${p.name} 何時完成大聯盟初登場?`, a: `${p.name} 於 ${b.debut.replaceAll("-", "/")} 完成大聯盟初登場。` });
  } else if (p.first_year) {
    items.push({ q: `${p.name} 哪一年開始在日本職棒出賽?`, a: `${p.name} 自 ${p.first_year} 年起在日本職棒出賽,最後一個球季為 ${p.last_year} 年。` });
  }
  const best = alumniBestSeason(p);
  if (best) {
    const s = best.s;
    const q = best.by === "win" ? `${p.name} ${where}單季最多勝是哪一年?`
      : best.by === "hr" ? `${p.name} ${where}單季最多全壘打是哪一年?`
      : `${p.name} 在${where}出賽最多的一季是哪一年?`;
    items.push({
      q,
      a: p.role === "pitcher"
        ? `${best.yr} 年,該季出賽 ${s.g} 場、${s.w}勝${s.l}敗、${s.ip} 局、防禦率 ${s.era}。`
        : `${best.yr} 年,該季出賽 ${s.g} 場、打擊率 ${s.avg}、${s.hr} 轟、${s.rbi} 打點。`,
    });
  }
  return items;
}

function alumniFaqHtml(p) {
  const items = alumniFaqItems(p);
  if (!items.length) return "";
  const blocks = items.map((it) => `<h3 class="faq-q">${esc(it.q)}</h3><p class="faq-a">${esc(it.a)}</p>`).join("");
  // 這些前輩在 clutchgtime 沒有專屬文章(查過,搜到的都是別人的文章提到他們),
  // 所以連該聯盟的總表 pillar。**要看球員的聯盟** —— 郭源治是旅日,連到
  // 「台灣旅美球員全整理」是錯的。
  const hub = HUB_FALLBACK[p.league === "npb" ? "旅日" : "旅美"];
  const more = hub
    ? `<p class="faq-more">延伸閱讀:<a href="${esc(hub.url)}">The Clutch Time —《${esc(hub.title)}》</a></p>`
    : "";
  return `<section class="faq"><h2>常見問題</h2>${blocks}${more}</section>`;
}

function alumniFaqLd(p) {
  const items = alumniFaqItems(p);
  if (!items.length) return "";
  return ldScript({
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: items.map((it) => ({
      "@type": "Question", name: it.q,
      acceptedAnswer: { "@type": "Answer", text: it.a },
    })),
  });
}

// ---- 歷代球員頁 + /alumni/ 索引 ----
const alumniUrls = [];
for (const p of alumni) {
  const canonical = `${SITE}player/${p.slug}/`;
  const span = alumniSpan(p).trim().replace(" 年", "");
  const where = p.league === "npb" ? "日職" : "大聯盟";
  const bodyHtml =
    `<article class="pd">` +
    `<nav class="crumb" aria-label="breadcrumb"><a href="${BASE}">首頁</a><span class="crumb-sep">›</span>` +
    `<a href="${BASE}alumni/">歷代球員</a><span class="crumb-sep">›</span>` +
    `<span class="crumb-cur">${esc(p.name)}</span></nav>` +
    `<h1>${esc(p.name)}${p.name_en && p.name_en !== p.name ? ` <span class="pd-en">${esc(p.name_en)}</span>` : ""}</h1>` +
    `<p class="pd-bio">${esc(alumniBio(p))}</p>` +
    `<p class="pd-heritage">🏅 歷代旅外球員${span ? `・${where} ${span}` : ""}</p>` +
    `<p class="pd-intro">${esc(alumniIntro(p))}</p>` +
    (alumniSummary(p) ? `<p class="pd-summary"><b>生涯戰績</b>：${esc(alumniSummary(p))}</p>` : "") +
    careerYearTable(p) +
    ((p.career || {}).MLB && (p.career || {}).MLB.war != null
      ? `<p class="adv-line"><span class="adv-t">生涯 WAR</span>${(p.career || {}).MLB.war}` +
        `<span class="adv-note">大聯盟生涯勝場貢獻值,由逐年 WAR 相加</span></p>`
      : "") +
    highlightsHtml(p) +
    alumniFaqHtml(p) +
    adSlotHtml() +
    `<section class="morep"><h2>其他歷代旅外球員</h2><nav class="morep-list">` +
    alumni.filter((x) => x.slug !== p.slug).slice(0, 8)
      .map((x) => `<a href="${BASE}player/${x.slug}/">${esc(x.name)}</a>`).join("") +
    `</nav></section>` +
    `</article>`;
  writeFileSync(
    (mkdirSync(resolve(DIST, "player", p.slug), { recursive: true }), resolve(DIST, "player", p.slug, "index.html")),
    renderPage(template, {
      // clutchgtime 沒有任何一位歷代前輩的專文(查過 WP REST),所以這裡沒有
      // 跨站競爭問題,可直接主打搜尋量最大的「{名}生涯成績」。
      title: (() => {
        const m = alumniMain(p);
        const core = m ? titleStats(p, m.c) : "";
        const where = p.league === "npb" ? "日職一軍" : "大聯盟";
        return core
          ? `${p.name}生涯成績｜${where} ${core}｜旅外球員情報站`
          : `${p.name}生涯成績｜旅外球員情報站`;
      })(),
      description: alumniIntro(p).slice(0, 155),
      canonical,
      bodyHtml: siteWrap(bodyHtml),
      headExtra: alumniLd(p) + alumniFaqLd(p),
      image: `og/${p.slug}.png`,
      noJs: true,
    })
  );
  alumniUrls.push([canonical, alumniLastmod]);
}

if (alumni.length) {
  const rows = [...alumni].sort((a, b) => (a.first_year || 0) - (b.first_year || 0));
  const li = rows.map((p) => {
    const m = alumniMain(p);
    const c = m && m.c;
    const line = !c ? "" : (p.role === "pitcher"
      ? `${c.g} 場・${c.w}勝${c.l}敗・防禦率 ${c.era}`
      : `${c.g} 場・打擊率 ${c.avg}・${c.hr} 轟`);
    const tag = p.league === "npb" ? "旅日" : "旅美";
    return `<li><a href="${BASE}player/${p.slug}/">${esc(p.name)}</a>` +
      `<span class="al-tag">${tag}</span>` +
      `<span class="al-yr">${p.first_year ? `${p.first_year}–${p.last_year}` : ""}</span>` +
      `<span class="al-line">${esc(line)}</span></li>`;
  }).join("");
  const body =
    `<article class="pd">` +
    `<nav class="crumb" aria-label="breadcrumb"><a href="${BASE}">首頁</a><span class="crumb-sep">›</span>` +
    `<span class="crumb-cur">歷代球員</span></nav>` +
    `<h1>歷代旅外球員</h1>` +
    `<p class="pd-intro">已退役或離開美日職棒體系的台灣旅外球員共 ${alumni.length} 位,` +
    `最早可回溯到 ${Math.min(...alumni.map((x) => x.first_year || 9999))} 年。依初登場年份排序,` +
    `資料為完整生涯逐年累積(旅美含小聯盟各層級)。</p>` +
    `<ol class="al-list">${li}</ol>` +
    `<p class="faq-more">依聯盟瀏覽:<a href="${BASE}mlb/">台灣大聯盟球員一覽</a>、` +
    `<a href="${BASE}npb/">台灣旅日球員一覽</a>、<a href="${BASE}kbo/">台灣旅韓球員一覽</a>、<a href="${BASE}leaders/">生涯紀錄排行榜</a></p>` +
    `</article>`;
  writeFileSync(
    (mkdirSync(resolve(DIST, "alumni"), { recursive: true }), resolve(DIST, "alumni", "index.html")),
    renderPage(template, {
      title: "歷代旅外球員｜台灣大聯盟球員生涯數據總覽｜旅外球員情報站",
      description: `王建民、陳偉殷、郭源治、郭泰源、陽岱鋼等 ${alumni.length} 位台灣旅外前輩的完整生涯逐年數據總覽,涵蓋美國職棒與日本職棒。`,
      canonical: `${SITE}alumni/`,
      bodyHtml: siteWrap(body),
      headExtra:
        ldScript({
          "@context": "https://schema.org",
          "@type": "ItemList",
          name: "歷代旅外球員",
          numberOfItems: rows.length,
          itemListElement: rows.map((p, i) => ({
            "@type": "ListItem", position: i + 1,
            url: `${SITE}player/${p.slug}/`, name: p.name,
          })),
        }) +
        ldScript({
          "@context": "https://schema.org",
          "@type": "BreadcrumbList",
          itemListElement: [
            { "@type": "ListItem", position: 1, name: "首頁", item: SITE },
            { "@type": "ListItem", position: 2, name: "歷代球員", item: `${SITE}alumni/` },
          ],
        }),
    })
  );
  alumniUrls.push([`${SITE}alumni/`, alumniLastmod]);
  console.log(`歷代球員:${alumni.length} 頁 + 索引頁`);
}

// ---- 聯盟索引頁 /mlb/ /npb/ /kbo/ ----
// 「台灣有幾個人打過大聯盟」「台灣旅日球員有誰」這類查詢需要的是一覽頁,
// 而 /alumni/ 只有退役的。這裡把歷代與現役合在一起,並給出確切人數 ——
// 那是這站算得出來、而別處講不清楚的東西。
// 台灣出生與台裔分開計數:柯賓·卡洛爾、費爾柴德是海外出生的台裔,
// 混在一起講「台灣人打過大聯盟幾個」會失準。
function leagueIndexPage({ path, title, h1, lead, levelKey, activeLevelKey, activeFilter, faq, seasonsKey }) {
  const aKey = activeLevelKey || levelKey;   // 現役 KBO 的層級寫「一軍」,歷代寫「韓職一軍」
  const alu = alumni.filter((p) => (p.career || {})[levelKey]);
  const act = data.players.filter(activeFilter);
  // 年份要用該聯盟的,不是整體生涯 —— 王維中在 /kbo/ 應該顯示 2018,不是 2013–2019
  const yrs = (p) => {
    const ys = seasonsKey && p[seasonsKey];
    if (ys && ys.length) return `${ys[0]}–${ys[ys.length - 1]}`;
    const inLeague = Object.keys(p.prev_season || {}).filter((y) => (p.prev_season[y] || {})[levelKey]).sort();
    if (inLeague.length) return `${inLeague[0]}–${inLeague[inLeague.length - 1]}`;
    return `${p.first_year}–${p.last_year}`;
  };
  const line = (p, st) => !st ? "" : (p.role === "pitcher"
    ? `${st.g} 場・${st.w}勝${st.l}敗・防禦率 ${st.era}`
    : `${st.g} 場・打擊率 ${st.avg}・${st.hr} 轟`);
  const alumniLi = [...alu].sort((a, b) => (a.first_year || 0) - (b.first_year || 0))
    .map((p) => `<li><a href="${BASE}player/${p.slug}/">${esc(p.name)}</a>` +
      `<span class="al-yr">${yrs(p)}</span>` +
      `<span class="al-line">${esc(line(p, (p.career || {})[levelKey]))}</span></li>`).join("");
  const actLi = act.map((p) => {
    const st = (p.season_stats || {})[aKey];
    return `<li><a href="${BASE}player/${p.slug}/">${esc(p.name)}</a>` +
      `<span class="al-tag">${p.heritage ? "台裔" : "現役"}</span>` +
      `<span class="al-line">${esc(st ? `${season} 年 ${line(p, st)}` : `${season} 年於${esc(LEVEL_LABEL[p.level] || p.level)}`)}</span></li>`;
  }).join("");
  const body =
    `<article class="pd">` +
    `<nav class="crumb" aria-label="breadcrumb"><a href="${BASE}">首頁</a><span class="crumb-sep">›</span>` +
    `<span class="crumb-cur">${esc(h1)}</span></nav>` +
    `<h1>${esc(h1)}</h1>` +
    `<p class="pd-intro">${esc(lead)}</p>` +
    (actLi ? `<h2>現役球員（${act.length} 人）</h2><ol class="al-list">${actLi}</ol>` : "") +
    (alumniLi ? `<h2>歷代球員（${alu.length} 人）</h2><ol class="al-list">${alumniLi}</ol>` : "") +
    `<section class="faq"><h2>常見問題</h2>` +
    faq.map((it) => `<h3 class="faq-q">${esc(it.q)}</h3><p class="faq-a">${esc(it.a)}</p>`).join("") +
    `</section>` +
    `<p class="faq-more">另見:<a href="${BASE}alumni/">歷代旅外球員總覽</a></p>` +
    `</article>`;
  writeFileSync(
    (mkdirSync(resolve(DIST, path), { recursive: true }), resolve(DIST, path, "index.html")),
    renderPage(template, {
      title, description: lead.slice(0, 155), canonical: `${SITE}${path}/`,
      bodyHtml: siteWrap(body),
      noJs: true,
      headExtra:
        ldScript({
          "@context": "https://schema.org", "@type": "ItemList", name: h1,
          numberOfItems: alu.length + act.length,
          itemListElement: [...act, ...alu].map((p, i) => ({
            "@type": "ListItem", position: i + 1,
            url: `${SITE}player/${p.slug}/`, name: p.name,
          })),
        }) +
        ldScript({
          "@context": "https://schema.org", "@type": "BreadcrumbList",
          itemListElement: [
            { "@type": "ListItem", position: 1, name: "首頁", item: SITE },
            { "@type": "ListItem", position: 2, name: h1, item: `${SITE}${path}/` },
          ],
        }) +
        ldScript({
          "@context": "https://schema.org", "@type": "FAQPage",
          mainEntity: faq.map((it) => ({
            "@type": "Question", name: it.q,
            acceptedAnswer: { "@type": "Answer", text: it.a },
          })),
        }),
    })
  );
  return `${SITE}${path}/`;
}

const mlbAlumni = alumni.filter((p) => (p.career || {}).MLB);
const mlbActive = data.players.filter((p) => (p.season_stats || {}).MLB ||
  Object.values(p.prev_season || {}).some((y) => y.MLB));
const mlbNative = mlbAlumni.length + mlbActive.filter((p) => !p.heritage).length;
const mlbHeritage = mlbActive.filter((p) => p.heritage).map((p) => p.name);
const npbAlumni = alumni.filter((p) => (p.career || {})["一軍"]);
const npbActive = data.players.filter((p) => p.league === "npb" &&
  ((p.season_stats || {})["一軍"] || Object.values(p.prev_season || {}).some((y) => y["一軍"])));
const kboActive = data.players.filter((p) => p.league === "kbo");
const kboAlumni = alumni.filter((p) => (p.career || {})["韓職一軍"]);
const firstMlb = [...mlbAlumni].sort((a, b) => (a.first_year || 0) - (b.first_year || 0))[0];

const indexUrls = [
  leagueIndexPage({
    path: "mlb",
    title: `台灣大聯盟球員一覽｜歷代 ${mlbNative} 位台灣球員登上 MLB｜旅外球員情報站`,
    h1: "台灣大聯盟球員一覽（歷代＋現役）",
    lead: `登上美國職棒大聯盟的台灣出生球員至今共 ${mlbNative} 位` +
      (firstMlb ? `,最早是 ${firstMlb.name}` : "") +
      `;另有 ${mlbHeritage.length} 位海外出生的台裔球員（${mlbHeritage.join("、")}）。` +
      `以下依年份列出每一位的生涯成績,點進去看完整逐年數據（含小聯盟各層級）。`,
    levelKey: "MLB",
    activeFilter: (p) => (p.season_stats || {}).MLB || Object.values(p.prev_season || {}).some((y) => y.MLB),
    faq: [
      { q: "台灣有幾位球員登上過美國職棒大聯盟?",
        a: `台灣出生的球員至今共 ${mlbNative} 位登上大聯盟` +
           (mlbHeritage.length ? `,另有 ${mlbHeritage.length} 位海外出生的台裔球員（${mlbHeritage.join("、")}）也在大聯盟出賽。` : "。") },
      ...(firstMlb ? [{ q: "第一位登上大聯盟的台灣球員是誰?",
        a: `${firstMlb.name},${firstMlb.bio && firstMlb.bio.debut ? `${firstMlb.bio.debut.replaceAll("-", "/")} 完成大聯盟初登場` : `${firstMlb.first_year} 年登上大聯盟`}。` }] : []),
    ],
  }),
  leagueIndexPage({
    path: "npb",
    title: `台灣旅日球員一覽｜歷代 ${npbAlumni.length + npbActive.length} 位台將登上日職一軍｜旅外球員情報站`,
    h1: "台灣旅日球員一覽（歷代＋現役）",
    lead: `在日本職棒一軍出賽過的台灣球員至今共 ${npbAlumni.length + npbActive.length} 位,` +
      `最早可回溯至 ${Math.min(...npbAlumni.map((p) => p.first_year || 9999))} 年。` +
      `包含郭源治、郭泰源、莊勝雄、陽岱鋼等前輩,以及目前效力日職的現役球員。`,
    levelKey: "一軍",
    activeFilter: (p) => p.league === "npb" &&
      ((p.season_stats || {})["一軍"] || Object.values(p.prev_season || {}).some((y) => y["一軍"])),
    faq: [
      { q: "台灣有幾位球員在日本職棒一軍出賽過?",
        a: `至今共 ${npbAlumni.length + npbActive.length} 位,最早是 ${Math.min(...npbAlumni.map((p) => p.first_year || 9999))} 年。` },
      { q: "日本職棒生涯成績最好的台灣投手是誰?",
        a: (() => {
          const best = npbAlumni.filter((p) => p.role === "pitcher")
            .sort((a, b) => (((b.career || {})["一軍"] || {}).w || 0) - (((a.career || {})["一軍"] || {}).w || 0))[0];
          if (!best) return "資料整理中。";
          const c = (best.career || {})["一軍"];
          return `以勝場計是 ${best.name},日職一軍生涯 ${c.g} 場、${c.w}勝${c.l}敗、${c.ip} 局、防禦率 ${c.era}。`;
        })() },
    ],
  }),
  leagueIndexPage({
    path: "kbo",
    title: `台灣旅韓球員一覽｜韓職 KBO 台灣球員完整名單｜旅外球員情報站`,
    h1: "台灣旅韓球員一覽",
    lead: `在韓國職棒 KBO 出賽過的台灣球員至今僅 ${kboAlumni.length + kboActive.length} 位。` +
      `KBO 自 ${season} 年起實施亞洲外援（亞援）制度、每隊可登錄一名亞洲外籍球員,` +
      `在此之前台灣球員需以一般洋將身分競爭名額,因此人數極少。`,
    levelKey: "韓職一軍",
    activeLevelKey: "一軍",
    seasonsKey: "kbo_seasons",
    activeFilter: (p) => p.league === "kbo",
    faq: [
      { q: "台灣有幾位球員打過韓國職棒?",
        a: `至今僅 ${kboAlumni.length + kboActive.length} 位:${[...kboAlumni, ...kboActive].map((p) => p.name).join("、")}。` },
      { q: "第一位在韓職出賽的台灣球員是誰?",
        a: kboAlumni.length
          ? `${kboAlumni[0].name},${(kboAlumni[0].kbo_seasons || [])[0]} 年效力 NC 恐龍。`
          : "資料整理中。" },
    ],
  }),
];
console.log(`聯盟索引頁:${indexUrls.length} 頁`);

// ---- /leaders/ 台灣旅外生涯紀錄排行榜 ----
// 有了 35 位歷代前輩之後這頁才有內容:郭泰源 117 勝 vs 王建民 68 勝這種比較,
// 中文網路上沒有第二處算得出來。現役與歷代同榜(現役標記出來),因為問「台灣旅外
// 最多勝是誰」的人要的是完整答案,不是只看退役的。
// 比率項目(防禦率/打擊率)必須設門檻,否則會被一場好投的人洗榜;門檻寫在頁面上。
function leaderBoards(levelKey, label) {
  const pool = [
    ...alumni.map((p) => ({ p, c: (p.career || {})[levelKey], active: false })),
    ...data.players.map((p) => ({ p, c: (p.career || {})[levelKey], active: true })),
  ].filter((x) => x.c);
  const outs = (ip) => {
    const [a, b] = String(ip || "0").split(".");
    return (parseInt(a, 10) || 0) * 3 + (parseInt(b, 10) || 0);
  };
  // **必須依守備位置分流**:同一個欄位在投打兩種紀錄裡意思相反 ——
  // 投手的 so 是奪三振、野手的 so 是被三振;投手的 hr 是被全壘打、h 是被安打。
  // 不分流的話柯賓·卡洛爾會用「被三振 572 次」登上奪三振榜。
  const board = (title, note, pick, fmt, who, filter) => {
    const rows = pool.filter((x) => (who === "pitcher") === (x.p.role === "pitcher"))
      .filter((x) => (filter ? filter(x.c) : true))
      .map((x) => ({ ...x, v: pick(x.c) }))
      .filter((x) => x.v !== null && x.v !== undefined && x.v !== "" && Number(x.v) > 0)
      .sort((a, b) => b.v - a.v)
      .slice(0, 10);
    if (rows.length < 3) return "";   // 湊不出三個人的榜沒有意義
    const li = rows.map((r, i) =>
      `<li><span class="lb-rank">${i + 1}</span>` +
      `<a href="${BASE}player/${r.p.slug}/">${esc(r.p.name)}</a>` +
      // 台裔(海外出生)要標出來,否則榜單會被讀成「台灣出生球員的紀錄」
      (r.p.heritage ? `<span class="al-tag">台裔</span>` : r.active ? `<span class="al-tag">現役</span>` : "") +
      `<span class="lb-val">${esc(fmt(r.v, r.c))}</span></li>`).join("");
    return `<div class="lb-board"><h3>${esc(title)}</h3>` +
      (note ? `<p class="lb-note">${esc(note)}</p>` : "") +
      `<ol class="lb-list">${li}</ol></div>`;
  };
  // WAR 只有大聯盟層級算得出來(日職一軍沒有這種公開指標),所以只在 MLB 榜出現
  const warBoards = levelKey !== "MLB" ? [] : [
    board("投手：生涯 WAR", "勝場貢獻值,由逐年 WAR 相加;越高代表對球隊的整體貢獻越大。",
      (c) => c.war, (v) => `WAR ${v}`, "pitcher"),
    board("野手：生涯 WAR", "勝場貢獻值,由逐年 WAR 相加。",
      (c) => c.war, (v) => `WAR ${v}`, "batter"),
  ];
  const boards = [
    board("投手：勝場", "", (c) => c.w, (v) => `${v} 勝`, "pitcher"),
    board("投手：奪三振", "", (c) => c.so, (v) => `${v} K`, "pitcher"),
    board("投手：投球局數", "", (c) => outs(c.ip), (v, c) => `${c.ip} 局`, "pitcher"),
    board("投手：防禦率（最低 200 局）", "投球局數未達 200 局者不列入,避免少數幾場好投洗榜。",
      (c) => (outs(c.ip) >= 600 ? 1000 - parseFloat(c.era || "99") : 0),
      (v, c) => `防禦率 ${c.era}`, "pitcher"),
    board("野手：全壘打", "", (c) => c.hr, (v) => `${v} 轟`, "batter"),
    board("野手：安打", "", (c) => c.h, (v) => `${v} 安`, "batter"),
    board("野手：打點", "", (c) => c.rbi, (v) => `${v} 打點`, "batter"),
    board("野手：打擊率（最低 500 打數）", "打數未達 500 者不列入。",
      (c) => (c.ab >= 500 ? parseFloat(c.avg || "0") : 0),
      (v, c) => `打擊率 ${c.avg}`, "batter"),
    ...warBoards,
  ].filter(Boolean);
  if (!boards.length) return "";
  return `<section class="lb-section"><h2>${esc(label)}生涯紀錄</h2>` +
    `<div class="lb-grid">${boards.join("")}</div></section>`;
}

if (alumni.length) {
  const topOf = (levelKey, pick) => {
    const pool = [...alumni, ...data.players].map((p) => ({ p, c: (p.career || {})[levelKey] })).filter((x) => x.c);
    return pool.map((x) => ({ ...x, v: pick(x.c) || 0 })).sort((a, b) => b.v - a.v)[0];
  };
  const mlbW = topOf("MLB", (c) => c.w);
  const npbW = topOf("一軍", (c) => c.w);
  const npbHr = topOf("一軍", (c) => c.hr);
  const faq = [
    mlbW && { q: "台灣球員大聯盟生涯最多勝是誰?",
      a: `${mlbW.p.name},大聯盟生涯 ${mlbW.c.g} 場、${mlbW.c.w}勝${mlbW.c.l}敗、防禦率 ${mlbW.c.era}。` },
    npbW && { q: "台灣球員日職生涯最多勝是誰?",
      a: `${npbW.p.name},日職一軍生涯 ${npbW.c.g} 場、${npbW.c.w}勝${npbW.c.l}敗、防禦率 ${npbW.c.era}。` },
    npbHr && { q: "台灣球員日職生涯最多全壘打是誰?",
      a: `${npbHr.p.name},日職一軍生涯 ${npbHr.c.g} 場、${npbHr.c.hr} 支全壘打、打擊率 ${npbHr.c.avg}。` },
  ].filter(Boolean);
  const body =
    `<article class="pd">` +
    `<nav class="crumb" aria-label="breadcrumb"><a href="${BASE}">首頁</a><span class="crumb-sep">›</span>` +
    `<span class="crumb-cur">生涯紀錄排行榜</span></nav>` +
    `<h1>台灣旅外生涯紀錄排行榜</h1>` +
    `<p class="pd-intro">歷代與現役台灣旅外球員的生涯累積數據排名,涵蓋美國職棒大聯盟與日本職棒一軍。` +
    `資料為各聯盟官方紀錄的生涯合計;小聯盟、二軍成績不計入。</p>` +
    leaderBoards("MLB", "大聯盟") +
    leaderBoards("一軍", "日職一軍") +
    `<section class="faq"><h2>常見問題</h2>` +
    faq.map((it) => `<h3 class="faq-q">${esc(it.q)}</h3><p class="faq-a">${esc(it.a)}</p>`).join("") +
    `</section>` +
    `<p class="faq-more">另見:<a href="${BASE}alumni/">歷代旅外球員</a>、<a href="${BASE}mlb/">台灣大聯盟球員一覽</a>、<a href="${BASE}npb/">台灣旅日球員一覽</a></p>` +
    `</article>`;
  writeFileSync(
    (mkdirSync(resolve(DIST, "leaders"), { recursive: true }), resolve(DIST, "leaders", "index.html")),
    renderPage(template, {
      title: `台灣旅外生涯紀錄排行榜｜大聯盟與日職勝場、全壘打、三振榜｜旅外球員情報站`,
      description: `台灣旅外球員的生涯累積排名:大聯盟與日職一軍的勝場、三振、全壘打、安打、打點榜,歷代與現役同榜。${faq[0] ? faq[0].a : ""}`,
      canonical: `${SITE}leaders/`,
      bodyHtml: siteWrap(body),
      noJs: true,
      headExtra:
        ldScript({
          "@context": "https://schema.org", "@type": "BreadcrumbList",
          itemListElement: [
            { "@type": "ListItem", position: 1, name: "首頁", item: SITE },
            { "@type": "ListItem", position: 2, name: "生涯紀錄排行榜", item: `${SITE}leaders/` },
          ],
        }) +
        ldScript({
          "@context": "https://schema.org", "@type": "FAQPage",
          mainEntity: faq.map((it) => ({
            "@type": "Question", name: it.q,
            acceptedAnswer: { "@type": "Answer", text: it.a },
          })),
        }),
    })
  );
  indexUrls.push(`${SITE}leaders/`);
  console.log("生涯紀錄排行榜:1 頁");
}

// ---- /players/ 全部球員索引(含搜尋)----
// 74 個球員頁散在首頁、/alumni/、三個聯盟索引裡,沒有一頁能一次看完並快速找人。
// 這頁按羅馬拼音 A–Z 分組(BR 的作法),並附一個純 JS 的即時篩選 —— 這頁不掛
// React(在 main.jsx 的 STATIC_PAGES 裡),所以搜尋是頁內的一小段原生 script,
// 沒有 JS 時清單仍完整可瀏覽、可爬。
function playersIndexPage() {
  const rows = [
    ...data.players.map((p) => ({
      p, kind: "現役",
      meta: [LEAGUE_LABEL[p.league], LEVEL_LABEL[p.level] || p.level, p.org].filter(Boolean).join("・"),
    })),
    ...alumni.map((p) => ({
      p, kind: "歷代",
      meta: [p.league === "npb" ? "旅日" : "旅美",
             `${p.first_year}–${p.last_year}`].filter(Boolean).join("・"),
    })),
  ].sort((a, b) => a.p.slug.localeCompare(b.p.slug));

  const groups = new Map();
  for (const r of rows) {
    const letter = (r.p.slug[0] || "#").toUpperCase();
    if (!groups.has(letter)) groups.set(letter, []);
    groups.get(letter).push(r);
  }
  const letters = [...groups.keys()].sort();
  const jump = letters.map((l) => `<a href="#g-${l}">${l}</a>`).join("");
  const sections = letters.map((l) => {
    const li = groups.get(l).map(({ p, kind, meta }) =>
      `<li data-s="${esc((p.name + " " + (p.name_en || "") + " " + p.slug + " " + meta).toLowerCase())}">` +
      `<a href="${BASE}player/${p.slug}/">${esc(p.name)}</a>` +
      `<span class="al-tag">${kind}</span>` +
      `<span class="al-line">${esc(meta)}</span></li>`).join("");
    return `<section class="pi-group" id="g-${l}"><h2>${l}</h2><ul class="al-list">${li}</ul></section>`;
  }).join("");

  const body =
    `<article class="pd">` +
    `<nav class="crumb" aria-label="breadcrumb"><a href="${BASE}">首頁</a><span class="crumb-sep">›</span>` +
    `<span class="crumb-cur">球員索引</span></nav>` +
    `<h1>台灣旅外球員索引</h1>` +
    `<p class="pd-intro">現役 ${data.players.length} 位、歷代 ${alumni.length} 位,` +
    `共 ${rows.length} 位台灣旅外球員,依羅馬拼音排序。輸入中文名、英文名或球隊即可篩選。</p>` +
    `<input id="pi-q" class="pi-search" type="search" placeholder="搜尋球員（王建民、Wang、洋基…）" autocomplete="off" />` +
    `<p class="pi-jump">${jump}</p>` +
    `<p id="pi-empty" class="empty-note" hidden>找不到符合的球員。</p>` +
    sections +
    `</article>` +
    // 這頁不掛 React,篩選用原生 script;沒有 JS 時清單仍完整可用
    `<script>(function(){var q=document.getElementById("pi-q");if(!q)return;` +
    `var items=[].slice.call(document.querySelectorAll(".pi-group li"));` +
    `var groups=[].slice.call(document.querySelectorAll(".pi-group"));` +
    `var empty=document.getElementById("pi-empty");` +
    `q.addEventListener("input",function(){var v=q.value.trim().toLowerCase();var n=0;` +
    `items.forEach(function(li){var hit=!v||li.getAttribute("data-s").indexOf(v)>=0;li.hidden=!hit;if(hit)n++;});` +
    `groups.forEach(function(g){g.hidden=![].slice.call(g.querySelectorAll("li")).some(function(li){return !li.hidden;});});` +
    `empty.hidden=n>0;});})();</script>`;
  writeFileSync(
    (mkdirSync(resolve(DIST, "players"), { recursive: true }), resolve(DIST, "players", "index.html")),
    renderPage(template, {
      title: `台灣旅外球員索引｜現役與歷代共 ${rows.length} 位球員｜旅外球員情報站`,
      description: `台灣旅外棒球員完整索引:現役 ${data.players.length} 位、歷代 ${alumni.length} 位,依羅馬拼音排序,可搜尋姓名或球隊。`,
      canonical: `${SITE}players/`,
      bodyHtml: siteWrap(body),
      noJs: true,   // 篩選是頁內的內嵌 script,不需要 bundle
      headExtra: ldScript({
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        itemListElement: [
          { "@type": "ListItem", position: 1, name: "首頁", item: SITE },
          { "@type": "ListItem", position: 2, name: "球員索引", item: `${SITE}players/` },
        ],
      }),
    })
  );
  console.log(`球員索引:1 頁(${rows.length} 位、${letters.length} 個字母)`);
  return `${SITE}players/`;
}

indexUrls.push(playersIndexPage());

// ---- 最新消息 /news/ ----
// **站上自己寫的消息頁**,不是外站標題的清單。每一則的來源分三種:
//   ① MLB 官方異動紀錄(transactions.json)—— DFA、下放、升上大聯盟、傷兵進出
//   ② 本站逐場資料(game_logs)—— 出賽當天的數據與近況,由 src/lib/recap.js 算
//   ③ 前兩者都推不出來的事(亞運名單、合約談判、專訪)—— 只能引用媒體原標題並
//      註明出處,不改寫別人的內文
// 收斂規則見 recap.buildFeed:同一位球員同一天只要我們寫得出來,那天的媒體報導
// 就退成出處掛名。費爾柴德遭 DFA 那天有九家媒體,這裡是一則事實 + 九個出處。
const WEEKDAY = ["日", "一", "二", "三", "四", "五", "六"];
const LEAGUE_ZH = { mlb: "旅美", milb: "旅美", npb: "旅日", kbo: "旅韓" };

function newsPage() {
  const feed = buildFeed({ players: data.players, transactions, moves: data.moves || [], news, days: 30 });
  if (!feed.length) {
    console.log("最新消息:沒有資料,跳過這頁");
    return null;
  }

  const entryHtml = (e) => {
    const p = e.player;
    const lg = LEAGUE_ZH[p.league] || "";
    const searchable = [e.headline, e.quote && e.quote.title, p.name, ...e.sources].filter(Boolean).join(" ");
    const own = !e.quote;

    // 自家寫的標題與引用別人的標題,版面上必須分得出來 —— 引用的用引號 + 「據…報導」
    const head = own
      ? `<p class="nw-hl">${esc(e.headline)}</p>`
      : `<p class="nw-hl nw-hl-q">「${esc(e.quote.title)}」</p>`;

    const srcBits = [];
    for (const f of e.facts) srcBits.push(`來源：${esc(f.src)}`);
    if (!own) {
      const first = e.quote.source || "媒體";
      srcBits.push(`據《${esc(first)}》報導` + (e.others ? `，另 ${e.others} 則同日報導` : ""));
    }
    if (own && e.sources.length) srcBits.push(`同日媒體報導：${esc(e.sources.slice(0, 6).join("、"))}`);
    if (!own && e.sources.length > 1) {
      srcBits.push(`出處：${esc(e.sources.slice(0, 6).join("、"))}`);
    }

    return (
      `<li class="nw-item${own ? "" : " nw-item-q"}" data-lg="${esc(lg)}" data-s="${esc(searchable.toLowerCase())}">` +
      head +
      (e.gameLine ? `<p class="nw-game">${e.badge ? `<span class="nw-badge">${esc(e.badge)}</span>` : ""}${esc(e.gameLine)}</p>` : "") +
      (e.seasonLine ? `<p class="nw-season">本季 ${esc(e.seasonLine)}</p>` : "") +
      (e.recentForm ? `<p class="nw-form">${esc(e.recentForm)}</p>` : "") +
      `<p class="nw-meta">${srcBits.join("・")}` +
      (!own && e.quote.url ? ` <a class="nw-orig" href="${esc(e.quote.url)}" target="_blank" rel="noopener nofollow">原文</a>` : "") +
      `</p>` +
      `<a class="nw-go" href="${BASE}player/${p.slug}/">看${esc(p.name)}的完整逐場紀錄與數據 →</a>` +
      `</li>`
    );
  };

  const sections = feed.map((day) => {
    const [, m, dd] = day.date.split("-");
    const wd = WEEKDAY[new Date(`${day.date}T00:00:00Z`).getUTCDay()];
    return `<section class="nw-day"><h2 id="d-${day.date}">${Number(m)}月${Number(dd)}日<span class="nw-wd">週${wd}</span></h2>` +
      `<ul class="nw-list">${day.entries.map(entryHtml).join("")}</ul></section>`;
  }).join("");

  const all = feed.flatMap((d) => d.entries);
  const ownCount = all.filter((e) => !e.quote).length;
  const playerCount = new Set(all.map((e) => e.player.id)).size;
  const chips = ["全部", "旅美", "旅日", "旅韓"].map((c, i) =>
    `<button type="button" class="nw-chip${i ? "" : " nw-chip-on"}" data-lg="${c}">${c}</button>`).join("");

  const body =
    `<article class="pd">` +
    `<nav class="crumb" aria-label="breadcrumb"><a href="${BASE}">首頁</a><span class="crumb-sep">›</span>` +
    `<span class="crumb-cur">最新消息</span></nav>` +
    `<h1>台灣旅外球員最新消息</h1>` +
    `<p class="pd-intro">近 30 天旅外台將的異動與出賽整理,共 ${all.length} 則、涵蓋 ${playerCount} 位球員。` +
    `其中 ${ownCount} 則由本站依 MLB 官方異動紀錄與逐場數據寫成,` +
    `另 ${all.length - ownCount} 則是官方資料推不出來的消息,引用媒體原標題並註明出處。</p>` +
    `<div class="nw-bar"><div class="nw-chips">${chips}</div>` +
    `<input id="nw-q" class="nw-search" type="search" placeholder="搜尋球員、媒體或關鍵字" autocomplete="off" /></div>` +
    `<p id="nw-empty" class="empty-note" hidden>找不到符合的消息。</p>` +
    sections +
    `<p class="nw-note">異動事實來自 MLB Stats API 官方異動紀錄;出賽數據與近況由本站逐場資料計算。` +
    `標示「據《…》報導」者為官方資料無法取得的消息,僅引用原標題並連回原始報導,著作權屬各該媒體所有。</p>` +
    `</article>` +
    `<script>(function(){var q=document.getElementById("nw-q"),empty=document.getElementById("nw-empty");` +
    `var items=[].slice.call(document.querySelectorAll(".nw-item"));` +
    `var days=[].slice.call(document.querySelectorAll(".nw-day"));` +
    `var chips=[].slice.call(document.querySelectorAll(".nw-chip"));var lg="全部";` +
    `function apply(){var v=(q.value||"").trim().toLowerCase(),n=0;` +
    `items.forEach(function(li){var okL=lg==="全部"||li.getAttribute("data-lg").indexOf(lg)>=0;` +
    `var okQ=!v||li.getAttribute("data-s").indexOf(v)>=0;var hit=okL&&okQ;li.hidden=!hit;if(hit)n++;});` +
    `days.forEach(function(d){d.hidden=![].slice.call(d.querySelectorAll(".nw-item")).some(function(li){return !li.hidden;});});` +
    `empty.hidden=n>0;}` +
    `chips.forEach(function(c){c.addEventListener("click",function(){lg=c.getAttribute("data-lg");` +
    `chips.forEach(function(x){x.className="nw-chip"+(x===c?" nw-chip-on":"");});apply();});});` +
    `q.addEventListener("input",apply);})();</script>`;

  mkdirSync(resolve(DIST, "news"), { recursive: true });
  writeFileSync(
    resolve(DIST, "news", "index.html"),
    renderPage(template, {
      title: `台灣旅外球員最新消息｜異動、傷兵與近況整理｜旅外球員情報站`,
      description: `台灣旅外棒球員近 30 天消息:大聯盟官方異動(指定讓渡、下放、升上大聯盟、` +
        `傷兵名單)與日職、韓職台將的出賽近況,共 ${all.length} 則、${playerCount} 位球員,每日更新。`,
      canonical: `${SITE}news/`,
      bodyHtml: siteWrap(body),
      noJs: true,
      headExtra: ldScript({
        "@context": "https://schema.org", "@type": "CollectionPage",
        name: "台灣旅外球員最新消息", url: `${SITE}news/`, inLanguage: "zh-TW",
        isPartOf: { "@type": "WebSite", name: "旅外球員情報站", url: SITE },
      }) + ldScript({
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        itemListElement: [
          { "@type": "ListItem", position: 1, name: "首頁", item: SITE },
          { "@type": "ListItem", position: 2, name: "最新消息", item: `${SITE}news/` },
        ],
      }),
    })
  );
  console.log(`最新消息:1 頁(${all.length} 則,自家寫 ${ownCount}、引用 ${all.length - ownCount};${playerCount} 位球員、${feed.length} 天)`);
  return `${SITE}news/`;
}

const newsUrl = newsPage();
if (newsUrl) indexUrls.push(newsUrl);

// ---- 球季逐場頁 /player/{slug}/{year}/ ----
// 往年的逐場資料存在 public/data/gamelogs/{slug}.json(見 fetch_gamelogs.py),
// 不放進 players.json —— 那是首頁每次載入都會下載的檔案。這裡在 build 時讀進來
// 產出靜態頁,爬蟲與 LLM 直接拿得到完整表格,不必等 JS。
// 只有旅美有:npb.jp 的舊球季頁沒有逐場資料。
function seasonLogPages() {
  const urls = [];
  const all = [...data.players.map((p) => ({ p, alumni: false })),
               ...alumni.map((p) => ({ p, alumni: true }))];
  for (const { p, alumni: isAlumni } of all) {
    let store;
    try {
      store = JSON.parse(readFileSync(resolve(ROOT, `public/data/gamelogs/${p.slug}.json`), "utf-8"));
    } catch {
      continue;
    }
    const years = Object.keys(store).sort((a, b) => Number(b) - Number(a));
    for (const year of years) {
      const byLevel = store[year];
      const seasonStat = (p.prev_season || {})[year] || {};
      const isP = p.role === "pitcher";
      const blocks = Object.entries(byLevel).map(([level, games]) => {
        const st = seasonStat[level];
        const head = isP
          ? ["日期", "對手", "局", "安", "失", "自責", "K", "BB", "HR"]
          : ["日期", "對手", "打數", "安", "轟", "打點", "得", "盜", "BB"];
        const rows = games.map((g) => {
          const cells = isP
            ? [fmtDateZh(g.date), g.opponent || "", g.ip, g.h, g.r, g.er, g.so, g.bb, g.hr]
            : [fmtDateZh(g.date), g.opponent || "", g.ab, g.h, g.hr, g.rbi, g.r, g.sb, g.bb];
          return `<tr>${cells.map((c) => `<td>${esc(String(c ?? ""))}</td>`).join("")}</tr>`;
        }).join("");
        return `<h2>${esc(LEVEL_LABEL[level] || level)}（${games.length} 場${st ? `,${
          isP ? `${st.w}勝${st.l}敗、防禦率 ${st.era}` : `打擊率 ${st.avg}、${st.hr} 轟`}` : ""}）</h2>` +
          `<div class="table-scroll"><table class="stat-table rc-table"><thead><tr>` +
          head.map((h) => `<th>${h}</th>`).join("") + `</tr></thead><tbody>${rows}</tbody></table></div>`;
      }).join("");
      const mainLv = Object.keys(byLevel)[0];
      const st = seasonStat[mainLv];
      const core = st ? (isP ? `${st.g} 場 ${st.w}勝${st.l}敗、防禦率 ${st.era}`
                             : `${st.g} 場、打擊率 ${st.avg}、${st.hr} 轟`) : "";
      const nGames = Object.values(byLevel).reduce((a, g) => a + g.length, 0);
      const idx = years.indexOf(year);
      const nav = [
        idx > 0 ? `<a href="${BASE}player/${p.slug}/${years[idx - 1]}/">← ${years[idx - 1]} 球季</a>` : "",
        `<a href="${BASE}player/${p.slug}/">回 ${esc(p.name)} 完整生涯</a>`,
        idx < years.length - 1 ? `<a href="${BASE}player/${p.slug}/${years[idx + 1]}/">${years[idx + 1]} 球季 →</a>` : "",
      ].filter(Boolean).join("　·　");
      const lead = `${p.name}${year} 球季的完整逐場出賽紀錄,共 ${nGames} 場` +
        (core ? `,該季${LEVEL_LABEL[mainLv] || mainLv}成績為 ${core}` : "") + "。";
      const body =
        `<article class="pd">` +
        `<nav class="crumb" aria-label="breadcrumb"><a href="${BASE}">首頁</a><span class="crumb-sep">›</span>` +
        (isAlumni ? `<a href="${BASE}alumni/">歷代球員</a><span class="crumb-sep">›</span>` : "") +
        `<a href="${BASE}player/${p.slug}/">${esc(p.name)}</a><span class="crumb-sep">›</span>` +
        `<span class="crumb-cur">${year} 球季</span></nav>` +
        `<h1>${esc(p.name)} ${year} 逐場紀錄</h1>` +
        `<p class="pd-intro">${esc(lead)}</p>` +
        blocks +
        `<p class="faq-more">${nav}</p>` +
        `</article>`;
      const canonical = `${SITE}player/${p.slug}/${year}/`;
      writeFileSync(
        (mkdirSync(resolve(DIST, "player", p.slug, year), { recursive: true }),
         resolve(DIST, "player", p.slug, year, "index.html")),
        renderPage(template, {
          title: `${p.name} ${year} 逐場紀錄｜${core || `${nGames} 場出賽`}｜旅外球員情報站`,
          description: lead,
          canonical,
          bodyHtml: siteWrap(body),
          image: `og/${p.slug}.png`,
          noJs: true,
          headExtra: ldScript({
            "@context": "https://schema.org", "@type": "BreadcrumbList",
            itemListElement: [
              { "@type": "ListItem", position: 1, name: "首頁", item: SITE },
              { "@type": "ListItem", position: 2, name: p.name, item: `${SITE}player/${p.slug}/` },
              { "@type": "ListItem", position: 3, name: `${year} 球季`, item: canonical },
            ],
          }),
        })
      );
      const lastGame = Object.values(byLevel).flat().map((g) => g.date).sort().pop();
      urls.push([canonical, lastGame || `${year}-12-31`]);
    }
  }
  if (urls.length) console.log(`球季逐場頁:${urls.length} 頁`);
  return urls;
}

const seasonUrls = seasonLogPages();

// ---- sitemap:拆成分類索引 ----
// 原本 308 個網址混在同一個檔裡,GSC 只會給一個總涵蓋率,看不出是哪一類卡住。
// 拆開之後可以分別看到「球員頁索引了幾成」「球季頁索引了幾成」——
// 目前已知表現頁是 Discovered–currently not indexed、歷代與球季頁 Google 還沒發現,
// 拆開才追蹤得到後續變化。
const lastmod = (data.updated_at || new Date().toISOString()).slice(0, 10);
if (!alumniLastmod) alumniLastmod = lastmod;
// lastmod 要誠實。原本 308 個網址一律寫今天,包括 1981 年的球季頁 —— 每天都宣稱
// 全站更新,爬蟲會學到這個 lastmod 沒有資訊量而忽略它,反而更難把有限的檢索預算
// 導到真正變動的頁。改成:每天更新的頁(球員/首頁/索引)用資料時間,歷史頁用該場
// 或該季的日期。
const urlsetXml = (urls) =>
  `<?xml version="1.0" encoding="UTF-8"?>\n` +
  `<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n` +
  urls.map((u) => {
    const lm = typeof u === "string" ? lastmod : u[1];
    const loc = typeof u === "string" ? u : u[0];
    return `  <url><loc>${loc}</loc><lastmod>${lm}</lastmod></url>`;
  }).join("\n") +
  `\n</urlset>\n`;

const groups = [
  // core:首頁與各索引頁,最該優先被檢索
  ["sitemap-core.xml", [SITE, `${SITE}latest/`, ...indexUrls]],
  ["sitemap-players.xml", [...data.players.map((p) => `${SITE}player/${p.slug}/`), ...alumniUrls]],
  ["sitemap-seasons.xml", seasonUrls],
  ["sitemap-performance.xml", perfSitemapUrls],
].filter(([, u]) => u.length);

for (const [name, urls] of groups) writeFileSync(resolve(DIST, name), urlsetXml(urls));
writeFileSync(
  resolve(DIST, "sitemap.xml"),
  `<?xml version="1.0" encoding="UTF-8"?>\n` +
  `<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n` +
  groups.map(([name]) => `  <sitemap><loc>${SITE}${name}</loc><lastmod>${lastmod}</lastmod></sitemap>`).join("\n") +
  `\n</sitemapindex>\n`
);
console.log("sitemap:" + groups.map(([n, u]) => `${n.replace("sitemap-", "").replace(".xml", "")} ${u.length}`).join("、"));

// ---- llms.txt ----
// 給 AI 答案引擎(ChatGPT / Perplexity / Claude / AI Overviews)的站點導覽:
// 用一頁講清楚這站有什麼、資料從哪來、哪些頁最值得引用。內容由資料生成,
// 人數與年份會跟著每日更新,不會變成過期的手寫檔。
const alumniSorted = [...alumni].sort((a, b) => (a.first_year || 0) - (b.first_year || 0));
const notable = alumniSorted.filter((p) => ((p.career || {}).MLB || {}).g >= 100 || ((p.career || {})["一軍"] || {}).g >= 300);
const llms = [
  `# 旅外球員情報站（players.clutchgtime.com）`,
  ``,
  `> 台灣旅外棒球員的數據庫與每日戰報。收錄 ${data.players.length} 位現役球員（旅美 MLB／小聯盟、旅日 NPB、旅韓 KBO）的逐場出賽與 ${season} 球季累積數據，` +
  `以及 ${alumni.length} 位歷代前輩的完整生涯逐年成績，最早回溯至 ${alumniSorted.length ? alumniSorted[0].first_year : season} 年。`,
  ``,
  `資料來源：MLB Stats API（官方）、npb.jp（日本野球機構官方）、koreabaseball.com（KBO 官方）。`,
  `每日台灣時間清晨 6 點自動更新；每頁的數字皆由來源資料直接生成，不含人工推估。`,
  `所屬球隊、對手隊名為中文化後的譯名；查無通用中文譯名者保留英文原名。`,
  ``,
  `## 主要頁面`,
  `- [首頁：全站球員索引](${SITE}): 現役與歷代球員的完整清單`,
  `- [歷代旅外球員](${SITE}alumni/): ${alumni.length} 位已退役／離開美日韓職棒的台灣球員生涯數據`,
  `- [最新表現](${SITE}latest/): 近三週的亮點表現（開轟・勝投・救援・優質先發），含精華影片`,
  ...(news.length
    ? [`- [最新消息](${SITE}news/): 台灣媒體對旅外球員的近期報導彙整（標題與出處，連回原媒體）`]
    : []),
  ``,
  `## 代表性球員頁（含完整生涯逐年數據）`,
  ...notable.map((p) => {
    const m = (p.career || {}).MLB || (p.career || {})["一軍"] || {};
    const line = p.role === "pitcher"
      ? `${m.g} 場、${m.w}勝${m.l}敗、防禦率 ${m.era}`
      : `${m.g} 場、打擊率 ${m.avg}、${m.hr} 轟`;
    return `- [${p.name}](${SITE}player/${p.slug}/): ${p.first_year}–${p.last_year}，${p.league === "npb" ? "日職一軍" : "大聯盟"}生涯 ${line}`;
  }),
  ``,
  `## 現役球員頁`,
  ...data.players.map((p) => `- [${p.name}](${SITE}player/${p.slug}/): ${LEAGUE_LABEL[p.league]}${LEVEL_LABEL[p.level] || p.level}・${p.org}`),
  ``,
].join("\n");
writeFileSync(resolve(DIST, "llms.txt"), llms);
console.log(`llms.txt:${notable.length} 位代表球員 + ${data.players.length} 位現役`);

// ---- robots.txt ----
writeFileSync(
  resolve(DIST, "robots.txt"),
  `User-agent: *\nAllow: /\n\nSitemap: ${SITE}sitemap.xml\n`
);

console.log(`預渲染完成:${count} 個球員頁 + 首頁 + sitemap(${groups.reduce((a, [, u]) => a + u.length, 0)} 筆) + robots.txt`);
