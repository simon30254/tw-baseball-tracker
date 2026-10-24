/**
 * 每週戰報的資料層:把「這一週發生了什麼」固化成 public/data/weekly.json
 * ============================================================================
 * 為什麼要固化,而不是每次 build 從現有資料重算:
 *   news.json 只留 45 天(fetch_news.py 的 KEEP_DAYS)、逐場紀錄每人只留約 60 場。
 *   每週戰報若是獨立網址,那網址必須永久有效 —— 直接從活資料重算的話,三個月後
 *   同一個網址會算出空白頁。這個站已經因為 ~290 個「最新表現」頁變成 404 付過一次
 *   學費,不能再犯:所以每一週結束後就把那週的事實寫進 weekly.json,之後只讀檔。
 *
 * 內容邊界(與 /news/ 同一條線,不另開例外):
 *   ① 本站算得出來的事實 —— 出賽逐場、週累積數據、層級異動、MLB 官方異動
 *   ② 人工寫的事件摘要(scripts/events.json)
 *   ③ 以上都推不出來的,只記媒體標題 + 媒體名,不連出去、不抄內文、不自動生成摘要
 *   不做 AI 摘要:自動改寫別人的內文就是 Google 明講的 scaled content abuse。
 *
 * 執行:node scripts/build_weekly.mjs   (在抓資料之後、prerender 之前)
 *       node scripts/build_weekly.mjs --rebuild   (忽略防呆,全部重算)
 *
 * --rebuild 是給**資料修正**用的。平常的防呆會擋住「重算後內容反而變少」的結果
 * (那通常代表活資料已經滾掉,舊的封存比重算的完整),但資料本身出錯時 ——
 * 例如 2026-10-22 那四筆誤判的「升上一軍」—— 修正也會讓內容變少,就會被同一條
 * 防呆擋住。要推修正就帶這個旗標,不要去刪 weekly.json(那會連真正封存的舊週一起沒了)。
 */

import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { gameBadge, gameLine, ipToOuts, outsToIp } from "../src/lib/recap.js";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const rd = (p, fb = null) => {
  try { return JSON.parse(readFileSync(resolve(ROOT, p), "utf-8")); } catch { return fb; }
};

const data = rd("public/data/players.json", { players: [] });
const players = data.players || [];
const news = (rd("public/data/news.json", { items: [] }).items) || [];
const transactions = (rd("public/data/transactions.json", { items: [] }).items) || [];
const moves = rd("public/data/moves.json", []) || [];
const events = (rd("scripts/events.json", { events: [] }).events) || [];

const REBUILD = process.argv.includes("--rebuild");
const ARCHIVE = "public/data/weekly.json";
// 一週結束後再等幾天才封存:旅美的箱分、台灣媒體隔天才發的報導都要趕得上。
const SETTLE_DAYS = 3;

const TODAY = new Date().toISOString().slice(0, 10);
const shift = (d, n) =>
  new Date(new Date(`${d}T00:00:00Z`).getTime() + n * 86400000).toISOString().slice(0, 10);

// ISO 週(週一起算)。鍵用 2026-W43 這種格式 —— 跨年那週歸屬由 ISO 規則決定,
// 不會出現 2027-W01 與 2026-W53 同時存在的歧義。
function isoWeek(d) {
  const dt = new Date(`${d}T00:00:00Z`);
  const dow = (dt.getUTCDay() + 6) % 7;                 // 週一 = 0
  const thu = new Date(dt.getTime() + (3 - dow) * 86400000);
  const y = thu.getUTCFullYear();
  const jan1 = Date.UTC(y, 0, 1);
  const wk = 1 + Math.round((thu.getTime() - jan1) / 604800000);
  return {
    key: `${y}-W${String(wk).padStart(2, "0")}`,
    start: shift(d, -dow),
    end: shift(d, 6 - dow),
  };
}

// 逐場紀錄每人只保留最新 60 場(抓取端的上限),被截到的球員「早期出賽」整段不存在。
// 李灝宇的紀錄從 7/11 才開始、柯賓·卡洛爾 7/21 —— 那之前的週若照算,會寫出少算的
// 場數,而那是頁面上的事實陳述。所以算出一條邊界:在這之前開始的週標成 partial,
// 不渲染成頁面(資料仍留在檔案裡,日後要改決定看得到)。
const LOG_CAP = 60;
const capped = players.filter((p) => (p.game_logs || []).length >= LOG_CAP);
const COMPLETE_FROM = capped.length
  ? capped.map((p) => (p.game_logs || []).map((g) => g.date).sort()[0]).sort().pop()
  : "0000-00-00";

const bySlug = new Map(players.map((p) => [String(p.id), p]));
const who = (p) => ({ slug: p.slug, name: p.name, lg: p.league, role: p.role, team: p.team });

