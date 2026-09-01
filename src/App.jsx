import React, { useEffect, useMemo, useState, lazy, Suspense } from "react";

const MapView = lazy(() => import("./MapView.jsx"));

const LEVEL_LABEL = {
  MLB: "MLB", AAA: "3A", AA: "2A", "High-A": "高階1A", A: "1A", Rookie: "新人",
  一軍: "一軍", 二軍: "二軍",
};
const LEVEL_CLASS = {
  MLB: "MLB", AAA: "AAA", AA: "AA", "High-A": "HighA", A: "A", Rookie: "Rookie",
  一軍: "ichigun", 二軍: "nigun",
};
const LEAGUE_CHIPS = ["全部", "旅美", "旅日", "旅韓"];
const LEVEL_CHIPS_BY_LEAGUE = {
  旅美: ["全部", "MLB", "AAA", "AA", "A級以下"],
  旅日: ["全部", "一軍", "二軍"],
  旅韓: ["全部", "一軍", "二軍"],
};
const ROLE_CHIPS = ["全部", "投手", "野手"];

const LEAGUE_OF = { npb: "旅日", kbo: "旅韓" };
const playerLeague = (p) => LEAGUE_OF[p.league] || "旅美";
const levelClass = (level) => LEVEL_CLASS[level] || "other";

// 全站統一層級排序:大聯盟 > 日職一軍 > 韓職一軍 > 3A > 2A > 日/韓二軍 > 高階1A > 1A > 新人聯盟
function rankLevel(leagueZh, level) {
  if (level === "MLB") return 0;
  if (level === "一軍") return leagueZh === "旅日" ? 1 : 2;
  if (level === "AAA") return 3;
  if (level === "AA") return 4;
  if (level === "二軍") return 5;
  if (level === "High-A") return 6;
  if (level === "A") return 7;
  if (level === "Rookie") return 8;
  return 9;
}
const levelRank = (p) => rankLevel(playerLeague(p), p.level);

// 層級分組(下拉選單用):區分日/韓一軍、二軍
const LEVEL_TIERS = [
  { key: "MLB", label: "大聯盟" },
  { key: "npb1", label: "日職一軍" },
  { key: "kbo1", label: "韓職一軍" },
  { key: "AAA", label: "3A" },
  { key: "AA", label: "2A" },
  { key: "npb2", label: "日職二軍" },
  { key: "kbo2", label: "韓職二軍" },
  { key: "High-A", label: "高階1A" },
  { key: "A", label: "1A" },
  { key: "Rookie", label: "新人聯盟" },
];
function tierKey(p) {
  const lv = p.level;
  if (lv === "一軍") return playerLeague(p) === "旅日" ? "npb1" : "kbo1";
  if (lv === "二軍") return playerLeague(p) === "旅日" ? "npb2" : "kbo2";
  return lv;
}

function gapDays(player, latestISO) {
  const logs = player.game_logs;
  if (!logs || !logs.length || !latestISO) return Infinity;
  return Math.round(
    (new Date(latestISO + "T00:00:00") - new Date(logs[0].date + "T00:00:00")) / 86400000
  );
}

function fmtDate(iso) {
  const [y, m, d] = iso.split("-");
  return `${Number(m)}月${Number(d)}日`;
}

function weekday(iso) {
  return "週" + "日一二三四五六"[new Date(iso + "T00:00:00").getDay()];
}

function pitchLine(g) {
  const parts = [`${g.ip}局`, `${g.h}安`, `失${g.r}分`, `${g.so}K`];
  if (g.bb > 0) parts.push(`${g.bb}BB`);
  if (g.hr > 0) parts.push(`被${g.hr}轟`);
  return parts.join("　");
}

function hitLine(g) {
  const parts = [`${g.ab}打數${g.h}安`];
  if (g.hr > 0) parts.push(`${g.hr}轟`);
  if (g.rbi > 0) parts.push(`${g.rbi}打點`);
  if (g.r > 0) parts.push(`得${g.r}分`);
  if (g.bb > 0) parts.push(`${g.bb}保送`);
  if (g.sb > 0) parts.push(`${g.sb}盜`);
  return parts.join("　");
}

function decisionBadge(g) {
  if (g.type === "pitching") {
    if (g.win) return { text: "勝投", cls: "badge-win" };
    if (g.save) return { text: "救援", cls: "badge-win" };
    if (g.loss) return { text: "敗投", cls: "badge-loss" };
    return g.started ? { text: "先發", cls: "badge-start" } : { text: "後援", cls: "badge-relief" };
  }
  if (g.hr > 0) return { text: "開轟", cls: "badge-win" };
  return { text: "出賽", cls: "badge-relief" };
}

// 今日亮點:好表現才回 true(用於卡片高亮)
function isHot(g) {
  if (!g) return false;
  if (g.type === "pitching") {
    if (g.win || g.save) return true;
    if (g.started && parseFloat(g.ip) >= 6 && g.er <= 2) return true; // 優質先發
    return g.so >= 7;
  }
  return g.hr > 0 || g.h >= 2 || g.rbi >= 2;
}

function matchLevel(chip, level) {
  if (chip === "全部") return true;
  if (chip === "A級以下") return ["High-A", "A", "Rookie"].includes(level);
  return level === chip;
}

function Sparkline({ player }) {
  const games = (player.game_logs || []).slice(0, 10).reverse(); // 舊→新
  if (games.length < 2) return null;
  const isP = player.role === "pitcher";
  const bars = games.map((g) => {
    if (isP) {
      const er = g.er ?? g.r;
      if (g.win || g.save || (g.started && parseFloat(g.ip) >= 6 && er <= 2)) return { cls: "spk-good", h: 100 };
      if (g.loss || er >= 4) return { cls: "spk-bad", h: 45 };
      return { cls: "spk-mid", h: 70 };
    }
    if (g.hr > 0) return { cls: "spk-good", h: 100 };
    if (g.h >= 2) return { cls: "spk-good", h: 82 };
    if (g.h === 1) return { cls: "spk-mid", h: 58 };
    return { cls: "spk-bad", h: 32 };
  });
  return (
    <div className="spark">
      <span className="spark-label">近況（舊→新）</span>
      <div className="spark-bars">
        {bars.map((b, i) => (
          <span key={i} className={`spk ${b.cls}`} style={{ height: `${b.h}%` }} />
        ))}
      </div>
    </div>
  );
}

function Bio({ player }) {
  const b = player.bio || {};
  const parts = [];
  if (b.age) parts.push(`${b.age}歲`);
  if (b.pos_zh) parts.push(b.pos_zh);
  if (b.throws && b.bats) parts.push(`${b.throws}投${b.bats}打`);
  else if (b.bats) parts.push(`${b.bats}打`);
  if (b.ht && b.wt) parts.push(`${b.ht}cm / ${b.wt}kg`);
  if (!parts.length && !b.velo && !b.debut) return null;
  return (
    <div className="bio">
      {parts.length > 0 && <p className="bio-line">{parts.join("・")}</p>}
      {b.velo && (
        <p className="bio-velo">
          最快球速 <b>{b.velo}</b>
        </p>
      )}
      {b.debut && (
        <p className="bio-milestone">
          🎖 大聯盟初登場 <b>{b.debut.replaceAll("-", "/")}</b>
        </p>
      )}
    </div>
  );
}

