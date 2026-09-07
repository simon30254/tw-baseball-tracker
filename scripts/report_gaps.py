#!/usr/bin/env python3
"""列出「有比賽但文章還沒寫逐場戰報」的清單。

逐場戰報是唯一不能自動生成的部分(要看 play-by-play、球速、賽後訪談),
但「哪幾場還沒寫」完全可以自動盤點 —— 這支只做盤點,不改任何文章。

判斷方式:長文的每則戰報都有一段 <p><strong>時間：</strong> 9/3</p>,
把這些日期跟 players.json 的 game_logs 對起來即可。

三條「不要亂報」的規則(都是實跑後才發現的):
① 短文(近期狀態表格式)根本沒有戰報區塊 → 標示為短文,不列缺口。
② 只列「比最新一則戰報還新」的比賽。更早的空缺多半是編輯看過後
   決定不寫的 0 安場,每天重報只會變成雜訊。要看全部用 --all。
③ 日期偏移:美國賽事的台灣日期 = 美國日期 +1,日韓賽事同日。這個以層級
   決定(見 OFFSET),不用整篇回推 —— 鄧愷威那篇早期用美國日期、近期改用
   台灣日期,整篇最佳解會被舊文拉去 +0,反而把已寫的當成缺口。
   改成:層級預設為主,只有「近期戰報」明顯支持另一個偏移時才覆蓋並註記。

用法: python3 report_gaps.py [--days=N] [--slug=xxx] [--all]
需環境變數 WP_USER / WP_APP_PASSWORD;PLAYERS_JSON 可選。
"""
import os, re, sys, json, base64, pathlib, time, datetime, urllib.request, urllib.error

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
API = "https://clutchgtime.com/wp-json/wp/v2/posts"
DAYS = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--days=")), 21))
ONLY = next((a.split("=")[1] for a in sys.argv if a.startswith("--slug=")), None)
ALL = "--all" in sys.argv
# 層級 → 台灣日期相對於 game_log 日期的偏移。美國賽事寫台灣日期(+1),日韓同日。
OFFSET = {"MLB": 1, "AAA": 1, "AA": 1, "High-A": 1, "A": 1, "Rookie": 1,
          "一軍": 0, "二軍": 0}
RECENT_WIN = 30   # 回推偏移時只看近這麼多天的戰報:早期的寫法可能跟現在不同

_wp = json.loads((pathlib.Path(__file__).resolve().parent / "wp_articles.json")
                 .read_text(encoding="utf-8"))["articles"]

def http(url):
    auth = base64.b64encode(
        f"{os.environ['WP_USER']}:{os.environ['WP_APP_PASSWORD']}".encode()).decode()
    hdr = {"User-Agent": UA, "Authorization": f"Basic {auth}", "Accept": "application/json, */*"}
    for _ in range(4):
        try:
            return json.load(urllib.request.urlopen(
                urllib.request.Request(url, headers=hdr), timeout=60))
        except urllib.error.HTTPError as e:
            print("   HTTP", e.code, e.read().decode()[:120]); return None
        except Exception:
            time.sleep(4)
    return None

TIME_P = re.compile(r"<strong>時間：</strong>\s*(\d{1,2})/(\d{1,2})")

def md(iso, off):
    d = datetime.date.fromisoformat(iso) + datetime.timedelta(days=off)
    return (d.month, d.day)

def pick_offset(logs, aset, level, asof):
    """層級預設優先;只有近期戰報明顯支持另一個偏移時才改用它。"""
    base = OFFSET.get(level, 1)
    win = (datetime.date.fromisoformat(asof) - datetime.timedelta(days=RECENT_WIN)).isoformat()
    recent = [g for g in logs if g["date"] >= win]
    hit = {off: sum(1 for g in recent if md(g["date"], off) in aset) for off in (0, 1)}
    other = 1 - base
    if hit[other] > hit[base]:
        return other, hit, True
    return base, hit, False

