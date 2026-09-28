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

from PIL import Image, ImageDraw, ImageFilter, ImageFont

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


def track(d, xy, text, fnt, fill, sp):
    """字距。小字級的標籤拉開字距才有現代運動圖表的味道,PIL 沒有內建。"""
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=fnt, fill=fill)
        x += d.textlength(ch, font=fnt) + sp
    return x - sp


def track_w(d, text, fnt, sp):
    return sum(d.textlength(c, font=fnt) for c in text) + sp * (len(text) - 1)


def draw(path, name, roman, year, cover, stats):
    base = Image.new("RGB", (W, H), INK)
    d = ImageDraw.Draw(base)
    # 斜向漸層:單色平塗縮圖時會糊成一片灰,對角線讓左上到右下有層次
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(INK[i] + (INK_2[i] - INK[i]) * t) for i in range(3)))

    # 主角數字後面一團低透明度的光暈 —— 純平面配色在社群動態牆上會被滑過去,
    # 一點深度就拉得開。用高斯模糊做,不是漸層貼圖。
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).ellipse([-260, 300, 520, 860], fill=30)
    base.paste(Image.new("RGB", (W, H), ACCENT), (0, 0), glow.filter(ImageFilter.GaussianBlur(150)))
    # 右下角一道極淡的圓弧,呼應站徽的棒球,不搶戲
    seam = Image.new("L", (W, H), 0)
    sd = ImageDraw.Draw(seam)
    sd.ellipse([W - 300, H - 300, W + 320, H + 320], outline=16, width=3)
    sd.ellipse([W - 250, H - 250, W + 370, H + 370], outline=11, width=3)
    base.paste(Image.new("RGB", (W, H), CREAM), (0, 0), seam.filter(ImageFilter.GaussianBlur(1)))
    d = ImageDraw.Draw(base)

    M = 72
    # ── 頁首
    d.rectangle([(M, 60), (M + 5, 92)], fill=ACCENT)
    track(d, (M + 18, 62), f"{year} 球季總結", font(25, 1), ACCENT, 2.5)
    dom = "players.clutchgtime.com"
    f_dom = numfont(21, black=False)
    d.text((W - M - d.textlength(dom, font=f_dom), 66), dom, font=f_dom, fill=(92, 132, 112))

    # ── 球員名
    d.text((M - 4, 104), name, font=font(66, 2), fill=CREAM)
    if roman:
        track(d, (M, 190), roman.upper(), numfont(23, black=False), MUTED, 3)

    # ── 主角數字。單位貼在數字的帽高而不是基線,不然會像掉下去
    big, unit = cover["big"], cover.get("unit", "")
    f_big = numfont(206)
    bw = d.textlength(big, font=f_big)
    by = 200
    d.text((M - 10, by), big, font=f_big, fill=CREAM)
    # 說明的位置照實際字框算,不要用估的 —— 「73.2」比「10」低,寫死會被數字壓到
    bbox = d.textbbox((M - 10, by), big, font=f_big)
    if unit:
        # 單位貼在數字上緣,放在基線會像掉下去
        d.text((M - 6 + bw + 14, bbox[1] + 6), unit, font=font(44, 2), fill=ACCENT)
    if cover.get("note"):
        d.text((M - 2, bbox[3] + 22), cover["note"], font=font(29, 1), fill=ACCENT)

    # ── 底部數據帶。原本是一塊白面板浮在右邊,中間留一大塊空的;
    # 改成橫跨整個寬度的資料列,是現在運動圖卡的通用作法,版面也用滿了。
    ry = 478
    d.line([(M, ry), (W - M, ry)], fill=(46, 88, 70), width=2)
    cols = stats[:4]
    span = (W - M * 2) / len(cols)
    for i, (label, val) in enumerate(cols):
        x = M + span * i
        if i:
            d.line([(x - 22, ry + 16), (x - 22, ry + 82)], fill=(34, 70, 55), width=1)
        f_l = font(20, 1)
        track(d, (x, ry + 22), label, f_l, MUTED, 1.5)
        d.text((x - 2, ry + 48), str(val), font=numfont(46), fill=CREAM)

    base.convert("P", palette=Image.ADAPTIVE, colors=160).save(path, optimize=True)


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
