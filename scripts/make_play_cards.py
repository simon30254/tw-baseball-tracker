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
# 深底 + 單一高彩度重點色。原本用中綠平塗,縮圖時偏灰、層次也出不來。
INK = (8, 26, 20)              # 背景(近黑綠)
INK_2 = (12, 38, 29)           # 漸層下緣
PANEL = (17, 48, 37)           # 面板
LINE = (34, 74, 58)            # 分隔線
CREAM = (244, 250, 246)
MUTED = (126, 166, 146)
ACCENT = (74, 222, 150)        # 重點色(落點、標籤、數字底線)
GREEN = INK
GREEN_DARK = INK_2

LEVEL = {"MLB": "大聯盟", "AAA": "3A", "AA": "2A", "High-A": "高階1A", "A": "1A",
         "Rookie": "新人聯盟"}

# 中文字型。index 是 ttc 裡的字重(regular / medium / bold)
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

# 數字與羅馬名專用的拉丁窄體重字。**這是「像不像專業運動圖表」的關鍵** ——
# 中文字型的拉丁數字偏圓、字重也上不去,100.2 這種數字放大後看起來就是軟的。
# 廣播圖表用的是窄體黑(condensed black),同寬度能塞更大的字。
NUM_CANDIDATES = [
    ("/System/Library/Fonts/HelveticaNeue.ttc", 9, 4),        # Condensed Black / Condensed Bold
    ("/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf", 0, 0),
    ("/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Bold.ttf", 0, 0),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 0, 0),
]
NUM_PATH, NUM_BLACK, NUM_BOLD = None, 0, 0
for path, b, bb in NUM_CANDIDATES:
    if Path(path).exists():
        NUM_PATH, NUM_BLACK, NUM_BOLD = path, b, bb
        break


def font(size, weight=0):
    return ImageFont.truetype(FONT_PATH, size, index=WEIGHTS[min(weight, 2)])


def numfont(size, black=True):
    """數字/拉丁字用。沒有窄體可用時退回中文字型,不會壞只是沒那麼銳利。"""
    if not NUM_PATH:
        return font(size, 2)
    return ImageFont.truetype(NUM_PATH, size, index=NUM_BLACK if black else NUM_BOLD)


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



# Gameday 落點座標系:本壘約在 (125.42, 203.5),X 往右增、Y 往外野方向遞減。
# 實測 362 ft 的球落在距本壘約 151 座標單位處 → 約 2.4 ft/單位,用來換算比例尺。
HOME_X, HOME_Y = 125.42, 203.5
COORD_MAX = 200.0          # 扇形半徑對應的座標距離(約 480 ft,含最深的全壘打)


def draw_field(d, cx0, cy0, size, pl):
    """球場落點示意圖。用公開的落點座標自己畫,不是任何官網的圖片。"""
    import math
    home = (cx0 + size / 2, cy0 + size * 0.90)
    R = size * 0.80

    # 外野草皮扇形(界外線各 45 度 → 以正上方為中心展開 90 度)
    box = [home[0] - R, home[1] - R, home[0] + R, home[1] + R]
    d.pieslice(box, start=225, end=315, fill=(19, 56, 43))
    # 內野土(同心小扇形)
    r2 = R * 0.42
    d.pieslice([home[0] - r2, home[1] - r2, home[0] + r2, home[1] + r2],
               start=225, end=315, fill=(26, 70, 54))
    # 界外線
    for ang in (225, 315):
        a = math.radians(ang)
        d.line([home, (home[0] + R * math.cos(a), home[1] + R * math.sin(a))],
               fill=(44, 92, 72), width=2)
    # 全壘打牆
    d.arc(box, start=225, end=315, fill=(52, 108, 84), width=3)

    if pl.get("cx") is None or pl.get("cy") is None:
        return
    dx = float(pl["cx"]) - HOME_X
    dy = HOME_Y - float(pl["cy"])          # 往外野為正
    r = math.hypot(dx, dy)
    if r <= 0:
        return
    scale = min(r / COORD_MAX, 1.0) * R
    ang = math.atan2(dx, dy)               # 0 = 正中外野,右為正
    ang = max(min(ang, math.radians(45)), math.radians(-45))
    px = home[0] + scale * math.sin(ang)
    py = home[1] - scale * math.cos(ang)

    d.line([home, (px, py)], fill=(96, 150, 124), width=3)
    # 落點:外圈光暈 + 實心點,縮圖時仍然看得見
    d.ellipse([px - 17, py - 17, px + 17, py + 17], outline=ACCENT, width=3)
    d.ellipse([px - 8, py - 8, px + 8, py + 8], fill=ACCENT)
    d.ellipse([home[0] - 6, home[1] - 6, home[0] + 6, home[1] + 6], fill=(150, 190, 168))


