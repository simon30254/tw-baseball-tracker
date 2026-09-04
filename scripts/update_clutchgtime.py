#!/usr/bin/env python3
"""clutchgtime 球員文章「快速整理表」+ 標題數字 + 日期 自動更新(安全版)。
只重算結構化總結表與標題中的數字、且每篇釘死對應層級;不碰評價/背景/逐場戰報。
用法: python3 update_clutchgtime.py [--apply]   (預設乾跑)
需環境變數 WP_USER / WP_APP_PASSWORD;PLAYERS_JSON 可選(預設抓正式站)。"""
import os, re, sys, json, base64, urllib.request, urllib.error, time, datetime
APPLY = "--apply" in sys.argv
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
API = "https://clutchgtime.com/wp-json/wp/v2/posts"
TODAY = os.environ.get("CT_TODAY") or datetime.date.today().isoformat()
_y,_m,_d = TODAY.split("-"); DATE_ZH = f"{int(_m)} 月 {int(_d)} 日"

# 每篇文章:slug, 球員名, 釘死的層級(該文章在講哪個層級的成績), 標題模板(可省略)
# 標題模板用 {欄位} 佔位,欄位名同 players.json 的 season_stats key(avg/hr/rbi/w/l/era/h...)。
# 沒給模板 = 不動標題。模板算出來的標題與現有標題不同才會寫回。
ARTICLES = [
 ("kai-wei-teng-2026","鄧愷威","MLB","鄧愷威2026 MLB成績｜{w}勝{l}敗、防禦率{era}與重返太空人最新動態"),
 ("cheng-tsung-che-2026","鄭宗哲","MLB","鄭宗哲2026 MLB成績｜打擊率{avg}、{h}支安打與紅襪3A最新動態"),
 ("hao-yu-lee-2026","李灝宇","MLB","李灝宇2026 MLB成績｜打擊率{avg}、{hr}轟{rbi}打點與逐場安打紀錄"),
 ("2026-sun-yi-lei","孫易磊","一軍","孫易磊2026日職成績｜{w}勝{l}敗、防禦率{era}與日本火腿逐場紀錄"),
 ("jo-hsi-hsu-2026","徐若熙","一軍","徐若熙2026日職成績｜{w}勝{l}敗、防禦率{era}與軟銀逐場紀錄"),
 ("lin-an-ko-2026","林安可","一軍","林安可2026日職成績｜打擊率{avg}、{hr}轟{rbi}打點與西武獅逐場紀錄"),
 ("wang-yen-cheng-2026","王彥程","一軍","王彥程2026韓職成績｜{w}勝{l}敗、防禦率{era}與韓華鷹逐場紀錄"),
 ("corbin-carroll-2026","柯賓·卡洛爾","MLB"),
 ("yu-min-lin-2026","林昱珉","AAA"),
 ("chen-wei-lin-2026","林振瑋","AA"),
 ("chia-hao-sung-2026","宋家豪","一軍"),
]
def wl(s): return f"{s.get('w',0)}–{s.get('l',0)}"
HEADER = {"打數":"ab","安打":"h","打擊率":"avg","全壘打":"hr","打點":"rbi","OPS":"ops","上壘率":"obp",
 "長打率":"slg","得分":"r","盜壘":"sb","四壞":"bb","保送":"bb","出賽":"g","先發":"gs","勝敗":wl,
 "局數":"ip","投球局數":"ip","三振":"so","防禦率":"era","WHIP":"whip","被安打":"h","被全壘打":"hr",
 "救援成功":"sv","救援":"sv","中繼成功":"hld","中繼":"hld"}
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
def pick_summary_table(raw, name):
    """找總結表:先找舊有的關鍵字標題,再退而找「含球員名 + 成績/數據」的標題。取該標題之後的第一張表。"""
    pats=[r"<h[23][^>]*>[^<]*(?:快速整理|快速看|快速表|成績快速|成績總表)[^<]*</h[23]>",
          r"<h[23][^>]*>[^<]*"+re.escape(name)+r"[^<]*(?:成績|數據)[^<]*</h[23]>"]
    for pat in pats:
        for mm in re.finditer(pat, raw):
            t=re.search(r"<table.*?</table>", raw[mm.end():], re.S)
            if t: return mm.end()+t.start(), mm.end()+t.end()
    return None,None
