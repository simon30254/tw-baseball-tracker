/**
 * 消息與近況的產生器 —— 全部由站上自己的資料算出來。
 * ==================================================
 * scripts/prerender.mjs(靜態頁)與 src/App.jsx(SPA)共用這一份。此檔是純 JS、
 * 不碰 DOM,所以 node 與 vite 都能直接 import。站上其他「兩份要同步」的邏輯
 * (romanName / seasonSummary / faq …)吃過不少苦頭,新的東西不要再複製一份。
 *
 * 設計原則:**站上寫的每一句話都要能追到自己的資料或官方紀錄。**
 *   - 出賽事實 → game_logs(MLB Stats API / npb.jp / KBO 官方)
 *   - 異動事實 → transactions.json(MLB 官方異動)、moves.json(本站依層級變化判定)
 *   - 兩者都推不出來的事(合約談判、亞運名單…)→ 只能標示是哪家媒體報的,
 *     照原標題呈現並註明出處,不改寫別人的內文。
 */

const num = (v) => (v == null || v === "" ? null : Number(v));

/** 查無中譯的隊名會留英文(team_zh.json 的原則),夾在中文裡要補空格。 */
export const padLatin = (s) =>
  String(s ?? "")
    .replace(/([\u4e00-\u9fff])([A-Za-z0-9])/g, "$1 $2")
    .replace(/([A-Za-z0-9])([\u4e00-\u9fff])/g, "$1 $2");

/** 投球局數 "6.1" → 出局數,用來累加多場。NPB/MLB 都是這種零頭記法。 */
export function ipToOuts(ip) {
  const s = String(ip ?? "");
  if (!s) return 0;
  const [w, f] = s.split(".");
  return (parseInt(w, 10) || 0) * 3 + (parseInt(f, 10) || 0);
}

export function outsToIp(outs) {
  return `${Math.floor(outs / 3)}.${outs % 3}`;
}

/** 單場一句話。投打欄位同名但意思相反,分開處理(so 對投手是奪三振、對野手是被三振)。 */
export function gameLine(g) {
  if (!g) return "";
  if (g.type === "pitching") {
    const parts = [`${g.ip} 局`, `${g.h ?? 0} 安`, `失 ${g.r ?? 0} 分`, `${g.so ?? 0}K`];
    if (g.bb) parts.push(`${g.bb}BB`);
    return parts.join("・");
  }
  const parts = [`${g.ab ?? 0} 打數 ${g.h ?? 0} 安`];
  if (g.hr) parts.push(`${g.hr} 轟`);
  if (g.rbi) parts.push(`${g.rbi} 打點`);
  if (g.r) parts.push(`得 ${g.r} 分`);
  if (g.bb) parts.push(`${g.bb} 保送`);
  if (g.sb) parts.push(`${g.sb} 盜`);
  return parts.join("・");
}

/** 這一場的標籤(勝投/開轟…)。沒有值得標的就回空字串,不硬給。 */
export function gameBadge(g) {
  if (!g) return "";
  if (g.type === "pitching") {
    if (g.win) return "勝投";
    if (g.save) return "救援成功";
    if (g.started && ipToOuts(g.ip) >= 18 && (g.er ?? g.r ?? 0) <= 3) return "優質先發";
    if (g.loss) return "敗投";
    return "";
  }
  if (g.hr >= 2) return `${g.hr} 轟`;
  if (g.hr === 1) return "開轟";
  if ((g.h ?? 0) >= 3) return `${g.h} 安打`;
  return "";
}

