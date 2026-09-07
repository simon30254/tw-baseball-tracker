"""
歷代旅日台灣球員(已離開 NPB 者)生涯數據
=========================================
從郭源治(1981)、郭泰源、莊勝雄、呂明賜到陽岱鋼 —— 這段歷史在中文網路上
沒有任何一個地方有結構化的完整數據。npb.jp 的球員頁 /bis/players/{id}.html
有完整生涯逐年表(回溯到 1981 年,比季賽成績頁的 2005 年早得多)。

名單為什麼要人工策展:npb.jp 沒有 birthCountry 那種可掃的欄位,而「経歴」欄
也不可靠 —— 陽岱鋼(福岡第一高)、林威助(柳川高)、吳念庭(岡山県共生高)都唸
日本高中,靠學校名判斷會整批漏掉。所以名單放 scripts/npb_alumni_roster.json,
npb.jp 只負責提供 id 與數據。

輸出:併入 public/data/alumni.json。已在該檔的人(陳偉殷有大聯盟生涯)會把
NPB 的年份與層級**併進同一筆**,形成一份橫跨美日的完整生涯 —— 那正是這站
能提供而別處沒有的東西。

執行: python3 scripts/fetch_npb_alumni.py
"""

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_npb as N                                    # noqa: E402
from build_players import localize_teams, fill_whip      # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ROSTER_PATH = ROOT / "scripts" / "npb_alumni_roster.json"
ALUMNI_PATH = ROOT / "public" / "data" / "alumni.json"
PLAYERS_PATH = ROOT / "public" / "data" / "players.json"

TEAM_ZH = {
    "中日": "中日", "西武": "西武", "埼玉西武": "西武", "読売": "巨人", "南海": "南海",
    "ロッテ": "羅德", "千葉ロッテ": "羅德", "ヤクルト": "養樂多", "阪神": "阪神",
    "オリックス": "歐力士", "日本ハム": "日本火腿", "北海道日本ハム": "日本火腿",
    "ソフトバンク": "軟銀", "福岡ソフトバンク": "軟銀", "広島": "廣島", "横浜": "橫濱",
    "横浜ＤｅＮＡ": "DeNA", "横浜DeNA": "DeNA", "楽天": "樂天", "東北楽天": "樂天", "近鉄": "近鐵",
    "大阪近鉄": "近鐵", "阪急": "阪急", "日拓": "日拓", "太平洋": "太平洋",
    "クラウン": "皇冠", "大洋": "大洋", "ダイエー": "大榮", "福岡ダイエー": "大榮",
}


def ip_join(s):
    """npb.jp 的投球回被拆成整數與分數兩格(巢狀表格),攤平後是「21 .1」→「21.1」。"""
    s = re.sub(r"\s+", "", str(s or ""))
    if not s:
        return "0.0"
    return s if "." in s else f"{s}.0"


def num(s, default=0):
    s = re.sub(r"[^\d\-]", "", str(s or ""))
    try:
        return int(s)
    except ValueError:
        return default


def rate(s):
    """.333 / 3.22 原樣留著;空字串就空著,不要編一個 0 出來。"""
    s = str(s or "").strip()
    return s if re.match(r"^-?[\d.]+$", s) else ""


def parse_career(html, is_pitcher):
    """球員頁的生涯逐年表 → ({年份: {"一軍": stat}}, 通算)。"""
    p = N._TableExtractor()
    p.feed(html)
    want_head = ["年度", "所属球団"]
    key = "登板" if is_pitcher else "打席"
    for t in p.tables:
        head = [c.replace("　", "").strip() for c in t[0]] if t else []
        if head[:2] != want_head or key not in head:
            continue
        col = {h: i for i, h in enumerate(head)}

        def val(row, name, default=""):
            i = col.get(name)
            return row[i] if i is not None and i < len(row) else default

        years, total = {}, None
        for row in t[1:]:
            if not row:
                continue
            yr = row[0].strip()
            # _TableExtractor 已把全形空白正規化成半形,所以要去掉所有空白
            # 才對得上表:「南 海」→「南海」、「読 売」→「巨人」。
            raw_team = re.sub(r"\s+", "", val(row, "所属球団"))
            team = TEAM_ZH.get(raw_team, raw_team)
            if is_pitcher:
                s = {
                    "g": num(val(row, "登板")), "gs": 0,
                    "w": num(val(row, "勝利")), "l": num(val(row, "敗北")),
                    "sv": num(val(row, "セーブ")), "hld": num(val(row, "H")),
                    "ip": ip_join(val(row, "投球回")),
                    "h": num(val(row, "安打")), "hr": num(val(row, "本塁打")),
                    "so": num(val(row, "三振")), "bb": num(val(row, "四球")),
                    "hbp": num(val(row, "死球")), "tbf": num(val(row, "打者")),
                    "er": num(val(row, "自責点")), "era": rate(val(row, "防御率")),
                    "whip": "",
                }
            else:
                s = {
                    "g": num(val(row, "試合")), "pa": num(val(row, "打席")),
                    "ab": num(val(row, "打数")), "r": num(val(row, "得点")),
                    "h": num(val(row, "安打")), "hr": num(val(row, "本塁打")),
                    "rbi": num(val(row, "打点")), "sb": num(val(row, "盗塁")),
                    "bb": num(val(row, "四球")), "hbp": num(val(row, "死球")),
                    "so": num(val(row, "三振")),
                    "avg": rate(val(row, "打率")), "slg": rate(val(row, "長打率")),
                    "obp": rate(val(row, "出塁率")), "ops": "",
                }
            if yr.isdigit():
                s["team"] = team
                years[yr] = {"一軍": s}
            elif "通算" in re.sub(r"\s+", "", yr + raw_team):   # 「通 算」列(年度欄空白)
                total = s
        return years, total
    return {}, None


