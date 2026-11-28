"""分享圖用的字型解析(make_og / make_season_og / make_scouting_og / make_play_cards 共用)

原本三支畫圖腳本各自寫死 FONT = "/System/Library/Fonts/PingFang.ttc"。
2026-11-28 在 macOS 上整批壞掉:`OSError: cannot open resource` —— 這個版本的 macOS
已經不把 PingFang 放在 /System/Library/Fonts/,改成「隨需下載的字型資產」,實際檔案在
  /System/Library/AssetsV2/com_apple_MobileAsset_Font*/<hash>.asset/AssetData/PingFang.ttc
那串 hash 會隨系統更新改變,所以只能用 glob 找,不能寫死。
把解析集中在這裡,壞一次修一個地方。

**ttc 的 index 不是字重**:PingFang.ttc 裡是 0-3 = HK/MO/TC 的 Regular、4-7 = Medium、
8-11 = Semibold。原本的腳本用 (0, 1, 2) 當「regular / medium / bold」,其實三個都是
Regular,只是地區變體不同 —— 也就是既有的 78 張圖上沒有真的粗體。這裡**刻意沿用
(0, 1, 2)**:改成真字重會讓全部既有圖重新產生(二進位差異進 git,正是 make_og.py
開頭警告的事),為了外觀一致不值得。新卡要粗體時明確傳 index。
"""
from pathlib import Path
from glob import glob

# 中文字型。index 的意義見上面那段說明。
_CJK = [
    ("/System/Library/Fonts/PingFang.ttc", (0, 1, 2)),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", (0, 0, 1)),
    ("/usr/share/fonts/opentype/noto/NotoSansCJKtc-Regular.ttc", (0, 0, 1)),
    ("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc", (0, 0, 1)),
]
_CJK_GLOBS = ["/System/Library/AssetsV2/com_apple_MobileAsset_Font*/*.asset/AssetData/PingFang.ttc"]

# 數字與羅馬名專用的拉丁窄體重字。中文字型的數字偏圓、字重上不去,放大後是軟的。
_NUM = [
    ("/System/Library/Fonts/HelveticaNeue.ttc", 9, 4),        # Condensed Black / Condensed Bold
    ("/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf", 0, 0),
    ("/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Bold.ttf", 0, 0),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 0, 0),
]


def cjk():
    """(路徑, (regular, medium, bold) 的 index)。找不到回 (None, (0, 0, 0))。"""
    for path, w in _CJK:
        if Path(path).exists():
            return path, w
    for pat in _CJK_GLOBS:
        hits = sorted(glob(pat))
        if hits:
            return hits[-1], (0, 1, 2)      # 多個版本取最後一個(字典序最大)
    return None, (0, 0, 0)


def latin():
    """(路徑, black index, bold index)。找不到回 (None, 0, 0),呼叫端退回中文字型。"""
    for path, b, bb in _NUM:
        if Path(path).exists():
            return path, b, bb
    return None, 0, 0
