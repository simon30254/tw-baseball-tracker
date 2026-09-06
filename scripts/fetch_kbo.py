"""
旅韓(KBO)台灣球員資料抓取腳本
==============================
資料來源:**KBO 官方網站 koreabaseball.com**(無官方 API,爬 HTML)
2026 起 KBO 亞援制度首批台將:王彥程(韓華鷹)。

為什麼是官網(2026-09-06 換源)
------------------------------
原本抓運彩報馬仔 lottonavi,但該站掛 Cloudflare,對機房 IP 一律回挑戰頁,
GitHub Actions 上 100% 403(連首頁都進不去,加瀏覽器 header、走 r.jina.ai
代抓都無效)→ 正式站的王彥程數據從 8/18 起悄悄凍結了兩週多。
官網沒有 Cloudflare,已實測 runner 上 200;而且資料更準:lottonavi 的
「保送 59」其實是四壞 53 + 觸身 6 混在一起、投球局數也少算了一局。

頁面
----
* 逐場:`/Record/Player/{Pitcher,Hitter}Detail/Daily.aspx?playerId=`
  一個月一張表,只含例行賽(舊源把熱身賽混在同一張表的老問題自動消失)。
* 逐年+生涯:`/Record/Player/{Pitcher,Hitter}Detail/Total.aspx?playerId=`
  用來產當季 season_stats 與往年 prev_season(與旅美/旅日的回追一致)。

`playerId` 與舊的 lottonavi id 是同一組(lottonavi 直接沿用官方 id),
名單不必重編;roster 的 `kbo_id`(舊名 `lottonavi_id`)兩種寫法都吃。

限制:官網逐場表沒有主客場欄位,故 KBO 的 game_log 不帶 `is_home`
(前端遇到 None 就不顯示「（主場）／（客場）」)。

流程:
1. 讀 scripts/kbo_roster.json 手動名單
2. Daily.aspx → 逐場;Total.aspx → 當季 season_stats + 往年 prev_season
3. 輸出 public/data/kbo.json(與 MLB/NPB 相同 schema,league="kbo",level="一軍")

執行: python3 scripts/fetch_kbo.py
"""

import json
import re
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")
BASE = "https://www.koreabaseball.com"
KST = timezone(timedelta(hours=9))
TW = timezone(timedelta(hours=8))
SEASON = datetime.now(KST).year

ROOT = Path(__file__).resolve().parent.parent
ROSTER_PATH = ROOT / "scripts" / "kbo_roster.json"
OUTPUT_PATH = ROOT / "public" / "data" / "kbo.json"

# 對手隊名中譯。官網 상대 欄用韓文簡稱或英文縮寫,沿用站上既有的中文寫法
# (起亞/斗山/…),換源後前端與 clutchgtime 近況表的隊名才不會整批跳動。
TEAM_ZH = {
    "한화": "韓華", "KIA": "起亞", "두산": "斗山", "삼성": "三星", "키움": "英雄",
    "KT": "巫師", "SSG": "登陸者", "LG": "雙子", "롯데": "樂天", "NC": "恐龍",
}


def get(url):
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", "replace")
        except Exception as e:
            if attempt == 2:
                print(f"  [WARN] 放棄 {url}: {e}")
                return None
            time.sleep(2 * (attempt + 1))


def clean(s):
    return re.sub(r"<[^>]+>", "", s).replace("&nbsp;", "").strip()


def to_int(s):
    try:
        return int(str(s).strip())
    except (ValueError, TypeError):
        return 0


def parse_tables(html):
    """每張 <table> 解析成 (表頭, 資料列)。

    兩個官網版面上的坑:
    1. 「합계」(月合計)、「통산」(生涯合計)那幾列寫成 <th> 而不是 <td> ——
       只收 <td> 的話生涯合計整列會消失,所以逐列連 th 一起取。
    2. 那幾列的首格用 colspan 併掉了「팀명」欄,不展開 colspan 的話整排欄位
       會左移一格(生涯防禦率會讀到勝場數之類)。這裡照 colspan 補足空格。"""
    out = []
    for t in re.findall(r"<table.*?</table>", html, re.S):
        rows = []
        for r in re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S):
            cells = []
            for attrs, inner in re.findall(r"<t[hd]([^>]*)>(.*?)</t[hd]>", r, re.S):
                m = re.search(r'colspan\s*=\s*["\']?(\d+)', attrs, re.I)
                cells.append(clean(inner))
                cells += [""] * (int(m.group(1)) - 1 if m else 0)
            if cells:
                rows.append(cells)
        if len(rows) >= 2:
            out.append((rows[0], rows[1:]))
    return out


def ip_to_our(s):
    """官網投球局數「3 1/3」「5」「2/3」→ 站內慣用的「3.1」「5.0」「0.2」。"""
    s = str(s).strip()
    if not s:
        return "0.0"
    m = re.match(r"^(?:(\d+))?\s*(?:(\d)/3)?$", s)
    if not m:
        return s
    whole = int(m.group(1) or 0)
    third = int(m.group(2) or 0)
    return f"{whole}.{third}"


