import React, { useEffect, useMemo, useState } from "react";

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

function SeasonTable({ player }) {
  const levels = Object.entries(player.season_stats || {});
  if (!levels.length) return <p className="empty-note">本季尚無累積數據</p>;
  const isP = player.role === "pitcher";
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

function RecentGames({ player }) {
  const games = (player.game_logs || []).slice(0, 10);
  if (!games.length) return null;
  return (
    <div className="recent">
      <p className="recent-title">最近出賽</p>
      {games.map((g, i) => (
        <div className="recent-row" key={i}>
          <span className="recent-date">{g.date.slice(5).replace("-", "/")}</span>
          <span className="recent-opp">{g.level && `[${LEVEL_LABEL[g.level] || g.level}] `}vs {g.opponent}</span>
          <span className="recent-line mono">{g.type === "pitching" ? pitchLine(g) : hitLine(g)}</span>
        </div>
      ))}
    </div>
  );
}

function PlayerCard({ player, game, expanded, onToggle, latestDate }) {
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
    <div className={`card level-${levelClass(player.level)} ${played ? "" : "card-idle"} ${injured ? "card-il" : ""} ${hot ? "card-hot" : ""}`}>
      <button className="card-head" onClick={onToggle} aria-expanded={expanded}>
        <div className="card-id">
          <span className="card-name">{player.name}{injured && <span className="il-dot" title="傷兵名單">🏥</span>}</span>
          <span className="card-meta">
            {[LEVEL_LABEL[player.level] || player.level, player.org, player.position]
              .filter(Boolean)
              .join("・")}
          </span>
        </div>
        <div className="card-right">
          <span className={`badge ${badge.cls}`}>{badge.text}</span>
        </div>
      </button>
      {played && (
        <p className="card-line mono">
          {hot && <span className="hot-mark">🔥</span>}
          {game.type === "pitching" ? pitchLine(game) : hitLine(game)}
        </p>
      )}
      {expanded && (
        <div className="card-detail">
          <SeasonTable player={player} />
          <RecentGames player={player} />
        </div>
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
const LEVEL_RANK = { MLB: 0, AAA: 1, AA: 2, "High-A": 3, A: 4, Rookie: 5, 一軍: 0, 二軍: 1 };
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

function LeaderTable({ title, cols, rows, volumeKey, initialSort }) {
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
      const ra = LEVEL_RANK[a.sl.level] ?? 99;
      const rb = LEVEL_RANK[b.sl.level] ?? 99;
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
                  {p.name}
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

function StatsBoard({ players, leagueChip, levelChip, roleChip, season }) {
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
        />
      )}
      {adv && <p className="board-note">FIP 用固定常數 3.10 近似;KBO 打者數為估算。wOBA/wRC+/Statcast 因缺乏各聯盟統一基準,暫不提供。</p>}
      {empty && <p className="empty-note">沒有符合篩選條件的累積數據</p>}
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
  const [expandedId, setExpandedId] = useState(null);
  const [view, setView] = useState("report"); // report | stats

  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}data/players.json`)
      .then((r) => r.json())
      .then(setData)
      .catch(() => setError(true));
  }, []);

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
        if (Boolean(b.game) !== Boolean(a.game)) return b.game ? 1 : -1;
        if (a.game && b.game) {
          const sa = a.game.type === "pitching" && a.game.started ? 1 : 0;
          const sb = b.game.type === "pitching" && b.game.started ? 1 : 0;
          if (sa !== sb) return sb - sa;
        }
        return (a.player.level === "MLB" ? -1 : 0) - (b.player.level === "MLB" ? -1 : 0);
      });
  }, [data, currentDate, leagueChip, levelChip, roleChip]);

  if (error)
    return <main className="shell"><p className="empty-note">資料載入失敗,請稍後再試。</p></main>;
  if (!data)
    return <main className="shell"><p className="empty-note">載入中…</p></main>;

  const playedRows = rows.filter((r) => r.game);
  const playedCount = playedRows.length;
  const namesWhere = (fn) => playedRows.filter((r) => fn(r.game)).map((r) => r.player.name);
  const homers = namesWhere((g) => g.type === "hitting" && g.hr > 0);
  const wins = namesWhere((g) => g.win);
  const saves = namesWhere((g) => g.save);
  const byLeague = { 旅美: 0, 旅日: 0, 旅韓: 0 };
  playedRows.forEach((r) => (byLeague[playerLeague(r.player)] += 1));

  return (
    <main className="shell">
      <header className="masthead">
        <h1>旅外戰報</h1>
        <p className="masthead-sub">台灣球員・{data.season} 球季</p>
      </header>

      <div className="viewtabs" role="tablist" aria-label="檢視切換">
        <button className={`viewtab ${view === "report" ? "viewtab-on" : ""}`} onClick={() => setView("report")}>
          每日戰報
        </button>
        <button className={`viewtab ${view === "stats" ? "viewtab-on" : ""}`} onClick={() => setView("stats")}>
          累積數據
        </button>
      </div>

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
      {LEVEL_CHIPS_BY_LEAGUE[leagueChip] && (
        <div className="chips" role="group" aria-label="層級篩選">
          {LEVEL_CHIPS_BY_LEAGUE[leagueChip].map((c) => (
            <button key={c} className={`chip ${levelChip === c ? "chip-on" : ""}`} onClick={() => setLevelChip(c)}>
              {c === "AAA" ? "3A" : c === "AA" ? "2A" : c}
            </button>
          ))}
        </div>
      )}
      <div className="chips" role="group" aria-label="位置篩選">
        {ROLE_CHIPS.map((c) => (
          <button key={c} className={`chip ${roleChip === c ? "chip-on" : ""}`} onClick={() => setRoleChip(c)}>
            {c}
          </button>
        ))}
      </div>

      {view === "report" && (
        <div className="daysum">
          <div className="daysum-top">
            <span className="daysum-count"><b>{playedCount}</b> 人出賽</span>
            {leagueChip === "全部" && (
              <span className="daysum-lg">🇺🇸 {byLeague.旅美}　🇯🇵 {byLeague.旅日}　🇰🇷 {byLeague.旅韓}</span>
            )}
          </div>
          {playedCount === 0 ? (
            <p className="daysum-empty">本日暫無台將出賽</p>
          ) : (
            (homers.length > 0 || wins.length > 0 || saves.length > 0) && (
              <div className="daysum-tags">
                {homers.length > 0 && <span className="dtag dtag-hr">🔥 開轟 {homers.join("、")}</span>}
                {wins.length > 0 && <span className="dtag dtag-w">✅ 勝投 {wins.join("、")}</span>}
                {saves.length > 0 && <span className="dtag dtag-sv">🧤 救援 {saves.join("、")}</span>}
              </div>
            )
          )}
        </div>
      )}

      {view === "report" ? (
        <section className="cards">
          {rows.map(({ player, game }) => (
            <PlayerCard
              key={player.id}
              player={player}
              game={game}
              latestDate={dates[0]}
              expanded={expandedId === player.id}
              onToggle={() => setExpandedId(expandedId === player.id ? null : player.id)}
            />
          ))}
          {!rows.length && <p className="empty-note">沒有符合篩選條件的球員</p>}
        </section>
      ) : (
        <StatsBoard
          players={data.players}
          leagueChip={leagueChip}
          levelChip={levelChip}
          roleChip={roleChip}
          season={data.season}
        />
      )}

      <footer className="foot">
        資料更新於 {data.updated_at?.slice(0, 16).replace("T", " ")}・來源:MLB / NPB / KBO 公開資料
      </footer>
    </main>
  );
}