function StatTableJsx({ levels, isP }) {
  return (
    <div className="table-scroll">
      <table className="stat-table">
        <thead>
          <tr>
            <th>層級</th>
            {isP ? (
              <><th>出賽</th><th>勝敗</th><th>救援</th><th>局數</th><th>被安</th><th>保送</th><th>K</th><th>ERA</th><th>WHIP</th></>
            ) : (
              <><th>出賽</th><th>打數</th><th>安打</th><th>轟</th><th>打點</th><th>得分</th><th>盜</th><th>保送</th><th>K</th><th>打率</th><th>OPS</th></>
            )}
          </tr>
        </thead>
        <tbody>
          {levels.map(([lv, s]) => (
            <tr key={lv}>
              <td>{LEVEL_LABEL[lv] || lv}</td>
              {isP ? (
                <><td>{s.g}</td><td>{s.w}-{s.l}</td><td>{s.sv}</td><td>{s.ip}</td><td>{s.h ?? "—"}</td><td>{s.bb}</td><td>{s.so}</td><td>{s.era}</td><td>{s.whip}</td></>
              ) : (
                <><td>{s.g}</td><td>{s.ab}</td><td>{s.h}</td><td>{s.hr}</td><td>{s.rbi}</td><td>{s.r ?? "—"}</td><td>{s.sb}</td><td>{s.bb ?? "—"}</td><td>{s.so ?? "—"}</td><td>{s.avg}</td><td>{s.ops}</td></>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SeasonTable({ player }) {
  const levels = Object.entries(player.season_stats || {});
  if (!levels.length) return <p className="empty-note">本季尚無累積數據</p>;
  const isP = player.role === "pitcher";
  const prevYear = player.prev_season ? Object.keys(player.prev_season)[0] : null;
  const prevLevels = prevYear ? Object.entries(player.prev_season[prevYear] || {}) : [];
  return (
    <>
      <StatTableJsx levels={levels} isP={isP} />
      {prevLevels.length > 0 && (
        <div className="prev-season">
          <p className="prev-season-t">{prevYear} 賽季累積</p>
          <StatTableJsx levels={prevLevels} isP={isP} />
        </div>
      )}
    </>
  );
}

function RecentGames({ player }) {
  const games = (player.game_logs || []).slice(0, 10);
  if (!games.length) return null;
  const isP = player.role === "pitcher";
  const head = isP
    ? ["日期", "對手", "局", "安", "失", "K", "BB", "HR"]
    : ["日期", "對手", "打數", "安", "轟", "打點", "得", "盜", "BB"];
  return (
    <div className="recent">
      <p className="recent-title">最近出賽</p>
      <div className="table-scroll">
        <table className="stat-table rc-table">
          <thead>
            <tr>{head.map((h) => <th key={h}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {games.map((g, i) => {
              const date = g.date.slice(5).replace("-", "/");
              const opp = (g.level ? `[${LEVEL_LABEL[g.level] || g.level}] ` : "") + (g.opponent || "");
              const cells = isP
                ? [date, opp, g.ip, g.h, g.r, g.so, g.bb, g.hr]
                : [date, opp, g.ab, g.h, g.hr, g.rbi, g.r, g.sb, g.bb];
              return (
                <tr key={i}>
                  {cells.map((c, j) => (
                    <td key={j} className={j === 1 ? "rc-opp" : undefined}>{c}</td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// 可點擊的球員名 → 球員個人頁(stopPropagation 以免觸發外層卡片/展開)
function PlayerLink({ slug, name, onView, className = "", children }) {
  if (!slug) return <span className={className}>{children || name}</span>;
  return (
    <a
      className={`plink ${className}`}
      href={`${import.meta.env.BASE_URL}player/${slug}/`}
      onClick={(e) => { e.preventDefault(); e.stopPropagation(); onView(slug); }}
    >
      {children || name}
    </a>
  );
}

function PlayerCard({ player, game, latestDate, fav, onFav, onView }) {
  const go = () => player.slug && onView(player.slug);
  const played = Boolean(game);
  const hot = played && isHot(game);
  const injured = player.status === "傷兵";
  const cold = !injured && !played && gapDays(player, latestDate) > 21;
  const badge = injured
    ? { text: player.status_note || "傷兵", cls: "badge-il" }
    : played
    ? decisionBadge(game)
    : cold
    ? { text: "長期未出賽", cls: "badge-cold" }
    : { text: "未出賽", cls: "badge-idle" };
  return (
    <div
      className={`card clickable-card level-${levelClass(player.level)} ${played ? "" : "card-idle"} ${injured ? "card-il" : ""} ${hot ? "card-hot" : ""} ${fav ? "card-fav" : ""}`}
      role="link"
      tabIndex={0}
      onClick={go}
      onKeyDown={(e) => { if (e.key === "Enter") go(); }}
    >
      <div className="card-top">
        <div className="card-head">
          <div className="card-id">
            <span className="card-name">{player.name}</span>
            {injured && <span className="il-dot" title="傷兵名單">🏥</span>}
            <span className="card-meta">
              {[LEVEL_LABEL[player.level] || player.level, player.org, player.position]
                .filter(Boolean)
                .join("・")}
            </span>
            {player.heritage && <span className="heritage-chip">🇹🇼 台裔</span>}
            {player.accolades?.badge && <span className="acc-chip">⭐ {player.accolades.badge}</span>}
          </div>
        </div>
        <div className="card-right">
          <button
            className={`fav-btn ${fav ? "fav-on" : ""}`}
            onClick={(e) => { e.stopPropagation(); onFav(); }}
            aria-label={fav ? "取消最愛" : "加入最愛"}
            title={fav ? "取消最愛" : "加入最愛"}
          >
            {fav ? "★" : "☆"}
          </button>
          <span className={`badge ${badge.cls}`}>{badge.text}</span>
        </div>
      </div>
      {player.slug && <span className="card-permalink">個人頁 →</span>}
      {player.next_start && (
        <p className="card-next">
          ⚾ {twTime(player.next_start.game_time)} 先發 {player.next_start.home ? "vs" : "@"} {player.next_start.opp}
        </p>
      )}
      {played && (
        <p className="card-line mono">
          {hot && <span className="hot-mark">🔥</span>}
          {game.type === "pitching" ? pitchLine(game) : hitLine(game)}
        </p>
      )}
    </div>
  );
}

// ---- 數據榜(累積數據) ----
const PITCH_COLS = [
  { key: "g", label: "出賽" },
  { key: "wl", label: "勝敗", nosort: true },
  { key: "ip", label: "局數" },
  { key: "era", label: "ERA", asc: true },
  { key: "so", label: "K" },
  { key: "bb", label: "保送" },
  { key: "whip", label: "WHIP", asc: true },
];
const BAT_COLS = [
  { key: "g", label: "出賽" },
  { key: "ab", label: "打數" },
  { key: "h", label: "安打" },
  { key: "hr", label: "HR" },
  { key: "rbi", label: "打點" },
  { key: "r", label: "得分" },
  { key: "bb", label: "保送" },
  { key: "so", label: "K" },
  { key: "avg", label: "打率" },
  { key: "ops", label: "OPS" },
];
const PITCH_ADV_COLS = [
  { key: "ip", label: "局數" },
  { key: "k9", label: "K/9" },
  { key: "bb9", label: "BB/9" },
  { key: "kbb", label: "K/BB" },
  { key: "h9", label: "H/9" },
  { key: "hr9", label: "HR/9", asc: true },
  { key: "whipA", label: "WHIP", asc: true },
  { key: "fip", label: "FIP", asc: true },
];
const BAT_ADV_COLS = [
  { key: "ab", label: "打數" },
  { key: "slg", label: "SLG" },
  { key: "iso", label: "ISO" },
  { key: "babip", label: "BABIP" },
  { key: "kpct", label: "K%", asc: true },
  { key: "bbpct", label: "BB%" },
  { key: "ops", label: "OPS" },
];

const toNum = (v) => {
  const n = parseFloat(v);
  return Number.isFinite(n) ? n : -Infinity;
};

// 進階數據計算
const ipToFloat = (ip) => {
  const [w, f] = String(ip).split(".");
  return (parseInt(w) || 0) + (f ? parseInt(f) / 3 : 0);
};
const f1 = (n) => (Number.isFinite(n) ? n.toFixed(1) : undefined);
const f2 = (n) => (Number.isFinite(n) ? n.toFixed(2) : undefined);
const f3 = (n) => (Number.isFinite(n) ? n.toFixed(3).replace(/^0\./, ".") : undefined);

function advPitch(s) {
  const ip = ipToFloat(s.ip);
  const p9 = (v) => (ip > 0 ? (v / ip) * 9 : NaN);
  const hr = s.hr || 0;
  return {
    k9: f1(p9(s.so)),
    bb9: f1(p9(s.bb)),
    kbb: s.bb > 0 ? f1(s.so / s.bb) : s.so > 0 ? "∞" : undefined,
    h9: f1(p9(s.h)),
    hr9: f2(p9(hr)),
    whipA: ip > 0 ? f2((s.h + s.bb) / ip) : s.whip || undefined,
    kpct: s.tbf > 0 ? f1((s.so / s.tbf) * 100) : undefined,
    bbpct: s.tbf > 0 ? f1((s.bb / s.tbf) * 100) : undefined,
    fip: ip > 0 ? f2((13 * hr + 3 * s.bb - 2 * s.so) / ip + 3.1) : undefined,
  };
}
function advBat(s) {
  const ops = parseFloat(s.ops);
  const obp = parseFloat(s.obp);
  const avg = parseFloat(s.avg);
  const slg = Number.isFinite(parseFloat(s.slg))
    ? parseFloat(s.slg)
    : Number.isFinite(ops) && Number.isFinite(obp)
    ? ops - obp
    : NaN;
  const iso = Number.isFinite(slg) && Number.isFinite(avg) ? slg - avg : NaN;
  const bDen = s.ab - s.so - s.hr;
  const babip = bDen > 0 ? (s.h - s.hr) / bDen : NaN;
  return {
    slg: f3(slg),
    iso: f3(iso),
    babip: f3(babip),
    kpct: s.pa > 0 ? f1((s.so / s.pa) * 100) : undefined,
    bbpct: s.pa > 0 ? f1((s.bb / s.pa) * 100) : undefined,
  };
}

// 層級高低排序:數字越小層級越高(大聯盟 > 3A > 2A > 高階1A > 1A > 新人;一軍 > 二軍)
const LEVEL_COL = { key: "level", asc: true };

// 選出要顯示的層級:指定層級→該層;A級以下/全部→出賽最多的層
function pickLevel(player, levelChip) {
  const ss = player.season_stats || {};
  const keys = Object.keys(ss);
  if (!keys.length) return null;
  const mostGames = (cands) =>
    cands.reduce((a, b) => ((ss[b].g || 0) > (ss[a].g || 0) ? b : a));
  if (levelChip === "全部") return { level: mostGames(keys), s: ss[mostGames(keys)] };
  if (levelChip === "A級以下") {
    const c = ["High-A", "A", "Rookie"].filter((k) => ss[k]);
    return c.length ? { level: mostGames(c), s: ss[mostGames(c)] } : null;
  }
  return ss[levelChip] ? { level: levelChip, s: ss[levelChip] } : null;
}

function LeaderTable({ title, cols, rows, volumeKey, initialSort, onView }) {
  const [sort, setSort] = useState(initialSort);
  const onSort = (c) => {
    if (c.nosort) return;
    setSort((s) =>
      s.key === c.key
        ? { key: c.key, dir: s.dir === "desc" ? "asc" : "desc" }
        : { key: c.key, dir: c.asc ? "asc" : "desc" }
    );
  };
  const arrow = (key) => (sort.key === key ? (sort.dir === "asc" ? " ↑" : " ↓") : "");
  const sorted = [...rows].sort((a, b) => {
    if (sort.key === "level") {
      const ra = rankLevel(playerLeague(a.p), a.sl.level);
      const rb = rankLevel(playerLeague(b.p), b.sl.level);
      if (ra !== rb) return sort.dir === "asc" ? ra - rb : rb - ra;
      return toNum(b.sl.s[volumeKey]) - toNum(a.sl.s[volumeKey]); // 同層級以出賽量排
    }
    const va = toNum(a.sl.s[sort.key]);
    const vb = toNum(b.sl.s[sort.key]);
    if (va === vb) return toNum(b.sl.s[volumeKey]) - toNum(a.sl.s[volumeKey]);
    return sort.dir === "asc" ? va - vb : vb - va;
  });
  return (
    <div className="board">
      <p className="board-title">{title}</p>
      <div className="table-scroll">
        <table className="stat-table board-table">
          <thead>
            <tr>
              <th className="col-name">球員</th>
              <th
                className={`th-click ${sort.key === "level" ? "th-sort" : ""}`}
                onClick={() => onSort(LEVEL_COL)}
              >
                層級{arrow("level")}
              </th>
              {cols.map((c) => (
                <th
                  key={c.key}
                  onClick={() => onSort(c)}
                  className={`${c.nosort ? "" : "th-click"} ${sort.key === c.key ? "th-sort" : ""}`}
                >
                  {c.label}
                  {arrow(c.key)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map(({ p, sl }) => (
              <tr key={p.id}>
                <td className="col-name">
                  <PlayerLink slug={p.slug} name={p.name} onView={onView} />
                  {p.status === "傷兵" && <span className="il-dot">🏥</span>}
                </td>
                <td>{LEVEL_LABEL[sl.level] || sl.level}</td>
                {cols.map((c) => (
                  <td key={c.key}>{c.key === "wl" ? `${sl.s.w}-${sl.s.l}` : sl.s[c.key] ?? "—"}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const STAT_MODES = ["基本", "進階"];

function StatsBoard({ players, leagueChip, levelChip, roleChip, season, onView }) {
  const [statMode, setStatMode] = useState("基本");
  const adv = statMode === "進階";
  const withStats = players
    .filter((p) => leagueChip === "全部" || playerLeague(p) === leagueChip)
    .map((p) => {
      const sl = pickLevel(p, levelChip);
      if (sl) {
        const extra = adv ? (p.role === "pitcher" ? advPitch(sl.s) : advBat(sl.s)) : {};
        return { p, sl: { level: sl.level, s: { ...sl.s, ...extra } } };
      }
      return { p, sl };
    })
    .filter((x) => x.sl);
  const pitchers = withStats.filter((x) => x.p.role === "pitcher");
  const batters = withStats.filter((x) => x.p.role === "batter");
  const showP = roleChip !== "野手";
  const showB = roleChip !== "投手";
  const empty = (!showP || !pitchers.length) && (!showB || !batters.length);
  // 旅美(多層級)預設依層級排:大聯盟 > 3A > 2A …;其他聯盟預設依出賽量排
  const initSort = (vol) =>
    leagueChip === "旅美" ? { key: "level", dir: "asc" } : { key: vol, dir: "desc" };
  const boardKey = `${leagueChip}-${levelChip}-${statMode}`;
  return (
    <section className="boards">
      <div className="board-head">
        <p className="board-season">{season} 球季累積・截至今日</p>
        <div className="statmode">
          {STAT_MODES.map((m) => (
            <button
              key={m}
              className={`statmode-btn ${statMode === m ? "statmode-on" : ""}`}
              onClick={() => setStatMode(m)}
            >
              {m}
            </button>
          ))}
        </div>
      </div>
      {showP && pitchers.length > 0 && (
        <LeaderTable
          key={`p-${boardKey}`}
          title="投手榜"
          cols={adv ? PITCH_ADV_COLS : PITCH_COLS}
          rows={pitchers}
          volumeKey="ip"
          initialSort={initSort("ip")}
          onView={onView}
        />
      )}
      {showB && batters.length > 0 && (
        <LeaderTable
          key={`b-${boardKey}`}
          title="野手榜"
          cols={adv ? BAT_ADV_COLS : BAT_COLS}
          rows={batters}
          volumeKey="ab"
          initialSort={initSort("ab")}
          onView={onView}
        />
      )}
      {adv && <p className="board-note">FIP 用固定常數 3.10 近似;KBO 打者數為估算。wOBA/wRC+/Statcast 因缺乏各聯盟統一基準,暫不提供。</p>}
      {empty && <p className="empty-note">沒有符合篩選條件的累積數據</p>}
    </section>
  );
}

function twTime(iso) {
  try {
    return new Intl.DateTimeFormat("zh-TW", {
      timeZone: "Asia/Taipei", month: "numeric", day: "numeric",
      hour: "2-digit", minute: "2-digit", hour12: false,
    }).format(new Date(iso));
  } catch {
    return "";
  }
}

function StartsPreview({ players, leagueChip, onView }) {
  const list = players
    .filter((p) => p.next_start && (leagueChip === "全部" || playerLeague(p) === leagueChip))
    .sort((a, b) => (a.next_start.game_time < b.next_start.game_time ? -1 : 1));
  if (!list.length) return null;
  return (
    <div className="starts">
      <p className="starts-title">⚾ 先發預告（台灣時間）</p>
      {list.map((p) => (
        <div className="start-row" key={p.id}>
          <span className="start-time">{twTime(p.next_start.game_time)}</span>
          <PlayerLink slug={p.slug} name={p.name} onView={onView} className="start-name" />
          <span className="start-vs">
            {p.next_start.home ? "vs" : "@"} {p.next_start.opp}
          </span>
        </div>
      ))}
    </div>
  );
}

const MOVE_ICON = { promote: "↑", demote: "↓", il: "🏥", return: "↩" };
function moveLeague(lg) {
  return lg === "npb" ? "旅日" : lg === "kbo" ? "旅韓" : "旅美";
}

function MovesFeed({ moves, leagueChip, slugById, onView }) {
  const list = (moves || []).filter((m) => leagueChip === "全部" || moveLeague(m.league) === leagueChip);
  if (!list.length) return null;
  return (
    <div className="moves">
      <p className="moves-title">近期異動</p>
      {list.slice(0, 8).map((m, i) => (
        <div className="move-row" key={i}>
          <span className="move-date">{m.date.slice(5).replace("-", "/")}</span>
          <span className={`move-tag move-${m.type}`}>{MOVE_ICON[m.type] || "・"}</span>
          <PlayerLink slug={slugById && slugById[m.id]} name={m.name} onView={onView} className="move-name" />
          <span className="move-text">{m.text}</span>
        </div>
      ))}
    </div>
  );
}

// 英文/羅馬名:旅美 name_en 本就是英文;旅日/旅韓為中文,改用 slug 還原(與 prerender.mjs 一致)
function romanName(p) {
  if (/[a-z]/i.test(p.name_en || "")) return p.name_en;
  return (p.slug || "")
    .split("-")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

// 球員相關內容(報導 + 延伸問答);球員頁用
function RelatedContent({ player }) {
  const c = player.content || {};
  const articles = c.articles || [];
  const qa = c.qa || [];
  if (!articles.length && !qa.length) return null;
  return (
    <section className="related">
      {articles.length > 0 && (
        <div className="related-block">
          <h2 className="related-title">📰 相關報導</h2>
          <ul className="related-list">
            {articles.map((a, i) => (
              <li key={i}>
                <a href={a.url} target="_blank" rel="noopener noreferrer">{a.title}</a>
                {a.date && <span className="related-date">{a.date.slice(5).replace("-", "/")}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
      {qa.length > 0 && (
        <div className="related-block">
          <h2 className="related-title">❓ 延伸問答</h2>
          <ul className="related-list">
            {qa.map((q, i) => (
              <li key={i}>
                <a href={q.url} target="_blank" rel="noopener noreferrer">{q.q}</a>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

// 首頁側欄:跨球員彙整最新報導
function NewsRail({ players, leagueChip, onView }) {
  const items = [];
  players
    .filter((p) => leagueChip === "全部" || playerLeague(p) === leagueChip)
    .forEach((p) =>
      (p.content?.articles || []).forEach((a) => items.push({ ...a, name: p.name, slug: p.slug }))
    );
  items.sort((a, b) => ((a.date || "") < (b.date || "") ? 1 : -1));
  if (!items.length) return null;
  return (
    <div className="newsrail">
      <p className="rail-title">📰 最新報導</p>
      {items.slice(0, 6).map((a, i) => (
        <a className="news-item" href={a.url} target="_blank" rel="noopener noreferrer" key={i}>
          <span className="news-t">{a.title}</span>
          <span className="news-m">
            {a.name}
            {a.date && `・${a.date.slice(5).replace("-", "/")}`}
          </span>
        </a>
      ))}
    </div>
  );
}

// 從網址判斷是否為球員個人頁:/player/{slug}/(含 GitHub Pages 子路徑 base)
function slugFromPath() {
  const m = window.location.pathname.match(/\/player\/([^/]+)\/?$/);
  return m ? decodeURIComponent(m[1]) : null;
}

// 出賽最多的主層 → 當季戰績摘要 / FAQ(與 prerender.mjs 同邏輯,須同步)
function mainLevelOf(p) {
  const ss = p.season_stats || {};
  const keys = Object.keys(ss);
  if (!keys.length) return null;
  const lv = keys.reduce((a, b) => ((ss[b].g || 0) > (ss[a].g || 0) ? b : a));
  return { level: lv, s: ss[lv] };
}
function seasonSummaryText(p, season) {
  const ml = mainLevelOf(p);
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
function faqFor(p, season) {
  const items = [];
  const sum = seasonSummaryText(p, season);
  if (sum) items.push({ q: `${p.name} ${season} 球季成績如何?`, a: sum });
  items.push({
    q: `${p.name} 目前效力哪一隊?`,
    a: `${p.name} 目前效力於 ${p.org}（${playerLeague(p)}${LEVEL_LABEL[p.level] || p.level}）。`,
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
function newestArticle(player) {
  const arts = (player.content && player.content.articles) || [];
  if (!arts.length) return null;
  return arts.slice().sort((a, b) => (b.date || "").localeCompare(a.date || ""))[0];
}
const TCT_HUB = {
  旅美: { url: "https://clutchgtime.com/taiwan-mlb-players/", title: "台灣旅美球員全整理" },
  旅日: { url: "https://clutchgtime.com/npb-taiwan-players/", title: "台灣旅日球員全整理" },
  旅韓: { url: "https://clutchgtime.com/kbo-to-mlb-stars/", title: "韓職 KBO 焦點" },
};
function FAQ({ player, season }) {
  const items = faqFor(player, season);
  if (!items.length) return null;
  const na = newestArticle(player);
  const a = na ? { url: na.url, title: na.title } : TCT_HUB[playerLeague(player)];
  return (
    <section className="faq">
      <h2 className="faq-title">常見問題</h2>
      {items.map((it, i) => (
        <div className="faq-item" key={i}>
          <h3 className="faq-q">{it.q}</h3>
          <p className="faq-a">{it.a}</p>
        </div>
      ))}
      {a && (
        <p className="faq-more">
          延伸閱讀:
          <a href={a.url} target="_blank" rel="noopener noreferrer">
            The Clutch Time —《{a.title}》
          </a>
        </p>
      )}
    </section>
  );
}

// 同聯盟其他球員(內鏈,與 prerender.mjs 同邏輯)
function relatedPlayers(p, all, n = 6) {
  const lg = playerLeague(p);
  const group = all
    .filter((x) => x.slug && playerLeague(x) === lg)
    .sort((a, b) => levelRank(a) - levelRank(b) || a.slug.localeCompare(b.slug));
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
      .filter((x) => x.slug && x.id !== p.id && !picked.includes(x) && playerLeague(x) !== lg)
      .sort((a, b) => levelRank(a) - levelRank(b));
    picked = picked.concat(extra.slice(0, n - picked.length));
  }
  return picked;
}
function MorePlayers({ player, players, onView }) {
  const rel = relatedPlayers(player, players, 6);
  if (!rel.length) return null;
  return (
    <section className="morep">
      <h2 className="morep-title">其他旅外球員</h2>
      <nav className="morep-list">
        {rel.map((x) => (
          <a
            key={x.id}
            href={`${import.meta.env.BASE_URL}player/${x.slug}/`}
            onClick={(e) => {
              e.preventDefault();
              onView(x.slug);
            }}
          >
            {x.name}
            <span>{(LEVEL_LABEL[x.level] || x.level) + "・" + x.org}</span>
          </a>
        ))}
      </nav>
    </section>
  );
}

function PlayerDetail({ player, season, players, onView, onBack }) {
  useEffect(() => {
    const prev = document.title;
    document.title = `${player.name} ${romanName(player)}｜球季數據・最近出賽｜旅外球員情報站`;
    return () => {
      document.title = prev;
    };
  }, [player]);
  return (
    <div className="site">
      <SiteHeader onBrand={onBack} />
      <div className="wrap page">
        <nav className="crumb" aria-label="breadcrumb">
          <a
            href={import.meta.env.BASE_URL}
            onClick={(e) => {
              e.preventDefault();
              onBack();
            }}
          >
            首頁
          </a>
          <span className="crumb-sep">›</span>
          <span className="crumb-cur">{player.name}</span>
        </nav>
        <header className="pd-head">
          <h1>
            {player.name} <span className="pd-en">{romanName(player)}</span>
          </h1>
        </header>
        {player.heritage && <p className="pd-heritage">🇹🇼 台裔球員 · 具台灣血統</p>}
        {seasonSummaryText(player, season) && (
          <p className="pd-summary">
            <b>戰績摘要</b>：{seasonSummaryText(player, season)}
          </p>
        )}
        <div className={`card level-${levelClass(player.level)}`}>
          <div className="card-detail">
            <Bio player={player} />
            <Sparkline player={player} />
            <SeasonTable player={player} />
            <RecentGames player={player} />
          </div>
        </div>
        <RelatedContent player={player} />
        <FAQ player={player} season={season} />
        <MorePlayers player={player} players={players} onView={onView} />
      </div>
      <footer className="foot">
        <div className="wrap">資料來源:MLB / NPB / KBO 公開資料</div>
      </footer>
    </div>
  );
}

// 網站頁首列(logo + 導覽);view 為選填,球員頁不顯示分頁高亮
function SiteHeader({ view, onNav, onBrand }) {
  const NAV = [
    ["report", "每日戰報"],
    ["latest", "最新表現"],
    ["stats", "累積數據"],
    ["map", "地圖"],
    ["honors", "評比"],
  ];
  return (
    <header className="topbar">
      <div className="topbar-in wrap">
        <a
          className="brand"
          href={import.meta.env.BASE_URL}
          onClick={(e) => {
            e.preventDefault();
            onBrand ? onBrand() : onNav && onNav("report");
          }}
        >
          <img className="brand-mark" src={`${import.meta.env.BASE_URL}logo.svg`} alt="" width="26" height="34" />
          旅外球員情報站<span className="brand-sub">台灣旅外棒球員即時數據</span>
        </a>
        {onNav && (
          <nav className="topnav" aria-label="主導覽">
            {NAV.map(([v, label]) => (
              <button
                key={v}
                className={`topnav-btn ${view === v ? "topnav-on" : ""}`}
                onClick={() => onNav(v)}
              >
                {label}
              </button>
            ))}
          </nav>
        )}
      </div>
    </header>
  );
}

function HonorsView({ players, leagueChip, onView }) {
  const list = players
    .filter((p) => p.accolades)
    .filter((p) => leagueChip === "全部" || playerLeague(p) === leagueChip);
  if (!list.length) return <p className="empty-note">此聯盟目前無評比資料</p>;
  return (
    <section className="honors">
      <p className="board-season">新秀排名・榮譽・入選(人工維護,持續更新)</p>
      {list.map((p) => (
        <div className="honor-card" key={p.id}>
          <div className="honor-head">
            <PlayerLink slug={p.slug} name={p.name} onView={onView} className="honor-name" />
            <span className="honor-meta">
              {[LEVEL_LABEL[p.level] || p.level, p.org].filter(Boolean).join("・")}
            </span>
          </div>
          <ul className="honor-list">
            {p.accolades.list.map((it, i) => {
              const yr = typeof it === "object" ? it.y : "";
              const txt = typeof it === "object" ? it.t : it;
              return (
                <li key={i}>
                  {yr && <span className="honor-yr">{yr}</span>}
                  {txt}
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </section>
  );
}

// ---- 最新表現(亮點)相關 ----
// 一場亮點表現的一句話結果(徽章 + 數據)
function perfLine(g) {
  return g.type === "pitching" ? pitchLine(g) : hitLine(g);
}
// YouTube 精華搜尋連結(Phase A 影片來源;有 g.video 時改為站內嵌入)
function ytSearch(p, g) {
  const q = `${p.name} ${g.date.slice(0, 4)} 精華`;
  return `https://www.youtube.com/results?search_query=${encodeURIComponent(q)}`;
}
// 從網址判斷是否為表現頁:/performance/{slug}/{YYYY-MM-DD}/
function perfFromPath() {
  const m = window.location.pathname.match(/\/performance\/([^/]+)\/(\d{4}-\d{2}-\d{2})\/?$/);
  return m ? { slug: decodeURIComponent(m[1]), date: m[2] } : null;
}
// 蒐集跨球員的近期亮點表現(給總覽頁與 sitemap)
function collectHighlights(players, leagueChip, days = 21) {
  const items = [];
  players
    .filter((p) => leagueChip === "全部" || playerLeague(p) === leagueChip)
    .forEach((p) =>
      (p.game_logs || []).forEach((g) => {
        if (isHot(g)) items.push({ p, g });
      })
    );
  items.sort((a, b) =>
    a.g.date !== b.g.date ? (a.g.date < b.g.date ? 1 : -1) : levelRank(a.p) - levelRank(b.p)
  );
  const cut = items.length ? items[0].g.date : "";
  const cutDate = cut ? new Date(cut + "T00:00:00").getTime() - days * 86400000 : 0;
  return items.filter((it) => new Date(it.g.date + "T00:00:00").getTime() >= cutDate);
}

function PerfVideo({ player, game }) {
  const v = game.video; // Phase B: { id, title }
  if (v && v.id) {
    return (
      <div className="perf-video">
        <div className="perf-video-frame">
          <iframe
            src={`https://www.youtube-nocookie.com/embed/${v.id}`}
            title={v.title || `${player.name} 精華`}
            loading="lazy"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
          />
        </div>
        {v.title && <p className="perf-video-cap">{v.title}</p>}
      </div>
    );
  }
  return (
    <a className="perf-video-search" href={ytSearch(player, game)} target="_blank" rel="noopener noreferrer">
      ▶ 在 YouTube 搜尋「{player.name} 精華」
    </a>
  );
}

function PerformanceDetail({ player, game, season, players, onViewPerf, onPlayer, onBack, onLatest }) {
  const b = decisionBadge(game);
  const dstr = `${fmtDate(game.date)}（${weekday(game.date)}）`;
  useEffect(() => {
    const prev = document.title;
    document.title = `${player.name} ${dstr} ${b.text}｜${perfLine(game)}｜旅外球員情報站`;
    return () => { document.title = prev; };
  }, [player, game]);
  const lg = playerLeague(player);
  const arts = (player.content && player.content.articles) || [];
  const hub = TCT_HUB[lg];
  const others = (player.game_logs || []).filter((g) => g !== game && isHot(g)).slice(0, 6);
  const oppLevel = (game.level ? `[${LEVEL_LABEL[game.level] || game.level}] ` : "") + (game.opponent || "");
  return (
    <div className="site">
      <SiteHeader onBrand={onBack} />
      <div className="wrap page">
        <nav className="crumb" aria-label="breadcrumb">
          <a href={import.meta.env.BASE_URL} onClick={(e) => { e.preventDefault(); onBack(); }}>首頁</a>
          <span className="crumb-sep">›</span>
          <a href={`${import.meta.env.BASE_URL}player/${player.slug}/`} onClick={(e) => { e.preventDefault(); onPlayer(player.slug); }}>{player.name}</a>
          <span className="crumb-sep">›</span>
          <span className="crumb-cur">{fmtDate(game.date)}表現</span>
        </nav>

        <div className={`perf-hero level-${levelClass(player.level)}`}>
          <div className="perf-hero-top">
            <span className={`badge ${b.cls}`}>{b.text}</span>
            <span className="perf-date">{dstr}</span>
          </div>
          <h1 className="perf-h1"><PlayerLink slug={player.slug} name={player.name} onView={onPlayer} className="perf-h1-link" /><span className="perf-en"> {romanName(player)}</span></h1>
          <p className="perf-opp">對戰 {oppLevel}{game.is_home === true ? "（主場）" : game.is_home === false ? "（客場）" : ""}</p>
          <p className="perf-stat">{perfLine(game)}</p>
        </div>

        <section className="perf-sec">
          <h2 className="perf-sec-t">🎬 比賽影片</h2>
          <PerfVideo player={player} game={game} />
        </section>

        <section className="perf-sec">
          <h2 className="perf-sec-t">📰 消息來源</h2>
          {arts.length > 0 ? (
            <ul className="related-list">
              {arts.map((a, i) => (
                <li key={i}>
                  <a href={a.url} target="_blank" rel="noopener noreferrer">{a.title}</a>
                  {a.date && <span className="related-date">{a.date.slice(5).replace("-", "/")}</span>}
                </li>
              ))}
            </ul>
          ) : (
            <p className="perf-muted">暫無站內收錄的相關報導。</p>
          )}
          {hub && (
            <p className="faq-more">延伸閱讀:<a href={hub.url} target="_blank" rel="noopener noreferrer">The Clutch Time —《{hub.title}》</a></p>
          )}
        </section>

        <section className="perf-sec">
          <h2 className="perf-sec-t">關於 {player.name}</h2>
          {seasonSummaryText(player, season) && <p className="perf-about">{seasonSummaryText(player, season)}</p>}
          <button className="perf-btn" onClick={() => onPlayer(player.slug)}>看 {player.name} 完整數據與近況 →</button>
        </section>

        {others.length > 0 && (
          <section className="perf-sec">
            <h2 className="perf-sec-t">{player.name} 其他亮點</h2>
            <div className="perf-more-grid">
              {others.map((g, i) => {
                const bb = decisionBadge(g);
                return (
                  <button className="perf-mini" key={i} onClick={() => onViewPerf(player.slug, g.date)}>
                    <span className={`badge ${bb.cls}`}>{bb.text}</span>
                    <span className="perf-mini-d">{fmtDate(g.date)}</span>
                    <span className="perf-mini-l">{perfLine(g)}</span>
                  </button>
                );
              })}
            </div>
          </section>
        )}

        <p className="perf-back"><button className="perf-btn ghost" onClick={onLatest}>← 看更多最新表現</button></p>
      </div>
      <footer className="foot"><div className="wrap">資料來源:MLB / NPB / KBO 公開資料</div></footer>
    </div>
  );
}

function LatestView({ players, leagueChip, levelFilter, setLevelFilter, onViewPerf, onView }) {
  const all = collectHighlights(players, leagueChip, 21);
  // 下拉只列出「目前有亮點」的層級;若目前選的層級已無資料則視同全部
  const present = LEVEL_TIERS.filter((t) => all.some(({ p }) => tierKey(p) === t.key));
  const eff = present.some((t) => t.key === levelFilter) ? levelFilter : "全部";
  const items = eff === "全部" ? all : all.filter(({ p }) => tierKey(p) === eff);
  // 依日期分組
  const groups = [];
  let cur = null;
  items.forEach((it) => {
    if (!cur || cur.date !== it.g.date) { cur = { date: it.g.date, list: [] }; groups.push(cur); }
    cur.list.push(it);
  });
  return (
    <section className="latest">
      <div className="latest-bar">
        <label className="latest-sel-label" htmlFor="latest-level">層級</label>
        <select
          id="latest-level"
          className="latest-sel"
          value={eff}
          onChange={(e) => setLevelFilter(e.target.value)}
        >
          <option value="全部">全部層級</option>
          {present.map((t) => (
            <option key={t.key} value={t.key}>{t.label}</option>
          ))}
        </select>
      </div>
      <p className="latest-lead">🔥 近三週旅外台將的亮點表現(開轟・勝投・救援・優質先發・多安打),點進看數據、消息與影片。</p>
      {!items.length && <p className="empty-note">此層級近期暫無亮點表現</p>}
      {groups.map((grp) => (
        <div className="latest-day" key={grp.date}>
          <h2 className="latest-date">{fmtDate(grp.date)}<span className="latest-wd">{weekday(grp.date)}</span></h2>
          <div className="latest-grid">
            {grp.list.map(({ p, g }, i) => {
              const b = decisionBadge(g);
              return (
                <div className={`perf-card level-${levelClass(p.level)}`} key={i}>
                  <div className="perf-card-top">
                    <PlayerLink slug={p.slug} name={p.name} onView={onView} className="perf-card-name" />
                    <span className={`badge ${b.cls}`}>{b.text}</span>
                  </div>
                  <button className="perf-card-body" onClick={() => onViewPerf(p.slug, g.date)}>
                    <span className="perf-card-meta">{(g.level ? `${LEVEL_LABEL[g.level] || g.level}・` : "")}{playerLeague(p)}</span>
                    <span className="perf-card-line">{perfLine(g)}</span>
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </section>
  );
}

// 首頁「最新亮點」預覽(秀最新幾張表現卡,連到 /latest 與各表現頁)
function LatestPreview({ players, leagueChip, levelFilter, setLevelFilter, onViewPerf, onView, onMore }) {
  const all = collectHighlights(players, leagueChip, 21);
  if (!all.length) return null;
  const present = LEVEL_TIERS.filter((t) => all.some(({ p }) => tierKey(p) === t.key));
  const eff = present.some((t) => t.key === levelFilter) ? levelFilter : "全部";
  const items = (eff === "全部" ? all : all.filter(({ p }) => tierKey(p) === eff)).slice(0, 6);
  return (
    <section className="lp">
      <div className="lp-head">
        <h2 className="lp-title">🔥 最新亮點</h2>
        <div className="lp-head-right">
          <select className="latest-sel lp-sel" value={eff} onChange={(e) => setLevelFilter(e.target.value)} aria-label="層級篩選">
            <option value="全部">全部層級</option>
            {present.map((t) => (
              <option key={t.key} value={t.key}>{t.label}</option>
            ))}
          </select>
          <button className="lp-more" onClick={onMore}>看全部 →</button>
        </div>
      </div>
      <div className="lp-grid">
        {items.map(({ p, g }, i) => {
          const b = decisionBadge(g);
          return (
            <div className={`perf-card level-${levelClass(p.level)}`} key={i}>
              <div className="perf-card-top">
                <PlayerLink slug={p.slug} name={p.name} onView={onView} className="perf-card-name" />
                <span className={`badge ${b.cls}`}>{b.text}</span>
              </div>
              <button className="perf-card-body" onClick={() => onViewPerf(p.slug, g.date)}>
                <span className="perf-card-meta">{fmtDate(g.date)}・{(g.level ? `${LEVEL_LABEL[g.level] || g.level}・` : "")}{playerLeague(p)}</span>
                <span className="perf-card-line">{perfLine(g)}</span>
              </button>
            </div>
          );
        })}
      </div>
    </section>
  );
}

export default function App() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const [dateIdx, setDateIdx] = useState(0);
  const [leagueChip, setLeagueChip] = useState("全部");
  const [levelChip, setLevelChip] = useState("全部");
  const [roleChip, setRoleChip] = useState("全部");
  const [view, setView] = useState("report"); // report | latest | stats | map | honors
  const [latestLevel, setLatestLevel] = useState("全部");
  const [playerSlug, setPlayerSlug] = useState(() => slugFromPath());
  const [perf, setPerf] = useState(() => perfFromPath());
  const [favorites, setFavorites] = useState(() => {
    try {
      return new Set(JSON.parse(localStorage.getItem("tw_favs") || "[]"));
    } catch {
      return new Set();
    }
  });
  const toggleFav = (id) =>
    setFavorites((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      try {
        localStorage.setItem("tw_favs", JSON.stringify([...next]));
      } catch {}
      return next;
    });
  const [todayOpen, setTodayOpen] = useState(() => {
    try {
      return localStorage.getItem("tw_today") !== "0";
    } catch {
      return true;
    }
  });
  const toggleToday = () =>
    setTodayOpen((v) => {
      try {
        localStorage.setItem("tw_today", v ? "0" : "1");
      } catch {}
      return !v;
    });

  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}data/players.json`)
      .then((r) => r.json())
      .then(setData)
      .catch(() => setError(true));
  }, []);

  // 瀏覽器上/下一頁時同步球員個人頁狀態
  useEffect(() => {
    const onPop = () => { setPlayerSlug(slugFromPath()); setPerf(perfFromPath()); };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const goPlayer = (slug) => {
    window.history.pushState({}, "", `${import.meta.env.BASE_URL}player/${slug}/`);
    setPerf(null);
    setPlayerSlug(slug);
    window.scrollTo(0, 0);
  };
  const goPerf = (slug, date) => {
    window.history.pushState({}, "", `${import.meta.env.BASE_URL}performance/${slug}/${date}/`);
    setPlayerSlug(null);
    setPerf({ slug, date });
    window.scrollTo(0, 0);
  };
  const goHome = () => {
    window.history.pushState({}, "", import.meta.env.BASE_URL);
    setPerf(null);
    setPlayerSlug(null);
  };
  const goLatest = () => { goHome(); setView("latest"); };

  const dates = useMemo(() => {
    if (!data) return [];
    const set = new Set();
    data.players.forEach((p) => p.game_logs.forEach((g) => set.add(g.date)));
    return [...set].sort().reverse();
  }, [data]);

  const currentDate = dates[dateIdx];

  const rows = useMemo(() => {
    if (!data || !currentDate) return [];
    return data.players
      .filter((p) => leagueChip === "全部" || playerLeague(p) === leagueChip)
      .filter((p) => matchLevel(levelChip, p.level))
      .filter((p) =>
        roleChip === "全部" ? true : roleChip === "投手" ? p.role === "pitcher" : p.role === "batter"
      )
      .map((p) => ({ player: p, game: p.game_logs.find((g) => g.date === currentDate) || null }))
      .sort((a, b) => {
        const fa = favorites.has(a.player.id);
        const fb = favorites.has(b.player.id);
        if (fa !== fb) return fa ? -1 : 1; // 最愛置頂
        const lr = levelRank(a.player) - levelRank(b.player);
        if (lr !== 0) return lr; // 依層級(大聯盟>日一軍>韓一軍>3A>2A>二軍>1A>新人)
        if (Boolean(b.game) !== Boolean(a.game)) return b.game ? 1 : -1; // 同層級:今日有出賽者優先
        if (a.game && b.game) {
          const sa = a.game.type === "pitching" && a.game.started ? 1 : 0;
          const sb = b.game.type === "pitching" && b.game.started ? 1 : 0;
          if (sa !== sb) return sb - sa;
        }
        return 0;
      });
  }, [data, currentDate, leagueChip, levelChip, roleChip, favorites]);

  if (error)
    return <div className="wrap"><p className="empty-note">資料載入失敗,請稍後再試。</p></div>;
  if (!data)
    return <div className="wrap"><p className="empty-note">載入中…</p></div>;

  if (perf) {
    const p = data.players.find((x) => x.slug === perf.slug);
    const g = p && (p.game_logs || []).find((x) => x.date === perf.date);
    if (p && g)
      return (
        <PerformanceDetail
          player={p}
          game={g}
          season={data.season}
          players={data.players}
          onViewPerf={goPerf}
          onPlayer={goPlayer}
          onBack={goHome}
          onLatest={goLatest}
        />
      );
    // 找不到對應表現 → 回球員頁或首頁
    if (p) { setPerf(null); setPlayerSlug(p.slug); }
  }

  if (playerSlug) {
    const p = data.players.find((x) => x.slug === playerSlug);
    if (p)
      return (
        <PlayerDetail
          player={p}
          season={data.season}
          players={data.players}
          onView={goPlayer}
          onBack={goHome}
        />
      );
    // 找不到對應球員(舊連結/錯字)→ 回首頁
  }

  const playedRows = rows.filter((r) => r.game);
  const playedCount = playedRows.length;
  const namesWhere = (fn) => playedRows.filter((r) => fn(r.game)).map((r) => r.player);
  const homers = namesWhere((g) => g.type === "hitting" && g.hr > 0);
  const wins = namesWhere((g) => g.win);
  const saves = namesWhere((g) => g.save);
  const slugById = {};
  data.players.forEach((p) => { slugById[p.id] = p.slug; });
  const nameLinks = (arr) =>
    arr.map((p, i) => (
      <React.Fragment key={p.id}>
        {i > 0 && "、"}
        <PlayerLink slug={p.slug} name={p.name} onView={goPlayer} />
      </React.Fragment>
    ));
  const byLeague = { 旅美: 0, 旅日: 0, 旅韓: 0 };
  playedRows.forEach((r) => (byLeague[playerLeague(r.player)] += 1));
  const inLeague = (lg) => leagueChip === "全部" || lg === leagueChip;
  const startsCount = data.players.filter((p) => p.next_start && inLeague(playerLeague(p))).length;
  const hlCount = homers.length + wins.length + saves.length;
  const movesCount = (data.moves || []).filter((m) => inLeague(moveLeague(m.league))).length;
  const teaser = [
    startsCount > 0 && `⚾${startsCount}`,
    hlCount > 0 && `🔥${hlCount}`,
    movesCount > 0 && `↕${movesCount}`,
  ].filter(Boolean).join("　");

  const todayPanel = (
    <div className="today">
      <button className="today-toggle" onClick={toggleToday} aria-expanded={todayOpen}>
        <span className="today-h">今日</span>
        {!todayOpen && teaser && <span className="today-teaser">{teaser}</span>}
        <span className="today-chev">{todayOpen ? "▾" : "▸"}</span>
      </button>
      {todayOpen && <StartsPreview players={data.players} leagueChip={leagueChip} onView={goPlayer} />}
      {todayOpen && (leagueChip === "全部" || homers.length + wins.length + saves.length > 0 || playedCount === 0) && (
        <div className="daysum">
          {leagueChip === "全部" && (
            <span className="daysum-lg">🇺🇸 {byLeague.旅美}　🇯🇵 {byLeague.旅日}　🇰🇷 {byLeague.旅韓}</span>
          )}
          {playedCount === 0 ? (
            <span className="daysum-empty">本日暫無台將出賽</span>
          ) : (
            (homers.length > 0 || wins.length > 0 || saves.length > 0) && (
              <span className="daysum-tags">
                {homers.length > 0 && <span className="dtag dtag-hr">🔥 {nameLinks(homers)}</span>}
                {wins.length > 0 && <span className="dtag dtag-w">✅ 勝 {nameLinks(wins)}</span>}
                {saves.length > 0 && <span className="dtag dtag-sv">🧤 {nameLinks(saves)}</span>}
              </span>
            )
          )}
        </div>
      )}
      {todayOpen && <MovesFeed moves={data.moves} leagueChip={leagueChip} slugById={slugById} onView={goPlayer} />}
    </div>
  );

  return (
    <div className="site">
      <SiteHeader view={view} onNav={setView} />
      <div className="wrap page">

      {view === "report" && (
        <nav className="datebar" aria-label="日期切換">
          <button
            className="date-arrow"
            onClick={() => setDateIdx((i) => Math.min(i + 1, dates.length - 1))}
            disabled={dateIdx >= dates.length - 1}
            aria-label="前一天"
          >‹</button>
          <div className="date-label">
            <span className="date-main">{currentDate ? fmtDate(currentDate) : "—"}</span>
            <span className="date-sub">{currentDate ? `${weekday(currentDate)}・${playedCount} 人出賽` : ""}</span>
          </div>
          <button
            className="date-arrow"
            onClick={() => setDateIdx((i) => Math.max(i - 1, 0))}
            disabled={dateIdx === 0}
            aria-label="後一天"
          >›</button>
        </nav>
      )}

      <div className="chips" role="group" aria-label="聯盟篩選">
        {LEAGUE_CHIPS.map((c) => (
          <button
            key={c}
            className={`chip ${leagueChip === c ? "chip-on" : ""}`}
            onClick={() => {
              setLeagueChip(c);
              setLevelChip("全部");
            }}
          >
            {c}
          </button>
        ))}
      </div>
      {view !== "honors" && view !== "map" && view !== "latest" && LEVEL_CHIPS_BY_LEAGUE[leagueChip] && (
        <div className="chips" role="group" aria-label="層級篩選">
          {LEVEL_CHIPS_BY_LEAGUE[leagueChip].map((c) => (
            <button key={c} className={`chip ${levelChip === c ? "chip-on" : ""}`} onClick={() => setLevelChip(c)}>
              {c === "AAA" ? "3A" : c === "AA" ? "2A" : c}
            </button>
          ))}
        </div>
      )}
      {view !== "honors" && view !== "map" && view !== "latest" && (
        <div className="chips" role="group" aria-label="位置篩選">
          {ROLE_CHIPS.map((c) => (
            <button key={c} className={`chip ${roleChip === c ? "chip-on" : ""}`} onClick={() => setRoleChip(c)}>
              {c}
            </button>
          ))}
        </div>
      )}

      {view === "report" && (
        <LatestPreview players={data.players} leagueChip={leagueChip} levelFilter={latestLevel} setLevelFilter={setLatestLevel} onViewPerf={goPerf} onView={goPlayer} onMore={() => setView("latest")} />
      )}

      {view === "latest" && (
        <LatestView players={data.players} leagueChip={leagueChip} levelFilter={latestLevel} setLevelFilter={setLatestLevel} onViewPerf={goPerf} onView={goPlayer} />
      )}

      {view === "report" && (
        <div className="report-grid">
          <section className="main-col cards">
            {rows.map(({ player, game }) => (
              <PlayerCard
                key={player.id}
                player={player}
                game={game}
                latestDate={dates[0]}
                fav={favorites.has(player.id)}
                onFav={() => toggleFav(player.id)}
                onView={goPlayer}
              />
            ))}
            {!rows.length && <p className="empty-note">沒有符合篩選條件的球員</p>}
          </section>
          <aside className="side-col">
            {todayPanel}
            <NewsRail players={data.players} leagueChip={leagueChip} onView={goPlayer} />
          </aside>
        </div>
      )}
      {view === "stats" && (
        <StatsBoard
          players={data.players}
          leagueChip={leagueChip}
          levelChip={levelChip}
          roleChip={roleChip}
          season={data.season}
          onView={goPlayer}
        />
      )}
      {view === "map" && (
        <Suspense fallback={<p className="empty-note">載入地圖…</p>}>
          <MapView players={data.players} leagueChip={leagueChip} />
        </Suspense>
      )}
      {view === "honors" && <HonorsView players={data.players} leagueChip={leagueChip} onView={goPlayer} />}

      </div>
      <footer className="foot">
        <div className="wrap">
          資料更新於 {data.updated_at?.slice(0, 16).replace("T", " ")}・來源:MLB / NPB / KBO 公開資料
        </div>
      </footer>
    </div>
  );
}