def outs_of(ip):
    p = str(ip).split(".")
    return int(p[0]) * 3 + (int(p[1]) if len(p) > 1 else 0)


def fmt_ip(outs):
    whole, frac = divmod(outs, 3)
    return f"{whole}.{frac}"


def rate(num, den, digits=2):
    """自算 ERA/WHIP/AVG:官網逐年表沒給的欄位才用,除數 0 就留空。"""
    if not den:
        return ""
    v = num / den
    return f"{v:.{digits}f}" if digits == 2 else f"{v:.3f}".lstrip("0")


# ---------------------------------------------------------------------------
# 逐場(Daily.aspx)
# ---------------------------------------------------------------------------

def parse_daily(html, is_pitcher):
    """月份表 → game_logs。資料列首欄是「09.03」這種 MM.DD。"""
    logs = []
    for heads, rows in parse_tables(html):
        col = {h: i for i, h in enumerate(heads)}
        for c in rows:
            if not re.match(r"^\d{2}\.\d{2}$", c[0] or ""):
                continue

            def v(name, default=""):
                i = col.get(name)
                return c[i] if i is not None and i < len(c) else default

            mm, dd = c[0].split(".")
            opp = v("상대")
            g = {
                "date": f"{SEASON}-{mm}-{dd}",
                "level": "一軍",
                "opponent": TEAM_ZH.get(opp, opp),
            }
            if is_pitcher:
                result = v("결과")
                g.update({
                    "type": "pitching",
                    "ip": ip_to_our(v("IP")),
                    "h": to_int(v("H")), "r": to_int(v("R")), "er": to_int(v("ER")),
                    "hr": to_int(v("HR")), "bb": to_int(v("BB")), "so": to_int(v("SO")),
                    "win": result == "승", "loss": result == "패",
                    "save": result == "세", "hold": result == "홀",
                    "started": v("구분") == "선발",
                })
            else:
                g.update({
                    "type": "hitting",
                    "ab": to_int(v("AB")), "r": to_int(v("R")), "h": to_int(v("H")),
                    "rbi": to_int(v("RBI")), "sb": to_int(v("SB")), "hr": to_int(v("HR")),
                    "bb": to_int(v("BB")), "so": to_int(v("SO")), "avg": "",
                })
            logs.append(g)
    logs.sort(key=lambda x: x["date"], reverse=True)
    return logs


# ---------------------------------------------------------------------------
# 逐年 / 生涯(Total.aspx)
# ---------------------------------------------------------------------------

def parse_total(html, is_pitcher):
    """→ ({年份: stats}, 生涯合計)。同年多列(季中換隊)就把累計欄位相加、比率欄位重算。"""
    years, career = {}, None
    for heads, rows in parse_tables(html):
        col = {h: i for i, h in enumerate(heads)}
        if "연도" not in col:
            continue
        for c in rows:
            yr = c[col["연도"]] if col["연도"] < len(c) else ""

            def v(name, default=""):
                i = col.get(name)
                return c[i] if i is not None and i < len(c) else default

            team = TEAM_ZH.get(v("팀명"), v("팀명"))
            if is_pitcher:
                s = {
                    "g": to_int(v("G")), "gs": 0,
                    "w": to_int(v("W")), "l": to_int(v("L")),
                    "sv": to_int(v("SV")), "hld": to_int(v("HLD")),
                    "ip": ip_to_our(v("IP")), "h": to_int(v("H")),
                    "hr": to_int(v("HR")), "tbf": to_int(v("TBF")),
                    "so": to_int(v("SO")), "bb": to_int(v("BB")),
                    "hbp": to_int(v("HBP")), "er": to_int(v("ER")),
                    "era": v("ERA"), "whip": "", "team": team,
                }
            else:
                s = {
                    "g": to_int(v("G")), "pa": to_int(v("PA")), "ab": to_int(v("AB")),
                    "h": to_int(v("H")), "hr": to_int(v("HR")), "rbi": to_int(v("RBI")),
                    "r": to_int(v("R")), "sb": to_int(v("SB")), "bb": to_int(v("BB")),
                    "hbp": to_int(v("HBP")), "so": to_int(v("SO")),
                    "avg": v("AVG"), "obp": v("OBP"), "slg": v("SLG"),
                    "ops": v("OPS"), "team": team,
                }
            if re.match(r"^\d{4}$", yr):
                years[yr] = merge_season(years[yr], s, is_pitcher) if yr in years else s
            elif yr == "통산":          # 生涯合計列
                s.pop("team", None)
                career = s
    for s in list(years.values()) + ([career] if career else []):
        finalize(s, is_pitcher)
    return years, career


