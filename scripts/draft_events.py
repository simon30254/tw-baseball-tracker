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


# 逐場資料推不出來的事。derived 的邏輯是「這位球員那天有出賽,所以我們寫得出來」,
# 但同一天同一個人可以同時有「我們寫得出來的事」(他投了幾局)和「我們寫不出來的事」
# (他退出亞運)。潘文輝 9/18 亞運撞期、9/20 確定退出都是這樣被吞掉的,兩則各有
# 五家以上報導卻一次都沒進草稿。
#
# 這裡**只用來把被 derived 蓋掉的東西救回來**,不是用來過濾 —— 方向跟記憶裡
# 「不要加棒球關鍵字白名單」那個教訓相反:白名單當過濾器會誤殺真新聞,當救援清單
# 最壞的情況只是多一筆待寫草稿,由人判斷後略過。
NON_GAME = (
    # 國家隊:站上完全沒有這類資料
    "亞運", "奧運", "經典賽", "國家隊", "中華隊", "代表隊", "徵召",
    # 錢與約:站上完全沒有
    "合約", "簽約", "續約", "年薪", "薪資", "自由球員", "入札", "轉隊", "加盟", "退休",
    # 傷勢細節:旅美的傷兵名單有官方異動,旅日旅韓沒有
    "開刀", "手術", "復健", "傷勢",
    # 獎項:站上沒有
    "獲獎", "獎項", "得獎", "頒獎",
    # 生涯里程碑:逐場只寫得出那天的數字,寫不出「這是他第一次」
    "初登板", "初先發",
)

# 刻意**不**放進來的詞,以及原因:
#   紀錄/名單/首度 —— 台灣體育標題幾乎每則都有(「堆高台將紀錄」「季後賽名單」),
#     放進來會變成全部 45 群都被救回,等於這個機制沒作用
#   升上/下放/DFA/指定讓渡 —— 旅美已由 transactions.json 的官方異動涵蓋,
#     旅日旅韓的升降由 moves.json 推定,都不需要靠媒體標題救


def non_game_hit(item):
    """標題裡有沒有逐場資料交代不了的事。回傳命中的詞,供草稿標註。

    **只看標題**:摘要動輒兩百字、什麼都提到,拿來比對會把「今日賽事預告與轉播」
    這種整理文也救回來(它順帶提了亞運)。標題才是那則在講什麼。
    """
    return next((w for w in NON_GAME if w in (item.get("title") or "")), None)


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

    # 已經寫成事件的當天(±1 給時差)算涵蓋。**不要放寬到 ±3** —— 那會把事件之後
    # 才發生的新發展一起當成「寫過了」,亞運那件事就這樣吞掉了「養樂多放行徐翔聖」。
    written_days = set()
    for e in load(ROOT / "scripts" / "events.json", "events"):
        start = e.get("from") or shift(e["date"], -1)
        # updated:後續已寫進該事件,涵蓋到那天為止
        last = e.get("updated") if (e.get("updated") or "") > e["date"] else e["date"]
        end = shift(last, 1)
        for pid in e.get("players", []):
            d = start
            while d <= end:
                written_days.add((str(pid), d))
                d = shift(d, 1)

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
        # 有逐場資料就跳過 —— 除非這則講的是逐場資料交代不了的事
        hit = non_game_hit(n)
        if not hit and all((str(p["id"]), n["date"]) in derived for p in tagged):
            continue
        if hit:
            n = {**n, "_救回": hit}
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
        rescued = sorted({x["_救回"] for x in g["items"] if x.get("_救回")})
        # 被救回的仍要 2 家以上。原本放寬到 1 家,結果單一媒體的側寫、專訪、
        # 賽事預告整理全湧進來(25 群裡 19 群是單一來源),人得逐則篩,等於沒省事。
        # 真正的事件本來就會有多家跟進:潘文輝退出亞運 9 家、陳睦衡初登板 8 家。
        if len(srcs) < MIN_SOURCES:
            continue
        drafts.append({
            "date": date,
            "_關於": list(names),
            "_家數": len(srcs),
            "_逐場推不出來": rescued or None,
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
