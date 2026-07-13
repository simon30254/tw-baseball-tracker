"""
旅美台灣球員資料抓取腳本
=========================
資料來源:MLB Stats API (statsapi.mlb.com,官方免費、無需金鑰)

流程:
1. 掃描 MLB + 小聯盟各層級 (AAA/AA/High-A/Single-A/Rookie) 的球員名單,
   用 birthCountry 自動找出台灣球員 —— 不用手動維護名單
2. 逐一抓取每位球員的球季累積數據 + 逐場 game log
3. 輸出 public/data/players.json 給前端使用

執行: python3 scripts/fetch_data.py
"""

import json
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

API = "https://statsapi.mlb.com/api/v1"
SEASON = datetime.now().year

# sportId 對應層級
SPORTS = {
    1: "MLB",
    11: "AAA",
    12: "AA",
    13: "High-A",
    14: "A",
    16: "Rookie",
}

TAIWAN_LABELS = {"Taiwan", "Chinese Taipei", "Taiwan, Republic of China"}

ROOT = Path(__file__).resolve().parent.parent
NAME_MAP_PATH = ROOT / "scripts" / "name_map.json"
OUTPUT_PATH = ROOT / "public" / "data" / "players.json"


def get(url: str):
    """帶重試的 GET,回傳 JSON。"""
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "tw-baseball-tracker"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            if attempt == 2:
                print(f"  [WARN] 放棄請求 {url}: {e}")
                return None
            time.sleep(2 * (attempt + 1))


def discover_taiwanese_players():
    """掃描各層級球員名單,找出台灣球員。回傳 {player_id: info}。"""
    players = {}
    for sport_id, level in SPORTS.items():
        print(f"掃描 {level} (sportId={sport_id}) ...")
        data = get(f"{API}/sports/{sport_id}/players?season={SEASON}")
        if not data:
            continue
        for p in data.get("people", []):
            if p.get("birthCountry") in TAIWAN_LABELS:
                pid = p["id"]
                # 同一人可能出現在多個層級名單,以最高層級為準(sportId 小 = 層級高)
                if pid in players and players[pid]["sport_id"] <= sport_id:
                    continue
                players[pid] = {
                    "id": pid,
                    "name_en": p.get("fullName", ""),
                    "sport_id": sport_id,
                    "level": level,
                    "position": (p.get("primaryPosition") or {}).get("abbreviation", ""),
                    "position_type": (p.get("primaryPosition") or {}).get("type", ""),
                    "team_id": (p.get("currentTeam") or {}).get("id"),
                    "active": p.get("active", True),
                }
        time.sleep(0.3)
    print(f"共找到 {len(players)} 位台灣球員")
    return players


def fetch_team_info(team_id):
    """取得球隊名稱與所屬母隊 (小聯盟球隊會有 parentOrgName)。"""
    if not team_id:
        return {"team": "", "org": ""}
    data = get(f"{API}/teams/{team_id}")
    if not data or not data.get("teams"):
        return {"team": "", "org": ""}
    t = data["teams"][0]
    return {
        "team": t.get("name", ""),
        "org": t.get("parentOrgName", "") or t.get("name", ""),
    }


def parse_game_log(splits, group):
    """把 API 的 game log split 轉成前端要的精簡格式。"""
    games = []
    for s in splits:
        stat = s.get("stat", {})
        base = {
            "date": s.get("date", ""),
            "level": (s.get("sport") or {}).get("abbreviation", ""),
            "opponent": (s.get("opponent") or {}).get("name", ""),
            "is_home": s.get("isHome", None),
        }
        if group == "pitching":
            base.update({
                "type": "pitching",
                "ip": stat.get("inningsPitched", "0"),
                "h": stat.get("hits", 0),
                "r": stat.get("runs", 0),
                "er": stat.get("earnedRuns", 0),
                "bb": stat.get("baseOnBalls", 0),
                "so": stat.get("strikeOuts", 0),
                "hr": stat.get("homeRuns", 0),
                "started": stat.get("gamesStarted", 0) > 0,
                "win": stat.get("wins", 0) > 0,
                "loss": stat.get("losses", 0) > 0,
                "save": stat.get("saves", 0) > 0,
            })
        else:
            base.update({
                "type": "hitting",
                "ab": stat.get("atBats", 0),
                "h": stat.get("hits", 0),
                "hr": stat.get("homeRuns", 0),
                "rbi": stat.get("rbi", 0),
                "r": stat.get("runs", 0),
                "bb": stat.get("baseOnBalls", 0),
                "so": stat.get("strikeOuts", 0),
                "sb": stat.get("stolenBases", 0),
                "avg": stat.get("avg", ""),
            })
        games.append(base)
    return games


