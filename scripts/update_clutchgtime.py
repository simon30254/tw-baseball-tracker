#!/usr/bin/env python3
"""clutchgtime 球員文章「快速整理表」+ 日期 自動更新(安全版)。
只重算結構化總結表、且每篇釘死對應層級;不碰評價/背景/逐場戰報。
用法: python3 update_clutchgtime.py [--apply]   (預設乾跑)
需環境變數 WP_USER / WP_APP_PASSWORD;PLAYERS_JSON 可選(預設抓正式站)。"""
import os, re, sys, json, base64, urllib.request, urllib.error, time, datetime
APPLY = "--apply" in sys.argv
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
API = "https://clutchgtime.com/wp-json/wp/v2/posts"
TODAY = os.environ.get("CT_TODAY") or datetime.date.today().isoformat()
_y,_m,_d = TODAY.split("-"); DATE_ZH = f"{int(_m)} 月 {int(_d)} 日"

# 每篇文章:球員名 + 釘死的層級(該文章在講哪個層級的成績)
ARTICLES = [
 ("kai-wei-teng-2026","鄧愷威","MLB"), ("cheng-tsung-che-2026","鄭宗哲","MLB"),
 ("hao-yu-lee-2026","李灝宇","MLB"), ("2026-sun-yi-lei","孫易磊","一軍"),
 ("jo-hsi-hsu-2026","徐若熙","一軍"), ("lin-an-ko-2026","林安可","一軍"),
 ("wang-yen-cheng-2026","王彥程","一軍"), ("corbin-carroll-2026","柯賓·卡洛爾","MLB"),
 ("yu-min-lin-2026","林昱珉","AAA"), ("chen-wei-lin-2026","林振瑋","AA"),
 ("chia-hao-sung-2026","宋家豪","一軍"),
]
def wl(s): return f"{s.get('w',0)}–{s.get('l',0)}"
HEADER = {"打數":"ab","安打":"h","打擊率":"avg","全壘打":"hr","打點":"rbi","OPS":"ops","上壘率":"obp",
 "得分":"r","盜壘":"sb","出賽":"g","先發":"gs","勝敗":wl,"局數":"ip","三振":"so","保送":"bb",
 "防禦率":"era","WHIP":"whip","被安打":"h","被全壘打":"hr","救援成功":"sv","救援":"sv"}
def cellval(head, s):
    k=HEADER.get(head)
    if k is None: return None
    if callable(k): return k(s)
    return s.get(k)
def http(url, data=None, method="GET"):
    auth=base64.b64encode(f"{os.environ['WP_USER']}:{os.environ['WP_APP_PASSWORD']}".encode()).decode()
    hdr={"User-Agent":UA,"Authorization":f"Basic {auth}","Accept":"application/json, */*"}
    if data is not None:
        hdr["Content-Type"]="application/json"; hdr["Referer"]="https://clutchgtime.com/wp-admin/"
        data=json.dumps(data,ensure_ascii=False).encode("utf-8")
    for a in range(4):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(url,data=data,headers=hdr,method=method),timeout=60))
        except urllib.error.HTTPError as e: print("   HTTP",e.code,e.read().decode()[:100]); return None
        except Exception: time.sleep(4)
    return None
def pick_summary_table(raw):
    for mm in re.finditer(r"<h[23][^>]*>[^<]*(快速整理|快速看|快速表|成績快速|成績總表)[^<]*</h[23]>", raw):
        t=re.search(r"<table.*?</table>", raw[mm.end():], re.S)
        if t: return mm.end()+t.start(), mm.end()+t.end()
    return None,None
def regen_table(tbl, s):
    heads=[re.sub(r"<[^>]+>","",x).strip() for x in re.findall(r"<th[^>]*>(.*?)</th>", tbl, re.S)]
    bm=re.search(r"<tbody>(.*?)</tbody>", tbl, re.S)
    if not bm: return tbl, False
    rows=re.findall(r"<tr>(.*?)</tr>", bm.group(1), re.S)
    if len(rows)!=1: return tbl, False   # 只處理單列總結表
    cells=re.findall(r"<td[^>]*>(.*?)</td>", rows[0], re.S)
    if len(cells)!=len(heads): return tbl, False
    changed=False; out=[]
    for head,cell in zip(heads,cells):
        v=cellval(head, s)
        old=re.sub(r"<[^>]+>","",cell).strip()
        if v is None or v=="": out.append(f"<td>{cell}</td>")
        else:
            if str(v)!=old: changed=True
            out.append(f"<td>{v}</td>")
    return re.sub(r"<tbody>.*?</tbody>", "<tbody><tr>"+"".join(out)+"</tr></tbody>", tbl, flags=re.S), changed
def run():
    src=os.environ.get("PLAYERS_JSON","https://players.clutchgtime.com/data/players.json")
    players=(json.load(urllib.request.urlopen(urllib.request.Request(src,headers={"User-Agent":UA}),timeout=40)) if src.startswith("http") else json.load(open(src)))["players"]
    by={p["name"]:p for p in players}
    print(f"[{'APPLY' if APPLY else 'DRY-RUN'}] {DATE_ZH} | 文章 {len(ARTICLES)}")
    for slug,name,level in ARTICLES:
        p=by.get(name)
        if not p or level not in (p.get("season_stats") or {}):
            print(f"  – {name}: 無 {level} 數據,略過"); continue
        s=p["season_stats"][level]
        d=http(f"{API}?slug={slug}&_fields=id&context=edit")
        if not d: print(f"  ⚠ {name}({slug}): 找不到文章"); continue
        r=http(f"{API}/{d[0]['id']}?context=edit&_fields=content")
        if not r: continue
        raw=r["content"]["raw"]; new=raw; note=[]
        a,b=pick_summary_table(raw)
        if a is not None:
            nt,ch=regen_table(raw[a:b], s)
            if ch: new=raw[:a]+nt+raw[b:]; note.append("表格")
        n2=re.sub(r"最後更新：2026 年 \d{1,2} 月 \d{1,2} 日", f"最後更新：2026 年 {DATE_ZH}", new)
        if n2!=new: note.append("日期"); new=n2
        if not note: print(f"  = {name}: 已是最新"); continue
        if "表格" in note:
            aa,bb=pick_summary_table(new); tb=re.search(r"<tbody>.*?</tbody>",new[aa:bb],re.S).group(0)
            row=re.sub(r"<[^>]+>","",tb.replace("</td>"," | ").replace("</th>"," | "))
            print(f"  ✎ {name}: {'+'.join(note)} → {re.sub(r' +',' ',row).strip(' |')[:110]}")
        else: print(f"  ✎ {name}: {'+'.join(note)}")
        if APPLY:
            print("     →","✅" if http(f"{API}/{d[0]['id']}",data={"content":new},method="POST") else "❌")
if __name__=="__main__": run()
