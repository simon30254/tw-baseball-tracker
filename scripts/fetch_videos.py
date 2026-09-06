"""
為「亮點表現」抓 YouTube 精華影片 → scripts/videos_cache.json
===============================================================
對近期亮點場次(isHot:開轟/勝投/救援/優質先發/多安打),用 YouTube Data API 搜尋精華:
先以 publishedAfter/Before 鎖定「比賽日期前後」→ 抓到該場精華;找不到再退回通用集錦。
結果以 (球員id:日期) 為鍵快取(提交進 repo 持久化,不每天重查、省額度)。
build_players.py 會把命中的影片掛到對應 game_log(g.video),prerender 據此嵌入。

無 YOUTUBE_API_KEY 時安全跳過(exit 0),不影響其餘管線。
執行:YOUTUBE_API_KEY=... python3 scripts/fetch_videos.py
"""

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "public" / "data"
CACHE = ROOT / "scripts" / "videos_cache.json"
SOURCES = ["mlb.json", "npb.json", "kbo.json"]
KEY = os.environ.get("YOUTUBE_API_KEY", "").strip()

WINDOW_DAYS = 14      # 只查最近 14 天內的亮點場
MAX_CALLS = 85        # 單次執行 API 呼叫上限(每次 100 units;免費 10000/日)
RETRY_NULL_DAYS = 4   # 找不到影片者,4 天內仍重試(精華可能晚點才上傳)


def is_hot(g):
    if not g:
        return False
    if g.get("type") == "pitching":
        if g.get("win") or g.get("save"):
            return True
        try:
            if g.get("started") and float(g.get("ip", 0)) >= 6 and (g.get("er", g.get("r", 0)) or 0) <= 2:
                return True
        except (TypeError, ValueError):
            pass
        return (g.get("so", 0) or 0) >= 7
    return (g.get("hr", 0) or 0) > 0 or (g.get("h", 0) or 0) >= 2 or (g.get("rbi", 0) or 0) >= 2


def yt_search(q, after=None, before=None):
    params = {"part": "snippet", "q": q, "type": "video", "maxResults": 3, "order": "relevance", "key": KEY}
    if after:
        params["publishedAfter"] = after
    if before:
        params["publishedBefore"] = before
    url = "https://www.googleapis.com/youtube/v3/search?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.loads(r.read().decode("utf-8")).get("items", [])


def pick(items, name):
    """只接受標題或頻道名含球員全名的結果(避免抓到不相干影片)。"""
    for it in items:
        sn = it.get("snippet", {})
        if name in sn.get("title", "") or name in sn.get("channelTitle", ""):
            # publishedAt 供表現頁的 VideoObject 結構化資料用(uploadDate 是必要欄位,
            # 不能拿比賽日期充數 —— 影片常隔一天才上傳,寫錯就是給搜尋引擎錯資料)
            return it["id"]["videoId"], sn.get("title", ""), (sn.get("publishedAt") or "")[:10]
    return None, None, None


def backfill_published(cache):
    """舊快取只存了 id/title,沒有上傳日。用 videos.list 一次補 50 支(額度 1 點/次)。"""
    missing = [k for k, v in cache.items() if v.get("id") and not v.get("published")]
    if not missing:
        return 0
    filled = 0
    for i in range(0, len(missing), 50):
        chunk = missing[i:i + 50]
        ids = ",".join(cache[k]["id"] for k in chunk)
        url = ("https://www.googleapis.com/youtube/v3/videos?"
               + urllib.parse.urlencode({"part": "snippet", "id": ids, "key": KEY}))
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                items = json.loads(r.read().decode("utf-8")).get("items", [])
        except Exception as e:
            print(f"[fetch_videos] 補上傳日失敗 {str(e)[:80]}")
            return filled
        by_id = {it["id"]: (it.get("snippet", {}).get("publishedAt") or "")[:10] for it in items}
        for k in chunk:
            d = by_id.get(cache[k]["id"])
            if d:
                cache[k]["published"] = d
                filled += 1
    print(f"[fetch_videos] 補上傳日:{filled} 支")
    return filled


def main():
    if not KEY:
        print("[fetch_videos] 無 YOUTUBE_API_KEY,略過(不影響其他步驟)")
        return
    cache = {}
    if CACHE.exists():
        try:
            cache = json.loads(CACHE.read_text(encoding="utf-8"))
        except Exception:
            cache = {}

    games = []
    for s in SOURCES:
        p = DATA / s
        if not p.exists():
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        for pl in d.get("players", []):
            pid, name = str(pl["id"]), pl.get("name", "")
            for g in pl.get("game_logs", []):
                if is_hot(g) and g.get("date"):
                    games.append((g["date"], pid, name))
    if not games:
        print("[fetch_videos] 無亮點場次")
        return

    latest = max(g[0] for g in games)
    cutoff = (date.fromisoformat(latest) - timedelta(days=WINDOW_DAYS)).isoformat()
    stale = (date.fromisoformat(latest) - timedelta(days=RETRY_NULL_DAYS)).isoformat()
    # 近→遠、去重
    seen, todo = set(), []
    for dt, pid, name in sorted(set(games), reverse=True):
        if dt < cutoff:
            continue
        k = f"{pid}:{dt}"
        c = cache.get(k)
        if c and (c.get("id") or dt < stale):  # 已命中,或找不到且已過重試期 → 跳過
            continue
        todo.append((dt, pid, name, k))

    calls, found = 0, 0
    for dt, pid, name, k in todo:
        if calls >= MAX_CALLS:
            print(f"[fetch_videos] 達呼叫上限 {MAX_CALLS},其餘 {len(todo)-found} 場留待下次")
            break
        after = dt + "T00:00:00Z"
        before = (date.fromisoformat(dt) + timedelta(days=3)).isoformat() + "T00:00:00Z"
        vid = title = pub = None
        try:
            calls += 1
            vid, title, pub = pick(yt_search(name, after, before), name)  # 鎖定比賽日期
            if not vid and calls < MAX_CALLS:
                calls += 1
                vid, title, pub = pick(yt_search(f"{name} 精華"), name)   # 退回通用集錦
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:200]
            print(f"[fetch_videos] {k} HTTP {e.code} {body}")
            if e.code == 403 and "quota" in body.lower():
                print("[fetch_videos] 額度用盡,停止")
                break
            continue
        except Exception as e:
            print(f"[fetch_videos] {k} 錯誤 {str(e)[:80]}")
            continue
        cache[k] = {"id": vid, "title": title, "published": pub} if vid else {"id": None}
        if vid:
            found += 1

    backfill_published(cache)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
    hits = sum(1 for v in cache.values() if v.get("id"))
    print(f"[fetch_videos] 呼叫 {calls} 次、本次新命中 {found}、快取共 {len(cache)} 筆(有影片 {hits})")


if __name__ == "__main__":
    main()
