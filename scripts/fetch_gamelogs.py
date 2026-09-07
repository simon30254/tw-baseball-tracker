"""
歷史逐場紀錄(每位球員一檔)
============================
球員的當季逐場已在 players.json 裡,但**往年的逐場**一直沒有 —— 那是這站要成為
「旅外球員的 Baseball Reference」缺的最後一塊(王建民 2006 年那 34 場先發,
中文網路上找不到逐場表)。

**為什麼要獨立成檔**:players.json 是首頁每次載入都會下載的,不能把歷年逐場
(全部約數千場)塞進去。所以拆成 `public/data/gamelogs/{slug}.json`,
只有球季頁 `/player/{slug}/{年}/` 會用到,由 prerender 在 build 時讀取。

只有旅美有:MLB Stats API 的 gameLog 涵蓋大小聯盟各層級;npb.jp 的舊球季頁
沒有逐場資料,旅日前輩因此沒有(這是資料源的限制,不是抓取失敗)。

歷史球季的逐場不會再變,抓過就不再抓;當季由 players.json 供應,這裡不重複存。

輸出:public/data/gamelogs/{slug}.json = {年份: {層級: [逐場]}}
執行: python3 scripts/fetch_gamelogs.py [--force]
"""

import json
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_data import parse_game_log      # noqa: E402  逐場欄位格式與現役共用一份
from build_players import load_team_zh     # noqa: E402  隊名中譯與全站共用同一份對照

API = "https://statsapi.mlb.com/api/v1"
SEASON = datetime.now().year
SPORTS = {1: "MLB", 11: "AAA", 12: "AA", 13: "High-A", 14: "A", 16: "Rookie"}
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

ROOT = Path(__file__).resolve().parent.parent
PLAYERS = ROOT / "public" / "data" / "players.json"
ALUMNI = ROOT / "public" / "data" / "alumni.json"
OUT_DIR = ROOT / "public" / "data" / "gamelogs"


def get(url):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30) as r:
                return json.loads(r.read())
        except Exception:
            if attempt == 2:
                return None
            time.sleep(1.2 * (attempt + 1))


_TEAMS, _PREFIX, _NICKS = load_team_zh()


def zh_team(name):
    if not name:
        return name
    if name in _TEAMS:
        return _TEAMS[name]
    head, _, rest = name.partition(" ")
    if head in _PREFIX and rest in _NICKS:
        return f"{head} {_NICKS[rest]}"
    return name            # 查無公認譯名就留英文原名(小聯盟球隊多屬此類)


def main():
    force = "--force" in sys.argv
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    people = json.loads(PLAYERS.read_text(encoding="utf-8"))["players"]
    try:
        people += json.loads(ALUMNI.read_text(encoding="utf-8"))["players"]
    except Exception:
        pass

    total_calls = total_games = 0
    for p in people:
        pid = str(p["id"])
        if not pid.isdigit():
            continue                      # 旅日/旅韓沒有逐場 API
        group = "pitching" if p.get("role") == "pitcher" else "hitting"
        path = OUT_DIR / f"{p['slug']}.json"
        try:
            store = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except Exception:
            store = {}
        changed = False
        for year, by_level in sorted((p.get("prev_season") or {}).items(), reverse=True):
            if int(year) >= SEASON:
                continue                  # 當季由 players.json 供應,不重複存
            if year in store and not force:
                continue                  # 往年逐場不會再變
            got = {}
            for sid, level in SPORTS.items():
                if level not in by_level:
                    continue
                d = get(f"{API}/people/{p['id']}/stats?stats=gameLog&group={group}&season={year}&sportId={sid}")
                total_calls += 1
                splits = (d or {}).get("stats", [{}])[0].get("splits", []) if (d or {}).get("stats") else []
                games = parse_game_log(splits, group)
                if games:
                    for g in games:      # 隊名中譯,與 players.json 的逐場一致
                        g["opponent"] = zh_team(g.get("opponent"))
                    got[level] = games
                    total_games += len(games)
                time.sleep(0.06)
            if got:
                store[year] = got
                changed = True
        if changed:
            path.write_text(json.dumps(store, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        elif not store and path.exists():
            path.unlink()

    files = list(OUT_DIR.glob("*.json"))
    size = sum(f.stat().st_size for f in files)
    print(f"歷史逐場:呼叫 {total_calls} 次、新增 {total_games} 場;"
          f"共 {len(files)} 檔 / {size/1024:.0f} KB → public/data/gamelogs/")


if __name__ == "__main__":
    main()
