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
    """
    社群卡的成敗在縮圖 —— 在動態牆上只有一眼。所以刻意砍到只剩四件事:
    誰、做了什麼、最驚人的那個數字、一張看得懂的圖。
    本季累積、比分、層級、資料來源這些在動態牆上沒人讀的,全部拿掉或縮到最小。
    """
    img = Image.new("RGB", (W, H), INK)
    d = ImageDraw.Draw(img)
    for i in range(H):
        t = i / H
        d.line([(0, i), (W, i)],
               fill=(int(INK[0] + (INK_2[0] - INK[0]) * t),
                     int(INK[1] + (INK_2[1] - INK[1]) * t),
                     int(INK[2] + (INK_2[2] - INK[2]) * t)))

    PAD = 72
    FIELD = 400                       # 球場圖放大:它是這張卡唯一的圖像元素
    fx = W - 44 - FIELD

    if pl.get("cx") is not None:
        draw_field(d, fx, (H - FIELD) / 2, FIELD, pl)

    # ── 事件(最上方,重點色橫條而非膠囊 —— 縮圖時色塊比圓角更搶眼)
    y = 80
    tag = pl.get("event_zh") or "精彩表現"
    f_tag = font(30, 2)
    d.rectangle([(PAD, y), (PAD + 6, y + 40)], fill=ACCENT)
    d.text((PAD + 20, y + 2), tag, font=f_tag, fill=ACCENT)
    tw = d.textlength(tag, font=f_tag)
    if pl.get("hr_no"):
        x = PAD + 20 + tw + 18
        d.text((x, y + 6), "第", font=font(24, 1), fill=MUTED)
        x += d.textlength("第", font=font(24, 1)) + 4
        f_n = numfont(32)
        d.text((x, y - 1), str(pl["hr_no"]), font=f_n, fill=CREAM)
        x += d.textlength(str(pl["hr_no"]), font=f_n) + 4
        d.text((x, y + 6), "號", font=font(24, 1), fill=MUTED)

    # ── 球員名:整張卡最大的字
    y += 60
    name = pl.get("name", "")
    size = 112 if len(name) <= 3 else (92 if len(name) <= 5 else 74)
    f_name = font(size, 2)
    d.text((PAD, y), name, font=f_name, fill=CREAM)
    # 用實際 bbox 的下緣定位下一行,不要用字級推 —— 中文字型的字高小於字級,
    # 用字級算出來的位置會讓羅馬名貼上中文名的下緣。
    y = d.textbbox((PAD, y), name, font=f_name)[3] + 18
    if roman and roman != name:
        d.text((PAD + 4, y), roman.upper(), font=numfont(26, black=False), fill=MUTED)
        y += 38

    # ── 主角數字:全壘打看距離,其餘看擊球初速
    hero = None
    if pl.get("event") in ("Home Run", "Grand Slam") and pl.get("dist") is not None:
        hero = (str(round(float(pl["dist"]))), "ft", "飛行距離")
    elif pl.get("ev") is not None:
        hero = (f"{float(pl['ev']):.1f}", "mph", "擊球初速")
    if hero:
        y += 26
        val, unit, label = hero
        f_hero = numfont(132)
        d.text((PAD, y), val, font=f_hero, fill=ACCENT)
        vw = d.textlength(val, font=f_hero)
        d.text((PAD + vw + 12, y + 74), unit, font=numfont(34, black=False), fill=ACCENT)
        # 標籤與下一行都接著 bbox 走。先前上半用流式、下半釘在卡片底部,
        # 主角數字一往下推,標籤就撞上那行小字。
        # 不放「飛行距離」這種標籤 —— 單位 ft/mph 已經說明了是什麼,
        # 多一行只是讓左欄長度超出 630px,再用 min() 夾制就會壓到下一行。
        y = d.textbbox((PAD, y), val, font=f_hero)[3] + 18

    # ── 其餘兩項縮到最小,只給想看的人
    rest = []
    if hero and hero[2] != "擊球初速" and pl.get("ev") is not None:
        rest.append(f"初速 {float(pl['ev']):.1f} mph")
    if pl.get("angle") is not None:
        rest.append(f"仰角 {round(float(pl['angle']))}°")
    if pl.get("opponent"):
        rest.append(f"對{pl['opponent']}")
    if rest:
        d.text((PAD, y), "　".join(rest), font=font(23, 0), fill=MUTED)

    # ── 頁尾只留網址一行
    d.text((PAD, H - 66), "players.clutchgtime.com",
           font=numfont(24, black=False), fill=(96, 140, 118))
    dt = pl.get("date", "").replace("-", "/")
    dw = d.textlength(dt, font=numfont(24, black=False))
    d.text((W - 72 - dw, H - 66), dt, font=numfont(24, black=False), fill=(96, 140, 118))

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