/** 我們自己寫的單場標題:「6 局 1 失分，奪本季第 11 勝」這種。 */
export function gameHeadline(p, g, seasonStats) {
  if (!g) return "";
  const wrap = padLatin;
  const who = p.name;
  const vs = g.opponent ? `對${g.opponent}` : "";
  if (g.type === "pitching") {
    const core = `${g.ip} 局失 ${g.r ?? 0} 分`;
    if (g.win) {
      const w = num((seasonStats || {}).w);
      return wrap(`${who} ${core}，${w ? `奪本季第 ${w} 勝` : "奪勝"}${vs ? `（${vs}）` : ""}`);
    }
    if (g.save) return wrap(`${who} 後援關門，收下本季救援成功${vs ? `（${vs}）` : ""}`);
    const badge = gameBadge(g);
    return wrap(`${who} ${core}、${g.so ?? 0} 次三振${badge ? `（${badge}）` : ""}${vs ? `（${vs}）` : ""}`);
  }
  if (g.hr) {
    const hr = num((seasonStats || {}).hr);
    return wrap(`${who} 開轟${g.hr > 1 ? `（${g.hr} 發）` : ""}${hr ? `，本季第 ${hr} 轟` : ""}${vs ? `（${vs}）` : ""}`);
  }
  return wrap(`${who} ${g.ab ?? 0} 打數 ${g.h ?? 0} 安${g.rbi ? `、${g.rbi} 打點` : ""}${vs ? `（${vs}）` : ""}`);
}

/** 出賽最多的那一層(球員可能同季跨層級)。 */
export function mainLevel(p) {
  const ss = p.season_stats || {};
  let best = null;
  for (const [lv, s] of Object.entries(ss)) {
    const g = num(s.g) || 0;
    if (!best || g > best.g) best = { lv, g, s };
  }
  return best;
}

/** 本季數據一行。 */
export function seasonLine(p) {
  const b = mainLevel(p);
  if (!b) return "";
  const s = b.s;
  if (p.role === "pitcher") {
    const bits = [`${b.lv} ${s.g} 場`];
    if (s.w != null || s.l != null) bits.push(`${s.w ?? 0} 勝 ${s.l ?? 0} 敗`);
    if (s.sv) bits.push(`${s.sv} 救援`);
    if (s.era) bits.push(`防禦率 ${s.era}`);
    if (s.whip) bits.push(`WHIP ${s.whip}`);
    return padLatin(bits.join("・"));
  }
  const bits = [`${b.lv} ${s.g} 場`];
  if (s.avg) bits.push(`打擊率 ${s.avg}`);
  if (s.hr != null) bits.push(`${s.hr} 轟`);
  if (s.rbi != null) bits.push(`${s.rbi} 打點`);
  if (s.ops) bits.push(`OPS ${s.ops}`);
  return bits.join("・");
}

/**
 * 近況一句話:拿最近 N 場自己累加,和球季平均比。
 * 只講數字算得出來的事,不做「狀況火燙」這種主觀評價。
 */
export function recentForm(p, n = 5) {
  const logs = (p.game_logs || []).slice(0, n);
  if (logs.length < 2) return "";
  const b = mainLevel(p);
  if (p.role === "pitcher") {
    const outs = logs.reduce((a, g) => a + ipToOuts(g.ip), 0);
    if (outs < 9) return "";
    const er = logs.reduce((a, g) => a + (num(g.er) ?? num(g.r) ?? 0), 0);
    const so = logs.reduce((a, g) => a + (num(g.so) || 0), 0);
    const era = ((er * 27) / outs).toFixed(2);
    const seasonEra = b && b.s.era ? Number(b.s.era) : null;
    const trend = seasonEra == null ? "" :
      Number(era) < seasonEra ? `，較球季的 ${b.s.era} 低` :
      Number(era) > seasonEra ? `，高於球季的 ${b.s.era}` : "";
    return padLatin(`近 ${logs.length} 場投 ${outsToIp(outs)} 局、防禦率 ${era}${trend}，共 ${so} 次三振。`);
  }
  const ab = logs.reduce((a, g) => a + (num(g.ab) || 0), 0);
  if (ab < 5) return "";
  const h = logs.reduce((a, g) => a + (num(g.h) || 0), 0);
  const hr = logs.reduce((a, g) => a + (num(g.hr) || 0), 0);
  const rbi = logs.reduce((a, g) => a + (num(g.rbi) || 0), 0);
  const avg = (h / ab).toFixed(3).replace(/^0/, "");
  const seasonAvg = b && b.s.avg ? Number(b.s.avg) : null;
  const trend = seasonAvg == null ? "" :
    h / ab > seasonAvg ? `，優於球季的 ${b.s.avg}` :
    h / ab < seasonAvg ? `，低於球季的 ${b.s.avg}` : "";
  const extra = [hr ? `${hr} 轟` : "", rbi ? `${rbi} 打點` : ""].filter(Boolean).join(" ");
  return padLatin(`近 ${logs.length} 場 ${ab} 打數 ${h} 安、打擊率 ${avg}${trend}${extra ? `，${extra}` : ""}。`);
}

