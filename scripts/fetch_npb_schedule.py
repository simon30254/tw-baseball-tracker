#!/usr/bin/env python3
"""NPB 賽程抓取 → 給 clutchgtime 的「日本職棒賽程」表格。

資料來源:npb.jp 官方月賽程頁(無官方 API,故爬 HTML,與 fetch_npb.py 同一慣例)
  https://npb.jp/games/{season}/schedule_{MM}_detail.html

為什麼不是照搬官方表:照抄等於做一個比 npb.jp 更差的 npb.jp,排名贏不了它。
這份的差異化在三件事,都是官方沒有的——繁中隊名、台灣時間、每座球場接到
clutchgtime 自己的看球攻略頁。所以輸出以「台灣人去日本看球」為主體。

用法:
  python3 scripts/fetch_npb_schedule.py            # 抓取 + 寫 npb_schedule.json + 預覽
  python3 scripts/fetch_npb_schedule.py --days 21  # 表格取未來幾天(預設 14)
輸出:scripts/npb_schedule.json(原始場次)、預覽 HTML 印在 stdout
"""
import json, re, sys, time, urllib.request, urllib.error
from datetime import date, datetime, timedelta
from pathlib import Path

SEASON = int(__import__("os").environ.get("NPB_SEASON") or date.today().year)
BASE = "https://npb.jp"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")
OUT = Path(__file__).resolve().parent / "npb_schedule.json"

# 隊名沿用 fetch_npb.py 既有的簡短譯名,兩邊不該各寫各的。
TEAM_ZH = {
    "巨人": "巨人", "阪神": "阪神", "広島": "廣島", "ヤクルト": "養樂多",
    "中日": "中日", "DeNA": "DeNA", "ロッテ": "羅德", "楽天": "樂天",
    "ソフトバンク": "軟銀", "オリックス": "歐力士", "西武": "西武",
    "日本ハム": "日本火腿", "セ・リーグ": "中央聯盟", "パ・リーグ": "太平洋聯盟",
}

# 球場 → (繁中名, clutchgtime 攻略頁 slug)。slug 全部是站上實際存在的頁面,
# 沒有攻略頁的地方球場留 None,寧可不連也不要連到 404。
STADIUM = {
    "横浜":            ("橫濱球場",           "yokohama-stadium-guide"),
    "京セラD大阪":     ("京瓷巨蛋大阪",       "kyocera-dome-osaka-guide"),
    "マツダスタジアム": ("MAZDA 廣島球場",     "mazda-stadium-hiroshima-guide"),
    "ZOZOマリン":      ("ZOZO 海洋球場",      "zozo-marine-stadium-guide"),
    "神宮":            ("明治神宮球場",       "meiji-jingu-stadium-guide"),
    "エスコンＦ":      ("ES CON FIELD 北海道", "es-con-field-hokkaido-guide"),
    "甲子園":          ("阪神甲子園球場",     "koshien-baseball-guide"),
    "東京ドーム":      ("東京巨蛋",           "tokyo-dome-baseball-guide"),
    "バンテリンドーム": ("Vantelin 巨蛋名古屋", "vantelin-dome-nagoya-guide"),
    "みずほPayPay":    ("福岡 PayPay 巨蛋",   "mizuho-paypay-dome-fukuoka-guide"),
    "楽天モバイル":    ("樂天 Mobile 宮城",   "rakuten-mobile-park-miyagi-guide"),
    "ベルーナドーム":  ("Belluna 巨蛋",       "belluna-dome-guide"),
    "ほっと神戸":      ("Hotto Motto 神戶",   "hotto-motto-field-kobe-guide"),
}
WEEK_ZH = ["一", "二", "三", "四", "五", "六", "日"]
ROW = re.compile(r'<tr id="date(\d{4})"[^>]*>(.*?)</tr>', re.S)


def get(url, tries=3):
    for a in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return ""       # 該月沒有賽程(季外),不是錯誤
            time.sleep(3)
        except Exception:
            time.sleep(3)
    return ""