def line(g):
    if g.get("type") == "pitching" or g.get("ip") is not None:
        s = (f"{g.get('ip','?')}局 {g.get('h',0)}安 {g.get('r',0)}失 "
             f"{g.get('er',0)}責 {g.get('so',0)}K {g.get('bb',0)}BB")
        for k, t in (("win", " 勝投"), ("loss", " 敗投"), ("save", " 救援")):
            if g.get(k): s += t
        return s
    s = f"{g.get('ab',0)}打數{g.get('h',0)}安"
    for k, t in (("hr", "轟"), ("rbi", "打點"), ("r", "得分"),
                 ("bb", "保送"), ("so", "K"), ("sb", "盜")):
        if g.get(k): s += f" {g[k]}{t}"
    return s

def merge_same_day(logs):
    """雙重賽合成一列:一則戰報通常涵蓋兩場,分開列會有一場永遠補不掉。"""
    out = []
    for g in logs:
        if out and out[-1][0]["date"] == g["date"]:
            out[-1].append(g)
        else:
            out.append([g])
    return out

def run():
    src = os.environ.get("PLAYERS_JSON", "https://players.clutchgtime.com/data/players.json")
    blob = (json.load(urllib.request.urlopen(
        urllib.request.Request(src, headers={"User-Agent": UA}), timeout=40))
        if src.startswith("http") else json.load(open(src)))
    by = {p["name"]: p for p in blob["players"]}
    asof = blob.get("updated_at", "")[:10]
    cutoff = (datetime.date.fromisoformat(asof) - datetime.timedelta(days=DAYS)).isoformat()
    mode = "全部空缺" if ALL else "只列比最新戰報更新的比賽"
    print(f"逐場戰報缺口盤點｜資料 {asof}｜回看 {DAYS} 天(>= {cutoff})｜{mode}")
    total = 0
    for a in _wp:
        if ONLY and a["slug"] != ONLY:
            continue
        name = a["name"]
        p = by.get(name)
        if not p:
            print(f"  ⚠ {name}: players.json 查無此人"); continue
        # 專文釘死層級,但升降級後舊層級的比賽也算(例:鄭宗哲 MLB↔3A),所以看全部 game_logs
        logs = sorted((p.get("game_logs") or []), key=lambda g: g["date"], reverse=True)
        if not logs:
            print(f"  – {name}: 無 game_logs"); continue
        d = http(f"{API}?slug={a['slug']}&_fields=id&context=edit")
        if not d:
            print(f"  ⚠ {name}({a['slug']}): 找不到文章"); continue
        r = http(f"{API}/{d[0]['id']}?context=edit&_fields=content")
        if not r:
            continue
        arts = [(int(m.group(1)), int(m.group(2))) for m in TIME_P.finditer(r["content"]["raw"])]
        if not arts:
            print(f"  ○ {name}: 短文格式(無逐場戰報區塊),近況表已自動同步"); continue
        aset = set(arts)
        off, hit, flipped = pick_offset(logs, aset, a["level"], asof)
        groups = [g for g in merge_same_day(logs) if g[0]["date"] >= cutoff]
        gaps = [g for g in groups if md(g[0]["date"], off) not in aset]
        if not ALL and gaps:
            # 最新一則戰報對應的比賽日期 = 分界線;更早的空缺視為編輯已看過並跳過
            newest = next((g[0]["date"] for g in merge_same_day(logs)
                           if md(g[0]["date"], off) in aset), None)
            if newest:
                gaps = [g for g in gaps if g[0]["date"] > newest]
        tag = (f"日期+{off}{'(依近期戰報回推)' if flipped else ''}｜"
               f"近{RECENT_WIN}天命中 {hit[off]}｜文章 {len(arts)} 則")
        if not gaps:
            print(f"  = {name}: 沒有待補的新賽事（{tag}）"); continue
        total += len(gaps)
        print(f"  ✎ {name} 待補 {len(gaps)} 場（{tag}）  {a['slug']}")
        for grp in gaps:
            m, dd = md(grp[0]["date"], off)
            dh = "（雙重賽）" if len(grp) > 1 else ""
            vid = "  📺" if any((g.get("video") or {}).get("id") for g in grp) else ""
            body = " ／ ".join(line(g) for g in grp)
            print(f"       {m}/{dd}{dh}  {grp[0].get('level',''):5s} "
                  f"vs {grp[0].get('opponent','?'):8s} {body}{vid}")
    print(f"\n合計待補 {total} 場")

if __name__ == "__main__":
    run()
