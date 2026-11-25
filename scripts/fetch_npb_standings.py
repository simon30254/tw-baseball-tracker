#!/usr/bin/env python3
"""NPB 戰績與個人排行 → public/data/npb_standings.json(給 /npb-standings/ 頁用)。

資料來源:npb.jp 官方(無 API,解析 HTML;需瀏覽器 UA)。
- 戰績:/bis/{年}/stats/std_c.html(央聯)、std_p.html(洋聯)
- 排行:/bis/{年}/stats/lb_*_{c,p}.html(打擊)、lp_*_{c,p}.html(投手),取前 10
  率類(打擊率、上壘率、防禦率)npb.jp 只列達規定打席/投球局者,照官方。
當年頁面還沒有(開季前)就退回上一季。球員名照 npb.jp 原文(日文漢字/片假名),不自行翻譯。
用法:python3 scripts/fetch_npb_standings.py
"""
import datetime as dt
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = ROOT / "public" / "data" / "archive"  # 每季一份,給 /{頁}/{年}/ 歷年頁用
OUT = ROOT / "public" / "data" / "npb_standings.json"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")
BASE = "https://npb.jp/bis/{y}/stats/"
LEAGUES = [("c", "中央聯盟"), ("p", "太平洋聯盟")]
# npb.jp 正式隊名 → 本站中文全名(與 prerender TEAM_DEFS 一致)
TEAM = {
    "阪神タイガース": "阪神虎", "読売ジャイアンツ": "讀賣巨人", "横浜DeNAベイスターズ": "橫濱DeNA海灣之星",
    "広島東洋カープ": "廣島東洋鯉魚", "東京ヤクルトスワローズ": "東京養樂多燕子", "中日ドラゴンズ": "中日龍",
    "福岡ソフトバンクホークス": "福岡軟銀鷹", "北海道日本ハムファイターズ": "北海道日本火腿鬥士",
    "オリックス・バファローズ": "歐力士猛牛", "東北楽天ゴールデンイーグルス": "東北樂天金鷲",
    "埼玉西武ライオンズ": "埼玉西武獅", "千葉ロッテマリーンズ": "千葉羅德海洋",
}
# 排行頁上的球隊簡稱 → 中文短名
ABBR = {"神": "阪神", "巨": "巨人", "デ": "DeNA", "広": "廣島", "ヤ": "養樂多", "中": "中日",
        "ソ": "軟銀", "日": "日本火腿", "オ": "歐力士", "楽": "樂天", "西": "西武", "ロ": "羅德"}
BAT = [("avg", "打擊率"), ("hr", "全壘打"), ("rbi", "打點"), ("h", "安打"), ("sb", "盜壘"), ("obp", "上壘率")]
PIT = [("era", "防禦率"), ("w", "勝投"), ("so", "三振"), ("sv", "救援成功"), ("hldp", "中繼成功點")]


def get(url):
    last = None
    for i in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8", "ignore")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            last = e
        except Exception as e:  # noqa: BLE001
            last = e
        time.sleep(5 * (i + 1))
    raise RuntimeError(f"{url}: {last}")


def cells(row):
    return [re.sub(r"\s+", " ", html.unescape(re.sub(r"<br\s*/?>", " ", re.sub(r"<(?!br)[^>]+>", "", c), flags=re.I))).strip()
            for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S | re.I)]


def standings(y, lg):
    h = get(BASE.format(y=y) + f"std_{lg}.html")
    if not h:
        return None
    t = h[h.find("<table"):]
    t = t[:t.find("</table>")]
    rows = []
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S):
        c = cells(r)
        if len(c) < 9 or c[0] not in TEAM:
            continue
        rows.append({"team": TEAM[c[0]], "team_ja": c[0], "g": int(c[1]), "w": int(c[2]), "l": int(c[3]),
                     "t": int(c[4]), "pct": c[5], "gb": "—" if c[6] in ("--", "-") else c[6],
                     "home": c[7].split(" ")[0], "away": c[8].split(" ")[0]})
    return rows


def leaders(y, prefix, key, lg):
    h = get(BASE.format(y=y) + f"{prefix}_{key}_{lg}.html")
    if not h:
        return []
    out = []
    for r in re.findall(r'<tr class="ststats">(.*?)</tr>', h, re.S):
        c = cells(r)
        if len(c) < 3:
            continue
        m = re.match(r"(.+?)\s*\((.)\)$", c[1])
        name, ab = (m.group(1), m.group(2)) if m else (c[1], "")
        out.append({"rank": int(c[0]) if c[0].isdigit() else None, "name": name.strip(), "team": ABBR.get(ab, ab), "value": c[2]})
        if len(out) >= 10 and (out[-1]["rank"] or 0) >= 10:
            break
    return out


def fetch(y):
    lgs = []
    for lg, zh in LEAGUES:
        st = standings(y, lg)
        if not st:
            return None
        cats = [{"key": k, "group": "batting", "name": n, "rows": leaders(y, "lb", k, lg)} for k, n in BAT]
        cats += [{"key": k, "group": "pitching", "name": n, "rows": leaders(y, "lp", k, lg)} for k, n in PIT]
        lgs.append({"id": lg, "name": zh, "teams": st, "leaders": cats})
    return lgs


def main():
    y = dt.date.today().year
    lgs = fetch(y)
    if not lgs or sum(t["g"] for l in lgs for t in l["teams"]) == 0:
        y -= 1
        lgs = fetch(y)
    if not lgs or any(len(l["teams"]) != 6 for l in lgs):
        sys.exit(f"NPB 戰績不完整,不覆寫 {OUT.name}")
    games = {t["g"] for l in lgs for t in l["teams"]}
    _payload = json.dumps({
        "season": y, "final": games == {143},
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "leagues": lgs,
    }, ensure_ascii=False, indent=1)
    OUT.write_text(_payload, encoding="utf-8")
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    (ARCHIVE / f"npb_standings_{json.loads(_payload)['season']}.json").write_text(_payload, encoding="utf-8")
    print(f"NPB 戰績:{y} 球季{'(例行賽已結束)' if games == {143} else ''},寫入 {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
