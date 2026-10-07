"""
投手球種(pitch arsenal)抓取
============================
MLB Stats API 的 `stats=pitchArsenal` 提供每位投手各球種的使用球數與**平均**球速。

兩個關鍵細節:
1. **必須帶 sportId**,不帶只會回空;而且要掃過所有層級再合併 —— 球員的 level
   是「目前」層級,但本季可能在別的層級投過球(只查目前層級會少掉三分之一的人)。
2. 只有**有測速追蹤的球場**才有資料。實測 17 位旅美投手中 9 位有;
   1A／新人聯盟多半沒有。旅日、旅韓完全沒有這種 API。

**最快球速抓不到**:pitchArsenal 只給平均球速,pitchLog 沒有逐球速度欄位,
Baseball Savant 的 breakdown 也只有 release_speed(平均)。所以最快球速維持
人工維護在 scripts/bio_extra.json,兩者在頁面上分開標示,不可混為一談。

輸出:scripts/arsenal_cache.json(build_players 掛到 player.bio.pitches)
執行: python3 scripts/fetch_arsenal.py
"""

import json
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

API = "https://statsapi.mlb.com/api/v1"
SEASON = datetime.now().year
SPORT_IDS = (1, 11, 12, 13, 14, 16)   # MLB / 3A / 2A / 高階1A / 1A / 新人
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

ROOT = Path(__file__).resolve().parent.parent
PLAYERS_PATH = ROOT / "public" / "data" / "players.json"
CACHE_PATH = ROOT / "scripts" / "arsenal_cache.json"

# 球種中譯。查不到對照就留英文原名(顯眼好補),不自己造詞。
PITCH_ZH = {
    "Four-Seam Fastball": "四縫線速球", "Four-seam FB": "四縫線速球",
    "Fastball": "速球", "Sinker": "伸卡球", "Cutter": "卡特球",
    "Slider": "滑球", "Sweeper": "橫掃滑球", "Slurve": "曲滑球",
    "Curveball": "曲球", "Knuckle Curve": "彈指曲球", "Slow Curve": "慢速曲球",
    "Changeup": "變速球", "Split-Finger": "指叉球", "Splitter": "指叉球",
    "Forkball": "叉指球", "Screwball": "螺旋球", "Knuckleball": "蝴蝶球",
    "Eephus": "超慢速曲球", "Pitch Out": "故意四壞", "Intentional Ball": "故意四壞",
}

MPH_TO_KMH = 1.60934


def get(url):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=25) as r:
                return json.loads(r.read())
        except Exception:
            if attempt == 2:
                return None
            time.sleep(1.5 * (attempt + 1))


LAST_FAILED = False


def arsenal_for(pid, season=None):
    """跨層級合併同一位投手的球種。以球數加權平均球速,不是把各層級平均再平均。"""
    season = season or SEASON
    agg = {}
    global LAST_FAILED
    LAST_FAILED = False
    for sid in SPORT_IDS:
        data = get(f"{API}/people/{pid}/stats?stats=pitchArsenal&group=pitching&season={season}&sportId={sid}")
        if data is None:
            # 請求失敗 ≠ 該年沒資料。不標出來的話,主流程會往前一季退,頁面就顯示錯的年份
            LAST_FAILED = True
        for block in (data or {}).get("stats", []):
            for s in block.get("splits", []):
                st = s.get("stat") or {}
                t = st.get("type") or {}
                code = t.get("code")
                n = st.get("count") or 0
                if not code or not n:
                    continue
                a = agg.setdefault(code, {"desc": t.get("description", code), "n": 0, "spd": 0.0})
                a["n"] += n
                a["spd"] += (st.get("averageSpeed") or 0) * n
        time.sleep(0.05)
    if not agg:
        return []
    total = sum(a["n"] for a in agg.values())
    out = []
    for code, a in sorted(agg.items(), key=lambda kv: -kv[1]["n"]):
        out.append({
            "code": code,
            "name": PITCH_ZH.get(a["desc"], a["desc"]),
            "pct": round(a["n"] / total * 100),
            "kmh": round(a["spd"] / a["n"] * MPH_TO_KMH) if a["n"] else None,
        })
    return out


