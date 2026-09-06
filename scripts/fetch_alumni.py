"""
歷代旅外球員(已離開大聯盟體系者)資料抓取
==========================================
定位:把站從「現役每日戰報」延伸成「旅外球員的參考資料庫」。王建民、陳偉殷、
郭泓志這些人的搜尋量遠大於任何現役球員,但站上原本完全沒有他們。

作法:MLB Stats API 支援用球季列出該季所有球員,逐年掃 birthCountry 就能得到
**歷代**大聯盟台灣球員名單(1990 起掃到今年,不必人工維護)。名單存進
scripts/alumni_roster.json 當快取,之後每天只補掃最近兩季(便宜)找新面孔;
要重掃全部用 `--discover`。

資料深度:季級(逐年 + 生涯合計 + 各層級),不含逐場 —— 逐場資料量是季級的
數十倍,等資料架構拆檔後再說。

現役球員(mlb.json 已有的)會被排除,避免同一人出現兩次。

輸出:public/data/alumni.json
執行: python3 scripts/fetch_alumni.py [--discover]
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_data import (API, SEASON, SPORTS, TAIWAN_LABELS, get,   # noqa: E402
                        height_cm, weight_kg, season_stat_dict)
from build_players import slugify, localize_teams, fill_whip       # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ROSTER_PATH = ROOT / "scripts" / "alumni_roster.json"
NAME_MAP_PATH = ROOT / "scripts" / "name_map.json"
ACTIVE_PATH = ROOT / "public" / "data" / "mlb.json"
PLAYERS_PATH = ROOT / "public" / "data" / "players.json"
OUTPUT_PATH = ROOT / "public" / "data" / "alumni.json"

FIRST_SEASON = 1990   # 台灣球員登上大聯盟是 2002(陳金鋒),往前多掃十餘年當保險


def discover(seasons):
    """逐季列出大聯盟球員,挑 birthCountry 是台灣的。回傳 {id: {name_en, seasons}}。"""
    found = {}
    for yr in seasons:
        data = get(f"{API}/sports/1/players?season={yr}")
        if not data:
            continue
        for p in data.get("people", []):
            if p.get("birthCountry") in TAIWAN_LABELS:
                e = found.setdefault(str(p["id"]), {"name_en": p.get("fullName", ""), "seasons": []})
                e["seasons"].append(yr)
        time.sleep(0.1)
    return found


def load_roster():
    if ROSTER_PATH.exists():
        raw = json.loads(ROSTER_PATH.read_text(encoding="utf-8"))
        return {k: v for k, v in raw.get("players", {}).items()}
    return {}


def save_roster(roster):
    ROSTER_PATH.write_text(json.dumps({
        "_說明": "歷代大聯盟台灣球員名單(由 fetch_alumni.py --discover 掃 MLB Stats API 的 "
                 "birthCountry 產生,非人工維護)。每日跑只補掃最近兩季;要重掃全部用 --discover。"
                 "中文名放 scripts/name_map.json(與現役共用同一份 id→中文名對照)。",
        "players": dict(sorted(roster.items(), key=lambda kv: min(kv[1]["seasons"]))),
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def career_blocks(pid, group):
    """逐年 + 生涯合計(不限年份,與 fetch_data 的近 N 年版本不同)。"""
    is_pitcher = group == "pitching"
    history, career = {}, {}
    for sport_id, level in SPORTS.items():
        data = get(f"{API}/people/{pid}/stats?stats=yearByYear&group={group}&sportId={sport_id}")
        if data:
            by_year = {}
            for block in data.get("stats", []):
                for s in block.get("splits", []):
                    yr = str(s.get("season", ""))
                    if not yr:
                        continue
                    slot = by_year.setdefault(yr, {"total": None, "single": None, "teams": []})
                    tm = (s.get("team") or {}).get("name")
                    if tm is None:      # 該年多隊時的年度總計列
                        slot["total"] = s.get("stat", {})
                    else:
                        slot["teams"].append(tm)
                        slot["single"] = s.get("stat", {})
            for yr, slot in by_year.items():
                stat = slot["total"] or slot["single"]
                if not stat:
                    continue
                d = season_stat_dict(stat, is_pitcher)
                if slot["teams"]:
                    d["team"] = "、".join(dict.fromkeys(slot["teams"]))
                history.setdefault(yr, {})[level] = d
        data = get(f"{API}/people/{pid}/stats?stats=career&group={group}&sportId={sport_id}")
        if data:
            for block in data.get("stats", []):
                for s in block.get("splits", []):
                    stat = s.get("stat", {})
                    if stat:
                        career[level] = season_stat_dict(stat, is_pitcher)
        time.sleep(0.12)
    return history, career


def main():
    roster = load_roster()
    if "--discover" in sys.argv or not roster:
        seasons = range(FIRST_SEASON, SEASON + 1)
        print(f"全面掃描 {FIRST_SEASON}–{SEASON}（{len(list(seasons))} 季）…")
    else:
        seasons = range(SEASON - 1, SEASON + 1)   # 平時只補掃最近兩季找新面孔
    found = discover(seasons)
    new = [pid for pid in found if pid not in roster]
    for pid, e in found.items():
        cur = roster.setdefault(pid, {"name_en": e["name_en"], "seasons": []})
        cur["name_en"] = cur.get("name_en") or e["name_en"]
        cur["seasons"] = sorted(set(cur["seasons"]) | set(e["seasons"]))
    if new:
        print(f"新發現 {len(new)} 人:" + "、".join(roster[p]["name_en"] for p in new))
    save_roster(roster)

    # 退役球員的生涯數據不會再變,沒必要每天重抓 16 人(約 2 分鐘、上百次 API)。
    # 只有這幾種情況才真的抓:掃到新面孔、輸出檔不存在、檔案超過 7 天、或 --force。
    stale = True
    if OUTPUT_PATH.exists() and not new and "--force" not in sys.argv and "--discover" not in sys.argv:
        age = (time.time() - OUTPUT_PATH.stat().st_mtime) / 86400
        stale = age > 7
        if not stale:
            print(f"名單無變動、alumni.json 僅 {age:.1f} 天大 → 跳過重抓(要強制用 --force)")
            return

    # 現役球員已在 players.json,排除避免重複
    active_ids, active_slugs = set(), set()
    try:
        for p in json.loads(PLAYERS_PATH.read_text(encoding="utf-8"))["players"]:
            active_ids.add(str(p["id"]))
            if p.get("slug"):
                active_slugs.add(p["slug"])
    except Exception:
        pass
    name_map = json.loads(NAME_MAP_PATH.read_text(encoding="utf-8")) if NAME_MAP_PATH.exists() else {}

    players, no_zh, slugs = [], [], set()
    for pid, e in sorted(roster.items(), key=lambda kv: min(kv[1]["seasons"])):
        if pid in active_ids:
            continue
        info = get(f"{API}/people/{pid}")
        person = (info or {}).get("people", [{}])[0]
        pos = (person.get("primaryPosition") or {}).get("abbreviation", "")
        is_pitcher = pos == "P"
        group = "pitching" if is_pitcher else "hitting"
        history, career = career_blocks(pid, group)
        if not history and not career:
            print(f"  [略過] {e['name_en']}(id={pid}):查無任何數據")
            continue
        zh = (name_map.get(pid) or {}).get("zh")
        if not zh:
            no_zh.append(f"{e['name_en']}(id={pid})")
        slug = slugify(person.get("fullName") or e["name_en"])
        if not slug or slug in slugs or slug in active_slugs:
            print(f"  [錯誤] slug 無法決定或撞名:{e['name_en']} → {slug}", file=sys.stderr)
            sys.exit(1)
        slugs.add(slug)
        yrs = sorted(int(y) for y in history) or sorted(e["seasons"])
        players.append({
            "id": int(pid),
            "name": zh or person.get("fullName") or e["name_en"],
            "name_en": person.get("fullName") or e["name_en"],
            "slug": slug,
            "league": "mlb",
            "alumni": True,
            "role": "pitcher" if is_pitcher else "batter",
            "position": pos,
            "mlb_seasons": sorted(e["seasons"]),
            "first_year": yrs[0],
            "last_year": yrs[-1],
            "bio": {k: v for k, v in {
                "throws": {"L": "左", "R": "右", "S": "雙"}.get((person.get("pitchHand") or {}).get("code")),
                "bats": {"L": "左", "R": "右", "S": "雙"}.get((person.get("batSide") or {}).get("code")),
                "ht": height_cm(person.get("height")),
                "wt": weight_kg(person.get("weight")),
                "birth": person.get("birthDate", ""),
                "debut": person.get("mlbDebutDate", ""),
                "pos_zh": "投手" if is_pitcher else "野手",
            }.items() if v},
            "prev_season": {y: history[y] for y in sorted(history, reverse=True)},
            "career": career,
        })
        print(f"  {zh or e['name_en']:10} {yrs[0]}–{yrs[-1]}  逐年 {len(history)} 季、生涯 {len(career)} 層級")

    localize_teams(players)   # 球隊名走與現役共用的 scripts/team_zh.json
    fill_whip(players)
    OUTPUT_PATH.write_text(json.dumps({
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "players": players,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"完成:{OUTPUT_PATH}({len(players)} 人)")
    if no_zh:
        print(f"::warning::以下歷代球員沒有中文名,請補 scripts/name_map.json:{'、'.join(no_zh)}")


if __name__ == "__main__":
    main()