// ---------------------------------------------------------------------------
// 消息彙整
// ---------------------------------------------------------------------------
/**
 * 把「官方異動 + 本站判定的升降 + 逐場資料 + 媒體報導」收斂成一天一組的消息。
 *
 * 核心規則:**同一位球員同一天,只要我們自己推得出事實,就由我們寫**,那天的媒體
 * 報導退成出處掛名(「聯合新聞網、ETtoday、自由體育等 5 家報導」)。費爾柴德遭
 * DFA 那天有五則媒體標題,收斂後是一則我們寫的事實 + 五個出處。
 * 只有兩邊都推不出來的事(合約談判、亞運名單、專訪),才照媒體原標題呈現並註明
 * 出處 —— 那是別人採訪來的,不改寫也不假裝是自己的。
 *
 * 旅美一律以 MLB 官方 transactions 為準,不用 moves.json(那是本站依層級變化推的,
 * 官方有紀錄就沒有理由用推定值);旅日/旅韓沒有等價官方來源,才用 moves.json。
 */
export function buildFeed({ players, transactions = [], moves = [], news = [], events = [], days = 30 }) {
  const byId = new Map(players.map((p) => [String(p.id), p]));
  const isUS = (p) => /^\d+$/.test(String(p.id));

  const allDates = [
    ...transactions.map((t) => t.date),
    ...moves.map((m) => m.date),
    ...news.map((n) => n.date),
    ...players.flatMap((p) => (p.game_logs || []).slice(0, 1).map((g) => g.date)),
  ].filter(Boolean).sort();
  if (!allDates.length) return [];
  const newest = allDates[allDates.length - 1];
  const shiftDay = (d, n) =>
    new Date(new Date(`${d}T00:00:00Z`).getTime() + n * 86400000).toISOString().slice(0, 10);
  const cutoff = shiftDay(newest, -days);

  const slots = new Map();   // `${id}|${date}` → entry
  const slot = (p, date) => {
    const k = `${p.id}|${date}`;
    if (!slots.has(k)) {
      slots.set(k, { player: p, date, facts: [], media: [], mentions: [], game: null });
    }
    return slots.get(k);
  };

  for (const t of transactions) {
    if (!t.big || t.date < cutoff) continue;
    const p = byId.get(String(t.id));
    if (!p) continue;
    slot(p, t.date).facts.push({ text: t.text || t.official, src: "MLB 官方異動紀錄" });
  }
  for (const m of moves) {
    if (m.date < cutoff) continue;
    const p = byId.get(String(m.id));
    if (!p || isUS(p)) continue;            // 旅美看官方,不用本站推定
    slot(p, m.date).facts.push({ text: m.text, src: "本站依出賽層級判定" });
  }
  for (const p of players) {
    for (const g of p.game_logs || []) {
      if (g.date < cutoff) continue;
      const s = slots.get(`${p.id}|${g.date}`);
      if (s) s.game = g;
    }
  }
  // 一則新聞常同時標到好幾位球員(「古林睿煬退賽，仍警戒王彥程、林昱珉」)。若每位
  // 都拿它當代表,同一則標題會在同一天出現三次。所以先指定一位「主角」——
  // 標題裡出現名字的第一位;標題沒點名就算了 —— 其餘球員只拿它當出處掛名。
  for (const n of news) {
    if (!n.date || n.date < cutoff) continue;
    const tagged = (n.players || []).map((x) => byId.get(String(x.id))).filter(Boolean);
    if (!tagged.length) continue;
    const at = (p) => {
      const i = (n.title || "").indexOf(p.name);
      return i < 0 ? Infinity : i;
    };
    const ranked = [...tagged].sort((a, b) => at(a) - at(b));
    const lead = at(ranked[0]) === Infinity ? tagged[0] : ranked[0];
    for (const p of tagged) {
      const s = slot(p, n.date);
      if (p === lead) s.media.push(n);
      else s.mentions.push(n);
      // 旅美的逐場紀錄用美國日期,台灣媒體隔天才報 —— 9/01 的比賽會配到 9/02 的
      // 報導。只比同一天的話,已經有逐場資料的出賽會被誤判成「我們寫不出來」,
      // 於是又去引用別人的標題。所以往前多看一天。
      const g = (p.game_logs || []).find((y) => y.date === n.date || y.date === shiftDay(n.date, -1));
      if (g) s.game = g;
    }
  }

  // 官方異動的日期與媒體報導的日期常差一天(MLB 記 9/08、台灣媒體 9/09 才報)。
  // 只比同一天的話,費爾柴德遭 DFA 會變成「我們寫的事實」加「隔天引用的標題」兩則。
  const factDays = new Set();
  for (const s of slots.values()) {
    if (!s.facts.length) continue;
    for (const off of [-1, 0, 1]) factDays.add(`${s.player.id}|${shiftDay(s.date, off)}`);
  }

  // 已經寫成事件摘要的球員/日期,不必再引用媒體標題 —— 事件本身就是整合後的版本。
  // 亞運名單那件事橫跨 9/05–9/08、牽涉 11 位球員,不蓋掉的話會冒出七八則引用。
  const eventDays = new Set();
  for (const ev of events) {
    for (const pid of ev.players || []) {
      for (let off = -3; off <= 3; off++) eventDays.add(`${pid}|${shiftDay(ev.date, off)}`);
    }
  }

  const out = [];
  for (const s of slots.values()) {
    const p = s.player;
    const ss = (mainLevel(p) || {}).s;
    const derived = s.facts.length > 0 || !!s.game || factDays.has(`${p.id}|${s.date}`);
    const sources = [...new Set([...s.media, ...s.mentions].map((n) => n.source).filter(Boolean))];
    // 事實已由鄰日那則寫過,這天就只剩出處掛名,不再重複開一則
    if (factDays.has(`${p.id}|${s.date}`) && !s.facts.length && !s.game && !sources.length) continue;

    // 推不出事實時(合約談判、亞運退賽、專訪這類),只能引用媒體。同一位球員同一天
    // 的十幾則幾乎都在講同一件事 —— 古林睿煬退出亞運那天有 12 則 —— 所以只留一則
    // 代表,其餘退成出處掛名。代表挑最短的標題:各家報同一件事時,最短的通常是
    // 事實句,最長的是加了驚嘆號的改寫。
    let quote = null;
    if (!derived && s.media.length && !eventDays.has(`${p.id}|${s.date}`)) {
      // 英文報導只當出處與事件摘要的素材,不會被拿來當條目標題 —— 整篇翻譯是改作,
      // 把英文標題直接丟到中文站上也沒有意義。要上站就得由人寫成中文事實摘要。
      const zh = s.media.filter((n) => n.lang !== "en");
      if (zh.length) quote = [...zh].sort((a, b) => (a.title || "").length - (b.title || "").length)[0];
    }
    if (!derived && !quote) continue;   // 只有英文來源時就落到這裡:等人寫成事件才上站

    out.push({
      date: s.date,
      player: p,
      // headline 是我們自己寫的;quote 是引用別人的,兩者在版面上要分得出來
      headline: s.facts.length
        ? `${p.name} ${s.facts[0].text}`
        : s.game ? gameHeadline(p, s.game, ss) : "",
      quote,
      facts: s.facts,
      game: s.game,
      gameLine: s.game ? gameLine(s.game) : "",
      badge: s.game ? gameBadge(s.game) : "",
      seasonLine: seasonLine(p),
      recentForm: recentForm(p),
      sources,
      others: quote ? Math.max(0, s.media.length + s.mentions.length - 1) : 0,
    });
  }

  // 事實由鄰日那則寫過、這天自己又沒有新東西可寫的,不該留一則只有出處的空殼。
  // 把它的出處併回真正寫了事實的那一則(媒體隔天才報是常態,出處仍應記上)。
  const keep = [];
  for (const e of out) {
    if (e.headline || e.quote) {
      keep.push(e);
      continue;
    }
    const host = out.find((x) => x !== e && x.player.id === e.player.id
      && x.facts.length && Math.abs(Date.parse(`${x.date}T00:00:00Z`) - Date.parse(`${e.date}T00:00:00Z`)) <= 86400000);
    if (host) host.sources = [...new Set([...host.sources, ...e.sources])];
  }
  out.length = 0;
  out.push(...keep);

  out.sort((a, b) => (a.date !== b.date ? (a.date < b.date ? 1 : -1)
    : (b.facts.length - a.facts.length) || a.player.name.localeCompare(b.player.name)));

  const groups = [];
  for (const e of out) {
    const last = groups[groups.length - 1];
    if (last && last.date === e.date) last.entries.push(e);
    else groups.push({ date: e.date, entries: [e] });
  }
  return groups;
}