def fetch_player_stats(pid, is_pitcher):
    """抓球季累積數據 + 逐場紀錄。逐場要掃各層級 (球員可能季中升降)。"""
    group = "pitching" if is_pitcher else "hitting"
    season_stats = {}
    game_logs = []

    # 球季累積:不帶 sportId 逐層查,彙整各層級成績
    for sport_id, level in SPORTS.items():
        data = get(
            f"{API}/people/{pid}/stats"
            f"?stats=season&group={group}&season={SEASON}&sportId={sport_id}"
        )
        if not data:
            continue
        for block in data.get("stats", []):
            for s in block.get("splits", []):
                stat = s.get("stat", {})
                if not stat:
                    continue
                if is_pitcher:
                    season_stats[level] = {
                        "g": stat.get("gamesPlayed", 0),
                        "gs": stat.get("gamesStarted", 0),
                        "w": stat.get("wins", 0),
                        "l": stat.get("losses", 0),
                        "sv": stat.get("saves", 0),
                        "ip": stat.get("inningsPitched", "0"),
                        "so": stat.get("strikeOuts", 0),
                        "bb": stat.get("baseOnBalls", 0),
                        "era": stat.get("era", ""),
                        "whip": stat.get("whip", ""),
                    }
                else:
                    season_stats[level] = {
                        "g": stat.get("gamesPlayed", 0),
                        "ab": stat.get("atBats", 0),
                        "h": stat.get("hits", 0),
                        "hr": stat.get("homeRuns", 0),
                        "rbi": stat.get("rbi", 0),
                        "sb": stat.get("stolenBases", 0),
                        "avg": stat.get("avg", ""),
                        "obp": stat.get("obp", ""),
                        "ops": stat.get("ops", ""),
                    }

        # 逐場紀錄
        data = get(
            f"{API}/people/{pid}/stats"
            f"?stats=gameLog&group={group}&season={SEASON}&sportId={sport_id}"
        )
        if data:
            for block in data.get("stats", []):
                game_logs.extend(parse_game_log(block.get("splits", []), group))
        time.sleep(0.2)

    game_logs.sort(key=lambda g: g["date"], reverse=True)
    return season_stats, game_logs


def main():
    name_map = {}
    if NAME_MAP_PATH.exists():
        name_map = json.loads(NAME_MAP_PATH.read_text(encoding="utf-8"))

    roster = discover_taiwanese_players()
    team_cache = {}
    output_players = []

    for i, (pid, info) in enumerate(sorted(roster.items()), 1):
        print(f"[{i}/{len(roster)}] {info['name_en']} ({info['level']})")
        if info["team_id"] not in team_cache:
            team_cache[info["team_id"]] = fetch_team_info(info["team_id"])
        team_info = team_cache[info["team_id"]]

        is_pitcher = info["position_type"] == "Pitcher"
        season_stats, game_logs = fetch_player_stats(pid, is_pitcher)

        output_players.append({
            "id": pid,
            "name": name_map.get(str(pid), {}).get("zh") or info["name_en"],
            "name_en": info["name_en"],
            "league": "mlb" if info["sport_id"] == 1 else "milb",
            "level": info["level"],
            "team": team_info["team"],
            "org": team_info["org"],
            "position": info["position"],
            "role": "pitcher" if is_pitcher else "batter",
            "season_stats": season_stats,
            "game_logs": game_logs[:60],  # 最近 60 場,控制檔案大小
        })

    tz_taipei = timezone(timedelta(hours=8))
    result = {
        "updated_at": datetime.now(tz_taipei).isoformat(timespec="seconds"),
        "season": SEASON,
        "players": output_players,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(result, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    size_kb = OUTPUT_PATH.stat().st_size / 1024
    print(f"完成:{OUTPUT_PATH} ({size_kb:.0f} KB, {len(output_players)} 位球員)")


if __name__ == "__main__":
    main()
