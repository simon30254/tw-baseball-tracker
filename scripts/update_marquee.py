#!/usr/bin/env python3
"""clutchgtime 首頁「熱門話題」跑馬燈＋頁尾「本週熱門文章」:依 Jetpack 統計最近 7 天瀏覽數自動更新。

跑馬燈本體在 clutchgtime 頁尾小工具 block-8 的 <script id="ct-marquee-js"> 裡,
內容是一行 `var T=[[標籤,網址],...];`。這支只改那一行,其餘不動。

資料來源用 Jetpack 統計而不是 GSC:GSC 的 OAuth 只在本機、每 7 天過期,進不了 CI;
Jetpack 統計走 WP REST,CI 已有 WP_USER / WP_APP_PASSWORD。

寫入很保守:清單沒變就不寫(改小工具會清空 WP-Optimize 全站快取,不要每天白清一次)。

用法:python3 scripts/update_marquee.py [--apply]   (不加 --apply 只印出結果)
"""
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

SITE = "https://clutchgtime.com"
WIDGET = "block-8"
BLOG_ID = 160368443  # Jetpack blog id(/wp-json/jetpack/v4/connection/data)
MAX_ITEMS = 14
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")

# 標題太長放不進膠囊,常見頁面給短標籤;沒列到的用 short_label() 自動縮
LABELS = {
    "mlb-worldseries-mvp": "世界大賽",
    "mlb-2026-cba": "MLB 封館",
    "2025-mlb-salary": "大聯盟薪資排行",
    "2026-mlb-salary": "MLB 球員薪資",
    "yoshinobu-yamamoto-salary": "山本由伸合約",
    "2026-nba-draft": "2026 NBA 選秀",
    "2025-nbadraft": "2025 NBA 選秀",
    "nba-championship-fmvp": "NBA 總冠軍",
    "npb-schedule-guide": "日職賽程",
    "taiwan-mlb-players": "台灣旅美球員",
    "npb-taiwan-players": "台灣旅日球員",
    "pitch-types": "棒球球種",
    "sweeper": "Sweeper 掃球",
    "mlb-balk": "投手犯規",
    "2021-nike-shoes": "籃球鞋推薦",
    "low-top-basketball-shoes": "低筒籃球鞋",
    "outdoor-basketball-shoes": "戶外籃球鞋",
    "nike-training-shoes": "訓練鞋推薦",
    "2026-27-nba-salary": "NBA 薪資排行",
    "2025-26-nba-salary": "NBA 薪資",
    "moneyball": "魔球",
    "tampa-bay-rays-mode": "光芒學派",
    "tampa-rays-pitcher": "光芒投手工廠",
    "tampa-rays-trade": "光芒交易教科書",
    "tampa-rays-sect": "光芒學派分支",
    "opener-ray": "開場投手",
    "belluna-dome-guide": "西武巨蛋",
    "kyocera-dome-osaka-guide": "京瓷巨蛋",
    "mizuho-paypay-dome-fukuoka-guide": "福岡巨蛋",
    "koshien-baseball-guide": "甲子園",
    "npb-ticket-guide": "日職門票",
}
# 不上跑馬燈的分類:1 合作訊息(業配,如「羽衣甘藍」)、707 投資&創業&加密貨幣、1353 Uncategorized
EXCLUDE_CATS = {1, 707, 1353}
# 永遠放在最後的固定項目(子站入口)
PINNED = [("旅外球員數據", "https://players.clutchgtime.com/")]


def creds():
    u, p = os.environ.get("WP_USER"), os.environ.get("WP_APP_PASSWORD")
    if not (u and p):
        sys.exit("缺少 WP_USER / WP_APP_PASSWORD")
    return base64.b64encode(f"{u}:{p}".encode()).decode()