def _row(cells): return "<tr>"+"".join(cells)+"</tr>"
def regen_table(tbl, stats, level):
    """單列表 → 用釘死層級重算;多列表 → 只在每列首欄都是 season_stats 的層級名時,逐列重算。"""
    heads=[re.sub(r"<[^>]+>","",x).strip() for x in re.findall(r"<th[^>]*>(.*?)</th>", tbl, re.S)]
    bm=re.search(r"<tbody>(.*?)</tbody>", tbl, re.S)
    if not bm: return tbl, False
    rows=re.findall(r"<tr>(.*?)</tr>", bm.group(1), re.S)
    if not rows: return tbl, False
    plans=[]   # (cells, 該列要用的 stats)
    if len(rows)==1:
        cells=re.findall(r"<td[^>]*>(.*?)</td>", rows[0], re.S)
        if len(cells)!=len(heads): return tbl, False
        s=stats.get(level)
        if not s: return tbl, False
        plans.append((cells, s))
    else:
        for r in rows:
            cells=re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)
            if len(cells)!=len(heads): return tbl, False
            lv=re.sub(r"<[^>]+>","",cells[0]).strip()
            if lv not in stats: return tbl, False   # 首欄不是層級名(如中職生涯表)→ 整張不動
            plans.append((cells, stats[lv]))
    changed=False; out=[]
    for cells, s in plans:
        cur=[]
        for head,cell in zip(heads,cells):
            v=cellval(head, s)
            old=re.sub(r"<[^>]+>","",cell).strip()
            if v is None or v=="": cur.append(f"<td>{cell}</td>")
            else:
                if str(v)!=old: changed=True
                cur.append(f"<td>{v}</td>")
        out.append(_row(cur))
    return re.sub(r"<tbody>.*?</tbody>", "<tbody>"+"".join(out)+"</tbody>", tbl, flags=re.S), changed
# ── 「近期狀態」近 N 場表 ──────────────────────────────────────────
# 短文那張「日期／對手／…」的近況表原本純手工,幾天就過期。
# 只認表頭前兩欄是 日期+對手 的表,並用 game_logs 重建同樣列數。
# 對手中文名對照:MLB 30 隊 + 林昱珉(3A/PCL)、林振瑋(2A/德州聯盟)實際會碰到的隊伍。
# 查不到對照就直接寫英文原名(顯眼、好補),不亂音譯。
TEAM_ZH = {
 # MLB
 "Arizona Diamondbacks":"響尾蛇","Atlanta Braves":"勇士","Baltimore Orioles":"金鶯",
 "Boston Red Sox":"紅襪","Chicago Cubs":"小熊","Chicago White Sox":"白襪",
 "Cincinnati Reds":"紅人","Cleveland Guardians":"守護者","Colorado Rockies":"落磯",
 "Detroit Tigers":"老虎","Houston Astros":"太空人","Kansas City Royals":"皇家",
 "Los Angeles Angels":"天使","Los Angeles Dodgers":"道奇","Miami Marlins":"馬林魚",
 "Milwaukee Brewers":"釀酒人","Minnesota Twins":"雙城","New York Mets":"大都會",
 "New York Yankees":"洋基","Athletics":"運動家","Oakland Athletics":"運動家",
 "Philadelphia Phillies":"費城人","Pittsburgh Pirates":"海盜","San Diego Padres":"教士",
 "San Francisco Giants":"巨人","Seattle Mariners":"水手","St. Louis Cardinals":"紅雀",
 "Tampa Bay Rays":"光芒","Texas Rangers":"遊騎兵","Toronto Blue Jays":"藍鳥",
 "Washington Nationals":"國民",
 # 3A(林昱珉/Reno 常見對手)
 "Sacramento River Cats":"沙加緬度","Salt Lake Bees":"鹽湖","Tacoma Rainiers":"塔科馬",
 "El Paso Chihuahuas":"艾爾帕索","Round Rock Express":"圓石城","Las Vegas Aviators":"拉斯維加斯",
 "Albuquerque Isotopes":"阿布奎基","Oklahoma City Comets":"奧克拉荷馬市",
 "Sugar Land Space Cowboys":"蜜糖城","Fresno Grizzlies":"弗雷斯諾","Reno Aces":"雷諾",
 # 2A(林振瑋/Springfield 常見對手)
 "Corpus Christi Hooks":"柯柏斯克里斯提","San Antonio Missions":"聖安東尼奧",
 "Arkansas Travelers":"阿肯色","Northwest Arkansas Naturals":"西北阿肯色",
 "Wichita Wind Surge":"威奇塔","Frisco RoughRiders":"弗里斯科","Tulsa Drillers":"塔爾薩",
 "Amarillo Sod Poodles":"阿馬里洛","Midland RockHounds":"米德蘭",
 "Springfield Cardinals":"春田",
}
RECENT_COLS = {   # 表頭 → 從 game_log 取的欄位
 "打數":"ab","安打":"h","被安":"h","全壘打":"hr","被全壘打":"hr","打點":"rbi","盜壘":"sb",
 "得分":"r","失分":"r","責失":"er","局數":"ip","三振":"so","保送":"bb","四壞":"bb",
}
def _recent_date(zero, iso):
    """沿用原表的日期寫法:zero=True 時個位數日補 0(9/02),否則 9/2。"""
    mm, dd = iso[5:7], iso[8:10]
    return f"{int(mm)}/{dd if zero else int(dd)}"
