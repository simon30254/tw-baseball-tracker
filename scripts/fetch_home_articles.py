#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""首頁下方「主站深度內容」區塊的資料 → public/data/home_articles.json
==========================================================================
分組與篩選條件寫在 scripts/home_articles.json(人維護),這支只負責去主站
clutchgtime.com 的 WP REST 把各組最新文章的**標題、網址、日期**讀回來。

為什麼不手打清單:主站改一次標題,手打的那份就對不上了 —— venue_guides.json
踩過這個坑,所以那邊的標題也是從 API 讀的。這裡連「更多」連結都不手寫,取
分類封存頁自己回報的網址。

為什麼不直接抓「全站最新文章」:主站有 NBA、球鞋導購、跑步,而追蹤站的讀者
是來看台灣旅外棒球員的。另外主站的名詞解說是整批上線的(2026-11-26 一天 20 篇),
純按時間排會變成一整排同一天的名詞頁。所以是「每個主題各取最新幾篇」。

抓不到就**不覆寫**既有檔案(同站內其他抓取腳本的慣例):區塊少一天不更新沒差,
把它清空會讓首頁下方整塊消失。單一組失敗時,那一組沿用舊檔的內容。

執行:python3 scripts/fetch_home_articles.py [--dry-run]
"""
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONF = ROOT / "scripts" / "home_articles.json"
OUT = ROOT / "public" / "data" / "home_articles.json"
API = "https://clutchgtime.com/wp-json/wp/v2"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
TIMEOUT = 20
DRY = "--dry-run" in sys.argv


def get(path, **params):
    url = f"{API}/{path}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def plain(s):
    """WP 回傳的 rendered 標題含 HTML 實體與標籤(例:&#8217;、<em>)。"""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s or ""))).strip()


def item(post):
    return {"title": plain((post.get("title") or {}).get("rendered")),
            "url": post["link"],
            "date": (post.get("date") or "")[:10]}


def by_slug(slug):
    """置頂用:slug 可能是文章也可能是頁面(新手村那幾篇是 page)。"""
    for kind in ("posts", "pages"):
        try:
            hit = get(kind, slug=slug, _fields="link,title,date", per_page=1)
        except Exception as e:
            print(f"  [置頂失敗] {slug}: {e}", file=sys.stderr)
            return None
        if hit:
            return item(hit[0])
    print(f"  [置頂找不到] {slug} —— 主站上沒有這個 slug,請改 home_articles.json", file=sys.stderr)
    return None


def cat_meta(ids):
    """分類封存頁的網址與名稱。網址由分類自己回報,不要用 /category/{slug}/ 猜 ——
    子分類的網址帶父分類路徑(mlb-asia 是 /category/mlb/mlb-asia/)。
    名稱也一起讀回來當「更多」的文案:一組跨三個分類時(看球攻略),用組名當
    連結文字會騙人 —— 點進去只會是其中一個分類。用分類自己的名字才對得上。"""
    try:
        cs = get("categories", include=",".join(map(str, ids)), _fields="id,link,name",
                 per_page=min(len(ids) + 5, 100))
    except Exception as e:
        print(f"  [分類讀取失敗] {e}", file=sys.stderr)
        return {}
    return {c["id"]: {"link": c["link"], "name": plain(c["name"])} for c in cs}


def main():
    conf = json.loads(CONF.read_text(encoding="utf-8"))
    old = {}
    if OUT.exists():
        try:
            old = {g["key"]: g for g in json.loads(OUT.read_text(encoding="utf-8")).get("groups", [])}
        except Exception:
            old = {}
    drop = set(conf.get("排除") or [])
    # 「更多」要指的分類:預設 cats[0],可用 more_cat 指定(跨國那組指父分類才不會
    # 只連到其中一國)。一次把所有分類的網址與名稱讀回來。
    want = {g.get("more_cat") or g["cats"][0] for g in conf["groups"]}
    cats = cat_meta(sorted(want))
    seen = set()          # 跨組去重:同一篇可能掛兩個分類(韓華球場攻略同時在看球攻略與韓職)
    groups, n_fail = [], 0

    for g in conf["groups"]:
        items = []
        for slug in g.get("pin") or []:
            x = by_slug(slug)
            if x and x["url"] not in seen and x["url"] not in drop:
                seen.add(x["url"])
                items.append(x)
            time.sleep(0.3)
        try:
            # 多抓一些再篩:去重與排除會吃掉幾筆,剛好抓 n 篇可能補不滿
            posts = get("posts", categories=",".join(map(str, g["cats"])),
                        per_page=min(g["n"] + 8, 20), orderby="date", order="desc",
                        _fields="link,title,date")
        except Exception as e:
            print(f"  [略過] {g['label']}: {e}", file=sys.stderr)
            n_fail += 1
            if g["key"] in old:        # 這一組沿用舊資料,不要讓它消失
                groups.append(old[g["key"]])
                seen.update(x["url"] for x in old[g["key"]].get("items") or [])
            continue
        for p in posts:
            if len(items) >= g["n"] + len(g.get("pin") or []):
                break
            x = item(p)
            if not x["title"] or x["url"] in seen or x["url"] in drop:
                continue
            seen.add(x["url"])
            items.append(x)
        if not items:
            print(f"  [空的] {g['label']} —— 分類 {g['cats']} 沒有文章?", file=sys.stderr)
            continue
        cm = cats.get(g.get("more_cat") or g["cats"][0]) or {}
        groups.append({"key": g["key"], "label": g["label"], "items": items,
                       "more": cm.get("link", ""), "more_label": cm.get("name", "")})
        print(f"  {g['label']}:{len(items)} 篇")
        time.sleep(0.3)

    # 全組都失敗就別寫檔 —— 寧可讓首頁沿用昨天的清單,也不要把區塊變空
    if not groups:
        print("全部分組都抓不到,保留既有檔案不覆寫", file=sys.stderr)
        return 1
    if n_fail == len(conf["groups"]):
        print("全部分組都失敗,保留既有檔案不覆寫", file=sys.stderr)
        return 1

    out = {
        "_說明": "由 scripts/fetch_home_articles.py 自動產生,分組設定在 scripts/home_articles.json。"
                 "不要手改這個檔。",
        "updated": time.strftime("%Y-%m-%d"),
        "groups": groups,
    }
    txt = json.dumps(out, ensure_ascii=False, indent=1) + "\n"
    if DRY:
        print(txt)
        return 0
    OUT.write_text(txt, encoding="utf-8")
    print(f"完成:{OUT} — {len(groups)} 組、{sum(len(g['items']) for g in groups)} 篇")
    return 0


if __name__ == "__main__":
    sys.exit(main())
