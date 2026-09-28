"""
球季總結頁的分享圖 → public/og/season/{slug}-{year}.png
=====================================================
總結頁原本沿用球員頁那張通用圖(「現役球員・李灝宇・旅美大聯盟老虎」),分享出去
跟他的球員頁長得一模一樣,看不出這頁在講什麼 —— 而這種頁的重點正是「那個數字」。

版面沿用分享打席卡(make_play_cards.py)的廣播數據圖表感:深底、一個巨大的主角
數字、下面一排支撐數據。**支撐數據由 players.json 算**,主角數字與說明由
season_review.json 的 cover 欄位指定(人寫,才不會湊出無意義的組合)。

字型:本機 PingFang + HelveticaNeue 窄體(CI 上沒有),所以與 make_og.py 一樣是
本機手動跑、產物進 git。球季結束後才會動,不必掛每日流程。

執行: python3 scripts/make_season_og.py
"""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "public" / "og" / "season"
W, H = 1200, 630

# 與分享打席卡同一組配色,兩種卡放在一起才像同一個站出來的
INK, INK_2 = (8, 26, 20), (12, 38, 29)
CREAM, MUTED, ACCENT = (244, 250, 246), (126, 166, 146), (74, 222, 150)
PAPER, PAPER_INK, PAPER_MUTED = (244, 247, 245), (18, 26, 22), (108, 122, 114)

FONT_PATH = "/System/Library/Fonts/PingFang.ttc"
WEIGHTS = (0, 1, 2)
NUM_PATH, NUM_BLACK, NUM_BOLD = "/System/Library/Fonts/HelveticaNeue.ttc", 9, 4


def font(size, weight=0):
    return ImageFont.truetype(FONT_PATH, size, index=WEIGHTS[min(weight, 2)])


def numfont(size, black=True):
    return ImageFont.truetype(NUM_PATH, size, index=NUM_BLACK if black else NUM_BOLD)


def support_stats(p, st):
    """支撐數據由資料算,不手寫 —— 手寫會跟球季最終數字對不起來。"""
    if p.get("role") == "pitcher":
        return [("出賽", f"{st.get('g')}"), ("局數", f"{st.get('ip')}"),
                ("防禦率", f"{st.get('era')}"), ("三振", f"{st.get('so')}")]
    adv = st.get("adv") or {}
    rows = [("出賽", f"{st.get('g')}"), ("打擊率", f"{st.get('avg')}")]
    # 有速度的球季就把盜壘放上去 —— 卡洛爾的卡上寫「20 轟 20 盜」,
    # 面板卻只有 OPS,等於自己的說明自己不佐證
    if (st.get("sb") or 0) >= 10:
        rows.append(("盜壘", f"{st.get('sb')}"))
    rows.append(("OPS", f"{st.get('ops')}"))
    if adv.get("wrcPlus") is not None:
        rows.append(("wRC+", f"{adv['wrcPlus']:g}"))
    return rows[:4]


def draw(path, name, roman, year, cover, stats):
    img = Image.new("RGB", (W, H), INK)
    d = ImageDraw.Draw(img)
    for y in range(H):                       # 直向漸層,單色平塗縮圖時會偏灰
        t = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(INK[i] + (INK_2[i] - INK[i]) * t) for i in range(3)))

    d.rectangle([(60, 56), (66, 104)], fill=ACCENT)
    d.text((82, 58), f"{year} 球季總結", font=font(26, 1), fill=ACCENT)
    d.text((82, 96), name, font=font(58, 2), fill=CREAM)
    if roman:
        d.text((84, 172), roman.upper(), font=numfont(26, black=False), fill=MUTED)

    # ── 主角數字:一頁只有一個重點
    big, unit = cover["big"], cover.get("unit", "")
    f_big = numfont(200)
    bw = d.textlength(big, font=f_big)
    by = 214
    d.text((80, by), big, font=f_big, fill=CREAM)
    if unit:
        d.text((80 + bw + 12, by + 118), unit, font=font(44, 2), fill=ACCENT)
    if cover.get("note"):
        d.text((84, by + 208), cover["note"], font=font(30, 1), fill=ACCENT)

    # ── 右側亮色面板放支撐數據
    px, py, pw = 720, 214, 420
    ph = 44 + len(stats) * 74
    d.rounded_rectangle([(px, py), (px + pw, py + ph)], radius=16, fill=PAPER)
    y = py + 28
    for label, val in stats:
        d.text((px + 28, y + 6), label, font=font(24, 1), fill=PAPER_MUTED)
        f_v = numfont(46)
        vw = d.textlength(str(val), font=f_v)
        d.text((px + pw - 28 - vw, y - 4), str(val), font=f_v, fill=PAPER_INK)
        y += 74
        if y < py + ph - 20:
            d.line([(px + 28, y - 26), (px + pw - 28, y - 26)], fill=(220, 228, 223), width=1)

    d.text((60, H - 62), "players.clutchgtime.com", font=numfont(24, black=False), fill=(96, 140, 118))
    tw = d.textlength("旅外球員情報站", font=font(24, 1))
    d.text((W - 60 - tw, H - 62), "旅外球員情報站", font=font(24, 1), fill=MUTED)
    img.convert("P", palette=Image.ADAPTIVE, colors=128).save(path, optimize=True)


def main():
    reviews = json.loads((ROOT / "scripts" / "season_review.json").read_text(encoding="utf-8"))["reviews"]
    players = {p["slug"]: p for p in
               json.loads((ROOT / "public" / "data" / "players.json").read_text(encoding="utf-8"))["players"]}
    slugs = json.loads((ROOT / "scripts" / "slugs.json").read_text(encoding="utf-8")) \
        if (ROOT / "scripts" / "slugs.json").exists() else {}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    n = 0
    for rv in reviews:
        p = players.get(rv["slug"])
        if not p or not rv.get("cover"):
            print(f"  跳過 {rv['slug']}（{'找不到球員' if not p else '沒有 cover 設定'}）")
            continue
        st = (p.get("season_stats") or {}).get(rv.get("level") or "MLB")
        if not st:
            print(f"  跳過 {rv['slug']}（沒有 {rv.get('level')} 成績）")
            continue
        en = p.get("name_en") or ""
        roman = en if any(c.isascii() and c.isalpha() for c in en) else (slugs.get(str(p["id"])) or "").replace("-", " ")
        # 主角數字不要在右側面板再出現一次(鄧愷威的 73.2 局本來兩邊都有)
        stats = [x for x in support_stats(p, st) if str(x[1]) != str(rv["cover"]["big"])]
        draw(OUT_DIR / f"{rv['slug']}-{rv['year']}.png", p["name"], roman, rv["year"],
             rv["cover"], stats)
        n += 1
    print(f"球季總結分享圖:{n} 張 → public/og/season/")


if __name__ == "__main__":
    main()
