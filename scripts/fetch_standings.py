#!/usr/bin/env python3
"""MLB 戰績排名 → public/data/standings.json(給 /standings/ 頁用)。

資料來源:MLB Stats API /standings(例行賽)。開季前當年還沒有資料時,自動退回上一季。
只存頁面要用的欄位;球隊中文名在 prerender 端用 scripts/team_zh.json 對照(全站單一來源)。

用法:python3 scripts/fetch_standings.py
"""
import datetime as dt
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "public" / "data" / "standings.json"
API = "https://statsapi.mlb.com/api/v1/standings?leagueId=103,104&season={season}&standingsTypes=regularSeason&hydrate=team"

LEAGUES = {103: "美國聯盟", 104: "國家聯盟"}
# 分區 id → (聯盟, 中文名, 排序)
DIVISIONS = {
    201: (103, "美聯東區", 1), 202: (103, "美聯中區", 2), 200: (103, "美聯西區", 3),
    204: (104, "國聯東區", 1), 205: (104, "國聯中區", 2), 203: (104, "國聯西區", 3),
}


def get(url):
    last = None
    for i in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "tw-baseball-tracker/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001 — 網路錯誤一律退避重試
            last = e
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"{url}: {last}")


def split(rec, kind):
    for s in (rec.get("records") or {}).get("splitRecords") or []:
        if s.get("type") == kind:
            return f"{s.get('wins', 0)}-{s.get('losses', 0)}"
    return ""


def streak(rec):
    s = rec.get("streak") or {}
    n, t = s.get("streakNumber"), s.get("streakType")
    if not n or t not in ("wins", "losses"):
        return ""
    return f"{n} 連{'勝' if t == 'wins' else '敗'}"


def clinch(rec):
    # MLB 標記:y 拿下分區、z 拿下分區且聯盟戰績最佳、w 外卡、x 確定晉級季後賽
    # 以標記為準:2026 年費城人 divisionChamp=True 但標記是 w、分區排第 2(API 欄位自相矛盾)
    ind = rec.get("clinchIndicator") or ""
    if ind in ("y", "z"):
        return "division"
    if ind == "w":
        return "wildcard"
    if ind == "x":
        return "playoff"
    if rec.get("divisionChamp") and rec.get("divisionLeader"):
        return "division"
    return "playoff" if rec.get("clinched") else None


def team_row(rec):
    t = rec.get("team") or {}
    return {
        "id": t.get("id"),
        "name_en": t.get("name"),
        "abbr": t.get("abbreviation"),
        "w": rec.get("wins"), "l": rec.get("losses"), "pct": rec.get("winningPercentage"),
        "gb": rec.get("gamesBack"), "wcgb": rec.get("wildCardGamesBack"),
        "div_rank": int(rec.get("divisionRank") or 0) or None,
        "wc_rank": int(rec.get("wildCardRank")) if rec.get("wildCardRank") else None,
        "g": rec.get("gamesPlayed"),
        "rd": rec.get("runDifferential"), "rs": rec.get("runsScored"), "ra": rec.get("runsAllowed"),
        "l10": split(rec, "lastTen"), "home": split(rec, "home"), "away": split(rec, "away"),
        "streak": streak(rec), "clinch": clinch(rec),
        "elim": rec.get("eliminationNumber"),
    }


def fetch(season):
    d = get(API.format(season=season))
    divs = []
    for r in d.get("records") or []:
        did = (r.get("division") or {}).get("id")
        if did not in DIVISIONS:
            continue
        lg, name, order = DIVISIONS[did]
        teams = sorted((team_row(x) for x in r.get("teamRecords") or []),
                       key=lambda x: (x["div_rank"] or 99))
        divs.append({"id": did, "league": lg, "name": name, "order": order, "teams": teams,
                     "updated": r.get("lastUpdated")})
    return divs


def main():
    year = dt.date.today().year
    season, divs = year, fetch(year)
    played = sum(t["g"] or 0 for d in divs for t in d["teams"])
    if not divs or played == 0:  # 開季前:當年還沒比賽,改用上一季
        season, divs = year - 1, fetch(year - 1)
        played = sum(t["g"] or 0 for d in divs for t in d["teams"])
    if len(divs) != 6 or sum(len(d["teams"]) for d in divs) != 30:
        sys.exit(f"戰績資料不完整({len(divs)} 個分區),不覆寫 {OUT.name}")
    # 用官方例行賽結束日判斷(雨延賽沒補的球隊只打 161 場,不能用「打滿 162 場」判斷)
    end = (get(f"https://statsapi.mlb.com/api/v1/seasons/{season}?sportId=1").get("seasons") or [{}])[0].get("regularSeasonEndDate")
    final = bool(end) and dt.date.today().isoformat() > end
    leagues = []
    for lg, name in LEAGUES.items():
        ds = sorted((d for d in divs if d["league"] == lg), key=lambda d: d["order"])
        wc = sorted((t for d in ds for t in d["teams"] if t["wc_rank"]), key=lambda t: t["wc_rank"])
        leagues.append({"id": lg, "name": name, "divisions": ds, "wildcard": wc})
    out = {
        "season": season, "final": final, "regular_season_end": end,
        "updated_at": max((d["updated"] or "") for d in divs),
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "leagues": leagues,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"MLB 戰績:{season} 球季{'(已結束)' if final else ''},{played // 2} 場,寫入 {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
