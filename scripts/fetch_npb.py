"""
旅日(NPB)台灣球員資料抓取腳本
==============================
資料來源:npb.jp 官方(需帶瀏覽器 UA;無官方 API,故爬 HTML)

流程:
1. 讀 scripts/npb_roster.json 手動名單(NPB 無法用出生地自動篩選)
2. 季賽累積:各球隊一軍/二軍成績頁(idb1/idp1/idb2/idp2),用全名比對
3. 逐場 game log:當月賽程頁列出所有 box score 連結 → 逐場 box 解析,
   在「我方球隊該半場」用姓氏比對球員(避開日本 林/張 同姓誤判),
   萃取投/打逐場數據
4. 讀入既有 npb.json 保留歷史,依 date+level 去重合併
5. 輸出 public/data/npb.json(與 MLB 相同 schema,league="npb")

執行: python3 scripts/fetch_npb.py
環境變數 NPB_BACKFILL_DAYS 可覆寫回補天數(首次無 npb.json 時預設 30,否則 5)
"""

import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta, date
from html.parser import HTMLParser
from pathlib import Path

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")
BASE = "https://npb.jp"
JST = timezone(timedelta(hours=9))
TW = timezone(timedelta(hours=8))
SEASON = datetime.now(JST).year

ROOT = Path(__file__).resolve().parent.parent
ROSTER_PATH = ROOT / "scripts" / "npb_roster.json"
OUTPUT_PATH = ROOT / "public" / "data" / "npb.json"

# team_code -> (中文隊名, 日文名比對片段)。日文片段用來在 box 內辨識半場所屬球隊。
TEAMS = {
    "e": ("樂天", "楽天"),
    "f": ("日本火腿", "日本ハム"),
    "l": ("西武", "西武"),
    "h": ("軟銀", "ソフトバンク"),
    "s": ("養樂多", "ヤクルト"),
    "g": ("巨人", "ジャイアンツ"),
    "b": ("歐力士", "オリックス"),
    "d": ("中日", "中日"),
    "t": ("阪神", "阪神"),
    "c": ("廣島", "広島"),
    "db": ("DeNA", "DeNA"),
    "m": ("羅德", "ロッテ"),
}


def get(url):
    """帶重試的 GET,回傳 HTML 文字。"""
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", "replace")
        except Exception as e:
            if attempt == 2:
                print(f"  [WARN] 放棄 {url}: {e}")
                return None
            time.sleep(2 * (attempt + 1))


def strip_tags(s):
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("&nbsp;", " ").replace("　", "").replace("&amp;", "&")
    return s.strip()


def norm_name(s):
    """正規化姓名:去標籤、去空白、去左右打標記(* ＊ ○ ◎ ◇ ＋ + # 等),便於比對。"""
    s = re.sub(r"\s+", "", strip_tags(s))
    return s.lstrip("*＊○◎◇＋+#△▲☆・")


def to_num(s, integer=True):
    s = (s or "").strip()
    if s in ("", "-", "----", ".---"):
        return 0 if integer else s
    try:
        return int(s) if integer else s
    except ValueError:
        return 0 if integer else s


# ---------------------------------------------------------------------------
# 季賽累積數據:球隊成績頁
# ---------------------------------------------------------------------------

