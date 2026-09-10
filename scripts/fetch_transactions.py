"""
旅美球員官方異動 → public/data/transactions.json
===============================================
MLB Stats API 的 /transactions 是**官方異動紀錄**:指定讓渡、下放、升上大聯盟、
傷兵名單進出、交易、簽約。這是站上「消息」的主要來源 —— 事實直接來自官方,
可以用自己的話寫在站上,不必連到媒體去看別人怎麼寫。

中文句子是用 typeCode + fromTeam/toTeam **組出來的**,不是翻譯 description。
沒有把握的類型寧可只寫「{類型}」並保留官方英文原句,也不要猜錯講成假消息。

隊名中譯共用 scripts/team_zh.json(與逐場對手同一份)。
旅日/旅韓沒有等價的官方異動來源,那邊的升降靠 build_players 的 moves.json 推定。

執行:python3 scripts/fetch_transactions.py
"""

import json
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "public" / "data"
OUT = DATA / "transactions.json"
TEAM_ZH_PATH = ROOT / "scripts" / "team_zh.json"

API = "https://statsapi.mlb.com/api/v1/transactions"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
TW = timezone(timedelta(hours=8))
DAYS = 60
TIMEOUT = 40


def team_zh_map():
    try:
        d = json.loads(TEAM_ZH_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}, {}, []
    return d.get("球隊", {}), d.get("球隊暱稱", {}), d.get("複合聯盟前綴", [])


TEAMS, NICKS, PREFIXES = team_zh_map()


def zh_team(name):
    """查不到就留英文原名 —— 與 team_zh.json 的原則一致,不自己音譯。"""
    if not name:
        return ""
    if name in TEAMS:
        return TEAMS[name]
    for p in PREFIXES:                      # 'ACL White Sox' → 'ACL 白襪'
        if name.startswith(p + " "):
            nick = name[len(p) + 1:]
            if nick in NICKS:
                return f"{p} {NICKS[nick]}"
    return name


# description 裡的傷兵名單措辭 → 中文。Status Change 沒有結構化欄位可用,
# 只能讀官方句子,所以比對得很保守:只認這幾種明確的講法。
IL_PATTERNS = [
    (r"placed .* on the (\d+)-day injured list", "進入 {0} 日傷兵名單"),
    (r"placed .* on the (\d+)-day injured list, retroactive", "進入 {0} 日傷兵名單"),
    (r"activated .* from the (\d+)-day injured list", "自 {0} 日傷兵名單復出"),
    (r"transferred .* to the (\d+)-day injured list", "轉入 {0} 日傷兵名單"),
    (r"sent .* on a rehab assignment to (.+?)\.?$", "展開復健賽({0})"),
    (r"activated .* from the paternity list", "自陪產假名單復出"),
    (r"placed .* on the paternity list", "進入陪產假名單"),
    (r"transferred .* to the Development List", "轉入育成名單"),
    (r"activated .* from the Development List", "自育成名單復出"),
    # 明星賽的「activated」與球隊登錄長得一樣,但這是真消息,要先比對到
    (r"(American League|National League) All-Stars activated", "入選明星賽"),
    (r"^(.+?) activated .*?\.?$", "登錄於{0}"),
    (r"roster status changed by (.+?)\.?$", "名單狀態異動（{0}）"),
    (r"assigned .* to (.+?) from (.+?)\.?$", None),   # 交給 ASG 模板處理
]


def status_change_zh(desc):
    for pat, tmpl in IL_PATTERNS:
        m = re.search(pat, desc, re.I)
        if not m or not tmpl:
            continue
        if not m.groups():                  # 「轉入育成名單」這種句型沒有可帶入的值
            return tmpl
        arg = m.group(1)
        return tmpl.format(arg if arg.isdigit() else zh_team(arg))
    return None


def pad_latin(s):
    """查無中譯的隊名會留英文,夾在中文裡要補空格:「下放Worcester」→「下放 Worcester」。"""
    if not s:
        return s
    s = re.sub(r"([\u4e00-\u9fff])([A-Za-z0-9])", r"\1 \2", s)
    return re.sub(r"([A-Za-z0-9])([\u4e00-\u9fff])", r"\1 \2", s)


