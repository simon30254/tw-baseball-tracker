#!/usr/bin/env python3
"""MLB 歷屆世界大賽冠軍 + MVP/賽揚獎/新人王 → public/data/mlb_awards.json(給 /mlb-awards/ 系列頁用)。

資料來源:MLB Stats API
- 獎項:/awards/{ALMVP,NLMVP,ALCY,NLCY,ALROY,NLROY}/recipients(官方得獎名單)
- 世界大賽:/schedule/postseason/series?season=Y&gameTypes=W(以系列賽勝場判定冠軍)
- 隊名:/teams?sportId=1&season=Y(用「當年」的隊名,例如 1990 年代是 Montreal Expos 不是 Nationals)
歷史年份抓過就不再抓(存在檔內),每次只重抓最近兩季。
用法:python3 scripts/fetch_mlb_awards.py [--full]
"""
import datetime as dt
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "public" / "data" / "mlb_awards.json"
API = "https://statsapi.mlb.com/api/v1"
AWARDS = {"mvp": ("ALMVP", "NLMVP"), "cy": ("ALCY", "NLCY"), "roy": ("ALROY", "NLROY")}
FIRST_WS = 1903


def get(url):
    last = None
    for i in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "tw-baseball-tracker/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"{url}: {last}")


_teams = {}


def team_name(tid, season):
    if season not in _teams:
        _teams[season] = {t["id"]: t["name"] for t in get(f"{API}/teams?sportId=1&season={season}").get("teams") or []}
    return _teams[season].get(tid)


def world_series(season):
    d = get(f"{API}/schedule/postseason/series?season={season}&gameTypes=W&sportId=1")
    for s in d.get("series") or []:
        games = [g for g in s.get("games") or [] if (g.get("status") or {}).get("codedGameState") == "F"]
        if not games:
            continue
        last = games[-1]["teams"]
        a, h = last["away"], last["home"]
        aw, hw = (a.get("leagueRecord") or {}).get("wins", 0), (h.get("leagueRecord") or {}).get("wins", 0)
        need = 5 if season in (1903, 1919, 1920, 1921) else 4  # 這四年是九戰五勝制
        if max(aw, hw) < need:
            return {"status": "in_progress"}
        w, l = (a, h) if aw > hw else (h, a)
        ties = (w.get("leagueRecord") or {}).get("ties", 0)
        return {"champ_id": w["team"]["id"], "champ": w["team"]["name"], "runner_id": l["team"]["id"], "runner": l["team"]["name"],
                "result": f"{max(aw, hw)}-{min(aw, hw)}" + (f"-{ties}" if ties else ""), "games": len(games)}
    return None


def main():
    full = "--full" in sys.argv
    old = {}
    if OUT.exists() and not full:
        try:
            old = {y["season"]: y for y in json.loads(OUT.read_text(encoding="utf-8"))["years"]}
        except Exception:  # noqa: BLE001
            old = {}
    this = dt.date.today().year
    recips = {}
    for key, ids in AWARDS.items():
        for i, aid in enumerate(ids):
            for r in get(f"{API}/awards/{aid}/recipients?sportId=1").get("awards") or []:
                y = int(r["season"])
                recips.setdefault(y, {}).setdefault(key, [[], []])[i].append({
                    "id": (r.get("player") or {}).get("id"), "name": (r.get("player") or {}).get("nameFirstLast"),
                    "team_id": (r.get("team") or {}).get("id")})
    years = []
    for y in range(FIRST_WS, this + 1):
        if y in old and y < this - 1:
            years.append(old[y])
            continue
        ws = world_series(y)
        aw = recips.get(y, {})
        for key in aw:
            for lst in aw[key]:
                for p in lst:
                    p["team"] = team_name(p["team_id"], y) if p.get("team_id") else None
        rec = {"season": y, "ws": ws, "awards": aw}
        years.append(rec)
        print(y, (ws or {}).get("champ"), flush=True)
        time.sleep(0.2)
    # 驗證:近年獎項與冠軍不可缺
    last_full = this - 1
    chk = next(r for r in years if r["season"] == last_full)
    if not (chk["ws"] and chk["ws"].get("champ") and all(k in chk["awards"] for k in AWARDS)):
        sys.exit(f"{last_full} 資料不完整,不覆寫 {OUT.name}")
    # 現在的隊名(球團 id 不變):舊隊名沒有通用中譯時,頁面用「現在的中文隊名(當年英文隊名)」呈現
    cur = {t["id"]: t["name"] for t in get(f"{API}/teams?sportId=1&season={this}").get("teams") or []}
    OUT.write_text(json.dumps({"fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                               "current_teams": cur, "years": years}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"MLB 歷屆獎項:{len(years)} 季,寫入 {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
