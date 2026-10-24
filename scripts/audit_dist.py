#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dist/ 完整性稽核:在 prerender 之後跑,把「頁面自己講不通」的地方抓出來。
============================================================================
為什麼需要這支:2026-10-21 起 npb.jp 整站逾時,季累積被空值覆蓋,12 位日職球員的
meta description 變成「2026 球季尚無出賽紀錄。最近一場出賽在 10月16日。近 5 場
投 5.1 局…」—— 同一段話自相矛盾,而那是 Google 直接拿去當搜尋摘要的句子。
**靜默壞了三天沒人發現**,是查 GSC 時看到「排第 3 名卻 0 點擊」才回推出來的。
抓取端已各自補上「抓不到就沿用既有資料」,這支是最後一道網:不論哪個聯盟、哪支
腳本出問題,只要渲染出來的頁面講不通就會在 Actions 執行摘要上示警。

只示警不中斷(exit 0)。中斷會讓部署停住、線上停留在舊版,那比有瑕疵更糟。

執行:python3 scripts/audit_dist.py [dist 目錄]
"""
import collections
import glob
import html
import os
import re
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dist")
SITE = "https://players.clutchgtime.com/"

DESC_MAX = 170          # 超過就會被 Google 截斷
BAD_TOKENS = ["NaN", "undefined", "Infinity", "：。", "、。", "。。", "(null)"]

issues = collections.defaultdict(list)


def add(kind, detail):
    issues[kind].append(detail)


def meta(s, name):
    m = re.search(r'<meta name="%s" content="(.*?)"' % name, s, re.S)
    return html.unescape(m.group(1)) if m else ""


def title_of(s):
    m = re.search(r"<title>(.*?)</title>", s, re.S)
    return html.unescape(m.group(1)) if m else ""


def main():
    if not os.path.isdir(ROOT):
        print(f"找不到 {ROOT},跳過稽核")
        return 0

    pages = sorted(glob.glob(ROOT + "/**/index.html", recursive=True))
    titles = []
    for f in pages:
        url = "/" + os.path.relpath(f, ROOT).replace("index.html", "")
        s = open(f, encoding="utf-8").read()
        t, d = title_of(s), meta(s, "description")
        noindex = 'name="robots" content="noindex' in s

        # ① 摘要自相矛盾 —— 這一類最嚴重,會原封不動出現在搜尋結果上
        if "尚無出賽紀錄" in d and "最近一場出賽" in d:
            add("摘要自相矛盾:說本季沒出賽,下一句又說最近一場出賽在某天", url)
        # ② 程式漏出來的空值
        for bad in BAD_TOKENS:
            if bad in d or bad in t:
                add(f"標題或摘要出現 {bad!r}", url)
        # ③ 缺 meta
        if not t:
            add("沒有 title", url)
        if not d:
            add("沒有 meta description", url)
        if d and len(d) > DESC_MAX:
            add(f"摘要超過 {DESC_MAX} 字(會被截斷)", f"{url} [{len(d)}]")
        # ④ 散文裡的極端率值 = 樣本太小(見 recap.js 的 thinSample);
        #    數據表格不算,所以只看摘要
        for m in re.finditer(r"防禦率 (\d+\.\d+)", d):
            if float(m.group(1)) > 25:
                add("摘要的防禦率 > 25(樣本過小的率值不該當摘要)", f"{url} {m.group(1)}")
        # ⑤ 標題第二段留著未翻譯的英文隊名(7-ELEVEn 是中職官方隊名,不算)
        seg = t.split("｜")
        if len(seg) > 2 and re.search(r"[A-Za-z]{4}", seg[1]) and "7-ELEVEn" not in seg[1]:
            add("標題第 2 段含未翻譯英文", f"{url} {seg[1]}")
        if not noindex:
            titles.append((t, url))

    # ⑥ 同名標題會互搶同一個查詢
    for t, n in collections.Counter(t for t, _ in titles if t).items():
        if n > 1:
            add("可索引頁的標題重複", f"{n} 頁:{t[:70]}")

    # ⑦ 站內死連結
    def exists(path):
        p = path.split("#")[0].split("?")[0]
        if p.endswith("/"):
            p += "index.html"
        return os.path.exists(os.path.join(ROOT, p.lstrip("/")))

    dead = collections.defaultdict(set)
    nlink = 0
    allhtml = sorted(glob.glob(ROOT + "/**/*.html", recursive=True))
    linked = set()
    for f in allhtml:
        s = open(f, encoding="utf-8").read()
        for m in re.finditer(r'(?:href|src)="(/[^"]*)"', s):
            u = m.group(1)
            if u.startswith("//"):
                continue
            nlink += 1
            if not exists(u):
                dead[u].add("/" + os.path.relpath(f, ROOT))
        for m in re.finditer(r'href="(/[^"#?]*)"', s):
            linked.add(m.group(1))
    for u, srcs in dead.items():
        add("站內死連結", f"{u} ← {len(srcs)} 頁引用,例 {sorted(srcs)[0]}")

    # ⑧ sitemap 與 robots 自相矛盾
    sm = set()
    for f in glob.glob(ROOT + "/sitemap-*.xml"):
        sm |= set(re.findall(r"<loc>(.*?)</loc>", open(f, encoding="utf-8").read()))
    for u in sorted(sm):
        p = u.replace(SITE, "/")
        f = os.path.join(ROOT, p.lstrip("/") + ("index.html" if p.endswith("/") else ""))
        if not os.path.exists(f):
            add("sitemap 收錄的網址檔案不存在(會 404)", u)
        elif 'name="robots" content="noindex' in open(f, encoding="utf-8").read():
            add("sitemap 收錄的網址卻標 noindex(自相矛盾)", u)

    # ⑨ 孤島:可索引但站內沒有任何連結指到它。2026-10 的對照實驗結論是
    #    「只放 sitemap 不會被爬,要有內鏈」,所以孤島等於不會被收錄。
    for f in pages:
        s = open(f, encoding="utf-8").read()
        if 'name="robots" content="noindex' in s:
            continue
        p = "/" + os.path.relpath(f, ROOT).replace("index.html", "")
        if p != "/" and p not in linked:
            add("可索引頁但站內無任何連結(孤島,不會被爬到)", p)

    # ---- 輸出 ----
    print(f"dist 稽核:{len(pages)} 頁、{nlink} 個站內連結、{len(sm)} 個 sitemap 網址")
    if not issues:
        print("  沒有發現問題 ✓")
        return 0
    for kind in sorted(issues, key=lambda k: -len(issues[k])):
        v = issues[kind]
        print(f"  ■ {kind}:{len(v)}")
        for x in v[:6]:
            print(f"     {x}")
        if len(v) > 6:
            print(f"     …另 {len(v) - 6} 筆")
        # ::warning:: 會出現在 Actions 的執行摘要上 —— 埋在日誌裡的訊息沒有用
        print(f"::warning title=dist 稽核::{kind}:{len(v)} 筆(例:{v[0]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
