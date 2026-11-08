#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓中華隊國際賽的逐場逐人成績 → public/data/international.json
============================================================================
**資料範圍只有經典賽系列,這是來源限制不是偷懶。** 2026-11-08 查證過:
  MLB Stats API 的 sportId=51(International Baseball)有中華隊 team 791,
  涵蓋 2017 預賽、2023 預賽、2025 資格賽、2026 預賽,共 16 場,含完整 box score。
  不在裡面的:
    · 2024 世界十二強(中華隊冠軍)—— WBSC 辦的,MLB API 沒有;WBSC 全站在
      CloudFront 後面,連 robots.txt 都回 403,**不繞過機器人防護**,所以無法自動化。
    · 亞運、亞冠賽(APBC)—— 同上,無可用來源。
    · 奧運 —— sportId=52 查到 0 隊。
    · U18 —— sportId=509 有中華隊 team 2579,但各年賽程都是空的。
    · team 2474 是另一個 Chinese Taipei id,所有年份都 0 場(死 id)。
  所以頁面上必須寫明「本頁僅收錄經典賽」,不能叫「國際賽全紀錄」—— 球迷看到
  沒有十二強會以為資料壞了,講清楚範圍比假裝完整重要。

數字全部來自官方 box score,沒有任何推算。
執行:python3 scripts/fetch_intl.py
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = {"User-Agent": "Mozilla/5.0 (compatible; tw-baseball-tracker intl)"}
TEAM = 791          # Chinese Taipei (sportId=51)
SPORT = 51
SEASONS = [2017, 2023, 2025, 2026]
OUT = os.path.join(ROOT, "public", "data", "international.json")

# 對手國名:只放有通用中文譯名的(team_zh.json 的同一條規矩),查不到就留原文
NATION_ZH = {
    "Japan": "日本", "Korea": "韓國", "Republic of Korea": "韓國",
    "Cuba": "古巴", "Italy": "義大利", "Panama": "巴拿馬",
    "Kingdom of the Netherlands": "荷蘭", "Netherlands": "荷蘭",
    "Australia": "澳洲", "Czechia": "捷克", "Czech Republic": "捷克",
    "China": "中國", "Israel": "以色列", "Brazil": "巴西",
    "Dominican Republic": "多明尼加", "Venezuela": "委內瑞拉",
    "Puerto Rico": "波多黎各", "Mexico": "墨西哥", "Canada": "加拿大",
    "United States": "美國", "Great Britain": "英國", "Nicaragua": "尼加拉瓜",
    "Colombia": "哥倫比亞", "Spain": "西班牙", "Germany": "德國",
    "Chinese Taipei": "中華隊", "South Africa": "南非",
}
# 賽事名稱
EVENT_ZH = {
    "World Baseball Classic Pool Play": "世界棒球經典賽",
    "World Baseball Classic Qualifiers": "世界棒球經典賽資格賽",
    "World Baseball Classic Championship": "世界棒球經典賽",
    "Exhibition Game": "熱身賽",
}


def get(url, tries=5):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return json.loads(r.read())
        except Exception as e:
            if i == tries - 1:
                raise e
            time.sleep(3)
    return None


def ip_to_outs(v):
    """官方的 inningsPitched 是 "4.2" = 4 又 2/3 局,不是小數"""
    if v in (None, ""):
        return 0
    w, _, f = str(v).partition(".")
    return int(w or 0) * 3 + int(f or 0)


def outs_to_ip(o):
    return f"{o // 3}.{o % 3}"


