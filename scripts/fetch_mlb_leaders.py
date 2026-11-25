#!/usr/bin/env python3
"""MLB 個人排行榜 → public/data/mlb_leaders.json(給 /mlb-leaders/ 頁用)。

資料來源:MLB Stats API /stats/leaders(官方排行,率類數據由官方套用規定打席/投球局)。
開季前當年還沒有資料時,自動退回上一季。全聯盟、美聯、國聯各取前 10。
用法:python3 scripts/fetch_mlb_leaders.py
"""
import datetime as dt
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = ROOT / "public" / "data" / "archive"  # 每季一份,給 /{頁}/{年}/ 歷年頁用
OUT = ROOT / "public" / "data" / "mlb_leaders.json"
URL = ("https://statsapi.mlb.com/api/v1/stats/leaders?leaderCategories={cats}&season={season}"
       "&sportId=1&limit=10&statGroup={group}{league}")
# (API 類別, 中文名, 小數位顯示照官方字串)
HITTING = [("homeRuns", "全壘打"), ("runsBattedIn", "打點"), ("battingAverage", "打擊率"),
           ("onBasePlusSlugging", "OPS"), ("hits", "安打"), ("stolenBases", "盜壘"),
           ("runs", "得分"), ("doubles", "二壘安打")]
PITCHING = [("earnedRunAverage", "防禦率"), ("strikeouts", "三振"), ("wins", "勝投"),
            ("saves", "救援成功"), ("walksAndHitsPerInningPitched", "WHIP")]
SCOPES = [("mlb", "", "全大聯盟"), ("al", "&leagueId=103", "美國聯盟"), ("nl", "&leagueId=104", "國家聯盟")]


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


def fetch(season):
    out = {}
    for key, lg, _ in SCOPES:
        cats = []
        for group, defs in (("hitting", HITTING), ("pitching", PITCHING)):
            d = get(URL.format(cats=",".join(c for c, _ in defs), season=season, group=group, league=lg))
            by = {c["leaderCategory"]: c for c in d.get("leagueLeaders") or [] if c.get("statGroup") == group}
            for c, zh in defs:
                rows = [{"rank": x.get("rank"), "id": (x.get("person") or {}).get("id"),
                         "name": (x.get("person") or {}).get("fullName"),
                         "team": (x.get("team") or {}).get("name"), "value": x.get("value")}
                        for x in (by.get(c) or {}).get("leaders") or []]
                cats.append({"key": c, "group": group, "name": zh, "rows": rows})
        out[key] = cats
    return out


# --season YYYY:回補指定球季,只寫 archive/,不動當季檔
SEASON_ARG = int(sys.argv[sys.argv.index("--season") + 1]) if "--season" in sys.argv else None

def main():
    year = SEASON_ARG or dt.date.today().year
    season = year
    data = fetch(season)
    if not any(c["rows"] for c in data["mlb"]) and not SEASON_ARG:
        season = year - 1
        data = fetch(season)
    n = sum(len(c["rows"]) for c in data["mlb"])
    if n < 100:
        sys.exit(f"排行榜資料不完整({n} 筆),不覆寫 {OUT.name}")
    end = (get(f"https://statsapi.mlb.com/api/v1/seasons/{season}?sportId=1").get("seasons") or [{}])[0].get("regularSeasonEndDate")
    _payload = json.dumps({
        "season": season, "final": bool(end) and dt.date.today().isoformat() > end, "regular_season_end": end,
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "scopes": [{"key": k, "name": zh} for k, _, zh in SCOPES], "leaders": data,
    }, ensure_ascii=False, indent=1)
    if not SEASON_ARG:
        OUT.write_text(_payload, encoding="utf-8")
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    (ARCHIVE / f"mlb_leaders_{json.loads(_payload)['season']}.json").write_text(_payload, encoding="utf-8")
    print(f"MLB 排行榜:{season} 球季,{n} 筆(全聯盟),寫入 {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
