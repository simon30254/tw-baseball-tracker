#!/usr/bin/env python3
"""clutchgtime 兩篇總表 pillar 文的「2026 〇〇成績」數字自動更新。

處理 /taiwan-mlb-players/ 與 /npb-taiwan-players/:每位球員 <h3> 下方那行
「2026 大聯盟成績：25 場、5 勝 6 敗、防禦率 4.35、68.1 局、67 次三振（截至 8/23）」
只就地替換數字與「截至」日期,不重寫句型、不碰球探評價與其他段落。
球員名或層級在 players.json 找不到 → 該行原封不動。
用法: python3 update_clutchgtime_hubs.py [--apply]   (預設乾跑)
需 WP_USER / WP_APP_PASSWORD;PLAYERS_JSON 可選(預設抓正式站)。"""
import os, re, sys, json, base64, urllib.request, urllib.error, time, datetime
APPLY = "--apply" in sys.argv
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
API = "https://clutchgtime.com/wp-json/wp/v2/posts"
TODAY = os.environ.get("CT_TODAY") or datetime.date.today().isoformat()
_y,_m,_d = (int(x) for x in TODAY.split("-"))
HUBS = ["taiwan-mlb-players", "npb-taiwan-players"]
AS_M, AS_D = _m, _d   # 「截至」日期,run() 會依 players.json 的 updated_at 覆寫
# 文章裡的層級寫法 → players.json 的 season_stats key
LEVELS = {"大聯盟":"MLB","3A":"AAA","2A":"AA","高A":"High-A","1A":"A","新人聯盟":"Rookie",
          "一軍":"一軍","二軍":"二軍"}
LINE = re.compile(r"2026\s*(" + "|".join(map(re.escape, LEVELS)) + r")\s*成績：(.*?)（截至[^）]*）")
H3   = re.compile(r"<h3[^>]*>(.*?)</h3>", re.S)

def http(url, data=None, method="GET"):
    auth=base64.b64encode(f"{os.environ['WP_USER']}:{os.environ['WP_APP_PASSWORD']}".encode()).decode()
    hdr={"User-Agent":UA,"Authorization":f"Basic {auth}","Accept":"application/json, */*"}
    if data is not None:
        hdr["Content-Type"]="application/json"; hdr["Referer"]="https://clutchgtime.com/wp-admin/"
        data=json.dumps(data,ensure_ascii=False).encode("utf-8")
    for a in range(4):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(url,data=data,headers=hdr,method=method),timeout=60))
        except urllib.error.HTTPError as e: print("   HTTP",e.code,e.read().decode()[:120]); return None
        except Exception: time.sleep(4)
    return None

def sub_num(txt, pat, val):
    """只替換既有欄位的數字;該欄位不存在於句子裡就不動。"""
    if val in (None, ""): return txt, False
    new, n = re.subn(pat, lambda m: m.group(0).replace(m.group(1), str(val), 1), txt, count=1)
    return (new, n>0 and new!=txt)

def rebuild(body, s):
    """就地更新一行成績裡的各個數字。回傳 (新句子, 是否有變)。"""
    out=body; ch=False
    fields=[
        (r"(\d+)\s*場",            s.get("g")),
        (r"(\d+)\s*勝",            s.get("w")),
        (r"(\d+)\s*敗",            s.get("l")),
        (r"防禦率\s*([\d.]+)",      s.get("era")),
        (r"([\d.]+)\s*局",         s.get("ip")),
        (r"(\d+)\s*次三振",         s.get("so")),
        (r"(\d+)\s*打數",          s.get("ab")),
        (r"(\d+)\s*安打",          s.get("h")),
        (r"(\d+)\s*轟",            s.get("hr")),
        (r"(\d+)\s*打點",          s.get("rbi")),
        (r"打擊率\s*(\.?\d[\d.]*)", s.get("avg")),
        (r"OPS\s*(\.?\d[\d.]*)",   s.get("ops")),
    ]
    for pat,val in fields:
        out,c = sub_num(out, pat, val); ch = ch or c
    return out, ch