/**
 * 各家報導頁用:把手上所有報導依「日期 → 主角球員」分群。
 * 與 buildFeed 的差別是這裡**不丟棄任何一則** —— /news/ 收斂成事實,這裡保留
 * 每一家的標題與連結,讓讀者想看原文時有地方找。
 */
export function groupMedia({ players, news = [], days = 45 }) {
  const byId = new Map(players.map((p) => [String(p.id), p]));
  const dates = news.map((n) => n.date).filter(Boolean).sort();
  if (!dates.length) return [];
  const shiftDay = (d, n) =>
    new Date(new Date(`${d}T00:00:00Z`).getTime() + n * 86400000).toISOString().slice(0, 10);
  const cutoff = shiftDay(dates[dates.length - 1], -days);

  const slots = new Map();
  for (const n of news) {
    if (!n.date || n.date < cutoff) continue;
    const tagged = (n.players || []).map((x) => byId.get(String(x.id))).filter(Boolean);
    if (!tagged.length) continue;
    // 主角:名字在標題裡出現最早的那位(外電比對英文名)
    const at = (p) => {
      const t = n.title || "";
      const i = t.indexOf(p.name);
      if (i >= 0) return i;
      const en = p.name_en || "";
      const j = /^[A-Za-z]/.test(en) ? t.toLowerCase().indexOf(en.toLowerCase()) : -1;
      return j >= 0 ? j : Infinity;
    };
    const ranked = [...tagged].sort((a, b) => at(a) - at(b));
    const lead = at(ranked[0]) === Infinity ? tagged[0] : ranked[0];
    const k = `${n.date}|${lead.id}`;
    if (!slots.has(k)) slots.set(k, { date: n.date, player: lead, items: [] });
    slots.get(k).items.push(n);
  }

  const days_ = new Map();
  for (const s of slots.values()) {
    s.items.sort((a, b) => (a.lang === b.lang ? 0 : a.lang === "en" ? 1 : -1));
    if (!days_.has(s.date)) days_.set(s.date, []);
    days_.get(s.date).push(s);
  }
  return [...days_.entries()]
    .sort((a, b) => (a[0] < b[0] ? 1 : -1))
    .map(([date, groups]) => ({
      date,
      groups: groups.sort((a, b) => b.items.length - a.items.length),
    }));
}
