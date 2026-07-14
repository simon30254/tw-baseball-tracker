import React, { useEffect, useMemo, useState } from "react";

const LEVEL_LABEL = {
  MLB: "MLB", AAA: "3A", AA: "2A", "High-A": "高階1A", A: "1A", Rookie: "新人",
  一軍: "一軍", 二軍: "二軍",
};
const LEVEL_CLASS = {
  MLB: "MLB", AAA: "AAA", AA: "AA", "High-A": "HighA", A: "A", Rookie: "Rookie",
  一軍: "ichigun", 二軍: "nigun",
};
const LEAGUE_CHIPS = ["全部", "旅美", "旅日"];
const LEVEL_CHIPS_BY_LEAGUE = {
  旅美: ["全部", "MLB", "AAA", "AA", "A級以下"],
  旅日: ["全部", "一軍", "二軍"],
};
const ROLE_CHIPS = ["全部", "投手", "野手"];

const playerLeague = (p) => (p.league === "npb" ? "旅日" : "旅美");
const levelClass = (level) => LEVEL_CLASS[level] || "other";

function fmtDate(iso) {
  const [y, m, d] = iso.split("-");
  return `${Number(m)}月${Number(d)}日`;
}

function weekday(iso) {
  return "週" + "日一二三四五六"[new Date(iso + "T00:00:00").getDay()];
}

function pitchLine(g) {
  const parts = [`${g.ip}局`, `失${g.r}分`, `${g.so}K`];
  if (g.bb > 0) parts.push(`${g.bb}BB`);
  return parts.join("　");
}

function hitLine(g) {
  const parts = [`${g.ab}打數${g.h}安`];
  if (g.hr > 0) parts.push(`${g.hr}轟`);
  if (g.rbi > 0) parts.push(`${g.rbi}打點`);
  if (g.r > 0) parts.push(`得${g.r}分`);
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
    <table className="stat-table">
      <thead>
        <tr>
          <th>層級</th>
          {isP ? (
            <><th>出賽</th><th>局數</th><th>ERA</th><th>K</th><th>WHIP</th></>
          ) : (
            <><th>出賽</th><th>AVG</th><th>HR</th><th>打點</th><th>OPS</th></>
          )}
        </tr>
      </thead>
      <tbody>
        {levels.map(([lv, s]) => (
          <tr key={lv}>
            <td>{LEVEL_LABEL[lv] || lv}</td>
            {isP ? (
              <><td>{s.g}</td><td>{s.ip}</td><td>{s.era}</td><td>{s.so}</td><td>{s.whip}</td></>
            ) : (
              <><td>{s.g}</td><td>{s.avg}</td><td>{s.hr}</td><td>{s.rbi}</td><td>{s.ops}</td></>
            )}
          </tr>
        ))}
      </tbody>
    </table>
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

function PlayerCard({ player, game, expanded, onToggle }) {
  const played = Boolean(game);
  const badge = played ? decisionBadge(game) : null;
  return (
    <div className={`card level-${levelClass(player.level)} ${played ? "" : "card-idle"}`}>
      <button className="card-head" onClick={onToggle} aria-expanded={expanded}>
        <div className="card-id">
          <span className="card-name">{player.name}</span>
          <span className="card-meta">
            {[LEVEL_LABEL[player.level] || player.level, player.org, player.position]
              .filter(Boolean)
              .join("・")}
          </span>
        </div>
        <div className="card-right">
          {played ? (
            <span className={`badge ${badge.cls}`}>{badge.text}</span>
          ) : (
            <span className="badge badge-idle">未出賽</span>
          )}
        </div>
      </button>
      {played && (
        <p className="card-line mono">{game.type === "pitching" ? pitchLine(game) : hitLine(game)}</p>
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

export default function App() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const [dateIdx, setDateIdx] = useState(0);
  const [leagueChip, setLeagueChip] = useState("全部");
  const [levelChip, setLevelChip] = useState("全部");
  const [roleChip, setRoleChip] = useState("全部");
  const [expandedId, setExpandedId] = useState(null);

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

  const playedCount = rows.filter((r) => r.game).length;

  return (
    <main className="shell">
      <header className="masthead">
        <h1>旅外戰報</h1>
        <p className="masthead-sub">台灣球員・{data.season} 球季</p>
      </header>

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

      <section className="cards">
        {rows.map(({ player, game }) => (
          <PlayerCard
            key={player.id}
            player={player}
            game={game}
            expanded={expandedId === player.id}
            onToggle={() => setExpandedId(expandedId === player.id ? null : player.id)}
          />
        ))}
        {!rows.length && <p className="empty-note">沒有符合篩選條件的球員</p>}
      </section>

      <footer className="foot">
        資料更新於 {data.updated_at?.slice(0, 16).replace("T", " ")}・來源:MLB Stats API
      </footer>
    </main>
  );
}