def run():
    src=os.environ.get("PLAYERS_JSON","https://players.clutchgtime.com/data/players.json")
    blob=(json.load(urllib.request.urlopen(urllib.request.Request(src,headers={"User-Agent":UA}),timeout=40)) if src.startswith("http") else json.load(open(src)))
    by={p["name"]:p for p in blob["players"]}
    # 「截至」用資料本身的抓取日,不用今天 —— 抓取是台灣早上跑的,涵蓋到前一天的美國賽事,
    # 寫今天會高估。「最後更新」則維持今天(文章確實在今天被改動)。
    global AS_M, AS_D
    try:
        _a = blob.get("updated_at","")[:10].split("-"); AS_M, AS_D = int(_a[1]), int(_a[2])
    except Exception:
        AS_M, AS_D = _m, _d
    print(f"[{'APPLY' if APPLY else 'DRY-RUN'}] 最後更新 {_m}/{_d}｜資料截至 {AS_M}/{AS_D} | pillar {len(HUBS)} 篇")
    for slug in HUBS:
        d=http(f"{API}?slug={slug}&_fields=id&context=edit")
        if not d: print(f"  ⚠ {slug}: 找不到文章"); continue
        r=http(f"{API}/{d[0]['id']}?context=edit&_fields=content")
        if not r: continue
        raw=r["content"]["raw"]
        # 每行成績歸屬於它前面最近的一個 <h3>(=球員名)
        heads=[(m.start(), re.sub(r"<[^>]+>","",m.group(1)).strip()) for m in H3.finditer(raw)]
        pieces=[]; last=0; hit=miss=0
        for m in LINE.finditer(raw):
            name=None
            for pos,h in heads:
                if pos<m.start(): name=h
                else: break
            lv=LEVELS[m.group(1)]
            p=by.get(name); s=((p or {}).get("season_stats") or {}).get(lv)
            if not s:
                miss+=1; print(f"    – {name}／{m.group(1)}: 無對應數據,不動"); continue
            newbody,ch=rebuild(m.group(2), s)
            # 「截至」日期沿用原句型(8/23 或 8 月 23 日)
            asof = f"（截至 {AS_M}/{AS_D}）" if "/" in m.group(0)[m.group(0).rfind("（截至"):] else f"（截至 {AS_M} 月 {AS_D} 日）"
            new = f"2026 {m.group(1)}成績：{newbody}{asof}"
            if new==m.group(0): continue
            hit+=1
            if ch: print(f"    ✎ {name}／{m.group(1)}: {re.sub(r'\s+',' ',m.group(2)).strip()}\n            → {re.sub(r'\s+',' ',newbody).strip()}")
            pieces.append(raw[last:m.start()]); pieces.append(new); last=m.end()
        pieces.append(raw[last:]); new_raw="".join(pieces)
        new_raw=re.sub(r"最後更新：(\d{4}) 年 \d{1,2} 月 \d{1,2} 日", rf"最後更新：\1 年 {_m} 月 {_d} 日", new_raw)
        new_raw=re.sub(r"資料截至台灣時間 \d{1,2} 月 \d{1,2} 日", f"資料截至台灣時間 {AS_M} 月 {AS_D} 日", new_raw)
        new_raw=re.sub(r"資料截至 \d{1,2} 月 \d{1,2} 日", f"資料截至 {AS_M} 月 {AS_D} 日", new_raw)
        if new_raw==raw: print(f"  = {slug}: 已是最新（{miss} 行無數據）"); continue
        print(f"  ✎ {slug}: 更新 {hit} 行成績（{miss} 行無數據不動）")
        if APPLY:
            print("     →","✅" if http(f"{API}/{d[0]['id']}",data={"content":new_raw},method="POST") else "❌")
if __name__=="__main__": run()