def main():
    # **一定要用 gamePk 去重。** schedule 端點會把同一場比賽掛在兩個日期下:
    # 2017 的 pk=486905(中華 7-15 以色列)同時出現在 03-06 與 03-07,兩筆的
    # 狀態、gameNumber、doubleHeader 全部一樣,是不折不扣的重複記錄
    # (推測是賽事在首爾、跨了美東日期)。不去重的話那一場的每個人都被算兩次。
    # 日期採 game 自己的 officialDate,那是官方認定的比賽日。
    seen = {}
    for yr in SEASONS:
        d = get(f"https://statsapi.mlb.com/api/v1/schedule?sportId={SPORT}&teamId={TEAM}&season={yr}")
        for dt in d.get("dates", []):
            for g in dt["games"]:
                desc = g.get("seriesDescription") or ""
                # 熱身賽不算正式國際賽成績(bio_extra.json 立的同一條規矩)
                if "Exhibition" in desc:
                    continue
                pk = g["gamePk"]
                if pk in seen:
                    continue
                seen[pk] = {
                    "season": yr, "date": g.get("officialDate") or dt["date"], "pk": pk,
                    "event": EVENT_ZH.get(desc, desc), "event_en": desc,
                }
    games = sorted(seen.values(), key=lambda g: g["date"])
    print(f"賽事場次:{len(games)}（去重後;{SEASONS}）")

    players = {}
    out_games = []
    for g in games:
        b = get(f"https://statsapi.mlb.com/api/v1/game/{g['pk']}/boxscore")
        ln = get(f"https://statsapi.mlb.com/api/v1/game/{g['pk']}/linescore")
        side_tw = None
        for side in ("away", "home"):
            if "Taipei" in b["teams"][side]["team"]["name"]:
                side_tw = side
        if not side_tw:
            print(f"  ⚠ {g['date']} 找不到中華隊,跳過", file=sys.stderr)
            continue
        opp_side = "home" if side_tw == "away" else "away"
        opp_en = b["teams"][opp_side]["team"]["name"]
        sc_tw = (ln.get("teams", {}).get(side_tw) or {}).get("runs")
        sc_op = (ln.get("teams", {}).get(opp_side) or {}).get("runs")
        out_games.append({
            "date": g["date"], "season": g["season"], "event": g["event"],
            "opp": NATION_ZH.get(opp_en, opp_en), "opp_en": opp_en,
            "home": side_tw == "home",
            "score": f"{sc_tw}-{sc_op}" if sc_tw is not None else None,
            "win": (sc_tw > sc_op) if (sc_tw is not None and sc_op is not None) else None,
        })

        for p in b["teams"][side_tw]["players"].values():
            st = p.get("stats") or {}
            bat, pit = st.get("batting") or {}, st.get("pitching") or {}
            played = bool(bat.get("gamesPlayed") or pit.get("gamesPlayed"))
            if not played:
                continue
            pid = str(p["person"]["id"])
            rec = players.setdefault(pid, {
                "id": pid, "name_en": p["person"]["fullName"], "games": [],
            })
            line = {"date": g["date"], "season": g["season"], "event": g["event"],
                    "opp": NATION_ZH.get(opp_en, opp_en)}
            if bat.get("atBats") is not None and (bat.get("atBats") or bat.get("plateAppearances")):
                line["bat"] = {k: bat.get(v, 0) or 0 for k, v in
                               [("ab", "atBats"), ("h", "hits"), ("hr", "homeRuns"),
                                ("rbi", "runsBattedIn" if "runsBattedIn" in bat else "rbi"),
                                ("bb", "baseOnBalls"), ("so", "strikeOuts"), ("r", "runs")]}
            if pit.get("inningsPitched"):
                line["pit"] = {
                    "outs": ip_to_outs(pit.get("inningsPitched")),
                    "so": pit.get("strikeOuts", 0) or 0, "bb": pit.get("baseOnBalls", 0) or 0,
                    "er": pit.get("earnedRuns", 0) or 0, "h": pit.get("hits", 0) or 0,
                    "w": pit.get("wins", 0) or 0, "l": pit.get("losses", 0) or 0,
                    "sv": pit.get("saves", 0) or 0,
                }
            rec["games"].append(line)

    # 彙總(純加總,不推算)
    for rec in players.values():
        gs = rec["games"]
        bat = [x["bat"] for x in gs if "bat" in x]
        pit = [x["pit"] for x in gs if "pit" in x]
        rec["events"] = sorted({f"{x['season']} {x['event']}" for x in gs})
        rec["g"] = len(gs)
        if bat:
            t = {k: sum(b[k] for b in bat) for k in bat[0]}
            t["avg"] = f"{t['h'] / t['ab']:.3f}".lstrip("0") if t["ab"] else None
            rec["bat_total"] = t
        if pit:
            o = sum(p["outs"] for p in pit)
            t = {k: sum(p[k] for p in pit) for k in ("so", "bb", "er", "h", "w", "l", "sv")}
            t["outs"] = o
            t["ip"] = outs_to_ip(o)
            # 沒拿到任何出局數就被換下(鄧愷威 2023 對巴拿馬)→ 防禦率無法定義,
            # 留 None 讓頁面寫「—」,不要寫 0.00 或 無限,那兩種都會誤導。
            t["era"] = f"{t['er'] * 27 / o:.2f}" if o else None
            rec["pit_total"] = t

    data = {
        "updated": time.strftime("%Y-%m-%d"),
        "_範圍": ("僅收錄世界棒球經典賽系列(2017/2023 預賽、2025 資格賽、2026 預賽)。"
                 "2024 世界十二強、亞運、亞冠賽、奧運都沒有可用的官方 API —— WBSC 全站在 "
                 "CloudFront 後面連 robots.txt 都 403,不繞過機器人防護;奧運 sportId=52 查到 0 隊;"
                 "U18 sportId=509 的中華隊各年賽程皆空。頁面必須寫明範圍,不能稱作國際賽全紀錄。"),
        "_來源": "MLB Stats API sportId=51 team 791 的官方 box score,數字未經任何推算",
        "games": out_games,
        "players": sorted(players.values(), key=lambda r: (-r["g"], r["name_en"])),
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"寫出 {OUT}:{len(out_games)} 場、{len(players)} 位球員")
    return 0


if __name__ == "__main__":
    sys.exit(main())
