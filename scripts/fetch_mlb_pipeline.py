"""
MLB Pipeline 的球探評分(只取數字,不取評語)
==========================================
球探報告頁的「外部評價」區塊用。MLB Pipeline 的評分就寫在各隊農場頁的 HTML 裡,
格式固定:

    Scouting grades: Fastball: 60 | Slider: 60 | Changeup: 55 | Control: 50 | Overall: 55

**只抽這一行的數字,外加排名與原文連結。後面接的評語一個字都不存。**
分數是事實(陳述第三方做了什麼評價),評語是受著作權保護的表達 —— 這條線在這支
腳本裡就守住,不要等到渲染才想。讀者要看評語就點連結過去看原文。

覆蓋率先說清楚:Pipeline 只收各隊農場的球員,本站多數人要嘛已在大聯盟(不算
新秀)、要嘛排不上號。實測六隊只撈到 2 位,全掃 17 隊預估 3–6 位。撈不到是常態,
不是壞掉。

只掃「本站有球員」的球團,每週跑一次就夠,**不進每日 cron**(每頁約 870KB)。
執行: python3 scripts/fetch_mlb_pipeline.py
"""

import html
import json
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAYERS = ROOT / "public" / "data" / "players.json"
OUT = ROOT / "public" / "data" / "pipeline.json"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# players.json 的 org 中譯 → mlb.com 的隊伍代稱
TEAM_SLUG = {
    "響尾蛇": "dbacks", "運動家": "athletics", "水手": "mariners", "洋基": "yankees",
    "海盜": "pirates", "巨人": "giants", "馬林魚": "marlins", "太空人": "astros",
    "紅襪": "redsox", "老虎": "tigers", "紅人": "reds", "費城人": "phillies",
    "紅雀": "cardinals", "道奇": "dodgers", "釀酒人": "brewers", "教士": "padres",
    "雙城": "twins", "光芒": "rays", "皇家": "royals", "白襪": "whitesox",
    "藍鳥": "bluejays", "守護者": "guardians", "天使": "angels", "勇士": "braves",
    "國民": "nationals", "大都會": "mets", "小熊": "cubs", "落磯": "rockies",
    "遊騎兵": "rangers", "金鶯": "orioles",
}
# 「Scouting grades:」後面那行,到下一個標籤為止
GRADE_RE = re.compile(r"Scouting grades:\s*</strong>\s*([^<]{5,160})")
# 球員識別:頭像網址裡的 MLB 球員 id。**用 id 不用名字** —— 第一版用名字做鄰近比對,
# 結果「Wei-En Lin」出現在別人的評語內文裡(「簽約金與 Wei-En Lin 的 113 萬並列」),
# 抓到了隔壁球員的評分,三筆有兩筆是假的。
ID_RE = re.compile(r"people/(\d{6,7})")
# 投打的項目完全不同,用來驗證比對有沒有串號
PITCH_KEYS = {"Fastball", "Slider", "Curveball", "Changeup", "Control", "Cutter", "Splitter", "Sinker"}
HIT_KEYS = {"Hit", "Power", "Run", "Arm", "Field"}


def fetch(team):
    url = f"https://www.mlb.com/prospects/{team}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=40) as r:
            return html.unescape(html.unescape(r.read().decode("utf-8", "ignore"))), url
    except Exception as e:
        print(f"  [warn] {team}:{str(e)[:60]}")
        return None, url


def parse_grades(text):
    out = {}
    for part in text.split("|"):
        if ":" not in part:
            continue
        k, _, v = part.partition(":")
        v = v.strip()
        if v.isdigit():
            out[k.strip()] = int(v)
    return out


def harvest(doc):
    """回傳 {mlb_id: grades}。每一行評分歸給它前面最近的那個球員 id。"""
    ids = [(m.start(), m.group(1)) for m in ID_RE.finditer(doc)]
    if not ids:
        return {}
    found = {}
    for m in GRADE_RE.finditer(doc):
        pos = m.start()
        owner = None
        for p, pid in ids:              # 往前找最近的 id
            if p < pos:
                owner = pid
            else:
                break
        if not owner:
            continue
        g = parse_grades(m.group(1))
        if g and owner not in found:    # 同一人有多年份的 bio,取第一筆(最新)
            found[owner] = g
    return found


def main():
    players = [p for p in json.loads(PLAYERS.read_text(encoding="utf-8"))["players"]
               if str(p["id"]).isdigit() and p.get("name_en")]
    teams = {}
    for p in players:
        slug = TEAM_SLUG.get(p.get("org"))
        if slug:
            teams.setdefault(slug, []).append(p)
    if not teams:
        print("沒有可對應的球團,結束")
        sys.exit(0)

    out, scanned, rejected = {}, 0, 0
    for team, group in sorted(teams.items()):
        doc, url = fetch(team)
        if not doc:
            continue
        scanned += 1
        table = harvest(doc)
        for p in group:
            g = table.get(str(p["id"]))
            if not g:
                continue
            # 投手拿到打者項目(或反過來)就是比對串號了,寧可丟掉也不要寫錯的上站
            keys = set(g)
            is_p = p.get("role") == "pitcher"
            if (is_p and not keys & PITCH_KEYS) or (not is_p and not keys & HIT_KEYS):
                print(f"  ✗ {p['name']}:項目與身分不符({sorted(keys)}),捨棄")
                rejected += 1
                continue
            out[str(p["id"])] = {
                "org": "MLB Pipeline", "grades": g, "url": url,
                "asof": datetime.now().strftime("%Y-%m-%d"),
            }
            print(f"  ✓ {p['name']}：{g}")
        time.sleep(1.2)

    if not out:
        print(f"掃了 {scanned} 隊,沒有球員入榜(這是常態,不是失敗);保留既有檔案")
        sys.exit(0)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nMLB Pipeline 評分:{len(out)} 位 / 掃 {scanned} 隊"
          f"{f'、捨棄 {rejected} 筆不符' if rejected else ''} → {OUT.name}")


if __name__ == "__main__":
    main()
