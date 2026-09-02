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

// 靜態頁首導覽列(與 React SiteHeader 一致;React 掛載後會取代 #root,此為首次載入/爬蟲用)
function topbarHtml() {
  const nav = [
    ["", "每日戰報"], ["latest/", "最新表現"], ["", "累積數據"], ["", "地圖"], ["", "評比"],
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
    parts.push(`${s.ip} 局`, `${s.so} 次三振`, `防禦率 ${s.era}`, `WHIP ${s.whip}`);
  } else {
    parts = [`${s.g} 場`, `打擊率 ${s.avg}`];
    if (s.hr) parts.push(`${s.hr} 轟`);
    if (s.rbi) parts.push(`${s.rbi} 打點`);
    parts.push(`OPS ${s.ops}`);
  }
  return `${season} 球季在${lv}出賽 ${parts.join("、")}。`;
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
  let s = p.heritage
    ? `${p.name}（${romanName(p)}）是效力於${p.org}${LEVEL_LABEL[p.level] || p.level}、具台灣血統的台裔旅美${role}`
    : `${p.name}（${romanName(p)}）是效力於${p.org}${LEVEL_LABEL[p.level] || p.level}的台灣${league}${role}`;
  if (b.velo && p.role === "pitcher") s += `，最快球速 ${b.velo}`;
  if (b.debut) s += `，${b.debut.replaceAll("-", "/")} 完成大聯盟初登場`;
  s += `。以下為 ${season} 球季累積數據與最近出賽紀錄。`;
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

// 去年(回追)累積數據
function prevSeasonBlock(p) {
  const prev = (p.prev_season && p.prev_season[String(season - 1)]) || {};
  const levels = Object.entries(prev);
  if (!levels.length) return "";
  const teams = [...new Set(levels.map(([, s]) => s.team).filter(Boolean))];
  const cap = teams.length ? `<span class="prev-team">效力 ${esc(teams.join("、"))}</span>` : "";
  return `<h2>${season - 1} 賽季累積${cap}</h2>${statTable(levels, p.role === "pitcher")}`;
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

function relatedHtml(p) {
  const c = p.content || {};
  const articles = c.articles || [];
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
  return `<script type="application/ld+json">${JSON.stringify(schema)}</script>`;
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
      { "@type": "ListItem", position: 1, name: "首頁", item: SITE },
      { "@type": "ListItem", position: 2, name: p.name, item: url },
    ],
  };
  return (
    `<script type="application/ld+json">${JSON.stringify(person)}</script>` +
    `<script type="application/ld+json">${JSON.stringify(breadcrumb)}</script>`
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
  const others = (p.game_logs || []).filter((x) => x !== g && isHot(x)).slice(0, 6);
  const othersHtml = others.length
    ? `<section class="perf-sec"><h2 class="perf-sec-t">${esc(p.name)} 其他亮點</h2><nav class="perf-more-grid">${others.map((x) => `<a class="perf-mini" href="${BASE}performance/${p.slug}/${x.date}/"><span class="perf-mini-d">${esc(fmtDateZh(x.date))} ${esc(badgeText(x))}</span><span class="perf-mini-l">${esc(perfLineTxt(x))}</span></a>`).join("")}</nav></section>`
    : "";
  return (
    `<article class="pd">` +
    `<nav class="crumb" aria-label="breadcrumb"><a href="${BASE}">首頁</a><span class="crumb-sep">›</span><a href="${BASE}player/${p.slug}/">${esc(p.name)}</a><span class="crumb-sep">›</span><span class="crumb-cur">${esc(fmtDateZh(g.date))}表現</span></nav>` +
    `<div class="perf-hero level-${levelClassMjs(p.level)}"><div class="perf-hero-top"><span class="badge">${esc(badgeText(g))}</span><span class="perf-date">${esc(fmtDateZh(g.date))}（${esc(weekdayZh(g.date))}）</span></div>` +
    `<h1 class="perf-h1"><a class="perf-h1-link plink" href="${BASE}player/${p.slug}/">${esc(p.name)}</a><span class="perf-en"> ${esc(romanName(p))}</span></h1>` +
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
  return `<script type="application/ld+json">${JSON.stringify(schema)}</script>`;
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
    `<meta property="og:locale" content="zh_TW" />`,
    `<meta property="og:title" content="${esc(title)}" />`,
    `<meta property="og:description" content="${esc(description)}" />`,
    `<meta property="og:url" content="${canonical}" />`,
    `<meta property="og:site_name" content="旅外球員情報站" />`,
    `<meta property="og:image" content="${SITE}og.png" />`,
    `<meta property="og:image:width" content="1200" />`,
    `<meta property="og:image:height" content="630" />`,
    `<meta name="twitter:card" content="summary_large_image" />`,
    `<meta name="twitter:image" content="${SITE}og.png" />`,
    headExtra,
  ].join("\n    ");
  out = out.replace("</head>", `    ${meta}\n  </head>`);
  out = out.replace('<div id="root"></div>', `<div id="root">${bodyHtml}</div>`);
  return out;
}

// ---- 每位球員頁 ----
let count = 0;
for (const p of data.players) {
  const title = `${p.name} ${romanName(p)}｜${season} 球季數據・最近出賽｜旅外球員情報站`;
  const description = introText(p).slice(0, 150);
  const canonical = `${SITE}player/${p.slug}/`;
  const bodyHtml =
    `<article class="pd">` +
    `<nav class="crumb" aria-label="breadcrumb"><a href="${BASE}">首頁</a><span class="crumb-sep">›</span><span class="crumb-cur">${esc(p.name)}</span></nav>` +
    `<h1>${esc(p.name)} <span class="pd-en">${esc(romanName(p))}</span></h1>` +
    `<p class="pd-bio">${esc(bioLine(p))}</p>` +
    (p.heritage ? `<p class="pd-heritage">🇹🇼 台裔球員 · 具台灣血統</p>` : "") +
    `<p class="pd-intro">${esc(introText(p))}</p>` +
    (seasonSummary(p) ? `<p class="pd-summary"><b>戰績摘要</b>：${esc(seasonSummary(p))}</p>` : "") +
    `<h2>${season} 球季累積數據</h2>${seasonTable(p)}` +
    prevSeasonBlock(p) +
    recentGames(p) +
    relatedHtml(p) +
    faqHtml(p) +
    morePlayersHtml(p) +
    `</article>`;
  const html = renderPage(template, {
    title, description, canonical, bodyHtml: siteWrap(bodyHtml), headExtra: jsonLd(p) + faqJsonLd(p),
  });
  const dir = resolve(DIST, "player", p.slug);
  mkdirSync(dir, { recursive: true });
  writeFileSync(resolve(dir, "index.html"), html);
  count++;
}

// ---- 表現頁 /performance/{slug}/{date}/ 與 最新表現總覽 /latest/ ----
// 蒐集所有場次,取「最新場次日期往前 30 天」為視窗(控制頁數、保持新鮮)
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
  const headExtra = perfBreadcrumbLd(p, g) + (hot ? "" : `\n    <meta name="robots" content="noindex,follow" />`);
  const html = renderPage(template, { title, description, canonical, bodyHtml: siteWrap(perfBody(p, g)), headExtra });
  const dir = resolve(DIST, "performance", p.slug, g.date);
  mkdirSync(dir, { recursive: true });
  writeFileSync(resolve(dir, "index.html"), html);
  perfCount++;
  if (hot) perfSitemapUrls.push(canonical);
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
  headExtra: `<script type="application/ld+json">${JSON.stringify(latestLd)}</script>`,
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
const homeBody =
  `<div class="prerender-home">` +
  `<h1>旅外球員情報站｜台灣旅外棒球員</h1>` +
  `<p>每日追蹤旅美、旅日、旅韓共 ${data.players.length} 位台灣旅外棒球員的出賽表現與 ${season} 球季數據。</p>` +
  homeHlBlock +
  leagueBlock("mlb", "旅美（MLB / 小聯盟）") +
  leagueBlock("npb", "旅日（NPB）") +
  leagueBlock("kbo", "旅韓（KBO）") +
  `</div>`;
const homeDesc = `每日追蹤旅美、旅日、旅韓共 ${data.players.length} 位台灣旅外棒球員的出賽表現與 ${season} 球季數據。`;
// 首頁結構化資料:網站實體 + 發行組織(關聯 logo) + 球員名冊 ItemList
const homeSchemas = [
  { "@context": "https://schema.org", "@type": "WebSite", name: "旅外球員情報站", url: SITE, inLanguage: "zh-Hant" },
  {
    "@context": "https://schema.org",
    "@type": "Organization",
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
  .map((s) => `<script type="application/ld+json">${JSON.stringify(s)}</script>`)
  .join("\n    ");
const homeHtml = renderPage(template, {
  title: "旅外球員情報站｜台灣旅外棒球員即時數據",
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

// ---- sitemap.xml ----
const urls = [
  SITE,
  `${SITE}latest/`,
  ...data.players.map((p) => `${SITE}player/${p.slug}/`),
  ...perfSitemapUrls,
];
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
