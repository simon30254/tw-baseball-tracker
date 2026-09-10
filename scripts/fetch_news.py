"""
旅外球員新聞 → public/data/news.json
====================================
每位現役球員的名字丟進 Bing News RSS,把標題或摘要真的出現球員全名的新聞留下來,
每天累積成一份「最新消息」(首頁側欄 + /news/ 頁)。

為什麼是 Bing 而不是 Google News RSS:
  Google News RSS 覆蓋率更好(單一球員上百則),但 <link> 是 news.google.com 的
  不透明 token,新版既不轉址也解不出原始網址 —— 每則消息都連到 Google 中繼頁。
  Bing 的 apiclick.aspx 連結帶 `url=` 參數,可以還原成媒體的真實網址,另外還給
  <News:Source> 媒體名與 <description> 摘要,做出來的頁面品質差很多。

兩個踩過的坑:
  1. **查詢不能加引號**。Bing 的片語搜尋 `"林昱珉"` 回 0 筆,拿掉引號回 12 筆。
     所以查詢用裸名字,再自己用全名做精確比對(Bing 會回「廖宥期」「廖源霖」這種
     形近的別人,精確比對擋得掉)。
  2. **不要加棒球關鍵字白名單**。實測會誤殺真新聞 —— 「3A 炸裂本季第 9 轟」
     「本壘劇烈碰撞傷退」都沒有「棒球/大聯盟」這類詞。全名比對本身已經夠準。

執行:python3 scripts/fetch_news.py
"""

import html
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "public" / "data"
SOURCES = ["mlb.json", "npb.json", "kbo.json"]
ALIASES_PATH = ROOT / "scripts" / "news_aliases.json"
OUT = DATA / "news.json"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125 Safari/537.36")
TW = timezone(timedelta(hours=8))
TIMEOUT = 20
KEEP_DAYS = 45      # 保留天數(過期的自然淘汰,檔案不會無限長大)
MAX_ITEMS = 400
MAX_SUMMARY = 90

# Bing 的 News:Source 有時給網域或掛著 " on MSN" 的轉載標記,統一成讀得懂的媒體名
SOURCE_FIX = {
    "tw.sports": "Yahoo奇摩運動", "tw.news": "Yahoo奇摩新聞", "ltn.com.tw": "自由時報",
    "udn.com": "聯合新聞網", "ettoday.net": "ETtoday", "chinatimes.com": "中時新聞網",
    "setn.com": "三立新聞網", "tvbs.com.tw": "TVBS新聞網", "nownews.com": "NOWnews今日新聞",
    "今日新聞": "NOWnews今日新聞", "cna.com.tw": "中央社",
}
# 內文摘要裡的插播/導引句,留著會讓摘要整段是廣告詞
NOISE = ["我是廣告", "請繼續往下閱讀", "點我加入", "延伸閱讀", "更多內容", "▲", "記者", "／"]


def clean_source(s):
    s = re.sub(r"\s+on\s+MSN$", "", (s or "").strip(), flags=re.I)
    return SOURCE_FIX.get(s, s)


def clean_summary(s):
    s = re.sub(r"<[^>]+>", "", html.unescape(s or ""))
    s = re.sub(r"\s+", " ", s).strip()
    for n in NOISE:
        s = s.replace(n, " ")
    s = re.sub(r"\s+", " ", s).strip(" ．…·-—　")
    return (s[:MAX_SUMMARY] + "…") if len(s) > MAX_SUMMARY else s


def real_url(link):
    """apiclick.aspx?...&url=<真實網址> → 真實網址;取不到就退回原連結。"""
    try:
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(link).query)
        u = (qs.get("url") or [""])[0]
        if u.startswith("http"):
            return u
    except Exception:
        pass
    return link