def _ip_add(a, b):
    def outs(x):
        if x in (None, ""): return 0
        s = str(x).split("."); return int(s[0]) * 3 + (int(s[1]) if len(s) > 1 else 0)
    t = outs(a) + outs(b)
    return f"{t//3}.{t%3}" if t % 3 else f"{t//3}.0"
def _merge_dh(logs):
    """同一天多場(雙重賽)併成一列,累加計數欄位並在對手後標注。"""
    out = []
    for g in logs:
        if out and out[-1]["date"] == g["date"] and out[-1].get("opponent") == g.get("opponent"):
            m = out[-1]
            for k in ("ab", "h", "hr", "rbi", "sb", "r", "er", "so", "bb"):
                if g.get(k) is not None: m[k] = (m.get(k) or 0) + g[k]
            if g.get("ip"): m["ip"] = _ip_add(m.get("ip"), g["ip"])
            m["win"] = m.get("win") or g.get("win"); m["loss"] = m.get("loss") or g.get("loss")
            m["_dh"] = True
        else:
            out.append(dict(g))
    return out
def sync_recent_table(raw, player, level):
    """重建「日期/對手/…」近況表。回傳 (新內文, 是否有變)。"""
    logs = [g for g in (player.get("game_logs") or []) if g.get("level") == level]
    if not logs: return raw, False
    logs = _merge_dh(sorted(logs, key=lambda g: g["date"], reverse=True))
    for tm in re.finditer(r"<table.*?</table>", raw, re.S):
        tbl = tm.group(0)
        heads = [re.sub(r"<[^>]+>","",x).strip() for x in re.findall(r"<th[^>]*>(.*?)</th>", tbl, re.S)]
        if len(heads) < 3 or heads[0] != "日期" or heads[1] != "對手": continue
        rest = heads[2:]
        if any(h not in RECENT_COLS and h != "結果" for h in rest): return raw, False  # 有看不懂的欄位就整張不動
        bm = re.search(r"<tbody>(.*?)</tbody>", tbl, re.S)
        if not bm: continue
        rows = re.findall(r"<tr>(.*?)</tr>", bm.group(1), re.S)
        if not rows: continue
        # 補零與否要看整張表:只看第一列的話,遇到 8/28 這種兩位數日就判斷不出來
        dates = [re.sub(r"<[^>]+>","",re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)[0]).strip()
                 for r in rows if re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)]
        zero = any(re.match(r"^\d{1,2}/0\d$", x) for x in dates)
        out = []
        for g in logs[:len(rows)]:
            team = TEAM_ZH.get(g.get("opponent",""), g.get("opponent",""))
            if g.get("_dh"): team += "（雙重賽）"
            cells = [_recent_date(zero, g["date"]), team]
            for h in rest:
                if h == "結果":
                    cells.append("勝" if g.get("win") else ("敗" if g.get("loss") else "—"))
                else:
                    v = g.get(RECENT_COLS[h])
                    cells.append("" if v is None else str(v))
            out.append("<tr>\n" + "".join(f"<td>{x}</td>\n" for x in cells) + "</tr>")
        newtbl = re.sub(r"<tbody>.*?</tbody>", "<tbody>\n" + "\n".join(out) + "\n</tbody>", tbl, flags=re.S)
        if newtbl == tbl: return raw, False
        return raw[:tm.start()] + newtbl + raw[tm.end():], True
    return raw, False