// ---- 把所有素材按週分桶 ----
const weeks = new Map();
const bucket = (date) => {
  const w = isoWeek(date);
  if (!weeks.has(w.key)) {
    weeks.set(w.key, {
      week: w.key, start: w.start, end: w.end,
      games: [], moves: [], events: [], quotes: [],
    });
  }
  return weeks.get(w.key);
};

// ① 出賽:這是戰報的主體,全部來自本站逐場資料
for (const p of players) {
  for (const g of p.game_logs || []) {
    if (!g.date) continue;
    bucket(g.date).games.push({
      d: g.date, ...who(p),
      lv: g.level, opp: g.opponent, home: !!g.is_home, post: !!g.post,
      line: gameLine(g), badge: gameBadge(g), raw: g,
    });
  }
}

// ② 異動:MLB 官方紀錄 + 本站依出賽層級判定的日職/韓職一二軍升降
for (const t of transactions) {
  if (!t.date || !t.big) continue;
  const p = bySlug.get(String(t.id));
  if (!p) continue;
  bucket(t.date).moves.push({ d: t.date, ...who(p), text: t.text || t.official, src: "MLB 官方異動紀錄" });
}
for (const m of moves) {
  if (!m.date) continue;
  const p = bySlug.get(String(m.id));
  if (!p || /^\d+$/.test(String(p.id))) continue;        // 旅美看官方,不用本站推定
  bucket(m.date).moves.push({ d: m.date, ...who(p), text: m.text, src: "本站依出賽層級判定" });
}

// ③ 人工寫的事件摘要
for (const ev of events) {
  if (!ev.date) continue;
  const ps = (ev.players || []).map((x) => bySlug.get(String(x))).filter(Boolean).map(who);
  bucket(ev.date).events.push({
    d: ev.date, id: ev.id, title: ev.title, kind: ev.kind || "",
    body: ev.body || [], players: ps,
    sources: [...new Set((ev.sources || []).map((s) => s.name).filter(Boolean))],
  });
}

// ④ 媒體報導:只留標題與媒體名。全站零外媒連結,這裡不開例外。
//    中文標題才留 —— 英文標題直接掛在中文站上沒有意義,要上站得由人寫成事件摘要。
for (const n of news) {
  if (!n.date || n.lang === "en" || !n.title) continue;
  const ps = (n.players || []).map((x) => bySlug.get(String(x.id))).filter(Boolean);
  if (!ps.length) continue;
  const at = (p) => { const i = n.title.indexOf(p.name); return i < 0 ? Infinity : i; };
  const lead = [...ps].sort((a, b) => at(a) - at(b))[0];
  bucket(n.date).quotes.push({ d: n.date, ...who(at(lead) === Infinity ? ps[0] : lead),
    title: n.title, source: n.source || "" });
}

// ---- 每週收斂成一份可直接渲染的快照 ----
const sum = (xs, f) => xs.reduce((a, x) => a + (Number(f(x)) || 0), 0);

// 一位球員一週的累積數據。只用逐場欄位加總,不碰 season_stats ——
// season_stats 是「到今天為止」,封存後會跟那一週對不起來。
function weekStat(role, gs) {
  if (role === "pitcher") {
    const outs = sum(gs, (g) => ipToOuts(g.raw.ip));
    const er = sum(gs, (g) => g.raw.er);
    const parts = [`${gs.length} 場`, `${outsToIp(outs)} 局`];
    const w = gs.filter((g) => g.raw.win).length, l = gs.filter((g) => g.raw.loss).length;
    const sv = gs.filter((g) => g.raw.save).length, hd = gs.filter((g) => g.raw.hold).length;
    if (w || l) parts.push(`${w}勝${l}敗`);
    if (sv) parts.push(`${sv} 救援`);
    if (hd) parts.push(`${hd} 中繼成功`);
    parts.push(`${sum(gs, (g) => g.raw.so)} 次三振`);
    if (outs > 0) parts.push(`防禦率 ${(er * 27 / outs).toFixed(2)}`);
    return parts.join("、");
  }
  const ab = sum(gs, (g) => g.raw.ab), h = sum(gs, (g) => g.raw.h);
  const parts = [`${gs.length} 場`, `${ab} 打數 ${h} 安打`];
  const hr = sum(gs, (g) => g.raw.hr), rbi = sum(gs, (g) => g.raw.rbi);
  if (hr) parts.push(`${hr} 轟`);
  if (rbi) parts.push(`${rbi} 分打點`);
  const sb = sum(gs, (g) => g.raw.sb);
  if (sb) parts.push(`${sb} 盜壘`);
  if (ab > 0) parts.push(`週打擊率 ${(h / ab).toFixed(3).replace(/^0/, "")}`);
  return parts.join("、");
}

