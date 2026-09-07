"""
歷代旅韓台灣球員(已離開 KBO 者)生涯數據
=========================================
2026 年才有亞援制度,但在那之前台灣球員可用一般洋將身分登錄 ——
王維中 2018 年就在 NC 恐龍投了一整季(25 場 7勝10敗 141⅔ 局 防禦率 4.26)。

名單放 scripts/kbo_alumni_roster.json(人工策展,理由同旅日:KBO 官網沒有
國籍欄可掃,外籍球員以韓文音譯名登錄)。數據沿用 fetch_kbo 的官網解析。

輸出:併入 public/data/alumni.json。已在該檔的人(王維中有大聯盟生涯)會把
韓職的年份與層級併進同一筆。

執行: python3 scripts/fetch_kbo_alumni.py
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_kbo as K                                    # noqa: E402
from build_players import localize_teams, fill_whip      # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ROSTER_PATH = ROOT / "scripts" / "kbo_alumni_roster.json"
ALUMNI_PATH = ROOT / "public" / "data" / "alumni.json"
PLAYERS_PATH = ROOT / "public" / "data" / "players.json"

# 同一頁上還有大聯盟與小聯盟各層級,寫「一軍」會被讀成日職
LEVEL = "韓職一軍"


def main():
    roster = json.loads(ROSTER_PATH.read_text(encoding="utf-8"))["players"]
    try:
        blob = json.loads(ALUMNI_PATH.read_text(encoding="utf-8"))
    except Exception:
        blob = {"players": []}
    by_name = {p["name"]: p for p in blob["players"]}
    try:
        active = {p["name"] for p in json.loads(PLAYERS_PATH.read_text(encoding="utf-8"))["players"]}
    except Exception:
        active = set()

    merged = skipped = 0
    for r in roster:
        if r["zh"] in active:
            print(f"  [略過] {r['zh']}:現役球員,資料由 fetch_kbo 每天更新")
            skipped += 1
            continue
        is_pitcher = r["role"] == "pitcher"
        kind = "Pitcher" if is_pitcher else "Hitter"
        html = K.get(f"{K.BASE}/Record/Player/{kind}Detail/Total.aspx?playerId={r['kbo_id']}")
        time.sleep(0.3)
        if not html:
            print(f"  [略過] {r['zh']}:頁面抓不到")
            continue
        years, career = K.parse_total(html, is_pitcher)
        if not years:
            print(f"  [略過] {r['zh']}:無任何出賽紀錄")
            continue
        cur = by_name.get(r["zh"])
        if not cur:
            # 目前名單上的人都另有大聯盟生涯;若日後有純旅韓前輩再補建立新條目的分支
            print(f"  [略過] {r['zh']}:alumni.json 沒有這個人,尚未支援純旅韓前輩")
            continue
        for y, s in years.items():
            cur.setdefault("prev_season", {}).setdefault(y, {})[LEVEL] = s
        if career:
            cur.setdefault("career", {})[LEVEL] = career
        cur["kbo_seasons"] = sorted(int(y) for y in years)
        cur["prev_season"] = {y: cur["prev_season"][y] for y in sorted(cur["prev_season"], reverse=True)}
        merged += 1
        yrs = cur["kbo_seasons"]
        print(f"  併入 {r['zh']}:KBO {yrs[0]}–{yrs[-1]}({len(yrs)} 季)+ 既有生涯")

    if merged:
        localize_teams(blob["players"])
        fill_whip(blob["players"])
        blob["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S+08:00")
        ALUMNI_PATH.write_text(json.dumps(blob, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"完成:併入 {merged} 人、略過 {skipped} 人")


if __name__ == "__main__":
    main()
