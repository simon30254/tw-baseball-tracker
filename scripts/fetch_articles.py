"""
自動拉取 clutchgtime 相關報導 → scripts/articles_auto.json
========================================================
內容飛輪:每位球員用中文名查 clutchgtime WordPress REST,把命中的文章掛到球員頁
的「相關報導」。與手動策展檔 scripts/player_content.json 並存(build_players 合併,
手動優先)。此檔為 build 中間產物(.gitignore),CI 每日重跑;結果最終烘進 players.json。

WP search 是模糊比對(搜「鄧愷威」也可能回別人),故只保留「標題含球員全名」的文章。

執行:python3 scripts/fetch_articles.py
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
DATA = ROOT / "public" / "data"
SOURCES = ["mlb.json", "npb.json", "kbo.json"]
OUT = ROOT / "scripts" / "articles_auto.json"

WP_API = "https://clutchgtime.com/wp-json/wp/v2/posts"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
SOURCE_NAME = "The Clutch Time"
MAX_PER_PLAYER = 3
TIMEOUT = 15


def roster():
    """從各來源檔取 (id, 中文名),去重。"""
    seen, out = set(), []
    for name in SOURCES:
        path = DATA / name
        if not path.exists():
            continue
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  [略過] {name}: {e}", file=sys.stderr)
            continue
        for p in d.get("players", []):
            pid = str(p["id"])
            if pid not in seen and p.get("name"):
                seen.add(pid)
                out.append((pid, p["name"]))
    return out


def search(name):
    """查 clutchgtime,回傳標題含全名的文章(依日期新→舊)。"""
    q = urllib.parse.urlencode(
        {"search": name, "per_page": 8, "_fields": "id,date,link,title", "orderby": "relevance"}
    )
    req = urllib.request.Request(f"{WP_API}?{q}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        posts = json.loads(r.read().decode("utf-8"))
    out = []
    for post in posts:
        title = html.unescape(re.sub(r"<[^>]+>", "", post.get("title", {}).get("rendered", "")))
        if name in title:  # 只留真正關於這位球員的
            out.append({
                "title": title,
                "url": post["link"],
                "date": (post.get("date") or "")[:10],
                "source": SOURCE_NAME,
            })
    out.sort(key=lambda a: a["date"], reverse=True)
    return out[:MAX_PER_PLAYER]


def main():
    result = {}
    n_articles = 0
    for pid, name in roster():
        try:
            arts = search(name)
        except Exception as e:
            print(f"  [略過] {name}: {e}", file=sys.stderr)
            continue
        if arts:
            result[pid] = {"articles": arts}
            n_articles += len(arts)
        time.sleep(0.4)  # 對 clutchgtime 客氣一點
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"完成:{OUT} — {len(result)} 位球員、{n_articles} 篇報導")


if __name__ == "__main__":
    main()