def cell(body, cls):
    m = re.search(r'<div class="%s">(.*?)</div>' % cls, body, re.S)
    if not m:
        return ""
    return re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", m.group(1))).strip()


def fetch_month(month):
    html = get(f"{BASE}/games/{SEASON}/schedule_{month:02d}_detail.html")
    games = []
    for mmdd, body in ROW.findall(html):
        home, away = cell(body, "team1"), cell(body, "team2")
        if not (home and away):
            continue
        place = cell(body, "place")
        # 比分只在已結束的場次出現,用它判斷場次狀態
        played = bool(re.search(r'<div class="score1">\s*\d', body))
        games.append({
            "date": f"{SEASON}-{mmdd[:2]}-{mmdd[2:]}",
            "home": home, "away": away,
            "home_zh": TEAM_ZH.get(home, home), "away_zh": TEAM_ZH.get(away, away),
            "place": place,
            "place_zh": STADIUM.get(place, (place, None))[0],
            "guide": STADIUM.get(place, (place, None))[1],
            "time_jst": cell(body, "time"),
            "note": cell(body, "comment"),
            "played": played,
        })
    return games


def tw_time(jst):
    """日本 UTC+9、台灣 UTC+8,所以台灣時間永遠早一小時。看球行程會用到,官方沒有。"""
    m = re.match(r"^(\d{1,2}):(\d{2})$", jst or "")
    if not m:
        return ""
    h = (int(m.group(1)) - 1) % 24
    return f"{h:02d}:{m.group(2)}"


def render(games, days, today=None):
    today = today or date.today()
    end = today + timedelta(days=days)
    up = [g for g in games
          if not g["played"] and today.isoformat() <= g["date"] <= end.isoformat()]
    up.sort(key=lambda g: (g["date"], g["time_jst"]))
    rows = []
    for g in up:
        d = datetime.strptime(g["date"], "%Y-%m-%d").date()
        when = f"{d.month}/{d.day}（{WEEK_ZH[d.weekday()]}）"
        place = (f'<a href="https://clutchgtime.com/{g["guide"]}/">{g["place_zh"]}</a>'
                 if g["guide"] else g["place_zh"])
        tw = tw_time(g["time_jst"])
        rows.append(
            f'<tr><td>{when}</td><td>{g["away_zh"]} @ {g["home_zh"]}</td>'
            f'<td>{place}</td><td>{g["time_jst"] or "—"}</td><td>{tw or "—"}</td></tr>')
    return up, (
        '<table class="ct-npb-schedule">\n<thead><tr>'
        '<th>日期</th><th>對戰（客 @ 主）</th><th>球場</th>'
        '<th>開賽(日本)</th><th>台灣時間</th></tr></thead>\n<tbody>\n'
        + "\n".join(rows) + "\n</tbody>\n</table>")


def main():
    days = 14
    if "--days" in sys.argv:
        days = int(sys.argv[sys.argv.index("--days") + 1])

    games = []
    for mo in range(3, 12):
        g = fetch_month(mo)
        print(f"  {mo:02d} 月: {len(g)} 場", file=sys.stderr)
        games += g
    games.sort(key=lambda g: (g["date"], g["time_jst"]))
    OUT.write_text(json.dumps({"season": SEASON, "fetched": date.today().isoformat(),
                               "games": games}, ensure_ascii=False, indent=1), encoding="utf-8")

    unknown_t = sorted({g["home"] for g in games if g["home"] not in TEAM_ZH}
                       | {g["away"] for g in games if g["away"] not in TEAM_ZH})
    unknown_p = sorted({g["place"] for g in games if g["place"] not in STADIUM})
    print(f"\n總場次 {len(games)}  → {OUT}", file=sys.stderr)
    if unknown_t:
        print(f"⚠ 未對照隊名: {unknown_t}", file=sys.stderr)
    print(f"無攻略頁的球場({len(unknown_p)}, 皆為地方球場): {' '.join(unknown_p)}", file=sys.stderr)

    up, html = render(games, days)
    print(f"未來 {days} 天 {len(up)} 場\n", file=sys.stderr)
    print(html)


if __name__ == "__main__":
    main()
