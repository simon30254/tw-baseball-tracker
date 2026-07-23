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

import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");
const DIST = resolve(ROOT, "dist");

const BASE = (process.env.BASE_PATH || "/").replace(/\/*$/, "/"); // 保證結尾斜線
const ORIGIN = (process.env.SITE_ORIGIN || "https://simon30254.github.io").replace(/\/$/, "");
const SITE = ORIGIN + BASE; // 例:https://simon30254.github.io/tw-baseball-tracker/

const data = JSON.parse(readFileSync(resolve(ROOT, "public/data/players.json"), "utf-8"));
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

function bioLine(p) {
  const b = p.bio || {};
  const parts = [LEAGUE_ORG[p.league], LEVEL_LABEL[p.level] || p.level, p.org].filter(Boolean);
  const sub = [];
  if (b.age) sub.push(`${b.age}歲`);
  if (b.pos_zh) sub.push(b.pos_zh);
  if (b.throws && b.bats) sub.push(`${b.throws}投${b.bats}打`);
  if (b.ht && b.wt) sub.push(`${b.ht}cm / ${b.wt}kg`);
  if (b.velo) sub.push(`最快 ${b.velo}`);
  return parts.concat(sub).join("・");
}

function introText(p) {
  const b = p.bio || {};
  const league = LEAGUE_LABEL[p.league];
  const role = roleZh(p);
  let s = `${p.name}（${romanName(p)}）是效力於${p.org}${LEVEL_LABEL[p.level] || p.level}的台灣${league}${role}`;
  if (b.velo && p.role === "pitcher") s += `，最快球速 ${b.velo}`;
  if (b.debut) s += `，${b.debut.replaceAll("-", "/")} 完成大聯盟初登場`;
  s += `。以下為 ${season} 球季累積數據與最近出賽紀錄。`;
  return s;
}

function seasonTable(p) {
  const levels = Object.entries(p.season_stats || {});
  if (!levels.length) return `<p>本季尚無累積數據。</p>`;
  const isP = p.role === "pitcher";
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

function recentGames(p) {
  const games = (p.game_logs || []).slice(0, 10);
  if (!games.length) return "";
  const li = games.map((g) => {
    const date = g.date.slice(5).replace("-", "/");
    const lvl = g.level ? `[${LEVEL_LABEL[g.level] || g.level}] ` : "";
    let line;
    if (g.type === "pitching") {
      const parts = [`${g.ip}局`, `${g.h}安`, `失${g.r}分`, `${g.so}K`];
      if (g.bb > 0) parts.push(`${g.bb}BB`);
      if (g.hr > 0) parts.push(`被${g.hr}轟`);
      line = parts.join(" ");
    } else {
      const parts = [`${g.ab}打數${g.h}安`];
      if (g.hr > 0) parts.push(`${g.hr}轟`);
      if (g.rbi > 0) parts.push(`${g.rbi}打點`);
      if (g.sb > 0) parts.push(`${g.sb}盜`);
      line = parts.join(" ");
    }
    return `<li>${date} ${lvl}vs ${esc(g.opponent)}：${esc(line)}</li>`;
  });
  return `<h2>最近出賽</h2><ul>${li.join("")}</ul>`;
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
  const breadcrumb = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "旅外戰報", item: SITE },
      { "@type": "ListItem", position: 2, name: p.name, item: url },
    ],
  };
  return (
    `<script type="application/ld+json">${JSON.stringify(person)}</script>` +
    `<script type="application/ld+json">${JSON.stringify(breadcrumb)}</script>`
  );
}

// 把 head 的 title/description/canonical/OG 換掉,並在 #root 注入內容
function renderPage(html, { title, description, canonical, bodyHtml, headExtra = "" }) {
  let out = html.replace(/<title>[\s\S]*?<\/title>/, `<title>${esc(title)}</title>`);
  out = out.replace(
    /<meta name="description"[^>]*>/,
    `<meta name="description" content="${esc(description)}" />`
  );
  const meta = [
    `<link rel="canonical" href="${canonical}" />`,
    `<meta property="og:type" content="website" />`,
    `<meta property="og:title" content="${esc(title)}" />`,
    `<meta property="og:description" content="${esc(description)}" />`,
    `<meta property="og:url" content="${canonical}" />`,
    `<meta property="og:site_name" content="旅外戰報" />`,
    `<meta name="twitter:card" content="summary" />`,
    headExtra,
  ].join("\n    ");
  out = out.replace("</head>", `    ${meta}\n  </head>`);
  out = out.replace('<div id="root"></div>', `<div id="root">${bodyHtml}</div>`);
  return out;
}

// ---- 每位球員頁 ----
let count = 0;
for (const p of data.players) {
  const title = `${p.name} ${romanName(p)}｜${season} 球季數據・最近出賽｜旅外戰報`;
  const description = introText(p).slice(0, 150);
  const canonical = `${SITE}player/${p.slug}/`;
  const bodyHtml =
    `<article class="pd">` +
    `<a class="pd-back" href="${BASE}">← 回旅外戰報</a>` +
    `<h1>${esc(p.name)} <span class="pd-en">${esc(romanName(p))}</span></h1>` +
    `<p class="pd-bio">${esc(bioLine(p))}</p>` +
    `<p class="pd-intro">${esc(introText(p))}</p>` +
    `<h2>${season} 球季累積數據</h2>${seasonTable(p)}` +
    recentGames(p) +
    `</article>`;
  const html = renderPage(template, { title, description, canonical, bodyHtml, headExtra: jsonLd(p) });
  const dir = resolve(DIST, "player", p.slug);
  mkdirSync(dir, { recursive: true });
  writeFileSync(resolve(dir, "index.html"), html);
  count++;
}

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
const homeBody =
  `<div class="prerender-home">` +
  `<h1>旅外戰報｜台灣棒球員追蹤</h1>` +
  `<p>每日追蹤旅美、旅日、旅韓共 ${data.players.length} 位台灣旅外棒球員的出賽表現與 ${season} 球季數據。</p>` +
  leagueBlock("mlb", "旅美（MLB / 小聯盟）") +
  leagueBlock("npb", "旅日（NPB）") +
  leagueBlock("kbo", "旅韓（KBO）") +
  `</div>`;
const homeDesc = `每日追蹤旅美、旅日、旅韓共 ${data.players.length} 位台灣旅外棒球員的出賽表現與 ${season} 球季數據。`;
const homeHtml = renderPage(template, {
  title: "旅外戰報｜台灣棒球員追蹤",
  description: homeDesc,
  canonical: SITE,
  bodyHtml: homeBody,
});
writeFileSync(resolve(DIST, "index.html"), homeHtml);

// ---- sitemap.xml ----
const urls = [SITE, ...data.players.map((p) => `${SITE}player/${p.slug}/`)];
const lastmod = (data.updated_at || new Date().toISOString()).slice(0, 10);
const sitemap =
  `<?xml version="1.0" encoding="UTF-8"?>\n` +
  `<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n` +
  urls
    .map((u) => `  <url><loc>${u}</loc><lastmod>${lastmod}</lastmod></url>`)
    .join("\n") +
  `\n</urlset>\n`;
writeFileSync(resolve(DIST, "sitemap.xml"), sitemap);

// ---- robots.txt ----
writeFileSync(
  resolve(DIST, "robots.txt"),
  `User-agent: *\nAllow: /\n\nSitemap: ${SITE}sitemap.xml\n`
);

console.log(`預渲染完成:${count} 個球員頁 + 首頁 + sitemap(${urls.length} 筆) + robots.txt`);