def norm_url(u):
    """去掉追蹤參數與結尾斜線,同一篇文章不同來路才不會重複列。"""
    try:
        pr = urllib.parse.urlparse(u)
        keep = [(k, v) for k, v in urllib.parse.parse_qsl(pr.query)
                if not k.lower().startswith(("utm_", "fbclid", "gclid"))]
        return urllib.parse.urlunparse(
            (pr.scheme, pr.netloc.lower(), pr.path.rstrip("/"), "", urllib.parse.urlencode(keep), "")
        )
    except Exception:
        return u


def en_name_of(pid):
    """球員的英文名。旅日/旅韓的 name_en 存的是中文,那種不查英文來源。"""
    for name in SOURCES:
        path = DATA / name
        if not path.exists():
            continue
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for p in d.get("players", []):
            if str(p["id"]) != str(pid):
                continue
            en = (p.get("name_en") or "").strip()
            return en if re.match(r"^[A-Za-z][A-Za-z .'\-]+$", en) else ""
    return ""


def roster():
    """(id, 中文名, [比對用的別名]) —— 別名給媒體慣用寫法不同的球員(台裔)。"""
    aliases = {}
    if ALIASES_PATH.exists():
        try:
            aliases = json.loads(ALIASES_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  [略過] news_aliases.json: {e}", file=sys.stderr)
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
            if pid in seen or not p.get("name"):
                continue
            seen.add(pid)
            out.append((pid, p["name"], [p["name"], *aliases.get(pid, [])]))
    return out


def bing_news(term, market="zh-TW"):
    q = urllib.parse.urlencode({"q": term, "format": "RSS", "setmkt": market})
    req = urllib.request.Request(f"https://www.bing.com/news/search?{q}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        raw = html.unescape(r.read().decode("utf-8", "replace"))
    out = []
    for it in re.findall(r"<item>(.*?)</item>", raw, re.S):
        def tag(name):
            m = re.search(rf"<{name}>(.*?)</{name}>", it, re.S)
            return re.sub(r"<!\[CDATA\[|\]\]>", "", m.group(1)).strip() if m else ""
        title, link = tag("title"), tag("link")
        if not title or not link:
            continue
        try:
            when = parsedate_to_datetime(tag("pubDate")).astimezone(TW).date().isoformat()
        except Exception:
            when = datetime.now(TW).date().isoformat()
        out.append({
            "title": title,
            "url": real_url(link),
            "source": clean_source(tag("News:Source")),
            "date": when,
            "summary": clean_summary(tag("description")),
            "lang": "zh" if market.startswith("zh") else "en",
        })
    return out


def title_key(t):
    """同一篇被 MSN 轉載或通訊社轉發時,標題只差全形/半形驚嘆號。正規化後比對。"""
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", t or "")).lower()


def dedup_titles(items):
    """同一天同一則標題只留一筆,優先留原媒體的網址(MSN 轉載頁是二手來源)。"""
    best = {}
    for it in items:
        k = (it.get("date", ""), title_key(it.get("title")))
        cur = best.get(k)
        if cur is None or ("msn.com" in cur["url"] and "msn.com" not in it["url"]):
            if cur is not None:
                have = {x["id"] for x in it.get("players", [])}
                it["players"] = it.get("players", []) + [x for x in cur.get("players", []) if x["id"] not in have]
            best[k] = it
        else:
            have = {x["id"] for x in cur.get("players", [])}
            cur["players"] = cur.get("players", []) + [x for x in it.get("players", []) if x["id"] not in have]
    out = list(best.values())
    out.sort(key=lambda v: (v.get("date", ""), v.get("title", "")), reverse=True)
    return out


def main():
    people = roster()
    if not people:
        print("找不到球員名單,先跑 fetch_data / fetch_npb / fetch_kbo")
        sys.exit(1)
    # 一則新聞常同時提到好幾位球員(「徐若熙、鄭宗哲等 4 旅外退出亞運」),
    # 所以每則都拿全名單比對一次,標記出全部相關球員,而不是只掛在查詢的那位身上。
    all_terms = [(pid, name, terms) for pid, name, terms in people]

    # 英文來源。旅美球員在美國媒體(隨隊記者、球隊官網、CBS/NBC 的每日短訊)常有中文
    # 媒體沒報的東西 —— 傷勢更新、下放內幕、簽約背景。**這些不會直接上站**:整篇翻譯
    # 是改作(翻譯權是著作權法明列的專有權利),把英文標題丟到中文站上也沒有意義。
    # 它們只當兩件事:①出處掛名 ②scripts/draft_events.py 的素材,由人寫成中文事實摘要。
    en_terms = {}
    for pid, name, _ in people:
        p_en = en_name_of(pid)
        if p_en:
            en_terms[pid] = p_en

    found = {}   # norm_url -> item
    for i, (pid, name, terms) in enumerate(people, 1):
        try:
            items = bing_news(name)
        except Exception as e:
            print(f"  [失敗] {name}: {type(e).__name__} {e}", file=sys.stderr)
            continue
        en = en_terms.get(pid)
        if en:
            try:
                for x in bing_news(en, "en-US"):
                    text = x["title"] + " " + x["summary"]
                    if en.lower() in text.lower():
                        x["players_en"] = [pid]
                        items.append(x)
            except Exception as e:
                print(f"  [英文失敗] {en}: {type(e).__name__} {e}", file=sys.stderr)
            time.sleep(0.35)
        for it in items:
            text = it["title"] + " " + it["summary"]
            if it.get("lang") == "en":
                # 英文報導裡不會出現中文全名,改用英文名比對(順便讓一篇同時點到
                # 好幾位台將的英文報導也能標到全部的人)
                low = text.lower()
                tagged = [{"id": q, "name": nm} for q, nm, _ in all_terms
                          if (en_terms.get(q) or "").lower() and en_terms[q].lower() in low]
            else:
                tagged = [{"id": q, "name": n} for q, n, ts in all_terms if any(t in text for t in ts)]
            if not tagged:
                continue
            key = norm_url(it["url"])
            if key in found:
                # 同一篇被多位球員的查詢撈到:合併球員標記即可
                have = {x["id"] for x in found[key]["players"]}
                found[key]["players"] += [x for x in tagged if x["id"] not in have]
            else:
                found[key] = {**it, "players": tagged}
        if i % 10 == 0:
            print(f"  已查 {i}/{len(people)}")
        time.sleep(0.35)

    # 與既有檔合併:舊的留著(Bing 只回最近十幾則,不累積就等於每天洗掉昨天的)
    old = []
    if OUT.exists():
        try:
            old = json.loads(OUT.read_text(encoding="utf-8")).get("items", [])
        except Exception:
            old = []
    merged = {norm_url(o["url"]): o for o in old}
    added = 0
    for k, v in found.items():
        if k in merged:
            have = {x["id"] for x in merged[k].get("players", [])}
            merged[k]["players"] = merged[k].get("players", []) + [x for x in v["players"] if x["id"] not in have]
        else:
            merged[k] = v
            added += 1

    cutoff = (datetime.now(TW).date() - timedelta(days=KEEP_DAYS)).isoformat()
    items = [v for v in merged.values() if v.get("date", "") >= cutoff]
    items.sort(key=lambda v: (v.get("date", ""), v.get("title", "")), reverse=True)
    items = dedup_titles(items)[:MAX_ITEMS]

    # 抓不到任何東西時不要把既有的消息洗掉(Bing 擋機房 IP、改版都可能發生)
    if not found and old:
        print("這次一則都沒抓到,保留既有 news.json 不覆寫")
        sys.exit(1)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(
        {"updated_at": datetime.now(TW).isoformat(timespec="seconds"), "items": items},
        ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    with_news = len({x["id"] for v in items for x in v.get("players", [])})
    print(f"完成:{OUT} — 本次抓到 {len(found)} 則(新增 {added}),"
          f"檔內共 {len(items)} 則、涵蓋 {with_news}/{len(people)} 位球員")


if __name__ == "__main__":
    main()