def to_zh(t):
    """組出中文句子;沒把握時回 None,呼叫端保留官方英文原句。"""
    code = t.get("typeCode")
    frm, to = zh_team((t.get("fromTeam") or {}).get("name")), zh_team((t.get("toTeam") or {}).get("name"))
    desc = t.get("description") or ""

    if code == "DES":
        return f"遭{to or '球隊'}指定讓渡（DFA）"
    if code == "SE":
        return f"獲{to}升上大聯盟" + (f"（自{frm}）" if frm else "")
    if code == "REC":
        return f"獲{to}自{frm}升上大聯盟" if frm else f"獲{to}升上大聯盟"
    if code == "OPT":
        return f"遭{frm}下放{to}" if frm and to else f"遭下放小聯盟"
    if code == "OUT":
        return f"通過讓渡程序、指派至{to}" if to else "通過讓渡程序、指派至小聯盟"
    if code == "TR":
        return f"自{frm}被交易至{to}" if frm and to else "被交易"
    if code == "SFA":
        return f"以自由球員身分與{to}簽約" if to else "以自由球員身分簽約"
    if code == "DFA" or code == "REL":
        return f"遭{frm or to or '球隊'}釋出"
    if code == "DEC":
        return "成為自由球員"
    if code == "CU":
        return f"獲{to}自{frm}召回" if frm and to else None
    if code == "SC":
        return status_change_zh(desc)
    if code == "ASG":
        z = status_change_zh(desc)
        if z:
            return z
        if frm and to and frm != to:
            return f"自{frm}轉至{to}"
        return f"指派至{to}" if to else None
    return None


# 哪些異動值得當「消息」。小聯盟附屬隊之間的調動、以及跟在下放後面那筆機械式的
# 「{隊} activated {人}」是流程雜訊,放進消息頁只會把 DFA、傷兵這種真消息稀釋掉。
# 但球員頁的完整異動紀錄仍然全都留著。
BIG_TYPES = {"DES", "SE", "REC", "OPT", "TR", "SFA", "DFA", "REL", "DEC", "OUT", "CU"}
BIG_WORDS = ("傷兵名單", "復健賽", "育成名單", "明星賽")


def is_big(t, zh):
    if t.get("typeCode") in BIG_TYPES:
        return True
    return any(w in (zh or "") for w in BIG_WORDS)


def main():
    try:
        players = json.loads((DATA / "players.json").read_text(encoding="utf-8"))["players"]
    except Exception as e:
        print(f"讀不到 players.json:{e}")
        sys.exit(1)
    ids = {str(p["id"]): p["name"] for p in players if str(p["id"]).isdigit()}
    if not ids:
        print("沒有旅美球員,跳過")
        return

    today = datetime.now(TW).date()
    start = (today - timedelta(days=DAYS)).isoformat()
    url = f"{API}?startDate={start}&endDate={today.isoformat()}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = json.loads(r.read())
    except Exception as e:
        print(f"抓取失敗:{type(e).__name__} {e}")
        sys.exit(1)

    seen, items, unsure = set(), [], 0
    for t in raw.get("transactions", []):
        pid = str((t.get("person") or {}).get("id") or "")
        if pid not in ids:
            continue
        key = (t.get("date"), pid, t.get("typeCode"), t.get("description"))
        if key in seen:
            continue
        seen.add(key)
        zh = pad_latin(to_zh(t))
        if not zh:
            unsure += 1
        items.append({
            "date": t.get("date"),
            "id": pid,
            "name": ids[pid],
            "type": t.get("typeCode"),
            "type_en": t.get("typeDesc"),
            "text": zh or "",                    # 沒把握就空著,前端改顯示官方英文原句
            "official": t.get("description") or "",
            "big": is_big(t, zh),
        })

    items.sort(key=lambda x: (x["date"], x["name"]), reverse=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(
        {"updated_at": datetime.now(TW).isoformat(timespec="seconds"), "items": items},
        ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"完成:{OUT} — {len(items)} 筆(重要 {sum(1 for i in items if i['big'])})、"
          f"{len({i['id'] for i in items})} 位球員"
          f"{f',其中 {unsure} 筆無中文模板、保留官方原句' if unsure else ''}")


if __name__ == "__main__":
    main()
