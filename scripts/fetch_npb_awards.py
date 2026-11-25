#!/usr/bin/env python3
"""日職歷屆日本一 + MVP/新人王/澤村賞 → public/data/npb_awards.json(給 /npb-awards/ 系列頁用)。

資料來源:npb.jp 官方
- 日本大賽:/bis/scores/nipponseries/yearlyresults{1950,1960,…}.html(1950 年起,冠亞軍與勝場)
- 表彰:/award/{年}/cl.html、pl.html(最優秀選手、最優秀新人)、shosawa.html(沢村栄治賞)
  npb.jp 的表彰頁只收錄 2002 年起,所以獎項從 2002 年開始;更早的年份不從非官方來源補。
球隊照 npb.jp 寫法的簡稱轉中文短名(漢字隊名直接用繁體字,片假名用本站慣用譯名),球員名保留 npb.jp 原文。
用法:python3 scripts/fetch_npb_awards.py
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
OUT = ROOT / "public" / "data" / "npb_awards.json"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")
# npb.jp 上出現的球隊簡稱(去空白後)→ 中文短名。漢字隊名只轉繁體,不另取譯名。
TEAM = {
    "巨人": "巨人", "読売": "巨人", "阪神": "阪神", "中日": "中日", "広島": "廣島", "広島東洋": "廣島",
    "ヤクルト": "養樂多", "東京ヤクルト": "養樂多", "国鉄": "國鐵", "サンケイ": "產經", "アトムズ": "原子",
    "大洋": "大洋", "横浜": "橫濱", "横浜DeNA": "DeNA", "DeNA": "DeNA", "松竹": "松竹",
    "ソフトバンク": "軟銀", "福岡ソフトバンク": "軟銀", "ダイエー": "大榮", "福岡ダイエー": "大榮", "南海": "南海",
    "西武": "西武", "埼玉西武": "西武", "西鉄": "西鐵", "太平洋": "太平洋", "クラウン": "皇冠",
    "ロッテ": "羅德", "千葉ロッテ": "羅德", "毎日": "每日", "大毎": "大每", "東京": "東京",
    "日本ハム": "日本火腿", "北海道日本ハム": "日本火腿", "東映": "東映", "日拓": "日拓",
    "オリックス": "歐力士", "阪急": "阪急", "近鉄": "近鐵", "大阪近鉄": "近鐵", "楽天": "樂天", "東北楽天": "樂天",
}


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


def text(h):
    h = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->", "", h, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h))).replace("　", " ")


def team(x):
    k = re.sub(r"[\s　]", "", x)
    return TEAM.get(k, k)


def japan_series():
    out = {}
    for dec in range(1950, dt.date.today().year + 1, 10):
        h = get(f"https://npb.jp/bis/scores/nipponseries/yearlyresults{dec}.html")
        if not h:
            continue
        for m in re.finditer(r'class="seriesYear">【\s*(\d{4})\s*】</td>\s*<td class="seriesStats">(.*?)</td>', h, re.S):
            y, st = int(m.group(1)), m.group(2)
            w = re.search(r'seriesWinner">(.*?)</span>\s*<span class="seriesWin">（(\d)勝(?:(\d)分)?）', st, re.S)
            l = re.search(r'seriesLoser">(.*?)</span>\s*<span class="seriesWin">（(\d)勝(?:(\d)分)?）', st, re.S)
            if not (w and l):
                continue
            ties = w.group(3) or l.group(3)
            out[y] = {"champ": team(re.sub(r"<[^>]+>", "", w.group(1))), "runner": team(re.sub(r"<[^>]+>", "", l.group(1))),
                      "result": f"{w.group(2)}-{l.group(2)}" + (f"-{ties}" if ties else "")}
    return out


NAME_TEAM = r"([^\s（）]+(?: [^\s（）]+)?) ?（([^）]+)）"


def league_awards(y, lg):
    h = get(f"https://npb.jp/award/{y}/{lg}.html")
    if not h:
        return None
    t = text(h)
    t = t[t.find(f"{y}年度"):] if f"{y}年度" in t else t
    res = {}
    for key, label in (("mvp", "最優秀選手"), ("roy", "最優秀新人")):
        m = re.search(label + r"賞? (該当者なし|" + NAME_TEAM + ")", t)
        if not m:
            continue
        res[key] = [] if m.group(1) == "該当者なし" else [{"name": m.group(2), "team": team(m.group(3))}]
    return res


def sawamura(y):
    h = get(f"https://npb.jp/award/{y}/shosawa.html")
    if not h:
        return None
    t = text(h)
    if re.search(r"沢村栄治賞 該当者なし", t):  # 2019、2024 等年度從缺
        return []
    m = re.search(r"沢村栄治賞 沢村栄治賞 (.*?)(?: 長嶋茂雄賞| \d{4}年 |$)", t)
    if not m:
        return None
    seg = m.group(1)
    if "該当者なし" in seg[:20]:
        return []
    return [{"name": a, "team": team(b)} for a, b in re.findall(NAME_TEAM, seg)]


def main():
    this = dt.date.today().year
    js = japan_series()
    years = []
    for y in range(1950, this + 1):
        rec = {"season": y, "js": js.get(y)}
        if y >= 2002:
            aw = {}
            for lg in ("cl", "pl"):
                r = league_awards(y, lg)
                if r:
                    aw[lg] = r
            s = sawamura(y)
            if s is not None:
                aw["sawamura"] = s
            rec["awards"] = aw
            time.sleep(0.3)
        years.append(rec)
    last = next(r for r in years if r["season"] == this - 1)
    if not (last["js"] and last.get("awards", {}).get("cl", {}).get("mvp")):
        sys.exit(f"{this - 1} 資料不完整,不覆寫 {OUT.name}")
    OUT.write_text(json.dumps({"fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                               "years": years}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"NPB 歷屆:日本大賽 {len(js)} 屆、獎項 2002–{this},寫入 {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
