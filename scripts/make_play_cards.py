"""
表現頁的社群分享卡 → dist/og/play/{slug}-{date}.png
==================================================
貼連結到社群時展開的那張圖。**社群爬蟲不跑 JavaScript**,所以 og:image 必須是
真實存在的圖片網址 —— 這支在 build 之後產圖進 dist/,讓表現頁的 og:image 指過去。

**每個表現頁都要有一張**:有 Statcast 逐球資料的那幾場畫專屬打席卡(落點圖/球種),
其餘用逐場數據畫整場數據卡。prerender 已經把 og:image 一律指向這裡,所以這支沒跑
(找不到字型、Pillow 沒裝)的話,表現頁分享出去就是沒有圖 —— 不會壞,但會少一塊。

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
# prerender 寫的中間產物:哪些表現頁真的產出來了(見 game_cards)
PAGES_FILE = ROOT / ".perf-pages.json"

W, H = 1200, 630
# 深底 + 單一高彩度重點色。原本用中綠平塗,縮圖時偏灰、層次也出不來。
INK = (8, 26, 20)              # 背景(近黑綠)
INK_2 = (12, 38, 29)           # 漸層下緣
PANEL = (17, 48, 37)           # 面板
LINE = (34, 74, 58)            # 分隔線
CREAM = (244, 250, 246)
MUTED = (126, 166, 146)
ACCENT = (74, 222, 150)        # 重點色(落點、標籤)
PAPER = (244, 247, 245)        # 資訊面板底(亮色壓深底,對比才拉得開)
PAPER_LINE = (214, 222, 217)
PAPER_INK = (18, 26, 22)
PAPER_MUTED = (108, 122, 114)
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



def draw_arsenal(d, x0, y0, w, pitches):
    """球種分布橫條。投手沒有落點可畫,改用這個當右側的圖像元素。"""
    d.text((x0, y0), "球種分布", font=font(22, 1), fill=MUTED)
    y = y0 + 42
    for p in pitches[:4]:
        d.text((x0, y), p["name"], font=font(24, 1), fill=CREAM)
        pct = f"{p['pct']}%"
        f_p = numfont(24, black=False)
        pw = d.textlength(pct, font=f_p)
        d.text((x0 + w - pw, y + 2), pct, font=f_p, fill=ACCENT)
        by = y + 38
        d.rounded_rectangle([(x0, by), (x0 + w, by + 10)], radius=5, fill=(24, 62, 48))
        bw = max(10, int(w * p["pct"] / 100))
        d.rounded_rectangle([(x0, by), (x0 + bw, by + 10)], radius=5, fill=ACCENT)
        y = by + 40



def draw_statrows(d, x0, y0, w, title, rows):
    """右半的通用數據列。投手沒有逐球資料、或整場數據卡都用這個,不要開天窗。"""
    rows = [r for r in rows if r[1] is not None]
    d.text((x0, y0), title, font=font(22, 1), fill=MUTED)
    y = y0 + 48
    for label, val in rows:
        d.text((x0, y + 8), label, font=font(24, 1), fill=CREAM)
        f_v = numfont(44)
        vs = str(val)
        vw = d.textlength(vs, font=f_v)
        d.text((x0 + w - vw, y), vs, font=f_v, fill=ACCENT)
        y += 58
        d.line([(x0, y - 8), (x0 + w, y - 8)], fill=(28, 66, 52), width=1)


def pad_latin(t):
    """查無中譯的隊名留英文,夾在中文裡要補空格:「對Asheville」→「對 Asheville」。"""
    import re
    t = re.sub(r"([\u4e00-\u9fff])([A-Za-z0-9])", r"\1 \2", str(t or ""))
    return re.sub(r"([A-Za-z0-9])([\u4e00-\u9fff])", r"\1 \2", t)


def draw_pitchline(d, x0, y0, w, pl):
    draw_statrows(d, x0, y0, w, "投球內容",
                  [("被安打", pl.get("h")), ("四壞保送", pl.get("bb")), ("自責分", pl.get("er"))])


def draw_card(path, pl, season_line, roman):
    """
    版面採用廣播數據圖表的通用慣例:亮色面板壓深底、小標籤在上巨大數字在下、
    單位緊貼數字、資料直向堆疊用細線分隔。整張卡的識別(配色、站名、落點圖)
    都是本站自己的,不含任何聯盟、球隊或第三方的標誌與字標。
    """
    img = Image.new("RGB", (W, H), INK)
    d = ImageDraw.Draw(img)
    for i in range(H):
        t = i / H
        d.line([(0, i), (W, i)],
               fill=(int(INK[0] + (INK_2[0] - INK[0]) * t),
                     int(INK[1] + (INK_2[1] - INK[1]) * t),
                     int(INK[2] + (INK_2[2] - INK[2]) * t)))

    is_pitch = pl.get("kind") == "pitch"

    # ── 右半:野手看落點圖,投手看球種分布
    if pl.get("kind") == "game":
        draw_statrows(d, 660, 148, 440, "本場內容", pl["_rows"])
    elif is_pitch:
        if pl.get("pitches"):
            draw_arsenal(d, 660, 132, 440, pl["pitches"])
        else:
            draw_pitchline(d, 660, 148, 440, pl)
    else:
        FIELD = 430
        if pl.get("cx") is not None:
            draw_field(d, W - FIELD - 40, (H - FIELD) / 2 - 8, FIELD, pl)

    # ── 左側資訊面板
    PX, PY, PW = 60, 56, 520
    stats = []
    if pl.get("kind") == "game":
        stats = pl["_stats"]
    elif is_pitch:
        # 投手:三振是頭條,球速是台灣讀者最在意的第二項(用 km/h,站上其他地方也是)
        if pl.get("so") is not None:
            stats.append(("本場三振", str(pl["so"]), "K"))
        if pl.get("kmh_max"):
            stats.append(("最速球速", str(pl["kmh_max"]), "KM/H"))
        elif pl.get("ip"):
            stats.append(("投球局數", str(pl["ip"]), "IP"))
    else:
        if pl.get("dist") is not None:
            stats.append(("飛行距離", str(round(float(pl["dist"]))), "FT"))
        if pl.get("ev") is not None:
            stats.append(("擊球初速", f"{float(pl['ev']):.1f}", "MPH"))
        if pl.get("angle") is not None and len(stats) < 2:
            stats.append(("擊球仰角", str(round(float(pl["angle"]))), "°"))
    stats = stats[:2]

    # 面板高度必須用與畫列時**同一套 bbox 計算**量出來。先前用固定 118px/列估算,
    # 實際畫列走的是 textbbox 流式堆疊,兩邊對不上 → 第二列被面板下緣切掉。
    HEAD_H = 76
    f_lab_m, f_val_m = font(22, 1), numfont(84)
    row_hs = []
    for label, val, unit in stats:
        top = 0
        top += d.textbbox((0, 0), label, font=f_lab_m)[3] + 8
        top = 30 + d.textbbox((0, 30), val, font=f_val_m)[3] - 30 + 16
        row_hs.append(30 + d.textbbox((0, 0), val, font=f_val_m)[3] + 16)
    PH = HEAD_H + 14 + sum(row_hs) + 14 * (len(stats) - 1) + 10
    d.rectangle([(PX, PY), (PX + PW, PY + PH)], fill=PAPER)

    # 標頭:品牌色橫條 + 球員名(取代廣播圖表放隊徽的位置,這裡放本站的識別)
    d.rectangle([(PX, PY), (PX + PW, PY + HEAD_H)], fill=INK)
    d.rectangle([(PX, PY), (PX + 8, PY + HEAD_H)], fill=ACCENT)
    name = pl.get("name", "")
    f_nm = font(34 if len(name) <= 5 else 28, 2)
    d.text((PX + 26, PY + HEAD_H / 2 - 22), name, font=f_nm, fill=PAPER)
    nw = d.textlength(name, font=f_nm)
    if roman and roman != name:
        d.text((PX + 26 + nw + 14, PY + HEAD_H / 2 - 10),
               roman.upper(), font=numfont(19, black=False), fill=(150, 185, 166))

    # 數據列:小標籤在上、巨大數字在下、單位緊貼
    ry = PY + HEAD_H + 14
    for i, (label, val, unit) in enumerate(stats):
        if i:
            d.line([(PX + 26, ry), (PX + PW - 26, ry)], fill=PAPER_LINE, width=2)
            ry += 14
        d.text((PX + 26, ry), label, font=font(22, 1), fill=PAPER_MUTED)
        f_v = numfont(84)
        vy = ry + 30
        d.text((PX + 24, vy), val, font=f_v, fill=PAPER_INK)
        vw = d.textlength(val, font=f_v)
        vb = d.textbbox((PX + 24, vy), val, font=f_v)
        f_u = numfont(26, black=False)
        d.text((PX + 24 + vw + 6, vb[3] - 26), unit, font=f_u, fill=PAPER_INK)
        ry = vb[3] + 16

    # ── 面板下方:事件、對手、日期(深底上的小字)
    y = PY + PH + 30
    if pl.get("kind") == "game":
        tag = pl.get("event_zh") or "出賽"
    elif is_pitch:
        tag = "勝投" if pl.get("win") else ("救援成功" if pl.get("save") else "好投")
    else:
        tag = pl.get("event_zh") or "精彩表現"
    if pl.get("post"):
        tag = f"季後賽　{tag}"        # 不標的話會被當成例行賽
    f_tag = font(30, 2)
    d.rectangle([(PX, y + 4), (PX + 6, y + 40)], fill=ACCENT)
    d.text((PX + 20, y), tag, font=f_tag, fill=ACCENT)
    x = PX + 20 + d.textlength(tag, font=f_tag) + 18
    if pl.get("hr_no") and not is_pitch:
        d.text((x, y + 8), "第", font=font(22, 1), fill=MUTED)
        x += d.textlength("第", font=font(22, 1)) + 4
        f_n = numfont(30)
        d.text((x, y + 2), str(pl["hr_no"]), font=f_n, fill=CREAM)
        x += d.textlength(str(pl["hr_no"]), font=f_n) + 4
        d.text((x, y + 8), "號", font=font(22, 1), fill=MUTED)
    y += 54
    if pl.get("kind") == "game":
        bits = [b for b in [LEVEL.get(pl.get("level"), pl.get("level", "")),
                            f"對{pl['opponent']}" if pl.get("opponent") else ""] if b]
    elif is_pitch:
        bits = [b for b in [
            f"{pl['ip']} 局" if pl.get("ip") else "",
            f"失 {pl['er']} 分" if pl.get("er") is not None else "",
            f"對{pl['opponent']}" if pl.get("opponent") else "",
        ] if b]
    else:
        bits = [b for b in [f"對{pl['opponent']}" if pl.get("opponent") else "",
                            f"仰角 {round(float(pl['angle']))}°" if pl.get("angle") is not None else ""] if b]
    if bits:
        d.text((PX + 2, y), pad_latin("　".join(bits)), font=font(22, 0), fill=MUTED)

    # ── 頁尾
    d.text((PX + 2, H - 62), "players.clutchgtime.com",
           font=numfont(23, black=False), fill=(96, 140, 118))
    dt = pl.get("date", "").replace("-", "/")
    dw = d.textlength(dt, font=numfont(23, black=False))
    d.text((W - 60 - dw, H - 62), dt, font=numfont(23, black=False), fill=(96, 140, 118))

    img.convert("P", palette=Image.ADAPTIVE, colors=128).save(path, optimize=True)


def game_cards(players, have, out_dir):
    """
    從 players.json 的逐場資料補「整場數據卡」。
    先前只有全壘打/長打/好投才有卡(28 張),其餘 200 多個表現頁分享出去只會顯示
    通用的球員圖 —— 平常的比賽等於沒有卡可看。這裡讓每一個表現頁都有。
    不需要 Statcast,純用逐場數據;有專屬打席卡的場次跳過,不覆蓋。
    """
    # 只為真的存在的表現頁產卡。清單由 prerender 寫出(單一事實來源) ——
    # 自己照逐場全產的話會多出五百多張沒有頁面可掛的孤兒。
    try:
        pages = set(json.loads(PAGES_FILE.read_text(encoding="utf-8"))["keys"])
    except Exception:
        print(f"  找不到 {PAGES_FILE.name},跳過整場數據卡(請先跑 npm run build:site)")
        return 0
    n = 0
    for p in players:
        for g in p.get("game_logs", []):
            key = f"{p.get('slug')}-{g.get('date')}"
            if not p.get("slug") or key in have or key not in pages:
                continue
            is_p = g.get("type") == "pitching"
            if is_p:
                stats = [("投球局數", str(g.get("ip") or 0), "IP"),
                         ("三振", str(g.get("so") or 0), "K")]
                rows = [("被安打", g.get("h")), ("四壞保送", g.get("bb")), ("自責分", g.get("er"))]
                if (g.get("hr") or 0) > 0:
                    rows.append(("被全壘打", g.get("hr")))
                # 標籤用站上既有的說法(prerender 的 badgeText:先發/後援),沒有勝敗
                # 的中繼場次再看有沒有守住 —— 一律寫「出賽」等於什麼都沒說。
                tag = ("勝投" if g.get("win") else "救援成功" if g.get("save") else
                       "中繼成功" if g.get("hold") else "敗投" if g.get("loss") else
                       "無失分" if (g.get("er") == 0 and float(g.get("ip") or 0) >= 1) else
                       "先發" if g.get("started") else "後援")
            else:
                hits = g.get("h") or 0
                # 標籤沿用 hitLineTxt 的「N打數N安」語彙,單獨寫「安打 3-2」會讀不出
                # 哪個是打數。
                # 第二個主角數字:沒打點就改秀得分 —— 兩個位置只有兩個,不該擺著一個 0。
                runs = g.get("r") or 0
                second = (("打點", str(g.get("rbi") or 0), "RBI") if (g.get("rbi") or 0) > 0 else
                          ("得分", str(runs), "R") if runs > 0 else
                          ("打點", "0", "RBI"))
                stats = [("打數-安打", f"{g.get('ab') or 0}-{hits}", ""), second]
                rows = [("打點", g.get("rbi")), ("得分", g.get("r")),
                        ("四壞保送", g.get("bb")), ("三振", g.get("so"))]
                rows = [r for r in rows if r[0] != second[0]]   # 主角數字不再重複列一次
                if (g.get("sb") or 0) > 0:
                    rows.append(("盜壘", g.get("sb")))
                # 門檻與 prerender 的 isHot 對齊(2 安或 2 打點就算亮點),否則亮點頁
                # 的卡上會寫「出賽」。
                rbi = g.get("rbi") or 0
                tag = (f"{g['hr']} 轟" if (g.get("hr") or 0) > 1 else
                       "開轟" if g.get("hr") else
                       f"{hits} 安猛打賞" if hits >= 3 else
                       f"{rbi} 分打點" if rbi >= 3 else
                       f"{hits} 安打" if hits >= 2 else
                       f"{rbi} 分打點" if rbi >= 2 else "出賽")
            pl = {
                "kind": "game", "name": p["name"], "slug": p["slug"],
                "date": g.get("date"), "level": g.get("level"),
                "opponent": g.get("opponent"), "event_zh": tag,
                "post": g.get("post"), "_stats": stats, "_rows": rows,
            }
            roman = p.get("roman") or (p.get("name_en") if any(
                c.isascii() and c.isalpha() for c in (p.get("name_en") or "")) else "")
            draw_card(out_dir / f"{key}.png", pl, "", roman)
            n += 1
    return n


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
    # 其餘表現頁補整場數據卡,讓每個可分享的網址都有卡(不覆蓋上面的打席卡)
    g = game_cards(list(players.values()), set(best.keys()), OUT_DIR)
    num_name = Path(NUM_PATH).name if NUM_PATH else "(無窄體,退回中文字型)"
    print(f"分享卡:{n + g} 張(打席 {n}、整場 {g})→ dist/og/play/"
          f"(中文 {Path(FONT_PATH).name}、數字 {num_name})")


if __name__ == "__main__":
    main()