def call(auth, path, payload=None):
    last = None
    for i in range(4):
        try:
            req = urllib.request.Request(
                SITE + path,
                data=json.dumps(payload).encode() if payload is not None else None,
                headers={"Authorization": "Basic " + auth, "User-Agent": UA,
                         "Content-Type": "application/json"},
                method="POST" if payload is not None else "GET")
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last = e
            time.sleep(10 * (i + 1))  # 主機資料庫偶爾撐不住,退避久一點
    raise RuntimeError(f"{path}: {last}")


def short_label(title):
    t = re.split(r"[｜|：:？?（(]", title)[0].strip()
    return t if len(t) <= 12 else t[:11] + "…"


def top_posts(auth):
    data = call(auth, f"/wp-json/jetpack/v4/stats-app/sites/{BLOG_ID}/stats/top-posts"
                      f"?max=60&period=day&num=7")
    views = {}
    for day in (data.get("days") or {}).values():
        for p in day.get("postviews") or []:
            if p.get("type") != "post" or not p.get("public"):
                continue
            href = p.get("href") or ""
            v = views.setdefault(href, {"id": p.get("id"), "title": p.get("title") or "", "views": 0})
            v["views"] += int(p.get("views") or 0)
    ranked = sorted(views.items(), key=lambda kv: kv[1]["views"], reverse=True)[:40]
    ids = ",".join(str(v["id"]) for _, v in ranked if v["id"])
    cats = {x["id"]: set(x.get("categories") or []) for x in
            call(auth, f"/wp-json/wp/v2/posts?include={ids}&per_page=40&_fields=id,categories")}
    return [(h, v) for h, v in ranked if not (cats.get(v["id"], set()) & EXCLUDE_CATS)]


def build_items(posts):
    items, seen = [], set()
    for href, v in posts:
        slug = href.rstrip("/").rsplit("/", 1)[-1]
        label = LABELS.get(slug) or short_label(v["title"])
        if not label or label in seen:
            continue
        seen.add(label)
        items.append((label, href))
        if len(items) >= MAX_ITEMS:
            break
    return items + [x for x in PINNED if x[0] not in seen]


def update_popular(auth, posts, apply):
    """首頁「本週熱門文章」(Clutch Home Sections 外掛)讀 ct_sections_data.popular,這裡只改這個欄位。"""
    ids = [v["id"] for _, v in posts if v["id"]][:8]
    raw = call(auth, "/wp-json/wp/v2/settings").get("ct_sections_data")
    if raw is None:
        print("站上沒有 ct_sections_data(外掛沒啟用?),略過熱門文章")
        return
    data = json.loads(raw or "{}")
    if data.get("popular") == ids:
        print("熱門文章沒變,不寫入")
        return
    data["popular"] = ids
    if apply:
        call(auth, "/wp-json/wp/v2/settings",
             {"ct_sections_data": json.dumps(data, ensure_ascii=False, separators=(",", ":"))})
    print("熱門文章:", ids, "" if apply else "(dry-run,未寫入)")


def main():
    apply = "--apply" in sys.argv
    auth = creds()
    posts = top_posts(auth)
    if len(posts) < 5:
        print(f"統計資料太少({len(posts)} 篇),不更新")
        return
    update_popular(auth, posts, apply)
    items = build_items(posts)
    print("新清單:", "、".join(l for l, _ in items))

    w = call(auth, f"/wp-json/wp/v2/widgets/{WIDGET}?context=edit")
    raw = w["instance"]["raw"]["content"]
    m = re.search(r'(<script id="ct-marquee-js">.*?var T=)(\[.*?\]);', raw, re.S)
    if not m:
        sys.exit("找不到跑馬燈腳本(ct-marquee-js),不動")
    new_t = json.dumps([list(x) for x in items], ensure_ascii=False)
    if json.loads(m.group(2)) == json.loads(new_t):
        print("清單沒變,不寫入")
        return
    new_raw = raw[:m.start(2)] + new_t + raw[m.end(2):]
    if not apply:
        print("(dry-run,未寫入)")
        return
    call(auth, f"/wp-json/wp/v2/widgets/{WIDGET}", {"instance": {"raw": {"content": new_raw}}})
    print("已更新首頁跑馬燈")


if __name__ == "__main__":
    main()