def bio_from(html):
    p = N._TableExtractor()
    p.feed(html)
    out = {}
    for t in p.tables:
        for row in t:
            if len(row) < 2:
                continue
            k, v = row[0].strip(), row[1].strip()
            if k == "投打":
                m = re.match(r"(左|右|両)投(左|右|両)打", v)
                if m:
                    out["throws"], out["bats"] = m.group(1), m.group(2)
            elif k == "身長／体重":
                m = re.match(r"(\d+)cm／(\d+)kg", v)
                if m:
                    out["ht"], out["wt"] = int(m.group(1)), int(m.group(2))
            elif k == "生年月日":
                m = re.match(r"(\d+)年(\d+)月(\d+)日", v)
                if m:
                    out["birth"] = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return out


def fill_ops(players):
    """NPB 給出塁率與長打率但不給 OPS,兩者相加即得(定義如此,不是估算)。"""
    n = 0
    for p in players:
        buckets = [p.get("career") or {}]
        buckets += list((p.get("prev_season") or {}).values())
        for by_level in buckets:
            for s in (by_level or {}).values():
                if not isinstance(s, dict) or s.get("ops") or not (s.get("obp") and s.get("slg")):
                    continue
                try:
                    s["ops"] = f"{float(s['obp']) + float(s['slg']):.3f}".lstrip("0")
                    n += 1
                except ValueError:
                    pass
    if n:
        print(f"補算 OPS:{n} 筆")


def main():
    roster = json.loads(ROSTER_PATH.read_text(encoding="utf-8"))["players"]
    try:
        blob = json.loads(ALUMNI_PATH.read_text(encoding="utf-8"))
    except Exception:
        blob = {"players": []}
    by_name = {p["name"]: p for p in blob["players"]}

    # slug 撞到現役球員就是把兩個人蓋到同一個網址,必須擋下來
    active_slugs = set()
    try:
        active_slugs = {p["slug"] for p in json.loads(PLAYERS_PATH.read_text(encoding="utf-8"))["players"]}
    except Exception:
        pass

    added = merged = 0
    for r in roster:
        html = N.get(f"https://npb.jp/bis/players/{r['npb_id']}.html")
        time.sleep(0.25)
        if not html:
            print(f"  [略過] {r['zh']}:頁面抓不到")
            continue
        is_pitcher = r["role"] == "pitcher"
        years, total = parse_career(html, is_pitcher)
        if not years:
            print(f"  [略過] {r['zh']}:解析不到生涯逐年表")
            continue
        yrs = sorted(int(y) for y in years)
        teams = sorted({s["一軍"]["team"] for s in years.values() if s["一軍"].get("team")})

        cur = by_name.get(r["zh"])
        if cur:
            # 已有大聯盟生涯(陳偉殷)→ 併進同一筆,形成橫跨美日的完整生涯
            for y, v in years.items():
                cur.setdefault("prev_season", {}).setdefault(y, {}).update(v)
            if total:
                cur.setdefault("career", {})["一軍"] = total
            cur["npb_seasons"] = yrs
            cur["prev_season"] = {y: cur["prev_season"][y]
                                  for y in sorted(cur["prev_season"], reverse=True)}
            merged += 1
            print(f"  併入 {r['zh']}:NPB {yrs[0]}–{yrs[-1]}({len(yrs)} 季)+ 既有大聯盟生涯")
            continue

        if r["slug"] in active_slugs:
            print(f"  [錯誤] {r['zh']} 的 slug 與現役球員相同:{r['slug']}", file=sys.stderr)
            sys.exit(1)
        blob["players"].append({
            "id": f"npba{r['npb_id']}",
            "name": r["zh"],
            "name_en": r["zh"],
            "slug": r["slug"],
            "league": "npb",
            "alumni": True,
            "role": r["role"],
            "position": "P" if is_pitcher else "",
            "npb_seasons": yrs,
            "first_year": yrs[0],
            "last_year": yrs[-1],
            "org": teams[-1] if teams else "",
            "bio": {**bio_from(html), "pos_zh": "投手" if is_pitcher else "野手"},
            "prev_season": {y: years[y] for y in sorted(years, reverse=True)},
            "career": {"一軍": total} if total else {},
        })
        added += 1
        print(f"  {r['zh']:6} {yrs[0]}–{yrs[-1]}({len(yrs)} 季)  {'、'.join(teams)}")

    fill_ops(blob["players"])
    localize_teams(blob["players"])
    fill_whip(blob["players"])
    blob["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    ALUMNI_PATH.write_text(json.dumps(blob, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"完成:新增 {added} 人、併入 {merged} 人,alumni.json 共 {len(blob['players'])} 人")


if __name__ == "__main__":
    main()
