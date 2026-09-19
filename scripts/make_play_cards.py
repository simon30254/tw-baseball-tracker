"""
精彩打席的社群分享卡 → dist/og/play/{slug}-{date}.png
====================================================
貼連結到社群時展開的那張圖。**社群爬蟲不跑 JavaScript**,所以 og:image 必須是
真實存在的圖片網址 —— 這支在 build 之後產圖進 dist/,讓表現頁的 og:image 指過去。

**產物不進 git**:圖卡每天都有新的,幾十張 PNG 的二進位差異會把 repo 撐爆
(scripts/make_og.py 的說明裡記過同樣的教訓)。這支在 CI 上每次 build 重產,
只存在於部署產物裡。

字型:本機用 PingFang,CI(ubuntu)用 Noto Sans CJK —— workflow 會先 apt 裝。
兩邊都找不到就跳過產圖(表現頁會自動退回用球員的 OG 圖,不會壞)。

執行:python3 scripts/make_play_cards.py   (需先跑過 npm run build:site)
"""

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "public" / "data"
OUT_DIR = ROOT / "dist" / "og" / "play"

W, H = 1200, 630
GREEN = (15, 81, 56)
GREEN_DARK = (10, 58, 40)
CREAM = (246, 248, 246)
MUTED = (143, 196, 172)
ACCENT = (110, 200, 160)

LEVEL = {"MLB": "大聯盟", "AAA": "3A", "AA": "2A", "High-A": "高階1A", "A": "1A",
         "Rookie": "新人聯盟"}

# 本機 / CI 各自的中文字型。index 是 ttc 裡的字重
FONT_CANDIDATES = [
    ("/System/Library/Fonts/PingFang.ttc", (0, 1, 2)),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", (0, 0, 1)),
    ("/usr/share/fonts/opentype/noto/NotoSansCJKtc-Regular.ttc", (0, 0, 1)),
    ("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc", (0, 0, 1)),
]
FONT_PATH, WEIGHTS = None, (0, 0, 0)
for path, w in FONT_CANDIDATES:
    if Path(path).exists():
        FONT_PATH, WEIGHTS = path, w
        break


def font(size, weight=0):
    return ImageFont.truetype(FONT_PATH, size, index=WEIGHTS[min(weight, 2)])


def wrap(d, text, fnt, max_w):
    """中文沒有空格,逐字量寬換行。"""
    lines, line = [], ""
    for ch in text:
        if d.textlength(line + ch, font=fnt) > max_w and line:
            lines.append(line)
            line = ch
        else:
            line += ch
    if line:
        lines.append(line)
    return lines


