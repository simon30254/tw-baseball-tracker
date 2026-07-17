"""
旅韓(KBO)台灣球員資料抓取腳本
==============================
資料來源:運彩報馬仔 lottonavi(中文逐場,無官方 API,爬 HTML)
2026 起 KBO 亞援制度首批台將:王彥程(韓華鷹)。

流程:
1. 讀 scripts/kbo_roster.json 手動名單
2. 逐場 game log + 季賽累積:球員 game-logs 頁
3. 輸出 public/data/kbo.json(與 MLB 相同 schema,league="kbo",level="一軍")

執行: python3 scripts/fetch_kbo.py
"""

import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")
BASE = "https://www.lottonavi.com"
KST = timezone(timedelta(hours=9))
TW = timezone(timedelta(hours=8))
SEASON = datetime.now(KST).year

ROOT = Path(__file__).resolve().parent.parent
ROSTER_PATH = ROOT / "scripts" / "kbo_roster.json"
OUTPUT_PATH = ROOT / "public" / "data" / "kbo.json"


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
        return int(s)
    except (ValueError, TypeError):
        return 0


def parse_pitching_logs(html):
    """逐場投球:每列 17 欄
    [日期, 對戰, 比分, 隊結果, 個人決定, 局數, 球數, 安打, 失分, 責失, 全壘, 保送, 三振, 累勝, 累敗, 累救, 累防禦率]"""
    logs = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = [clean(c) for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, re.S)]
        if len(cells) < 13 or not re.match(r"\d{2}/\d{2}$", cells[0]):
            continue
        mm, dd = cells[0].split("/")
        opp = cells[1]
        is_home = not opp.startswith("@")
        decision = cells[4]
        logs.append({
            "type": "pitching",
            "date": f"{SEASON}-{mm}-{dd}",
            "level": "一軍",
            "opponent": opp.lstrip("@"),
            "is_home": is_home,
            "ip": cells[5],
            "h": to_int(cells[7]),
            "r": to_int(cells[8]),
            "er": to_int(cells[9]),
            "hr": to_int(cells[10]),
            "bb": to_int(cells[11]),
            "so": to_int(cells[12]),
            "win": decision == "勝",
            "loss": decision == "負",
            "save": decision in ("救援", "S"),
            "started": decision not in ("救援", "S", "H"),
        })
    logs.sort(key=lambda g: g["date"], reverse=True)
    return logs


def parse_season_summary(html):
    """頁首摘要:『勝敗 防禦率 WHIP』後接三個值(如 7-3 / 3.59 / 1.56)。"""
    ths = [clean(x) for x in re.findall(r"<th[^>]*>(.*?)</th>", html, re.S)]
    out = {}
    if "WHIP" in ths:
        i = ths.index("WHIP")
        vals = ths[i + 1:i + 4]
        if len(vals) == 3:
            out["record"], out["era"], out["whip"] = vals
    return out


def ip_sum(logs):
    thirds = 0
    for g in logs:
        parts = str(g["ip"]).split(".")
        thirds += int(parts[0]) * 3 + (int(parts[1]) if len(parts) > 1 else 0)
    whole, frac = divmod(thirds, 3)
    return f"{whole}.{frac}" if frac else str(whole)


def main():
    roster = json.loads(ROSTER_PATH.read_text(encoding="utf-8"))["players"]
    players = []
    for p in roster:
        name_path = urllib.parse.quote(p["korean"])
        url = f"{BASE}/player/kbo/{p['lottonavi_id']}/{name_path}/game-logs/"
        html = get(url)
        time.sleep(0.3)
        game_logs, season_stats = [], {}
        if html:
            if p["role"] == "pitcher":
                game_logs = parse_pitching_logs(html)
                summ = parse_season_summary(html)
                w, l = (summ.get("record", "0-0").split("-") + ["0"])[:2]

                def outs_of(ipstr):
                    p = str(ipstr).split(".")
                    return int(p[0]) * 3 + (int(p[1]) if len(p) > 1 else 0)

                # 打者數(TBF)lottonavi 未直接提供,以 出局數 + 被安 + 保送 近似
                tbf = sum(outs_of(g["ip"]) + g["h"] + g["bb"] for g in game_logs)
                season_stats = {"一軍": {
                    "g": len(game_logs), "gs": sum(1 for g in game_logs if g["started"]),
                    "w": to_int(w), "l": to_int(l), "sv": sum(1 for g in game_logs if g["save"]),
                    "ip": ip_sum(game_logs), "h": sum(g["h"] for g in game_logs),
                    "hr": sum(g["hr"] for g in game_logs), "tbf": tbf,
                    "so": sum(g["so"] for g in game_logs),
                    "bb": sum(g["bb"] for g in game_logs),
                    "era": summ.get("era", ""), "whip": summ.get("whip", ""),
                }}
        players.append({
            "id": f"kbo{p['lottonavi_id']}",
            "name": p["name_zh"],
            "name_en": p["name_zh"],
            "league": "kbo",
            "level": "一軍",
            "team": p["org_zh"],
            "org": p["org_zh"],
            "position": "P" if p["role"] == "pitcher" else "",
            "role": p["role"],
            "status": "",
            "status_note": "",
            "season_stats": season_stats,
            "game_logs": game_logs[:60],
        })
        print(f"  {p['name_zh']}: 逐場 {len(game_logs)}、季賽 {season_stats.get('一軍', {})}")

    result = {
        "updated_at": datetime.now(TW).isoformat(timespec="seconds"),
        "season": SEASON,
        "players": players,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                           encoding="utf-8")
    print(f"完成:{OUTPUT_PATH} ({len(players)} 人)")


if __name__ == "__main__":
    main()