class _TableExtractor(HTMLParser):
    """把 HTML 內所有(頂層)表格解析成 rows;正確處理巢狀表格(如投球回的巢狀 table):
    巢狀表格的文字會併入其所在儲存格,不會被誤當成外層的列/欄。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []          # 完成的頂層表格:[ [ [cell,...], ... ], ... ]
        self._tbl = []            # 表格堆疊(每層 = rows list)
        self._row = []            # 每層目前的 row(list 或 None)
        self._cell = []           # 儲存格文字緩衝堆疊

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._tbl.append([])
            self._row.append(None)
        elif tag == "tr" and self._row:
            self._row[-1] = []
        elif tag in ("td", "th"):
            self._cell.append([])

    def handle_data(self, data):
        if self._cell:
            self._cell[-1].append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th"):
            if self._cell:
                text = re.sub(r"\s+", " ", "".join(self._cell.pop())).strip()
                if self._row and self._row[-1] is not None:
                    self._row[-1].append(text)
                elif self._cell:
                    self._cell[-1].append(" " + text)
        elif tag == "tr":
            if self._row and self._row[-1] is not None and self._tbl:
                self._tbl[-1].append(self._row[-1])
                self._row[-1] = None
        elif tag == "table":
            if self._tbl:
                t = self._tbl.pop()
                if self._row:
                    self._row.pop()
                if self._tbl:  # 巢狀表格 → 文字併回外層儲存格
                    if self._cell:
                        self._cell[-1].append(" " + " ".join(c for r in t for c in r))
                else:
                    self.tables.append(t)


def _norm_header(h):
    return h.replace("　", "").replace(" ", "").strip()


def parse_stats_table(html, is_pitching):
    """把成績頁的表解析成 {全名正規化: {header: value}}。用 HTML parser 處理巢狀表格,
    對新版(thead)與舊球季(legacy 無 thead + 巢狀投球回)版面皆適用。"""
    out = {}
    p = _TableExtractor()
    try:
        p.feed(html)
    except Exception:
        return out
    for table in p.tables:
        # 找出表頭列(含已知欄位名)
        headers, hidx = None, -1
        for i, row in enumerate(table):
            joined = "".join(_norm_header(c) for c in row)
            if any(k in joined for k in ("登板", "試合", "防御率", "打率", "投球回")):
                headers = [_norm_header(c) for c in row]
                hidx = i
                break
        if not headers:
            continue
        # 名字欄:表頭為 選手/投手/打者 的那欄(legacy 版首欄是空的左右投記號欄)
        name_idx = 0
        for i, h in enumerate(headers):
            if h in ("選手", "投手", "打者"):
                name_idx = i
                break
        for row in table[hidx + 1:]:
            if len(row) <= name_idx or len(row) < len(headers):
                continue
            name = norm_name(row[name_idx])
            if not name or row[name_idx].replace("　", "").strip() in ("選手", "投手", "打者", "チーム計"):
                continue
            rec = dict(zip(headers, row[:len(headers)]))
            # 投球回:巢狀表格會被攤平成「39 2 3」(整局 分子 分母3)→ 39.2
            ip = rec.get("投球回")
            if ip:
                nums = re.findall(r"\d+", ip)
                if len(nums) >= 3 and nums[-1] == "3":
                    rec["投球回"] = f"{nums[0]}.{nums[1]}" if nums[1] != "0" else nums[0]
                elif nums:
                    rec["投球回"] = nums[0] if len(nums) == 1 else ".".join(nums[:2])
            out[name] = rec
    return out


def age_from(bd):
    """'2000.06.12' → 目前年齡。"""
    m = re.match(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", bd or "")
    if not m:
        return None
    y, mo, d = map(int, m.groups())
    t = datetime.now(JST).date()
    return t.year - y - ((t.month, t.day) < (mo, d))


def fetch_npb_bio(team_codes):
    """從各隊 rst 名冊頁抓 {正規化登録名: bio}。列:# 名 生日 身高 體重 投 打。"""
    bios = {}
    for tc in sorted(team_codes):
        html = get(f"{BASE}/bis/teams/rst_{tc}.html")
        time.sleep(0.3)
        if not html:
            continue
        for m in re.finditer(r"<tr[^>]*>(.*?)</tr>", html, re.S):
            row = m.group(1)
            link = re.search(r'players/\d+\.html">([^<]+)</a>', row)
            if not link:
                continue
            cells = [strip_tags(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
            if len(cells) < 7:
                continue
            bios[norm_name(link.group(1))] = {
                "age": age_from(cells[2]),
                "throws": cells[5], "bats": cells[6],
                "ht": to_num(cells[3]) or None, "wt": to_num(cells[4]) or None,
            }
    return bios


def fetch_season_stats(team_codes, season=SEASON):
    """回傳 {(team_code, level, 'pitching'/'hitting'): {name: rec}}。season 可指定(回追用)。"""
    cache = {}
    for tc in sorted(team_codes):
        for level, suffix in (("一軍", "1"), ("二軍", "2")):
            for grp, code in (("hitting", "idb"), ("pitching", "idp")):
                url = f"{BASE}/bis/{season}/stats/{code}{suffix}_{tc}.html"
                html = get(url)
                time.sleep(0.3)
                if not html:
                    continue
                cache[(tc, level, grp)] = parse_stats_table(html, grp == "pitching")
    return cache


def season_hitting(rec):
    obp = to_num(rec.get("出塁率"), False)
    slg = to_num(rec.get("長打率"), False)
    try:
        ops = f"{float(obp) + float(slg):.3f}".lstrip("0")  # OPS = OBP + SLG(npb 無直接欄位)
    except (ValueError, TypeError):
        ops = ""
    return {
        "g": to_num(rec.get("試合")), "pa": to_num(rec.get("打席")),
        "ab": to_num(rec.get("打数")),
        "h": to_num(rec.get("安打")), "hr": to_num(rec.get("本塁打")),
        "rbi": to_num(rec.get("打点")), "r": to_num(rec.get("得点")),
        "sb": to_num(rec.get("盗塁")), "bb": to_num(rec.get("四球")),
        "so": to_num(rec.get("三振")),
        "avg": to_num(rec.get("打率"), False), "obp": obp, "slg": slg, "ops": ops,
    }


def season_pitching(rec):
    return {
        "g": to_num(rec.get("登板")), "gs": 0,
        "w": to_num(rec.get("勝利")), "l": to_num(rec.get("敗北")),
        "sv": to_num(rec.get("セーブ")), "ip": to_num(rec.get("投球回"), False),
        "h": to_num(rec.get("安打")), "hr": to_num(rec.get("本塁打")),
        "tbf": to_num(rec.get("打者")),
        "so": to_num(rec.get("三振")), "bb": to_num(rec.get("四球")),
        "era": to_num(rec.get("防御率"), False), "whip": "",
    }


# ---------------------------------------------------------------------------
# 逐場 box score
# ---------------------------------------------------------------------------

def parse_ip(cell_html):
    """投球回欄含巢狀 table_inning,去標籤後兩格會黏在一起,兩種寫法都要認:
    ① <th>0</th><td>.1</td>   → "0.1"  → 0.1  (box score 實際用這種)
    ② <th>5</th><td>2/3</td>  → "52/3" → 5.2  (寫成三分之幾的版面)
    原本只認 ②,碰到 ① 會把小數整個丟掉 —— 孫易磊 2026/9/5 投 0.1 局
    被記成「0 局」,近況表同步後文章裡也就寫成 0 局。"""
    txt = re.sub(r"\s+", "", strip_tags(cell_html))
    m = re.fullmatch(r"(\d+)\.([12])", txt)          # ① 0.1
    if m:
        return f"{m.group(1)}.{m.group(2)}"
    m = re.fullmatch(r"(\d*)([12])/3", txt)           # ② 52/3 = 5 又 2/3
    if m:
        return f"{m.group(1) or '0'}.{m.group(2)}"
    m = re.match(r"(\d+)", txt)                       # 整數局數
    return m.group(1) if m else "0"


def cells_of(row_html):
    """回傳該 <tr> 依序的 (th|td) 原始 HTML 內容列表(保留巢狀,供 IP 解析)。"""
    return re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.S)


def parse_box_section(section_html, is_pitching):
    """解析 box 的一個半場(batting 或 pitching)表,回傳 [(name, statdict), ...]。
    以巢狀 table_inning 為切點還原被打斷的列。"""
    rows = []
    # 先把巢狀 table_inning 換成純文字 IP 佔位,避免打斷外層 <tr>
    def repl(m):
        # 巢狀表格攤平後會夾著換行(「0\n  .1」),佔位符要壓成單行,
        # 否則下面那個沒開 re.S 的 __IP__ 搜尋會整個對不到,IP 就靜靜變成 0。
        return "<td>__IP__" + re.sub(r"\s+", "", strip_tags(m.group(0))) + "__/IP__</td>"
    cleaned = re.sub(r'<td>\s*<table class="table_inning">.*?</table>\s*</td>',
                     repl, section_html, flags=re.S)
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", cleaned, re.S):
        link = re.search(r'players/(\d+)\.html">([^<]+)</a>', row)
        if not link:
            continue
        pid, name = link.group(1), norm_name(link.group(2))
        cells = [c for c in cells_of(row)]
        texts = [strip_tags(c) for c in cells]
        if is_pitching:
            # 欄位:決定, 名前, 投球数, 打者, 投球回(IP), 安打, 本塁打, 四球, 死球, 三振, 暴投, ボーク, 失点, 自責点
            ip = "0"
            ipm = re.search(r"__IP__(.*?)__/IP__", " ".join(cells), re.S)
            if ipm:
                ip = parse_ip(ipm.group(1))
            # 找到 name 之後的數值欄
            idx = next((i for i, t in enumerate(texts) if name in t), 1)
            after = texts[idx + 1:]
            # after = [投球数, 打者, IP佔位, 安打, 本塁打, 四球, 死球, 三振, 暴投, ボーク, 失点, 自責点]
            def a(i):
                return to_num(after[i]) if i < len(after) else 0
            decision = texts[idx - 1] if idx >= 1 else ""
            rows.append((pid, name, {
                "type": "pitching", "ip": ip,
                "h": a(3), "hr": a(4), "bb": a(5), "so": a(7),
                "r": a(10), "er": a(11),
                "win": "○" in decision, "loss": "●" in decision, "save": "Ｓ" in decision or "S" in decision,
                "started": None,  # 之後由半場第一位投手標記
            }))
        else:
            # 欄位:打順, (位置), 名前, 打数, 得点, 安打, 打点, 盗塁, 之後為逐打席結果
            idx = next((i for i, t in enumerate(texts) if name in t), 2)
            after = texts[idx + 1:]
            def a(i):
                return to_num(after[i]) if i < len(after) else 0
            outcomes = after[5:]  # 逐打席結果文字
            hr = sum(1 for t in outcomes if "本" in t)          # 全壘打
            bb = sum(1 for t in outcomes if "四球" in t or "敬遠" in t)  # 保送
            so = sum(1 for t in outcomes if "三振" in t)        # 三振
            rows.append((pid, name, {
                "type": "hitting", "ab": a(0), "r": a(1), "h": a(2),
                "rbi": a(3), "sb": a(4), "hr": hr, "bb": bb, "so": so, "avg": "",
            }))
    return rows


def section_team_code(html, section_id):
    """辨識某半場(table_top_*/table_bottom_*)所屬球隊 code:讀 div 前的日文隊名。"""
    j = html.find(f'id="{section_id}"')
    if j < 0:
        return None
    pre = strip_tags(html[max(0, j - 400):j])
    for tc, (_, jp) in TEAMS.items():
        if jp in pre:
            return tc
    return None


def parse_box(html):
    """回傳 {team_code: {'batting': [...], 'pitching': [...]}}。標記各半場先發投手。"""
    result = {}
    for pos in ("top", "bottom"):
        tc = section_team_code(html, f"table_{pos}_b") or section_team_code(html, f"table_{pos}_p")
        if not tc:
            continue
        entry = result.setdefault(tc, {"batting": [], "pitching": []})
        for grp, sid in (("batting", f"table_{pos}_b"), ("pitching", f"table_{pos}_p")):
            i = html.find(f'id="{sid}"')
            if i < 0:
                continue
            nxt = html.find('id="table_', i + 10)
            seg = html[i:nxt if nxt > 0 else i + 40000]
            parsed = parse_box_section(seg, grp == "pitching")
            if grp == "pitching" and parsed:
                parsed[0][2]["started"] = True
                for r in parsed[1:]:
                    r[2]["started"] = False
            entry[grp] = parsed
    return result


# ---------------------------------------------------------------------------
# 賽程 → box 連結
# ---------------------------------------------------------------------------

def month_box_links(month, farm):
    """回傳該月所有 box:[(date_str 'MMDD', home_code, away_code, url)]。"""
    if farm:
        url = f"{BASE}/farm/{SEASON}/schedule_{month:02d}_detail.html"
        pat = r"scores_farm/%d/(\d{4})/([a-z]+)-([a-z]+)-(\d+)/" % SEASON
    else:
        url = f"{BASE}/games/{SEASON}/schedule_{month:02d}_detail.html"
        pat = r"scores/%d/(\d{4})/([a-z]+)-([a-z]+)-(\d+)/" % SEASON
    html = get(url)
    if not html:
        return []
    seen, out = set(), []
    for mmdd, c1, c2, num in re.findall(pat, html):
        key = (mmdd, c1, c2, num)
        if key in seen:
            continue
        seen.add(key)
        sub = "scores_farm" if farm else "scores"
        box = f"{BASE}/{sub}/{SEASON}/{mmdd}/{c1}-{c2}-{num}/box.html"
        # 慣例:第一個 code = 主場(下半場), 第二個 = 客場(上半場);實際以 box 內隊名為準
        out.append((mmdd, c1, c2, box))
    return out


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 球員頁的生涯逐年表(/bis/players/{id}.html)
# ---------------------------------------------------------------------------
# 這份原本只有 fetch_npb_alumni 用來抓歷代前輩,但現役球員同樣需要「生涯合計」——
# 沒有的話生涯排行榜會漏掉宋家豪這種打了 8 季的人,榜就是錯的。移到這裡共用。
TEAM_ZH_CAREER = {
    "中日": "中日", "西武": "西武", "埼玉西武": "西武", "読売": "巨人", "南海": "南海",
    "ロッテ": "羅德", "千葉ロッテ": "羅德", "ヤクルト": "養樂多", "阪神": "阪神",
    "オリックス": "歐力士", "日本ハム": "日本火腿", "北海道日本ハム": "日本火腿",
    "ソフトバンク": "軟銀", "福岡ソフトバンク": "軟銀", "広島": "廣島", "横浜": "橫濱",
    "横浜ＤｅＮＡ": "DeNA", "横浜DeNA": "DeNA", "楽天": "樂天", "東北楽天": "樂天",
    "近鉄": "近鐵", "大阪近鉄": "近鐵", "阪急": "阪急", "日拓": "日拓",
    "太平洋": "太平洋", "クラウン": "皇冠", "大洋": "大洋", "ダイエー": "大榮",
    "福岡ダイエー": "大榮",
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
    p = _TableExtractor()
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
            team = TEAM_ZH_CAREER.get(raw_team, raw_team)
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


def main():
    roster = json.loads(ROSTER_PATH.read_text(encoding="utf-8"))["players"]
    team_codes = {p["team_code"] for p in roster}

    existing = {}
    if OUTPUT_PATH.exists():
        try:
            for p in json.loads(OUTPUT_PATH.read_text(encoding="utf-8")).get("players", []):
                existing[p["id"]] = p
        except Exception:
            existing = {}

    backfill = int(os.environ.get("NPB_BACKFILL_DAYS", "0")) or (30 if not existing else 5)
    today = datetime.now(JST).date()
    window = {(today - timedelta(days=d)).strftime("%m%d") for d in range(backfill + 1)}
    months = sorted({int(d[:2]) for d in window})
    print(f"NPB 抓取:{len(roster)} 人、回補 {backfill} 天、月份 {months}")

    # 1) 季賽累積 + 個人資料
    print("抓季賽累積 ...")
    stats = fetch_season_stats(team_codes)
    HISTORY_YEARS = 3  # 回追前幾年(parse_stats_table 用 HTML parser,可處理 legacy 舊球季版面)
    prev_stats_by_year = {}
    for y in range(SEASON - 1, SEASON - 1 - HISTORY_YEARS, -1):
        print(f"抓 {y} 回追累積 ...")
        prev_stats_by_year[y] = fetch_season_stats(team_codes, y)
    print("抓個人資料 ...")
    bios = fetch_npb_bio(team_codes)

    # 2) box 連結收集(一軍 + 二軍),過濾我方球隊 + 視窗內日期
    print("收集 box 連結 ...")
    boxes = []  # (mmdd, level, url)
    for m in months:
        for farm in (False, True):
            for mmdd, c1, c2, url in month_box_links(m, farm):
                if mmdd not in window:
                    continue
                if c1 not in team_codes and c2 not in team_codes:
                    continue
                boxes.append((mmdd, "二軍" if farm else "一軍", url))
    print(f"  命中 {len(boxes)} 場 box")

    # 3) 逐場解析,收集每位球員的 game log(以 pid 為主鍵累積)
    logs_by_pid = {}   # kanji -> list[gamelog]
    for i, (mmdd, level, url) in enumerate(boxes, 1):
        html = get(url)
        time.sleep(0.25)
        if not html or "試合中止" in html or "のため中止" in html:
            continue
        date_iso = f"{SEASON}-{mmdd[:2]}-{mmdd[2:]}"
        by_team = parse_box(html)
        for p in roster:
            tc = p["team_code"]
            if tc not in by_team:
                continue
            opp_code = next((k for k in by_team if k != tc), None)
            opponent = TEAMS.get(opp_code, ("", ""))[0] if opp_code else ""
            grp = "pitching" if p["role"] == "pitcher" else "batting"
            mk = norm_name(p.get("match") or p["kanji"])  # NPB 登録名(如林家正=リン),與 box 顯示一致
            for pid, name, stat in by_team[tc][grp]:
                if mk.startswith(name) or name.startswith(mk[:len(name)]):
                    g = dict(stat)
                    g["date"] = date_iso
                    g["level"] = level
                    g["opponent"] = opponent
                    logs_by_pid.setdefault(p["kanji"], []).append(g)
                    break
        if i % 10 == 0:
            print(f"  已解析 {i}/{len(boxes)}")

    # 4) 組裝球員,合併歷史
    players = []
    lost = []   # 逐場紀錄變少/主鍵對不上的球員,最後統一示警
    for p in roster:
        # 穩定主鍵。**不可從 npb_id 推導** —— 早期沒有 npb_id 的人用中文名當後綴,
        # 2026-09-07 補上 npb_id 時若跟著改 id,slugs/accolades/bio_extra/videos_cache
        # 這些用 id 當 key 的檔案會整批對不上,已上線的網址也會 404。
        # 所以後綴明確寫在名冊的 id_suffix,與 npb_id 是分開的兩件事。
        pid = f"npb{p.get('id_suffix') or p['npb_id'] or p['kanji']}"
        season_stats = {}
        key_name = norm_name(p.get("match") or p["kanji"])
        grp = "pitching" if p["role"] == "pitcher" else "hitting"
        for level in ("一軍", "二軍"):
            rec = (stats.get((p["team_code"], level, grp)) or {}).get(key_name)
            if rec:
                season_stats[level] = season_pitching(rec) if p["role"] == "pitcher" else season_hitting(rec)
        # 歷年回追:同隊假設(換隊者少見,抓不到則從缺)
        history = {}
        for y, ps in prev_stats_by_year.items():
            ys = {}
            for level in ("一軍", "二軍"):
                rec = (ps.get((p["team_code"], level, grp)) or {}).get(key_name)
                if rec:
                    d = season_pitching(rec) if p["role"] == "pitcher" else season_hitting(rec)
                    d["team"] = p["org_zh"]  # 同隊假設
                    ys[level] = d
            if ys:
                history[str(y)] = ys

        # 合併新舊 game log,依 date+level 去重;只保留本球季(換季自動汰除舊年)
        merged = {}
        old = existing.get(pid, {})
        if existing and pid not in existing:
            lost.append(f"{p['name_zh']} 主鍵 {pid} 不在既有 npb.json(id 規則被改過?)")
        for g in old.get("game_logs", []):
            if str(g.get("date", "")).startswith(str(SEASON)):
                merged[(g["date"], g.get("level"))] = g
        for g in logs_by_pid.get(p["kanji"], []):
            merged[(g["date"], g.get("level"))] = g
        game_logs = sorted(merged.values(), key=lambda g: g["date"], reverse=True)[:60]
        prev_n = len([g for g in old.get("game_logs", []) if str(g.get("date", "")).startswith(str(SEASON))])
        if len(game_logs) < prev_n:
            lost.append(f"{p['name_zh']} {prev_n}→{len(game_logs)}")

        # 目前層級:最近一場所屬;但若最近一場已逾 10 天(通常代表被下放/傷兵)
        # 且有二軍季賽紀錄,視為二軍(NPB 無乾淨的即時一二軍名冊可查)
        if game_logs:
            recent = game_logs[0]
            try:
                stale = (today - date.fromisoformat(recent["date"])).days > 10
            except ValueError:
                stale = False
            if stale and recent["level"] == "一軍" and season_stats.get("二軍"):
                cur_level = "二軍"
            else:
                cur_level = recent["level"]
        else:
            # 沒有任何逐場紀錄:沿用上一版判定的層級,**不可**退回名冊的 start_level。
            # start_level 是「開季時在哪」,拿它當現況會在逐場紀錄一旦消失時憑空翻轉層級,
            # 而層級翻轉會被 build_players.detect_moves 當成真的升降記進「最新動態」
            # (2026-09-07 徐若熙就這樣被寫出一筆不存在的「升上一軍」)。
            cur_level = (existing.get(pid) or {}).get("level") or p.get("start_level", "二軍")

        # 生涯合計:球員頁的「通算」列。季賽成績頁只有當年,沒有這個就無法排生涯榜
        career = None
        if p.get("npb_id"):
            html = get(f"https://npb.jp/bis/players/{p['npb_id']}.html")
            if html:
                _, career = parse_career(html, p["role"] == "pitcher")
            time.sleep(0.25)

        players.append({
            "id": pid,
            "name": p["name_zh"],
            "name_en": p["name_zh"],
            "league": "npb",
            "level": cur_level,
            "team": p["org_zh"],
            "org": p["org_zh"],
            "position": "P" if p["role"] == "pitcher" else "",
            "role": p["role"],
            "status": "",
            "status_note": "",
            "bio": {
                **bios.get(key_name, {}),
                "pos_zh": "投手" if p["role"] == "pitcher" else "野手",
            },
            "season_stats": season_stats,
            "game_logs": game_logs,
            **({"prev_season": history} if history else {}),
            **({"career": {"一軍": career}} if career else {}),
        })
        print(f"  {p['name_zh']}: {cur_level}、季賽層級 {list(season_stats)}、逐場 {len(game_logs)}、回追年 {sorted(history)}")

    # 逐場紀錄只增不減(除非換季)。變少代表主鍵漂掉或來源解析壞了 ——
    # 那會連帶讓層級誤判、寫出假的升降動態,所以寧可不覆寫,線上維持上次的好資料。
    if lost:
        print("逐場紀錄異常減少,不覆寫 npb.json:")
        for line in lost:
            print(f"  - {line}")
        sys.exit(1)

    result = {
        "updated_at": datetime.now(TW).isoformat(timespec="seconds"),
        "season": SEASON,
        "players": players,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                           encoding="utf-8")
    kb = OUTPUT_PATH.stat().st_size / 1024
    print(f"完成:{OUTPUT_PATH} ({kb:.0f} KB, {len(players)} 人)")


if __name__ == "__main__":
    main()
