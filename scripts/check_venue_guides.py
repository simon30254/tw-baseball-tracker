#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
核對主站的球場攻略與 scripts/venue_guides.json 的對照是否同步。
============================================================================
為什麼需要這支:2026-11-04 我拿 10-28 盤的「缺口清單」去判斷,結果 Comerica Park
的攻略其實 10-31 就上線了 —— 主站多了球場,追蹤站的對照沒跟上,兩位台將的球員頁
就一直連著「赴美看球總覽」而不是他們自己的主場。那個缺口清單是人工盤的,
會隨主站發文而過期,所以改成每天自動核對。

四件事:
  ① 對照裡的標題與主站現況不一致 → 可用 --apply 直接更新(標題是從 API 讀的)
  ② 對照裡的網址在主站找不到 → 大聲示警(連結可能已死)
  ③ 主站有 `-guide` 文章但對照沒收 → 列為候選,附上它可能對應哪支球團
  ④ 現役球員裡還落在「聯盟總覽」的 → 讓人看得出補哪一座最有價值

只示警不中斷(exit 0)。網路不通就跳過 —— 主站掛在 Bluehost,偶發連不上是常態,
不該因此讓資料流程失敗。

執行:python3 scripts/check_venue_guides.py [--apply]
"""
import json
import re
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
BASE = "https://clutchgtime.com"
UA = {"User-Agent": "Mozilla/5.0 (compatible; tw-baseball-tracker venue-guide check)"}
APPLY = "--apply" in sys.argv


def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read())
        except Exception as e:
            if i == tries - 1:
                raise e
    return None


def fetch_guides():
    """主站所有 slug 結尾為 -guide 的已發布文章/頁面 → {url: title}"""
    out = {}
    for typ in ("posts", "pages"):
        page = 1
        while True:
            url = f"{BASE}/wp-json/wp/v2/{typ}?per_page=100&page={page}&_fields=slug,link,title"
            try:
                rows = get(url)
            except urllib.error.HTTPError as e:
                if e.code == 400:      # 超出頁數
                    break
                raise
            if not rows:
                break
            for r in rows:
                if r["slug"].endswith("-guide"):
                    t = r["title"]
                    out[r["link"]] = t["rendered"] if isinstance(t, dict) else t
            if len(rows) < 100:
                break
            page += 1
    return out


def main():
    p = ROOT / "scripts" / "venue_guides.json"
    cfg = json.loads(p.read_text(encoding="utf-8"))
    teams = cfg.get("teams", {})
    leagues = cfg.get("leagues", {})

    try:
        live = fetch_guides()
    except Exception as e:
        print(f"主站 WP API 連不上({e}),跳過球場攻略核對")
        return 0
    # leagues 的退路有的指向 /topics/ 專題頁(韓職那筆),那不是 -guide 結尾,
    # 不會出現在上面的清單裡 —— 單獨補查,否則會被誤報成「網址找不到」。
    for v in leagues.values():
        u = v.get("url")
        if u and u not in live and "/topics/" in u:
            try:
                slug = u.rstrip("/").split("/")[-1]
                rows = get(f"{BASE}/wp-json/wp/v2/pages?slug={slug}&_fields=link,title")
                if rows:
                    t = rows[0]["title"]
                    live[rows[0]["link"]] = t["rendered"] if isinstance(t, dict) else t
            except Exception:
                pass
    print(f"主站 -guide 文章:{len(live)} 篇;對照:{len(teams)} 支球團 + {len(leagues)} 個聯盟退路")

    warn = []

    # ① 標題漂移 ② 網址消失
    # **要檢查的範圍必須和 --apply 會改的範圍一致** —— 原本只檢查 teams、
    # 卻連 leagues 一起改,結果它會修掉自己沒報出來的東西(MLB 支柱頁的標題在
    # 加進 Daikin Park 後從「6 座熱門球場」變成「7 座」,就是這樣被默默改掉的)。
    targets = [(f"teams:{k}", v) for k, v in sorted(teams.items())] + \
              [(f"leagues:{k}", v) for k, v in sorted(leagues.items())]
    changed, missing = [], []
    for key, v in targets:
        alt = v.get("alt")
        pairs = [(v.get("url"), v.get("title"), key)]
        if alt:
            pairs.append((alt.get("url"), alt.get("title"), key + "(第二主場)"))
        for u, t, label in pairs:
            if u not in live:
                missing.append(f"{label}: {u}")
            elif live[u] != t:
                changed.append((label, u, t, live[u]))

    if changed:
        print(f"\n■ 標題與主站不一致:{len(changed)}")
        for label, u, old, new in changed:
            print(f"   {label}\n     舊:{old}\n     新:{new}")
        if APPLY:
            for key, v in teams.items():
                if v.get("url") in live:
                    v["title"] = live[v["url"]]
                if v.get("alt", {}).get("url") in live:
                    v["alt"]["title"] = live[v["alt"]["url"]]
            for v in leagues.values():
                if v.get("url") in live:
                    v["title"] = live[v["url"]]
            p.write_text(json.dumps(cfg, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            print("   → 已更新標題")
        else:
            warn.append(f"對照表有 {len(changed)} 筆標題與主站不一致(跑 --apply 可自動更新)")

    if missing:
        print(f"\n■ 對照的網址在主站找不到:{len(missing)}")
        for m in missing:
            print(f"   {m}")
        warn.append(f"對照表有 {len(missing)} 個網址在主站找不到,連結可能已死")

    # ③ 主站有、對照沒收
    mapped = {v.get("url") for v in teams.values()} | {v.get("alt", {}).get("url") for v in teams.values() if v.get("alt")}
    mapped |= {v.get("url") for v in leagues.values()}
    # 球場攻略才算候選。排除兩類:
    #   /topics/ 底下的是專題彙整頁(球種與投球技術專題也叫 -guide,但跟球場無關);
    #   購票、座位、入場規定、賽程、應援、行程這類通則文不對應單一球場。
    SKIP = ("ticket", "seat", "rules", "schedule", "cheering", "trip", "travel",
            "league", "npb-baseball")
    cand = [(u, t) for u, t in sorted(live.items())
            if u not in mapped and "/topics/" not in u and not any(s in u for s in SKIP)]
    if cand:
        print(f"\n■ 主站有球場攻略但對照沒收:{len(cand)}")
        for u, t in cand:
            print(f"   {t[:56]}\n     {u}")
        warn.append(f"主站有 {len(cand)} 篇球場攻略還沒進對照表(補上後球員頁會自動切成主場連結)")

    # ④ 還落在聯盟總覽的現役球員
    try:
        players = json.loads((ROOT / "public" / "data" / "players.json").read_text(encoding="utf-8"))["players"]
    except Exception:
        players = []
    LEVELS = {"MLB", "一軍"}
    fallback = [(pl["name"], pl.get("league"), pl.get("org")) for pl in players
                if pl.get("level") in LEVELS and f"{pl.get('league')}:{pl.get('org')}" not in teams]
    if fallback:
        print(f"\n■ 仍落在聯盟總覽的大聯盟/一軍球員:{len(fallback)}")
        for n, lg, org in fallback:
            print(f"   {n}（{lg}:{org}）")

    if not (changed or missing or cand):
        print("\n對照表與主站同步 ✓")
    for w in warn:
        print(f"::warning title=球場攻略對照::{w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
