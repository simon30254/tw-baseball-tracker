"""球探報告頁的分享圖 → public/og/scouting/{report-id}.png

球探報告原本沿用球員頁那張通用卡(「現役球員・林昱珉・旅美 3A 響尾蛇」),分享出去
跟球員頁長得一樣,看不出這頁在講什麼 —— 而這種頁被分享時的重點就是那個評價。

版面直接用 make_season_og.draw(同一組配色與結構),差別只在左上角的小標與主角數字。
內容由 scouting.json 每份報告自己的 og 欄位指定(人寫的,跟 season_review.json 的
cover 同一個道理):數字要放哪一個、底部那排放什麼,程式湊不出有意義的組合。

og 欄位:
  header 左上小標 / big 主角數字 / unit 數字後面的小字(可省)
  note   主角數字下面那行 / band 底部四格 [["標籤", "值"], ...]

字型與 make_og.py 一樣是本機的 PingFang(CI 沒有),所以本機手動跑、產物進 git。
報告是人寫的、不會每天變,不掛每日流程。

執行: python3 scripts/make_scouting_og.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from make_season_og import draw          # noqa: E402  版面與球季總結卡共用

OUT_DIR = ROOT / "public" / "og" / "scouting"


def main():
    reports = json.loads((ROOT / "scripts" / "scouting.json").read_text(encoding="utf-8"))["reports"]
    players = {p["slug"]: p for p in json.loads(
        (ROOT / "public" / "data" / "players.json").read_text(encoding="utf-8"))["players"]}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    n = 0
    for rv in reports:
        og = rv.get("og")
        if not og:
            continue                     # 沒指定就沿用球員頁那張(prerender 同一個判斷)
        p = players.get(rv["slug"])
        if not p:
            print(f"  跳過 {rv['id']}(找不到球員)")
            continue
        en = p.get("name_en") or ""
        roman = en if any(c.isascii() and c.isalpha() for c in en) else ""
        cover = {"big": og["big"], "unit": og.get("unit", ""), "note": og.get("note", "")}
        draw(OUT_DIR / f"{rv['id']}.png", p["name"], roman, og["header"], cover,
             [(a, b) for a, b in og.get("band", [])])
        n += 1
        print(f"  {rv['id']}.png ← {og['header']}")
    print(f"球探報告分享圖:{n} 張 → public/og/scouting/")


if __name__ == "__main__":
    main()