function snapshot(w, old) {
  // 同一位球員那週的出賽收成一組,逐場按日期排
  const byP = new Map();
  for (const g of w.games) {
    if (!byP.has(g.slug)) byP.set(g.slug, []);
    byP.get(g.slug).push(g);
  }
  const lines = [...byP.entries()].map(([slug, gs]) => {
    gs.sort((a, b) => (a.d < b.d ? -1 : 1));
    const p = players.find((x) => x.slug === slug);
    return {
      ...who(p), lv: gs[gs.length - 1].lv,
      stat: weekStat(p.role, gs),
      games: gs.map((g) => ({ d: g.d, opp: g.opp, home: g.home, post: g.post, lv: g.lv,
        line: g.line, badge: g.badge })),
    };
  }).sort((a, b) => b.games.length - a.games.length || a.name.localeCompare(b.name, "zh-Hant"));

  // 媒體標題去重:同一位球員同一天的十幾則多半在講同一件事,只留最短的那則
  // (最短的通常是事實句,最長的是加了驚嘆號的改寫),其餘只記媒體名。
  const qk = new Map();
  for (const q of w.quotes) {
    const k = `${q.slug}|${q.d}`;
    const cur = qk.get(k);
    if (!cur) { qk.set(k, { ...q, sources: [q.source].filter(Boolean), others: 0 }); continue; }
    cur.others += 1;
    if (q.source && !cur.sources.includes(q.source)) cur.sources.push(q.source);
    if (q.title.length < cur.title.length) { cur.title = q.title; cur.source = q.source; }
  }
  // 已經寫成出賽或異動的球員/日期,不必再引用媒體標題 —— 本站的版本就是那天的事實
  const covered = new Set([...w.games.map((g) => `${g.slug}|${g.d}`),
    ...w.moves.flatMap((m) => [-1, 0, 1].map((o) => `${m.slug}|${shift(m.d, o)}`)),
    ...w.events.flatMap((e) => e.players.flatMap((p) => [-1, 0, 1].map((o) => `${p.slug}|${shift(e.d, o)}`)))]);
  const quotes = [...qk.values()].filter((q) => !covered.has(`${q.slug}|${q.d}`))
    .sort((a, b) => (a.d < b.d ? 1 : -1));

  const own = lines.length + w.moves.length + w.events.length;
  return {
    week: w.week, start: w.start, end: w.end,
    built: TODAY,
    frozen: w.end <= shift(TODAY, -SETTLE_DAYS),
    // 一旦某週被判定為「逐場紀錄完整」就永遠算完整 —— COMPLETE_FROM 會隨球季推進
    // 往前移(60 場上限不斷修掉更早的紀錄),若每次照算,今天出得了頁的週明年會被
    // 標成 partial、頁面跟著消失,已經發佈的獨立網址就變成 404。只能由 true → false
    // (資料補齊),不能反向。
    partial: old && old.partial === false ? false : w.start < COMPLETE_FROM,
    counts: {
      players: lines.length, games: w.games.length, moves: w.moves.length,
      events: w.events.length, quotes: quotes.length, own,
    },
    lines,
    moves: w.moves.sort((a, b) => (a.d < b.d ? 1 : -1)),
    events: w.events.sort((a, b) => (a.d < b.d ? 1 : -1)),
    quotes,
  };
}

// ---- 與既有封存合併:封存過的週一律不動 ----
const prev = rd(ARCHIVE, { weeks: [] });
const kept = new Map((prev.weeks || []).map((w) => [w.week, w]));
let froze = 0, fresh = 0, skipped = 0;
for (const w of weeks.values()) {
  const old = kept.get(w.week);
  if (old && old.frozen && !REBUILD) { skipped++; continue; }   // 已封存,活資料不再覆蓋
  const snap = snapshot(w, old);
  // 活資料已經滾掉的舊週:重算只會算出比封存更少的東西,寧可留舊的
  if (!REBUILD && old && !snap.frozen && snap.counts.own < old.counts.own) { skipped++; continue; }
  if (!REBUILD && old && snap.counts.own === 0 && old.counts.own > 0) { skipped++; continue; }
  kept.set(w.week, snap);
  if (snap.frozen) froze++; else fresh++;
}

const out = [...kept.values()].sort((a, b) => (a.week < b.week ? 1 : -1));
writeFileSync(resolve(ROOT, ARCHIVE),
  JSON.stringify({ updated_at: new Date().toISOString(), settle_days: SETTLE_DAYS,
    complete_from: COMPLETE_FROM, weeks: out }) + "\n");

const parts = out.filter((w) => w.partial).length;
console.log(`每週戰報資料:${out.length} 週(本次封存 ${froze}、更新進行中 ${fresh}、沿用既有 ${skipped})`);
console.log(`  逐場紀錄完整的起點 ${COMPLETE_FROM} —— 之前的 ${parts} 週標為 partial,不出頁`);
for (const w of out.slice(0, 4)) {
  console.log(`  ${w.week} ${w.start}~${w.end} ${w.frozen ? "已封存" : "進行中"}` +
    ` 出賽 ${w.counts.games} 場/${w.counts.players} 人、異動 ${w.counts.moves}、事件 ${w.counts.events}、引用 ${w.counts.quotes}`);
}