# ── 內文散文數字同步 ──────────────────────────────────────────────
# 只在 <span class="ct-auto-stats"> ... </span> 內部替換,絕不整段亂改。
# span 可帶 data-level 指定層級(如 3A 段落),沒帶就用該篇釘死的層級。
# 這是為了解決:表格/標題每天自動更新,但頂部資訊卡那句敘述停在人工寫的數字。
SPAN = re.compile(r'(<span class="ct-auto-stats"(?P<attrs>[^>]*)>)(?P<body>.*?)(</span>)', re.S)
LEVEL_ATTR = re.compile(r'data-level="([^"]*)"')
# (regex, season_stats key)。順序重要:具體的寫法要排在通用寫法前面。
PROSE_FIELDS = [
    (r"(\d+)\s*場出賽", "g"), (r"(\d+)\s*場先發", "gs"), (r"(\d+)\s*場(?!出賽|先發)", "g"),
    (r"(\d+)\s*打數", "ab"), (r"(\d+)\s*支安打", "h"), (r"(\d+)\s*安打", "h"),
    (r"打擊率\s*(\.?\d[\d.]*)", "avg"),
    (r"(\d+)\s*支全壘打", "hr"), (r"(\d+)\s*轟", "hr"),
    (r"(\d+)\s*分打點", "rbi"), (r"(\d+)\s*打點", "rbi"),
    (r"(\d+)\s*分得分", "r"), (r"(\d+)\s*得分", "r"),
    (r"(\d+)\s*次盜壘", "sb"), (r"(\d+)\s*盜壘", "sb"),
    (r"上壘率\s*(\.?\d[\d.]*)", "obp"), (r"OPS\s*(\.?\d[\d.]*)", "ops"),
    (r"(\d+)\s*勝", "w"), (r"(\d+)\s*敗", "l"),
    (r"([\d.]+)\s*局", "ip"), (r"(\d+)\s*次三振", "so"),
    (r"防禦率\s*([\d.]+)", "era"), (r"WHIP\s*([\d.]+)", "whip"),
    (r"(\d+)\s*次中繼成功", "hld"), (r"(\d+)\s*次救援成功", "sv"),
]
# 這些欄位在 NPB/KBO 資料源常常沒有值,會以 0 呈現(例:徐若熙一軍 gs=0,
# 但他實際先發 6 場)。對這幾個欄位,0 一律視為「沒資料」而不是真的 0,
# 保留文章原本的數字 —— 寧可舊,也不要把對的數字改成 0。
PLACEHOLDER_ZERO = {"gs", "sv", "hld"}
def sync_prose(raw, stats, level):
    """回傳 (新內文, 有變的 span 數)。season_stats 裡沒有的欄位一律不動。"""
    changed = [0]
    def one(m):
        am = LEVEL_ATTR.search(m.group("attrs") or "")
        lv = am.group(1) if am else level
        s = stats.get(lv)
        if not s: return m.group(0)
        body = m.group("body"); before = body
        for pat, key in PROSE_FIELDS:
            v = s.get(key)
            if v in (None, ""): continue
            if key in PLACEHOLDER_ZERO and str(v) in ("0", "0.0"): continue
            body = re.sub(pat, lambda mm: mm.group(0).replace(mm.group(1), str(v), 1), body, count=1)
        if body != before: changed[0] += 1
        return m.group(1) + body + m.group(4)
    return SPAN.sub(one, raw), changed[0]