def draw_card(path, pl, season_line, roman):
    img = Image.new("RGB", (W, H), GREEN)
    d = ImageDraw.Draw(img)
    d.polygon([(0, H), (W, H), (W, H - 150), (0, H - 70)], fill=GREEN_DARK)
    d.rectangle([(0, 0), (12, H)], fill=ACCENT)

    PAD = 64
    y = 52

    # 事件標籤 + 局數
    tag = pl.get("event_zh") or "精彩表現"
    f_tag = font(26, 2)
    tw = d.textlength(tag, font=f_tag)
    d.rounded_rectangle([(PAD, y), (PAD + tw + 36, y + 44)], radius=22, fill=ACCENT)
    d.text((PAD + 18, y + 8), tag, font=f_tag, fill=GREEN_DARK)
    if pl.get("inning"):
        half = "上" if pl.get("half") == "top" else "下"
        d.text((PAD + tw + 56, y + 8), f"{half} {pl['inning']} 局", font=font(26, 1), fill=MUTED)
    y += 72

    # 球員名 + 羅馬名
    name = pl.get("name", "")
    size = 76 if len(name) <= 4 else 62
    d.text((PAD, y), name, font=font(size, 2), fill=CREAM)
    nw = d.textlength(name, font=font(size, 2))
    if roman and roman != name:
        d.text((PAD + nw + 18, y + size - 34), roman, font=font(28, 0), fill=MUTED)
    y += size + 22

    # 事實敘述(開頭的局數拿掉,上面標籤列已顯示)
    text = pl.get("text", "")
    for pre in ("上", "下"):
        if text.startswith(pre) and "局，" in text[:8]:
            text = text.split("局，", 1)[1]
            break
    f_body = font(34, 0)
    for line in wrap(d, text, f_body, W - PAD * 2 - 20)[:2]:
        d.text((PAD, y), line, font=f_body, fill=CREAM)
        y += 46
    y += 8

    # 對手 / 層級 / 比分
    meta = "　·　".join(x for x in [
        pl.get("date", ""),
        LEVEL.get(pl.get("level"), pl.get("level", "")),
        f"對 {pl['opponent']}" if pl.get("opponent") else "",
        f"比分 {pl['away_score']}:{pl['home_score']}"
        if pl.get("away_score") is not None and pl.get("home_score") is not None else "",
    ] if x)
    d.text((PAD, y), meta, font=font(24, 0), fill=MUTED)
    y += 52

    # Statcast 三欄
    cells = []
    if pl.get("ev") is not None:
        cells.append(("擊球初速", f"{float(pl['ev']):.1f}", "mph"))
    if pl.get("dist") is not None:
        cells.append(("飛行距離", str(round(float(pl["dist"]))), "ft"))
    if pl.get("angle") is not None:
        cells.append(("擊球仰角", str(round(float(pl["angle"]))), "°"))
    if cells:
        cw = (W - PAD * 2) / len(cells)
        for i, (label, val, unit) in enumerate(cells):
            cx = PAD + cw * i
            d.text((cx, y), label, font=font(22, 1), fill=MUTED)
            f_val = font(52, 2)
            vw = d.textlength(val, font=f_val)
            d.text((cx, y + 30), val, font=f_val, fill=CREAM)
            d.text((cx + vw + 8, y + 58), unit, font=font(22, 1), fill=MUTED)

    # 本季累積 + 頁尾
    if season_line:
        d.text((PAD, H - 128), f"本季　{season_line}", font=font(24, 1), fill=MUTED)
    # 網址的 x 要量出來,不能寫死偏移 —— 站名在不同字型下寬度不同,寫死會疊上去
    f_brand = font(30, 2)
    d.text((PAD, H - 72), "旅外球員情報站", font=f_brand, fill=CREAM)
    bw = d.textlength("旅外球員情報站", font=f_brand)
    d.text((PAD + bw + 24, H - 66), "players.clutchgtime.com", font=font(24, 0), fill=MUTED)
    rw = d.textlength("數據來源：MLB Stats API", font=font(20, 0))
    d.text((W - PAD - rw, H - 62), "數據來源：MLB Stats API", font=font(20, 0), fill=MUTED)

    img.convert("P", palette=Image.ADAPTIVE, colors=96).save(path, optimize=True)


def main():
    if not FONT_PATH:
        print("找不到中文字型,跳過產圖(表現頁會退回用球員的 OG 圖)")
        return
    try:
        plays = json.loads((DATA / "plays.json").read_text(encoding="utf-8"))["plays"]
        players = {str(p["id"]): p for p in
                   json.loads((DATA / "players.json").read_text(encoding="utf-8"))["players"]}
    except Exception as e:
        print(f"讀不到資料:{e}")
        sys.exit(1)
    if not (ROOT / "dist").exists():
        print("dist/ 不存在,請先跑 npm run build:site")
        sys.exit(1)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 同一場同一位球員可能有多個打席 —— 分享連結是「一場一頁」,取最具代表性的
    # (優先全壘打,其次擊球初速最快)那一個。
    best = {}
    for pl in plays:
        if not pl.get("slug") or not pl.get("date"):
            continue
        k = f"{pl['slug']}-{pl['date']}"
        cur = best.get(k)
        rank = (1 if pl.get("event") in ("Home Run", "Grand Slam") else 0, float(pl.get("ev") or 0))
        if not cur or rank > cur[0]:
            best[k] = (rank, pl)

    n = 0
    for k, (_, pl) in best.items():
        p = players.get(str(pl["id"]))
        season = ""
        if p:
            ss = p.get("season_stats") or {}
            main_lv = max(ss.items(), key=lambda kv: kv[1].get("g", 0), default=(None, None))
            if main_lv[1]:
                s = main_lv[1]
                season = (f"{main_lv[0]} {s.get('g')} 場・打擊率 {s.get('avg')}・{s.get('hr')} 轟"
                          if p.get("role") != "pitcher"
                          else f"{main_lv[0]} {s.get('g')} 場・{s.get('w')}勝{s.get('l')}敗・防禦率 {s.get('era')}")
        roman = ""
        if p:
            en = (p.get("name_en") or "")
            roman = p.get("roman") or (en if any(c.isascii() and c.isalpha() for c in en) else "")
        draw_card(OUT_DIR / f"{k}.png", pl, season, roman)
        n += 1
    print(f"分享卡:{n} 張 → dist/og/play/(字型 {Path(FONT_PATH).name})")


if __name__ == "__main__":
    main()