def merge_season(a, b, is_pitcher):
    """同年兩列(換隊)合併。比率欄位先清掉,finalize 再重算。"""
    out = dict(a)
    keys = (("g", "w", "l", "sv", "hld", "h", "hr", "tbf", "so", "bb", "hbp", "er")
            if is_pitcher else
            ("g", "pa", "ab", "h", "hr", "rbi", "r", "sb", "bb", "hbp", "so"))
    for k in keys:
        out[k] = to_int(a.get(k)) + to_int(b.get(k))
    if is_pitcher:
        out["ip"] = fmt_ip(outs_of(a.get("ip") or 0) + outs_of(b.get("ip") or 0))
        out["era"] = ""
    else:
        out["avg"] = out["obp"] = out["slg"] = out["ops"] = ""
    out["team"] = f"{a.get('team','')}／{b.get('team','')}".strip("／")
    return out


def finalize(s, is_pitcher):
    """補官網沒直接給的欄位(WHIP/OPS),以及合併後要重算的比率。"""
    if is_pitcher:
        innings = outs_of(s.get("ip") or 0) / 3
        if not s.get("era"):
            s["era"] = rate(s.get("er", 0) * 9, innings)
        s["whip"] = rate(s.get("h", 0) + s.get("bb", 0), innings)
    else:
        if not s.get("avg"):
            s["avg"] = rate(s.get("h", 0), s.get("ab", 0), 3)
        if not s.get("ops") and s.get("obp") and s.get("slg"):
            try:
                s["ops"] = f"{float(s['obp']) + float(s['slg']):.3f}".lstrip("0")
            except ValueError:
                s["ops"] = ""
    # 站內數值一律不帶前導 0(.234 而非 0.234),官網是 0.234
    for k in ("era", "whip", "avg", "obp", "slg", "ops"):
        if isinstance(s.get(k), str) and s[k].startswith("0."):
            s[k] = s[k][1:]


def load_previous():
    """上一版 kbo.json:{球員名: entry}。抓取失敗時拿來墊底,避免把好資料洗成空的。"""
    try:
        return {q["name"]: q for q in json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))["players"]}
    except Exception:
        return {}


def main():
    roster = json.loads(ROSTER_PATH.read_text(encoding="utf-8"))["players"]
    previous = load_previous()
    players, failed = [], []
    for p in roster:
        pid = p.get("kbo_id") or p.get("lottonavi_id")
        is_pitcher = p["role"] == "pitcher"
        kind = "Pitcher" if is_pitcher else "Hitter"
        detail = f"{BASE}/Record/Player/{kind}Detail/{{}}.aspx?playerId={pid}"

        daily = get(detail.format("Daily"))
        time.sleep(0.3)
        total = get(detail.format("Total"))
        time.sleep(0.3)

        game_logs = parse_daily(daily, is_pitcher) if daily else []
        years, career = parse_total(total, is_pitcher) if total else ({}, None)
        cur = years.pop(str(SEASON), None)
        season_stats = {"一軍": cur} if cur else {}
        if cur and is_pitcher:
            # 官網逐年表沒有先發場次,由逐場的「선발」數回填
            cur["gs"] = sum(1 for g in game_logs if g.get("started"))

        # 抓不到(官網改版/暫時故障)就沿用上一版,不寫入空的 season_stats。
        if not season_stats:
            prev = previous.get(p["name_zh"])
            failed.append(p["name_zh"])
            if prev and prev.get("season_stats"):
                prev = dict(prev)
                prev["status_note"] = prev.get("status_note") or "資料源暫時無法存取,沿用上次成功抓取的數據"
                players.append(prev)
                print(f"  {p['name_zh']}: 抓取失敗 → 沿用上一版({len(prev.get('game_logs') or [])} 場)")
                continue

        entry = {
            "id": f"kbo{pid}",
            "name": p["name_zh"],
            "name_en": p["name_zh"],
            "league": "kbo",
            "level": "一軍",
            "team": p["org_zh"],
            "org": p["org_zh"],
            "position": "P" if is_pitcher else "",
            "role": p["role"],
            "status": "",
            "status_note": "",
            "bio": {"pos_zh": "投手" if is_pitcher else "野手"},
            "season_stats": season_stats,
            "game_logs": game_logs[:60],
        }
        if years:
            entry["prev_season"] = {y: {"一軍": s} for y, s in
                                    sorted(years.items(), reverse=True)}
            # 只有一個球季時,生涯合計會跟當季表一模一樣 → 不掛,免得畫面重複
            if career:
                entry["career"] = {"一軍": career}
        players.append(entry)
        print(f"  {p['name_zh']}: 逐場 {len(game_logs)}、季賽 {season_stats.get('一軍', {})}"
              f"{'、回追 ' + '/'.join(sorted(years, reverse=True)) if years else ''}")

    result = {
        "updated_at": datetime.now(TW).isoformat(timespec="seconds"),
        "season": SEASON,
        "players": players,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                           encoding="utf-8")
    print(f"完成:{OUTPUT_PATH} ({len(players)} 人)")
    if failed:
        print(f"::warning::KBO 抓取失敗:{'、'.join(failed)}(官網版面可能改了,檢查 Daily/Total.aspx)")


if __name__ == "__main__":
    main()
