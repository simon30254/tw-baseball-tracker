"""
分項數據(對左/右打者、主場/客場)
==================================
MLB Stats API 的 `stats=statSplits&sitCodes=vl,vr,h,a`。與 sabermetrics 不同,
**這個連小聯盟都有**(林昱珉 3A 拿得到),所以涵蓋率比進階數據高很多。

只抓當季:分項數據每天都在變,沒有快取意義;歷史球季的分項留待日後有需要再說。
球員在哪些層級有出賽就抓哪些層級(sitCodes 一次回四組,一個層級一次呼叫)。

sitCodes:vl=對左、vr=對右、h=主場、a=客場。
投手看到的 avg 是「被打擊率」,野手看到的是自己的打擊率 —— 同一個欄位在投打
兩邊意思不同,顯示時的欄位名要跟著換。

輸出:scripts/splits_cache.json(build_players 掛到 season_stats[層級].splits)
執行: python3 scripts/fetch_splits.py
"""

import json
import time
import urllib.request
from datetime import datetime
from pathlib import Path

API = "https://statsapi.mlb.com/api/v1"
SEASON = datetime.now().year
SPORTS = {1: "MLB", 11: "AAA", 12: "AA", 13: "High-A", 14: "A", 16: "Rookie"}
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

ROOT = Path(__file__).resolve().parent.parent
PLAYERS = ROOT / "public" / "data" / "players.json"
CACHE = ROOT / "scripts" / "splits_cache.json"


def get(url):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=25) as r:
                return json.loads(r.read())
        except Exception:
            if attempt == 2:
                return None
            time.sleep(1.2 * (attempt + 1))


def pick(stat, is_pitcher):
    if is_pitcher:
        out = {"era": stat.get("era"), "whip": stat.get("whip"), "avg": stat.get("avg"),
               "ip": stat.get("inningsPitched"), "so": stat.get("strikeOuts"),
               "hr": stat.get("homeRuns")}
    else:
        out = {"avg": stat.get("avg"), "ops": stat.get("ops"), "ab": stat.get("atBats"),
               "hr": stat.get("homeRuns"), "so": stat.get("strikeOuts")}
    return {k: v for k, v in out.items() if v not in (None, "", "-", ".---")}


def main():
    players = json.loads(PLAYERS.read_text(encoding="utf-8"))["players"]
    cache = {}
    calls = 0
    for p in players:
        pid = str(p["id"])
        if not pid.isdigit():
            continue                       # 旅日/旅韓沒有這種 API
        is_pitcher = p.get("role") == "pitcher"
        group = "pitching" if is_pitcher else "hitting"
        for sid, level in SPORTS.items():
            if level not in (p.get("season_stats") or {}):
                continue
            d = get(f"{API}/people/{p['id']}/stats?stats=statSplits&sitCodes=vl,vr,h,a"
                    f"&group={group}&season={SEASON}&sportId={sid}")
            calls += 1
            got = {}
            for block in (d or {}).get("stats", []):
                for s in block.get("splits", []):
                    code = (s.get("split") or {}).get("code")
                    st = pick(s.get("stat") or {}, is_pitcher)
                    if code and st:
                        got[code] = st
            if got:
                cache.setdefault(pid, {})[level] = got
            time.sleep(0.06)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0, sort_keys=True) + "\n", encoding="utf-8")
    n = sum(len(v) for v in cache.values())
    print(f"分項數據:呼叫 {calls} 次,{len(cache)} 人 / {n} 個層級有資料 → {CACHE.name}")


if __name__ == "__main__":
    main()
