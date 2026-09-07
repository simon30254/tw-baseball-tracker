"""
每位球員的社群分享圖(OG image)
================================
先前全站 74 個球員頁共用同一張 public/og.png,分享到社群長得一模一樣。
這支為每位球員產一張帶姓名與所屬球隊的圖。

**刻意不放當季數據**:數據每天變,圖就得每天重產、每天進 git,74 個 PNG 的
二進位差異會把 repo 撐爆。所以圖上只放「不常變」的資訊(姓名、羅馬名、
聯盟層級球隊、歷代球員的年份區間),並用簽章比對只重產真的變了的那幾張。

字型用 macOS 的 PingFang(CI 上沒有),所以這支是本機手動執行、產物進 git,
不掛在每日流程上。新增球員或球員換隊後跑一次即可。

執行: python3 scripts/make_og.py [--force]
"""

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
PLAYERS = ROOT / "public" / "data" / "players.json"
ALUMNI = ROOT / "public" / "data" / "alumni.json"
OUT_DIR = ROOT / "public" / "og"
SIG_PATH = ROOT / "scripts" / "og_signatures.json"

FONT = "/System/Library/Fonts/PingFang.ttc"
W, H = 1200, 630
GREEN = (15, 81, 56)
GREEN_DARK = (10, 58, 40)
CREAM = (246, 248, 246)
MUTED = (150, 190, 170)
ACCENT = (110, 200, 160)

LEAGUE = {"mlb": "旅美", "milb": "旅美", "npb": "旅日", "kbo": "旅韓"}
LEVEL = {"MLB": "大聯盟", "AAA": "3A", "AA": "2A", "High-A": "高階1A", "A": "1A",
         "Rookie": "新人聯盟", "一軍": "一軍", "二軍": "二軍", "韓職一軍": "韓職一軍"}


def font(size, weight=0):
    f = ImageFont.truetype(FONT, size, index=weight)
    return f


def draw_one(path, name, roman, meta, tag):
    img = Image.new("RGB", (W, H), GREEN)
    d = ImageDraw.Draw(img)
    # 斜切色塊,讓圖不是一片純色(縮圖時仍可辨識是同一個站)
    d.polygon([(0, H), (W, H), (W, H - 180), (0, H - 90)], fill=GREEN_DARK)
    d.rectangle([(0, 0), (14, H)], fill=ACCENT)

    d.text((70, 74), tag, font=font(30, 1), fill=ACCENT)
    # 中文名字數不同,字級跟著縮,避免長名字撐出畫面
    size = 128 if len(name) <= 3 else (108 if len(name) <= 4 else 92)
    d.text((70, 150), name, font=font(size, 2), fill=CREAM)
    y = 150 + size + 24
    if roman and roman != name:
        d.text((74, y), roman, font=font(44, 0), fill=MUTED)
        y += 66
    d.text((74, y), meta, font=font(38, 1), fill=CREAM)

    d.text((70, H - 78), "players.clutchgtime.com", font=font(30, 0), fill=MUTED)
    d.text((W - 330, H - 78), "旅外球員情報站", font=font(32, 1), fill=MUTED)
    # 扁平配色用調色盤模式存,檔案小很多(全彩約 130KB → 調色盤約 20KB)
    img.convert("P", palette=Image.ADAPTIVE, colors=64).save(path, optimize=True)


def entries():
    out = []
    players = json.loads(PLAYERS.read_text(encoding="utf-8"))["players"]
    for p in players:
        meta = "・".join(x for x in [LEAGUE.get(p["league"], ""),
                                     LEVEL.get(p.get("level"), p.get("level", "")),
                                     p.get("org", "")] if x)
        out.append((p["slug"], p["name"], p.get("name_en", ""), meta, "現役球員"))
    try:
        alu = json.loads(ALUMNI.read_text(encoding="utf-8"))["players"]
    except Exception:
        alu = []
    for p in alu:
        where = "日職" if p["league"] == "npb" else "大聯盟"
        span = f"{p.get('first_year','')}–{p.get('last_year','')}"
        meta = f"{where} {span}"
        out.append((p["slug"], p["name"], p.get("name_en", ""), meta, "歷代旅外球員"))
    return out


def main():
    force = "--force" in sys.argv
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        sigs = json.loads(SIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        sigs = {}
    made = kept = 0
    seen = set()
    for slug, name, roman, meta, tag in entries():
        seen.add(slug)
        sig = f"{name}|{roman}|{meta}|{tag}"
        path = OUT_DIR / f"{slug}.png"
        if not force and sigs.get(slug) == sig and path.exists():
            kept += 1
            continue
        draw_one(path, name, roman, meta, tag)
        sigs[slug] = sig
        made += 1
    # 已離開名單的球員圖留著也沒人連,清掉免得 repo 越積越多
    for old in list(sigs):
        if old not in seen:
            (OUT_DIR / f"{old}.png").unlink(missing_ok=True)
            sigs.pop(old)
    SIG_PATH.write_text(json.dumps(sigs, ensure_ascii=False, indent=0, sort_keys=True) + "\n",
                        encoding="utf-8")
    total = sum(f.stat().st_size for f in OUT_DIR.glob("*.png"))
    print(f"OG 圖:新產 {made} 張、沿用 {kept} 張,共 {len(seen)} 張 / {total/1024:.0f} KB")


if __name__ == "__main__":
    main()
