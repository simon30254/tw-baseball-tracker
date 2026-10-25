#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 scripts/team_zh.json 的隊名中譯重新套用到既有資料上,**不重抓**。
============================================================================
為什麼需要:三支抓取腳本(fetch_alumni / fetch_npb_alumni / fetch_kbo_alumni)與
build_players 都會呼叫 localize_teams,但那只在抓取時發生。改了 team_zh.json 之後,
既有的 alumni.json 要等下一次重抓才會更新 —— 而 `fetch_alumni.py --force` 曾經
把後段流程的資料(NPB/KBO 40 人、WAR 53 筆、球種 14 人)整批清掉,不能為了換隊名
去跑它。這支只改隊名字串,不碰任何其他欄位。

用法:
  python3 scripts/relocalize_teams.py            # dry-run,只列出會改什麼、還有誰沒對應
  python3 scripts/relocalize_teams.py --apply    # 寫回檔案
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_players import localize_teams          # noqa: E402

ROOT = Path(__file__).parent.parent
DATA = ROOT / "public" / "data"
# 只處理 alumni.json。
#   mlb/npb/kbo.json 是**原始抓取檔**,刻意保留英文原名 —— build_players 在合併成
#   players.json 時才中譯,所以改了 team_zh.json 只要重跑 build_players.py 就生效;
#   寫回原始檔反而會被下一次抓取蓋掉,也讓「原始資料」不再是原始的。
#   alumni.json 不一樣:它是 fetch_alumni 寫完就直接給 prerender 讀的成品,
#   中譯是在寫檔時套上去的,所以表改了就得在這裡原地重套。
TARGETS = ["alumni.json"]
APPLY = "--apply" in sys.argv


def main():
    for name in TARGETS:
        p = DATA / name
        if not p.exists():
            print(f"{name}: 不存在,跳過")
            continue
        blob = json.loads(p.read_text(encoding="utf-8"))
        players = blob.get("players") or []
        before = json.dumps(players, ensure_ascii=False, sort_keys=True)
        # season 只影響「當年」那幾個欄位(team/org/season_stats);歷年用各自的年份鍵,
        # 由 localize_teams 內部處理。
        localize_teams(players, blob.get("season"))
        after = json.dumps(players, ensure_ascii=False, sort_keys=True)
        changed = before != after
        print(f"{name}: {'有變更' if changed else '無變更'}")
        if changed and APPLY:
            blob["players"] = players
            p.write_text(json.dumps(blob, ensure_ascii=False, separators=(",", ":")),
                         encoding="utf-8")
            print(f"  → 已寫回 {p}")
    if not APPLY:
        print("\n(dry-run。要寫回請加 --apply)")


if __name__ == "__main__":
    main()