def build_title(tmpl, s):
    try: return tmpl.format(**{k:("" if v is None else v) for k,v in s.items()})
    except KeyError as e:
        print("   ⚠ 標題模板缺欄位",e); return None
def run():
    src=os.environ.get("PLAYERS_JSON","https://players.clutchgtime.com/data/players.json")
    blob=(json.load(urllib.request.urlopen(urllib.request.Request(src,headers={"User-Agent":UA}),timeout=40)) if src.startswith("http") else json.load(open(src)))
    by={p["name"]:p for p in blob["players"]}
    # 「截至」用資料抓取日(players.json 的 updated_at),不用今天:抓取在台灣早上跑,
    # 涵蓋到前一天的美國賽事,寫今天會高估。「最後更新」才是今天。
    try:
        _a=blob.get("updated_at","")[:10].split("-"); as_m,as_d=int(_a[1]),int(_a[2])
    except Exception:
        as_m,as_d=int(_m),int(_d)
    print(f"[{'APPLY' if APPLY else 'DRY-RUN'}] 最後更新 {DATE_ZH}｜資料截至 {as_m}/{as_d} | 文章 {len(ARTICLES)}")
    for row in ARTICLES:
        slug,name,level = row[0],row[1],row[2]
        tmpl = row[3] if len(row)>3 else None
        p=by.get(name); stats=(p or {}).get("season_stats") or {}
        if not p or level not in stats:
            print(f"  – {name}: 無 {level} 數據,略過"); continue
        s=stats[level]
        d=http(f"{API}?slug={slug}&_fields=id&context=edit")
        if not d: print(f"  ⚠ {name}({slug}): 找不到文章"); continue
        r=http(f"{API}/{d[0]['id']}?context=edit&_fields=content,title")
        if not r: continue
        raw=r["content"]["raw"]; new=raw; note=[]; body={}
        a,b=pick_summary_table(raw, name)
        if a is not None:
            nt,ch=regen_table(raw[a:b], stats, level)
            if ch: new=raw[:a]+nt+raw[b:]; note.append("表格")
        n0,rch=sync_recent_table(new, p, level)
        if rch: note.append("近況表"); new=n0
        n1,nspan=sync_prose(new, stats, level)
        if nspan: note.append(f"內文x{nspan}"); new=n1
        n2=re.sub(r"最後更新：(\d{4}) 年 \d{1,2} 月 \d{1,2} 日", rf"最後更新：\1 年 {DATE_ZH}", new)
        n2=re.sub(r"（截至 \d{1,2} 月 \d{1,2} 日）", f"（截至 {as_m} 月 {as_d} 日）", n2)
        n2=re.sub(r"資料截至 (\d{4}) 年 \d{1,2} 月 \d{1,2} 日", rf"資料截至 \1 年 {as_m} 月 {as_d} 日", n2)
        if n2!=new: note.append("日期"); new=n2
        if new!=raw: body["content"]=new
        if tmpl:
            cur=r["title"]["raw"]; want=build_title(tmpl, s)
            if want and want!=cur:
                note.append("標題"); body["title"]=want
                print(f"     標題: {cur}\n        → {want}")
        if not note: print(f"  = {name}: 已是最新"); continue
        if "表格" in note:
            aa,bb=pick_summary_table(new, name); tb=re.search(r"<tbody>.*?</tbody>",new[aa:bb],re.S).group(0)
            rw=re.sub(r"<[^>]+>","",tb.replace("</td>"," | ").replace("</tr>"," ／ "))
            print(f"  ✎ {name}: {'+'.join(note)} → {re.sub(r' +',' ',rw).strip(' |／')[:140]}")
        else: print(f"  ✎ {name}: {'+'.join(note)}")
        if APPLY:
            print("     →","✅" if http(f"{API}/{d[0]['id']}",data=body,method="POST") else "❌")
if __name__=="__main__": run()
