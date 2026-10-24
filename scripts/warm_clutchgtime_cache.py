#!/usr/bin/env python3
"""clutchgtime 熱門頁面暖快取:依 Jetpack 統計近 30 天有瀏覽的文章,加上首頁、專題頁、主要分類,
逐頁 GET 一次,讓 WP-Optimize 頁面快取(壽命 7 天)裡永遠有真正有人看的頁面。

刻意做得很溫和:一頁一頁抓、每頁間隔 GAP 秒、上限 MAX_URLS 頁。
不要改成並行或縮短間隔 — WP-Optimize 內建的全站預載曾經一個月打 5 萬多次自己,把資料庫拖垮。

用法:python3 scripts/warm_clutchgtime_cache.py [--dry-run]
需要 WP_USER / WP_APP_PASSWORD(讀 Jetpack 統計)。
"""
import base64
import json
import os
import sys
import time
import urllib.request

SITE = "https://clutchgtime.com"
BLOG_ID = 160368443
MAX_URLS = 180
GAP = 3  # 秒
UA = "Mozilla/5.0 (compatible; ClutchCacheWarm/1.0; +https://clutchgtime.com/)"
FIXED = ["/", "/topics/", "/topics/rays-way/", "/topics/baseball-tech/", "/topics/salary-contracts/",
         "/topics/japan-baseball/", "/topics/basketball-shoes/", "/category/mlb/", "/category/nba/",
         "/category/npb/"]


def stats_urls():
    u, p = os.environ.get("WP_USER"), os.environ.get("WP_APP_PASSWORD")
    if not (u and p):
        sys.exit("缺少 WP_USER / WP_APP_PASSWORD")
    req = urllib.request.Request(
        f"{SITE}/wp-json/jetpack/v4/stats-app/sites/{BLOG_ID}/stats/top-posts?max=200&period=day&num=30",
        headers={"Authorization": "Basic " + base64.b64encode(f"{u}:{p}".encode()).decode(), "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.load(r)
    views = {}
    for day in (data.get("days") or {}).values():
        for x in day.get("postviews") or []:
            href = x.get("href") or ""
            if x.get("public") and href.startswith(SITE):
                views[href] = views.get(href, 0) + int(x.get("views") or 0)
    return [h for h, _ in sorted(views.items(), key=lambda kv: -kv[1])]


def main():
    urls, seen = [], set()
    for u in [SITE + f for f in FIXED] + stats_urls():
        if u not in seen:
            seen.add(u)
            urls.append(u)
    urls = urls[:MAX_URLS]
    print(f"暖快取 {len(urls)} 頁(間隔 {GAP}s)")
    if "--dry-run" in sys.argv:
        return
    hit = miss = err = 0
    for u in urls:
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=60) as r:
                status = (r.headers.get("wpo-cache-status") or "").lower()
                r.read()
            if status == "cached":
                hit += 1
            else:
                miss += 1
        except Exception as e:  # 單頁失敗不影響其他頁
            err += 1
            print("  失敗", u, e)
        time.sleep(GAP)
    print(f"完成:原本已在快取 {hit}、這次新產生 {miss}、失敗 {err}")


if __name__ == "__main__":
    main()
