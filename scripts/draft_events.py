"""
事件摘要的待寫清單 → scripts/events_draft.json
=============================================
把「官方異動與逐場資料都推不出來、但多家媒體都報」的消息分群列出來,給人寫成
scripts/events.json 的一筆事件。

**這支腳本不寫內容,只做分群與列出處。** 事件摘要必須由人讀過各家報導後,用自己的
話陳述事實 —— 事實不受著作權保護,表達受保護,所以可以整合事實、不能改寫句子。
自動生成摘要等於把別人的內文洗一遍,那是 Google 明講的 scaled content abuse,
這個站的流量賭不起。

分群方式:同一天、標題共用足夠多的關鍵詞就視為同一件事(亞運名單那種橫跨數日、
牽涉十幾位球員的大事,人看一眼就併得起來,不必把分群做得太聰明)。

執行:python3 scripts/draft_events.py
"""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "public" / "data"
OUT = ROOT / "scripts" / "events_draft.json"
MIN_SOURCES = 2          # 只有一家報的先不列,通常是特寫而非事件


def load(p, key=None):
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d.get(key, d) if key else d
    except Exception:
        return [] if key else {}


def main():
    news = load(DATA / "news.json", "items")
    players = load(DATA / "players.json", "players")
    if not news or not players:
        print("缺 news.json 或 players.json")
        sys.exit(1)

    by_id = {str(p["id"]): p for p in players}

    from datetime import date as _d, timedelta as _td

    def shift(ds, n):
        y, m, dd = map(int, ds.split("-"))
        return (_d(y, m, dd) + _td(days=n)).isoformat()

    # 站上自己推得出來的日子(有逐場紀錄、或有官方異動)不必寫事件摘要 ——
    # 王彥程那場先發、費爾柴德遭 DFA,消息頁本來就由本站資料寫成了。
    # 旅美逐場用美國日期、媒體用台灣日期,所以前後各放寬一天。
    from datetime import date as _d, timedelta as _td
    def shift(ds, n):
        y, m, dd = map(int, ds.split("-"))
        return (_d(y, m, dd) + _td(days=n)).isoformat()

    # 已經寫成事件的,前後三天都算涵蓋(亞運名單那件事橫跨 9/05–9/08)
    written_days = set()
    for e in load(ROOT / "scripts" / "events.json", "events"):
        for pid in e.get("players", []):
            for off in range(-3, 4):
                written_days.add((str(pid), shift(e.get("date"), off)))

    derived = set()
    # 旅日/旅韓沒有官方異動來源,升降靠 build_players 判定的 moves.json
    for mv in load(DATA / "moves.json") or []:
        derived.add((str(mv.get("id")), mv.get("date")))
    for p in players:
        for g in p.get("game_logs", []):
            for off in (0, 1):
                derived.add((str(p["id"]), shift(g["date"], off)))
    for t in load(DATA / "transactions.json", "items"):
        if t.get("big"):
            for off in (-1, 0, 1):
                derived.add((str(t["id"]), shift(t["date"], off)))
    groups = defaultdict(lambda: {"items": [], "players": set()})
    for n in news:
        tagged = [by_id[str(x["id"])] for x in n.get("players", []) if str(x["id"]) in by_id]
        if not tagged:
            continue
        if any((str(p["id"]), n["date"]) in written_days for p in tagged):
            continue
        if all((str(p["id"]), n["date"]) in derived for p in tagged):
            continue
        # 分群鍵:日期 + 標題裡出現的球員名(同一件事通常點名同一批人)
        names = tuple(sorted(p["name"] for p in tagged if p["name"] in (n.get("title") or "")))
        key = (n["date"], names or tuple(sorted(p["name"] for p in tagged))[:1])
        g = groups[key]
        g["items"].append(n)
        g["players"].update(str(p["id"]) for p in tagged)

    drafts = []
    for (date, names), g in groups.items():
        srcs, seen = [], set()
        for n in g["items"]:
            if n.get("source") and n["source"] not in seen:
                seen.add(n["source"])
                srcs.append({"name": n["source"], "url": n["url"]})
        if len(srcs) < MIN_SOURCES:
            continue
        drafts.append({
            "date": date,
            "_關於": list(names),
            "_家數": len(srcs),
            "_各家標題": [n["title"] for n in g["items"]][:12],
            "id": "",
            "title": "",
            "body": [""],
            "players": sorted(g["players"]),
            "sources": srcs,
        })

    drafts.sort(key=lambda d: (d["_家數"], d["date"]), reverse=True)
    OUT.write_text(json.dumps(
        {"_說明": "待寫的事件。挑要寫的複製到 scripts/events.json,填好 id/title/body 後刪掉 _ 開頭的欄位。"
                  "body 請自己寫事實,不要抄任何一家的句子。",
         "drafts": drafts}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"完成:{OUT} — {len(drafts)} 群待寫(門檻 {MIN_SOURCES} 家以上報導)")
    for d in drafts[:8]:
        print(f"  {d['date']} {len(d['sources'])} 家 {'/'.join(d['_關於']) or '?'} — {d['_各家標題'][0][:40]}")


if __name__ == "__main__":
    main()