def draw_card(path, pl, season_line, roman):
    img = Image.new("RGB", (W, H), INK)
    d = ImageDraw.Draw(img)
    for i in range(H):
        t = i / H
        d.line([(0, i), (W, i)],
               fill=(int(INK[0] + (INK_2[0] - INK[0]) * t),
                     int(INK[1] + (INK_2[1] - INK[1]) * t),
                     int(INK[2] + (INK_2[2] - INK[2]) * t)))
    d.rectangle([(0, 0), (8, H)], fill=ACCENT)

    PAD = 68
    BAR_H = 92
    FIELD = 340
    COL_W = W - PAD * 2 - FIELD - 40          # 左欄寬(文字與數據共用同一條左緣)

    if pl.get("cx") is not None:
        fx = W - PAD - FIELD
        draw_field(d, fx, 104, FIELD, pl)
        f_cap = font(19, 1)
        cap = "落點示意"
        cw_ = d.textlength(cap, font=f_cap)
        d.text((fx + FIELD / 2 - cw_ / 2, 104 + FIELD * 0.96), cap, font=f_cap, fill=MUTED)

    # ── 第一列:事件標籤 + 局數 + 層級
    y = 54
    tag = pl.get("event_zh") or "精彩表現"
    f_tag = font(23, 2)
    tw = d.textlength(tag, font=f_tag)
    d.rounded_rectangle([(PAD, y), (PAD + tw + 32, y + 40)], radius=6, fill=ACCENT)
    d.text((PAD + 16, y + 6), tag, font=f_tag, fill=INK)
    bits = []
    if pl.get("inning"):
        bits.append(f"{'上' if pl.get('half') == 'top' else '下'}{pl['inning']}局")
    lv = LEVEL.get(pl.get("level"), pl.get("level", ""))
    if lv:
        bits.append(lv)
    if bits:
        d.text((PAD + tw + 50, y + 8), "　".join(bits), font=font(23, 1), fill=MUTED)

    # ── 球員名(主角)。羅馬名用拉丁字型,與中文名底線對齊
    y = 112
    name = pl.get("name", "")
    size = 92 if len(name) <= 3 else (78 if len(name) <= 5 else 64)
    f_name = font(size, 2)
    d.text((PAD, y), name, font=f_name, fill=CREAM)
    nw = d.textlength(name, font=f_name)
    if roman and roman != name:
        f_rom = numfont(30, black=False)
        d.text((PAD + nw + 22, y + size - 46), roman.upper(), font=f_rom, fill=MUTED)

    # ── 重點副標(本季第 N 號 / 打點)。數字用窄體黑
    y += size + 26
    x = PAD
    if pl.get("hr_no"):
        d.text((x, y + 6), "本季第", font=font(26, 1), fill=ACCENT)
        x += d.textlength("本季第", font=font(26, 1)) + 8
        f_n = numfont(38)
        d.text((x, y - 4), str(pl["hr_no"]), font=f_n, fill=ACCENT)
        x += d.textlength(str(pl["hr_no"]), font=f_n) + 8
        d.text((x, y + 6), "號", font=font(26, 1), fill=ACCENT)
        x += d.textlength("號", font=font(26, 1)) + 14
        d.text((x, y + 4), "·", font=font(26, 1), fill=(60, 120, 95))
        x += 22
    if pl.get("rbi"):
        f_n = numfont(38)
        d.text((x, y - 4), str(pl["rbi"]), font=f_n, fill=ACCENT)
        x += d.textlength(str(pl["rbi"]), font=f_n) + 8
        d.text((x, y + 6), "分打點", font=font(26, 1), fill=ACCENT)
    y += 56

    # ── 對戰資訊
    meta = "　".join(x for x in [
        pl.get("date", "").replace("-", "/"),
        f"對{pl['opponent']}" if pl.get("opponent") else "",
    ] if x)
    d.text((PAD, y), meta, font=font(23, 0), fill=MUTED)
    if pl.get("away_score") is not None and pl.get("home_score") is not None:
        mw = d.textlength(meta, font=font(23, 0))
        f_sc = numfont(26, black=False)
        d.text((PAD + mw + 26, y - 2), f"{pl['away_score']} : {pl['home_score']}",
               font=f_sc, fill=(170, 200, 184))

    # ── Statcast 面板:加外框與欄間分隔線,欄位就不會看起來參差
    cells = []
    if pl.get("ev") is not None:
        cells.append(("擊球初速", f"{float(pl['ev']):.1f}", "mph"))
    if pl.get("dist") is not None:
        cells.append(("飛行距離", str(round(float(pl["dist"]))), "ft"))
    if pl.get("angle") is not None:
        cells.append(("擊球仰角", str(round(float(pl["angle"]))), "°"))
    if cells:
        py0 = y + 54           # 接在對戰資訊下方,不要卡到底部留一條空白帶
        d.rounded_rectangle([(PAD, py0), (PAD + COL_W, py0 + 148)], radius=10,
                            fill=PANEL, outline=LINE, width=1)
        cw = COL_W / len(cells)
        for i, (label, val, unit) in enumerate(cells):
            cx = PAD + cw * i
            if i:
                d.line([(cx, py0 + 22), (cx, py0 + 126)], fill=LINE, width=1)
            # 欄內置中,寬度不同也不會看起來歪
            f_lab = font(20, 1)
            lw = d.textlength(label, font=f_lab)
            d.text((cx + cw / 2 - lw / 2, py0 + 26), label, font=f_lab, fill=MUTED)
            # 自動縮到欄寬內。CI 的 DejaVu 比本機的 Helvetica Neue 寬,
            # 「100.2 mph」這種最長的組合會頂到欄間分隔線 —— 不能靠目視保證。
            f_unit = font(20, 1)
            uw = d.textlength(unit, font=f_unit)
            size_v = 62
            while size_v > 34:
                f_val = numfont(size_v)
                vw = d.textlength(val, font=f_val)
                if vw + 8 + uw <= cw - 32:
                    break
                size_v -= 2
            f_val = numfont(size_v)
            vw = d.textlength(val, font=f_val)
            x0 = cx + cw / 2 - (vw + 8 + uw) / 2
            d.text((x0, py0 + 58 + (62 - size_v) * 0.4), val, font=f_val, fill=CREAM)
            d.text((x0 + vw + 8, py0 + 92), unit, font=f_unit, fill=MUTED)

    # ── 底部資訊列
    by = H - BAR_H
    d.rectangle([(0, by), (W, H)], fill=PANEL)
    d.line([(0, by), (W, by)], fill=LINE, width=1)
    f_brand = font(27, 2)
    d.text((PAD, by + 18), "旅外球員情報站", font=f_brand, fill=CREAM)
    bw = d.textlength("旅外球員情報站", font=f_brand)
    d.text((PAD + bw + 18, by + 24), "players.clutchgtime.com",
           font=numfont(21, black=False), fill=MUTED)
    if season_line:
        d.text((PAD, by + 54), f"本季　{season_line}", font=font(20, 1), fill=MUTED)
    src = "數據來源：MLB Stats API"
    sw = d.textlength(src, font=font(18, 0))
    d.text((W - PAD - sw, by + 56), src, font=font(18, 0), fill=MUTED)

    img.convert("P", palette=Image.ADAPTIVE, colors=128).save(path, optimize=True)


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
    num_name = Path(NUM_PATH).name if NUM_PATH else "(無窄體,退回中文字型)"
    print(f"分享卡:{n} 張 → dist/og/play/(中文 {Path(FONT_PATH).name}、數字 {num_name})")


if __name__ == "__main__":
    main()