def main():
    players = json.loads(PLAYERS_PATH.read_text(encoding="utf-8"))["players"]
    pitchers = [p for p in players if p.get("role") == "pitcher" and str(p["id"]).isdigit()]
    cache = {}
    if CACHE_PATH.exists():
        try:
            cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            cache = {}
    hit = 0
    for p in pitchers:
        # 本季在沒測速的層級投球(1A/新人聯盟)就往前找最近一季有資料的(張弘稜 2024、
        # 林振瑋 2025)。season 會一起存,頁面標「2025 年資料」,不會被當成本季數字
        pitches, season, failed = [], None, False
        for yr in (SEASON, SEASON - 1, SEASON - 2):
            pitches = arsenal_for(p["id"], yr)
            if pitches:
                season = yr
                break
            if LAST_FAILED:          # 這一季抓失敗,不能當成「沒資料」往前退
                failed = True
                break
        if failed and not pitches:
            print(f"  {p['name']:9}(API 請求失敗,沿用上次的快取)")
            continue
        if pitches:
            cache[str(p["id"])] = {"season": season, "pitches": pitches}
            hit += 1
            top = "、".join(f'{x["name"]} {x["pct"]}%' for x in pitches[:3])
            print(f"  {p['name']:9}{len(pitches)} 種  {top}{'' if season == SEASON else f'({season} 年)'}")
        else:
            cache.pop(str(p["id"]), None)
            print(f"  {p['name']:9}(近三季皆無測速追蹤資料)")
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
    print(f"完成:{hit}/{len(pitchers)} 位旅美投手有球種資料 → {CACHE_PATH.name}")
    alumni_arsenal()
    missing = [p["name"] for p in players
               if p.get("role") == "pitcher" and not (p.get("bio") or {}).get("velo")]
    if missing:
        print(f"::notice::以下投手尚無最快球速(API 無此資料,需人工補 scripts/bio_extra.json):{'、'.join(missing)}")


ALUMNI_PATH = ROOT / "public" / "data" / "alumni.json"
ALUMNI_CACHE = ROOT / "scripts" / "arsenal_alumni_cache.json"
FIRST_TRACKED = 2008   # PITCHf/x 起;更早的球季 API 沒有球種資料


def alumni_arsenal():
    """歷代旅美投手的逐年球種與均速(2008 起有追蹤的球季)。退役球員的資料不會再變,
    快取在 arsenal_alumni_cache.json,只抓還沒抓過的年份;最後寫回 alumni.json 的
    player.arsenal = {年份: [球種...]}。fetch_alumni 會整檔重寫 alumni.json,所以
    每天都要重新掛一次(workflow 裡 fetch_arsenal 排在 fetch_alumni 之後)。"""
    try:
        blob = json.loads(ALUMNI_PATH.read_text(encoding="utf-8"))
    except Exception:
        return
    try:
        cache = json.loads(ALUMNI_CACHE.read_text(encoding="utf-8"))
    except Exception:
        cache = {}
    fetched = 0
    for p in blob.get("players", []):
        if p.get("role") != "pitcher" or not str(p.get("id", "")).isdigit():
            continue
        pid = str(p["id"])
        years = sorted(int(y) for y in (p.get("prev_season") or {}) if int(y) >= FIRST_TRACKED
                       and any(lv not in ("一軍", "二軍", "日職二軍", "韓職一軍") for lv in p["prev_season"][y]))
        c = cache.setdefault(pid, {})
        for y in years:
            if str(y) in c:
                continue
            c[str(y)] = arsenal_for(int(pid), y)   # 空 list 也存,代表「該年無追蹤」,下次不重抓
            fetched += 1
        by_year = {y: v for y, v in c.items() if v}
        if by_year:
            p["arsenal"] = dict(sorted(by_year.items(), key=lambda kv: kv[0], reverse=True))
        else:
            p.pop("arsenal", None)
    ALUMNI_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
    ALUMNI_PATH.write_text(json.dumps(blob, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    n = sum(1 for p in blob.get("players", []) if p.get("arsenal"))
    print(f"歷代投手球種:{n} 人有逐年資料(本次新抓 {fetched} 個球季)")


if __name__ == "__main__":
    main()
