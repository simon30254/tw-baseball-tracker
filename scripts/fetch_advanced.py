"""
進階數據(FIP / xFIP / WAR / wRC+ / wOBA)
==========================================
MLB Stats API 的 `stats=sabermetrics` 提供這些欄位,**現役與歷史球季都有**
(王建民 2006:FIP 3.91、WAR 3.79)。只有大聯盟層級有,小聯盟查不到。

投手:fip / xfip / fipMinus / eraMinus / war
野手:woba / wRcPlus / war

歷史球季的值不會再變,所以快取永久有效,只補抓沒抓過的年份;當季每天重抓。
生涯 WAR 由逐年相加 —— WAR 本來就是可加總的累積型指標,不是自創算法。

輸出:scripts/advanced_cache.json(build_players 掛進 season_stats / prev_season / career)
執行: python3 scripts/fetch_advanced.py
"""

import json
import time
import urllib.request
from datetime import datetime
from pathlib import Path

API = "https://statsapi.mlb.com/api/v1"
SEASON = datetime.now().year
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

ROOT = Path(__file__).resolve().parent.parent
PLAYERS = ROOT / "public" / "data" / "players.json"
ALUMNI = ROOT / "public" / "data" / "alumni.json"
CACHE = ROOT / "scripts" / "advanced_cache.json"


def get(url):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=25) as r:
                return json.loads(r.read())
        except Exception:
            if attempt == 2:
                return None
            time.sleep(1.2 * (attempt + 1))


def r2(v, n=2):
    try:
        return round(float(v), n)
    except (TypeError, ValueError):
        return None


def fetch_one(pid, is_pitcher, year):
    group = "pitching" if is_pitcher else "hitting"
    d = get(f"{API}/people/{pid}/stats?stats=sabermetrics&group={group}&season={year}&sportId=1")
    for block in (d or {}).get("stats", []):
        for s in block.get("splits", []):
            st = s.get("stat") or {}
            if not st:
                continue
            if is_pitcher:
                out = {"fip": r2(st.get("fip")), "xfip": r2(st.get("xfip")),
                       "eraMinus": r2(st.get("eraMinus"), 0), "fipMinus": r2(st.get("fipMinus"), 0),
                       "war": r2(st.get("war"), 1)}
            else:
                out = {"woba": r2(st.get("woba"), 3), "wrcPlus": r2(st.get("wRcPlus"), 0),
                       "war": r2(st.get("war"), 1)}
            out = {k: v for k, v in out.items() if v is not None}
            return out or None
    return None


def mlb_years(p):
    """該球員有大聯盟出賽的年份(當季 + 逐年表裡有 MLB 的年)。"""
    years = set()
    if (p.get("season_stats") or {}).get("MLB"):
        years.add(SEASON)
    for y, by_level in (p.get("prev_season") or {}).items():
        if (by_level or {}).get("MLB"):
            years.add(int(y))
    return sorted(years)


def main():
    cache = {}
    if CACHE.exists():
        try:
            cache = json.loads(CACHE.read_text(encoding="utf-8"))
        except Exception:
            cache = {}
    people = []
    people += json.loads(PLAYERS.read_text(encoding="utf-8"))["players"]
    try:
        people += json.loads(ALUMNI.read_text(encoding="utf-8"))["players"]
    except Exception:
        pass

    calls = hit = 0
    for p in people:
        pid = str(p["id"])
        if not pid.isdigit():
            continue          # 旅日/旅韓沒有這種 API
        years = mlb_years(p)
        if not years:
            continue
        slot = cache.setdefault(pid, {})
        for y in years:
            key = str(y)
            # 歷史球季的值不會變,抓過就不再抓;當季每天更新
            if key in slot and y != SEASON:
                continue
            adv = fetch_one(p["id"], p.get("role") == "pitcher", y)
            calls += 1
            if adv:
                slot[key] = adv
                hit += 1
            else:
                slot.pop(key, None)
            time.sleep(0.08)
        if not slot:
            cache.pop(pid, None)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0, sort_keys=True) + "\n", encoding="utf-8")

    # alumni.json 不經過 build_players,這裡直接掛上去。生涯 WAR 由逐年相加。
    try:
        blob = json.loads(ALUMNI.read_text(encoding="utf-8"))
    except Exception:
        blob = None
    if blob:
        n = 0
        for p in blob["players"]:
            slot = cache.get(str(p["id"]))
            if not slot:
                continue
            for y, adv in slot.items():
                lv = (p.get("prev_season") or {}).get(y, {}).get("MLB")
                if lv:
                    lv["adv"] = adv
            wars = [a["war"] for a in slot.values() if a.get("war") is not None]
            if wars and (p.get("career") or {}).get("MLB"):
                p["career"]["MLB"]["war"] = round(sum(wars), 1)
            n += 1
        ALUMNI.write_text(json.dumps(blob, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"  掛上歷代球員進階數據:{n} 人")
    n_players = len(cache)
    n_years = sum(len(v) for v in cache.values())
    print(f"進階數據:呼叫 {calls} 次,{n_players} 人 / {n_years} 個球季有資料 → {CACHE.name}")


if __name__ == "__main__":
    main()
