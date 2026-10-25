"""
合併多來源 → public/data/players.json
=====================================
把旅美(mlb.json)與旅日(npb.json)合成前端唯一載入的 players.json。
任一來源缺失時,以另一來源為準(來源隔離:單一爬蟲失敗不會清空整站)。

執行: python3 scripts/build_players.py
"""

import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "public" / "data"
SOURCES = ["mlb.json", "npb.json", "kbo.json"]
ACCOLADES_PATH = ROOT / "scripts" / "accolades.json"
BIO_EXTRA_PATH = ROOT / "scripts" / "bio_extra.json"
SLUGS_PATH = ROOT / "scripts" / "slugs.json"
CONTENT_PATH = ROOT / "scripts" / "player_content.json"
ARTICLES_AUTO_PATH = ROOT / "scripts" / "articles_auto.json"
VIDEOS_CACHE_PATH = ROOT / "scripts" / "videos_cache.json"

LEVEL_RANK = {"MLB": 0, "AAA": 1, "AA": 2, "High-A": 3, "A": 4, "Rookie": 5, "一軍": 0, "二軍": 1}
LEVEL_ZH = {"MLB": "大聯盟", "AAA": "3A", "AA": "2A", "High-A": "高階1A", "A": "1A",
            "Rookie": "新人聯盟", "一軍": "一軍", "二軍": "二軍"}


def slugify(name_en):
    """Kai-Wei Teng → kai-wei-teng。非 ASCII 一律回 None,交給 slugs.json 人工指定。"""
    s = re.sub(r"[^a-z0-9]+", "-", (name_en or "").lower()).strip("-")
    return s or None


def assign_slugs(players):
    """給每位球員一個穩定的網址 slug,供 prerender 產生 /player/{slug}/。"""
    manual = {}
    if SLUGS_PATH.exists():
        manual = {k: v for k, v in json.loads(SLUGS_PATH.read_text(encoding="utf-8")).items()
                  if not k.startswith("_")}
    seen, missing = {}, []
    for p in players:
        # 值可以是字串(只給 slug),也可以是 {slug, roman};roman 用在 slug 拆不出
        # 正確英文名時(複姓:古林睿煬 jui-yang-ku-lin → 預設會拆成 Jui-Yang-Ku Lin)
        m = manual.get(str(p["id"]))
        if isinstance(m, dict):
            slug = m.get("slug")
            if m.get("roman"):
                p["roman"] = m["roman"]
        else:
            slug = m
        slug = slug or slugify(p.get("name_en"))
        if not slug:
            missing.append(f'{p["name"]}(id={p["id"]})')
            continue
        if slug in seen:
            # slug 撞名會讓兩個球員蓋到同一個網址,必須人工在 slugs.json 排解
            print(f'  [錯誤] slug 重複:{slug} — {seen[slug]} 與 {p["name"]}', file=sys.stderr)
            missing.append(f'{p["name"]}(slug 撞名 {slug})')
            continue
        seen[slug] = p["name"]
        p["slug"] = slug
    if missing:
        print("  [錯誤] 以下球員無法決定 slug,請在 scripts/slugs.json 補上:", file=sys.stderr)
        for m in missing:
            print(f"    - {m}", file=sys.stderr)
        sys.exit(1)
    print(f"產生 slug:{len(seen)} 人")


def sanity_check(players):
    """把關:疑似資料異常(爬蟲靜默失敗、寫出空資料)就中止,避免覆蓋掉好的 players.json。
    失敗會讓 workflow 紅燈通知;因未覆寫舊檔,線上維持上次的好資料。"""
    from collections import Counter
    c = Counter(p.get("league") for p in players)
    mlb, npb, kbo, total = c.get("mlb", 0) + c.get("milb", 0), c.get("npb", 0), c.get("kbo", 0), len(players)

    # 以上一版 players.json 作基準(偵測相對暴跌;比絕對門檻更耐名單變動)
    prev_total = prev_mlb = prev_npb = 0
    out = DATA / "players.json"
    if out.exists():
        try:
            old = json.loads(out.read_text(encoding="utf-8")).get("players", [])
            pc = Counter(p.get("league") for p in old)
            prev_mlb, prev_npb, prev_total = pc.get("mlb", 0) + pc.get("milb", 0), pc.get("npb", 0), len(old)
        except Exception:
            pass

    problems = []
    if total < 25:
        problems.append(f"總人數過低:{total}(<25)")
    if prev_mlb >= 10 and mlb == 0:
        problems.append(f"旅美資料全空(昨日 {prev_mlb} 人)— fetch_data 可能失敗")
    if prev_npb >= 5 and npb == 0:
        problems.append(f"旅日資料全空(昨日 {prev_npb} 人)— fetch_npb 可能失敗")
    if prev_total > 0 and total < prev_total * 0.7:
        problems.append(f"總人數較昨日暴跌:{prev_total} → {total}")

    if problems:
        print("[SANITY 失敗] 疑似資料異常,中止(不覆寫 players.json):", file=sys.stderr)
        for p in problems:
            print(f"    - {p}", file=sys.stderr)
        sys.exit(1)
    print(f"Sanity OK:{total} 人(旅美 {mlb}/旅日 {npb}/旅韓 {kbo})")


# ---------------------------------------------------------------------------
# 對手隊名中譯
# ---------------------------------------------------------------------------
# MLB/MiLB 的 game_log 對手是英文原名(Chicago White Sox),站上其他文字都是中文,
# 夾在裡面很突兀。在這裡一次譯完,前端、預渲染、clutchgtime 同步就都拿到中文,
# 不必各自帶一份對照表。查不到的維持英文原名 —— 那是刻意的,顯眼才好補,
# 硬音譯反而會生出沒人用的隊名。
def load_team_zh():
    try:
        cfg = json.loads((ROOT / "scripts" / "team_zh.json").read_text(encoding="utf-8"))
    except Exception:
        return {}, [], {}
    return (cfg.get("球隊", {}), cfg.get("複合聯盟前綴", []), cfg.get("球隊暱稱", {}),
            cfg.get("小聯盟附屬球隊", {}), set(cfg.get("保留原文", [])))


def localize_teams(players, season=None):
    """隊名中譯。season 是「當年」—— 小聯盟附屬球團的母隊會隨球季變,查表要帶年份。
    (fetch_npb_alumni.py 也匯入這支,所以 season 給預設值保持相容;日職沒有附屬
    球團的問題,不帶年份不影響。)"""
    teams, prefixes, nicks, farm, keep_en = load_team_zh()
    if not teams:
        return

    def farm_zh(name, year):
        """小聯盟附屬球團 →「母隊 層級」。值可能是字串,也可能是「年份→名稱」。

        母隊關係會隨球季變(Lansing Lugnuts 2005 是藍鳥、2024 起是運動家),所以
        逐年的那種一定要帶年份查;沒有年份、或那一年查不到(往前後五年也沒有)就
        回 None,讓呼叫端留著英文原名 —— 寧可顯眼好補,也不要寫出錯的母隊。
        """
        v = farm.get(name)
        if v is None:
            return None
        if isinstance(v, str):
            return v
        if not year:
            return None
        y = str(year)
        if y in v:
            return v[y]
        try:
            yi = int(y)
        except ValueError:
            return None
        for d in range(1, 6):
            for yy in (str(yi - d), str(yi + d)):
                if yy in v:
                    return v[yy]
        return None

    # 片假名也要認 —— 戰前日職球團 セネタース(東京參議員隊)就是這樣寫,
    # 原本只認拉丁字母,羅道厚的頁面整排顯示「セネタース」。
    NEED_ZH = r"[A-Za-z\u30A1-\u30FA]"

    def zh(name, year=None):
        if not name or not re.search(NEED_ZH, name):
            return None
        if name in teams:
            return teams[name]
        f = farm_zh(name, year)
        if f:
            return f
        # 新人聯盟以母隊命名(ACL White Sox)→「ACL 白襪」,與大聯盟母隊區分。
        # 分組隊(ACL Giants Orange)暱稱後面還跟著分組名,所以由長到短逐段試。
        head, _, rest = name.partition(" ")
        if head in prefixes and rest:
            toks = rest.split(" ")
            for n in range(len(toks), 0, -1):
                cand = " ".join(toks[:n])
                if cand in nicks:
                    return f"{head} {nicks[cand]}"
        return None

    hit = miss = 0
    unknown = set()

    def swap(obj, key, year=None):
        nonlocal hit, miss
        v = obj.get(key)
        if not v:
            return
        # 去重要在「有沒有東西可譯」之前做 —— 值可能已經全是中文(alumni.json 的
        # 中譯是寫檔時就套好的),但「白襪 新人聯盟、白襪 新人聯盟」這種重複還在,
        # 原本卡在下面那行提前 return 就永遠修不到。
        if "、" in v:
            ps = [x.strip() for x in v.split("、") if x.strip()]
            dd = list(dict.fromkeys(ps))
            if len(dd) != len(ps):
                v = "、".join(dd)
                obj[key] = v
        if not re.search(NEED_ZH, v):
            return
        # 球季中換隊的人這一欄是「A、B」。原本整串拿去查表,當然查不到,於是兩隊
        # 都留英文 —— 王維中 2019 大聯盟那列印出「Oakland Athletics、Pittsburgh
        # Pirates」,兩隊其實都在對照表裡;同一頁上 2017 年卻是中文的「釀酒人」。
        # 所以要逐隊查、逐隊換,查不到的那一隊才留英文。
        parts = [x.strip() for x in v.split("、") if x.strip()]
        out, any_hit = [], False
        for x in parts:
            if not re.search(NEED_ZH, x):
                out.append(x)
                continue
            t = zh(x, year)
            if t:
                out.append(t)
                hit += 1
                any_hit = True
            else:
                out.append(x)
                # ACL/FCL/DSL 開頭、後面已經是中文的(「ACL 白襪」)是**已經處理好**的 ——
                # 那個前綴是刻意保留的聯盟標記(見 team_zh.json 的複合聯盟說明),
                # 不是漏譯。原本算進 miss,於是那行警告永遠掛著 31 處 9 隊,
                # 真的有漏譯時反而看不出來。
                head, _, rest = x.partition(" ")
                if head in prefixes and rest and not re.search(r"[A-Za-z]", rest):
                    continue
                if x in keep_en:        # 已確認保留原文(DeNA),不算漏譯
                    continue
                miss += 1
                unknown.add(x)
        # 換隊字串「A、B」兩邊可能是同一個名稱(ACL White Sox 與 AZL White Sox 都會
        # 映成同一級的白襪),去重後才不會印出「ACL 皇家、ACL 皇家」。
        # **不論這次有沒有換到譯名都要做** —— alumni.json 的值早就是中文了,
        # 查表不會命中,但重複還在。
        seen_p, uniq = set(), []
        for x in out:
            if x in seen_p:
                continue
            seen_p.add(x)
            uniq.append(x)
        if any_hit or len(uniq) != len(out):
            obj[key] = "、".join(uniq)

    for p in players:
        # 球員自己的所屬球隊也要譯 —— 漏掉的話介紹文會出現「效力於Athletics3A」
        swap(p, "org", season)
        swap(p, "team", season)
        for g in p.get("game_logs") or []:
            swap(g, "opponent", str(g.get("date", ""))[:4])
        # 球季表的「效力 ○○」也要譯,不然數據表下方會冒出一排英文隊名。
        # 年份要帶對:歷年用那一年的鍵、季累積用當年;career 是跨年合計,沒有單一年份,
        # 所以逐年的附屬球團在那裡查不到會留英文(目前站上沒有這種情形)。
        for s in (p.get("season_stats") or {}).values():
            if isinstance(s, dict):
                swap(s, "team", season)
        for yr, by_level in (p.get("prev_season") or {}).items():
            for s in (by_level or {}).values():
                if isinstance(s, dict):
                    swap(s, "team", yr)
        for s in (p.get("career") or {}).values():
            if isinstance(s, dict):
                swap(s, "team")
    print(f"隊名中譯:{hit} 處;仍為英文 {miss} 處({len(unknown)} 隊,可補 scripts/team_zh.json)")
    if unknown:
        print("  未對應:" + "、".join(sorted(unknown)))


def fill_whip(players):
    """NPB 資料源不提供 WHIP,用 (被安 + 保送) ÷ 局數 補算。

    npb.py 的 bb 取自「四球」欄,死球是另一欄沒被算進去,所以符合 WHIP 定義。
    公式拿旅美 28 筆官方 WHIP 對照過,零誤差。補完後不只戰績摘要,累積數據表
    與投手排行榜的 WHIP 欄位也一起有值(原本旅日那欄整排是空的)。
    """
    filled = 0
    for p in players:
        if p.get("role") != "pitcher":
            continue
        buckets = [p.get("season_stats") or {}, p.get("career") or {}]
        buckets += list((p.get("prev_season") or {}).values())
        for by_level in buckets:
            for s in (by_level or {}).values():
                if not isinstance(s, dict) or s.get("whip") or not s.get("ip"):
                    continue
                parts = str(s["ip"]).split(".")
                try:
                    outs = int(parts[0]) * 3 + (int(parts[1]) if len(parts) > 1 else 0)
                except ValueError:
                    continue
                if not outs:
                    continue
                s["whip"] = f"{(s.get('h', 0) + s.get('bb', 0)) / (outs / 3):.2f}"
                filled += 1
    if filled:
        print(f"補算 WHIP:{filled} 筆")


def detect_moves(players):
    """比對上一版 players.json 偵測升降/傷兵異動,累積寫入 moves.json,回傳近期異動列表。"""
    out = DATA / "players.json"
    old = {}
    if out.exists():
        try:
            for p in json.loads(out.read_text(encoding="utf-8")).get("players", []):
                old[p["id"]] = {"level": p.get("level"), "status": p.get("status", "")}
        except Exception:
            pass
    today = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    fresh = []
    for p in players:
        o = old.get(p["id"])
        if not o:
            continue
        nl, ol = p.get("level"), o["level"]
        # 層級是推出來的就不生異動。「異動」是有日期的事實聲明,而「逾 10 天沒出賽
        # 所以大概被下放了」是沒有證據的推論,撐不起那個日期 —— 徐若熙 2026-10-16
        # 被寫成「下放二軍」,實際上他 10/01 登錄一軍、CS 決勝輪在登錄名單裡待命、
        # 10/22 入選日本大賽 40 人名單,從沒被下放;而且就算方向猜對(林安可 9/24
        # 真的被抹消登錄),這裡的日期用的是「偵測到的那天」,推定規則要等 11 天才
        # 觸發,所以一律晚十天以上。層級照舊顯示,只是不再冒充成一筆有日期的異動。
        if nl != ol and not p.get("level_stale") and nl in LEVEL_RANK and ol in LEVEL_RANK:
            up = LEVEL_RANK[nl] < LEVEL_RANK[ol]
            # 日期用「那個層級最近一場出賽」,不是「偵測到的今天」。異動是看到他在新
            # 層級出賽才認定的,所以那場比賽的日期就是能講的最早日期,比晚一天的
            # 偵測日準:徐若熙 10/01 登錄一軍、10/01 就在一軍出賽,原本寫成 10/02;
            # 陳睦衡 9/25 一軍初登板,原本寫成 9/26。抓不到對應比賽才退回今天。
            # 要的是「切換到新層級之後的第一場」,不是「新層級最近一場」。逐場是新到舊
            # 排的,所以從頭掃、一路覆寫,遇到舊層級就停 —— 停下來前最後記到的那場就是
            # 切換後的首戰(徐若熙:10/05→10/01→遇到 9/25 二軍停,取 10/01)。
            at = None
            for g in (p.get("game_logs") or []):
                if g.get("level") == nl:
                    at = g["date"]
                elif g.get("level") == ol:
                    break
            at = min(at or today, today)
            fresh.append({"date": at, "id": p["id"], "name": p["name"], "league": p["league"],
                          "type": "promote" if up else "demote",
                          "text": f"{'升上' if up else '下放'}{LEVEL_ZH.get(nl, nl)}"})
        ns, os_ = p.get("status", ""), o["status"]
        if ns != os_:
            if ns == "傷兵":
                fresh.append({"date": today, "id": p["id"], "name": p["name"], "league": p["league"],
                              "type": "il", "text": "進傷兵名單"})
            elif os_ == "傷兵":
                fresh.append({"date": today, "id": p["id"], "name": p["name"], "league": p["league"],
                              "type": "return", "text": "移出傷兵名單"})

    moves_path = DATA / "moves.json"
    moves = []
    if moves_path.exists():
        try:
            moves = json.loads(moves_path.read_text(encoding="utf-8"))
        except Exception:
            moves = []
    moves = fresh + moves
    seen, dedup = set(), []
    for m in moves:
        k = (m["date"], m["id"], m["type"])
        if k in seen:
            continue
        seen.add(k)
        dedup.append(m)
    cutoff = (date.today() - timedelta(days=30)).isoformat()
    dedup = [m for m in dedup if m["date"] >= cutoff][:60]
    moves_path.write_text(json.dumps(dedup, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    if fresh:
        print(f"偵測異動:{len(fresh)} 筆")
    return dedup


def main():
    players = []
    updated_at = ""
    season = None
    for name in SOURCES:
        path = DATA / name
        if not path.exists():
            print(f"  [略過] 找不到 {name}")
            continue
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  [略過] {name} 解析失敗: {e}")
            continue
        players.extend(d.get("players", []))
        if d.get("updated_at", "") > updated_at:
            updated_at = d["updated_at"]
        season = season or d.get("season")

    # 把關(在覆寫 players.json 前;失敗即中止,線上維持上次好資料)
    sanity_check(players)

    assign_slugs(players)

    # 掛上人工評比/榮譽
    accolades = {}
    if ACCOLADES_PATH.exists():
        accolades = json.loads(ACCOLADES_PATH.read_text(encoding="utf-8"))
    n_acc = 0
    for p in players:
        a = accolades.get(str(p["id"]))
        if a and a.get("list"):
            p["accolades"] = {"badge": a.get("badge", ""), "list": a["list"]}
            n_acc += 1
    print(f"掛上評比:{n_acc} 人")

    # 掛上個人資料補充(球速等,覆蓋/補足自動抓的 bio)
    bio_extra = {}
    if BIO_EXTRA_PATH.exists():
        bio_extra = json.loads(BIO_EXTRA_PATH.read_text(encoding="utf-8"))
    n_velo = 0
    for p in players:
        extra = bio_extra.get(str(p["id"]))
        if extra:
            bio = dict(p.get("bio") or {})
            bio.update({k: v for k, v in extra.items() if not k.startswith("_")})
            p["bio"] = bio
            if extra.get("velo"):
                n_velo += 1
    print(f"掛上球速:{n_velo} 人")

    # 掛上相關內容(報導/延伸問答)= 手動策展(優先)+ 自動拉取(fetch_articles)合併
    manual = {}
    if CONTENT_PATH.exists():
        manual = {k: v for k, v in json.loads(CONTENT_PATH.read_text(encoding="utf-8")).items()
                  if not k.startswith("_")}
    auto = {}
    if ARTICLES_AUTO_PATH.exists():
        try:
            auto = json.loads(ARTICLES_AUTO_PATH.read_text(encoding="utf-8"))
        except Exception:
            auto = {}
    n_content = 0
    for p in players:
        pid = str(p["id"])
        m, a = manual.get(pid, {}), auto.get(pid, {})
        # 文章:手動在前、自動在後,依 url 去重
        articles, seen = [], set()
        for src in (m.get("articles", []), a.get("articles", [])):
            for art in src:
                if art.get("url") and art["url"] not in seen:
                    seen.add(art["url"])
                    articles.append(art)
        qa = m.get("qa", []) + a.get("qa", [])
        if articles or qa:
            p["content"] = {"articles": articles, "qa": qa}
            n_content += 1
    print(f"掛上相關內容:{n_content} 人")

    # 掛上亮點精華影片(fetch_videos 抓的 YouTube 影片,鍵為 球員id:日期)
    videos = {}
    if VIDEOS_CACHE_PATH.exists():
        try:
            videos = json.loads(VIDEOS_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            videos = {}
    n_video = 0
    for p in players:
        pid = str(p["id"])
        for g in p.get("game_logs", []):
            v = videos.get(f"{pid}:{g.get('date')}")
            if v and v.get("id"):
                g["video"] = {"id": v["id"], "title": v.get("title")}
                if v.get("published"):   # 表現頁 VideoObject 的 uploadDate
                    g["video"]["published"] = v["published"]
                n_video += 1
    print(f"掛上精華影片:{n_video} 場")

    # 投手球種(fetch_arsenal 產生;只有有測速追蹤的層級才有)
    try:
        arsenal = json.loads((ROOT / "scripts" / "arsenal_cache.json").read_text(encoding="utf-8"))
    except Exception:
        arsenal = {}
    n_ars = 0
    for pl in players:
        a = arsenal.get(str(pl["id"]))
        if a and a.get("pitches"):
            pl.setdefault("bio", {})["pitches"] = a["pitches"]
            # 本季沒測速資料時 fetch_arsenal 會退回前一兩季;年份要跟著走,頁面才不會寫成「本季」
            pl["bio"]["pitches_season"] = a.get("season")
            n_ars += 1
    if arsenal:
        print(f"掛上投手球種:{n_ars} 人")

    # 分項數據(fetch_splits 產生;連小聯盟都有)
    try:
        splits_cache = json.loads((ROOT / "scripts" / "splits_cache.json").read_text(encoding="utf-8"))
    except Exception:
        splits_cache = {}
    n_sp = 0
    for pl in players:
        slot = splits_cache.get(str(pl["id"]))
        if not slot:
            continue
        for level, sp in slot.items():
            st = (pl.get("season_stats") or {}).get(level)
            if st:
                st["splits"] = sp
                n_sp += 1
    if splits_cache:
        print(f"掛上分項數據:{n_sp} 個層級")

    # 進階數據(fetch_advanced 產生;只有大聯盟層級有)
    try:
        adv_cache = json.loads((ROOT / "scripts" / "advanced_cache.json").read_text(encoding="utf-8"))
    except Exception:
        adv_cache = {}
    n_adv = 0
    for pl in players:
        slot = adv_cache.get(str(pl["id"]))
        if not slot:
            continue
        for y, adv in slot.items():
            if int(y) == season and (pl.get("season_stats") or {}).get("MLB"):
                pl["season_stats"]["MLB"]["adv"] = adv
            lv = (pl.get("prev_season") or {}).get(y, {}).get("MLB")
            if lv:
                lv["adv"] = adv
        wars = [a["war"] for a in slot.values() if a.get("war") is not None]
        if wars and (pl.get("career") or {}).get("MLB"):
            pl["career"]["MLB"]["war"] = round(sum(wars), 1)
        n_adv += 1
    if adv_cache:
        print(f"掛上進階數據:{n_adv} 人")

    localize_teams(players, season)
    fill_whip(players)

    # 近期異動(需在覆寫 players.json 前比對舊檔)
    moves = detect_moves(players)

    # 球員頁「最新動態」時間軸要用:把異動掛到各球員身上。
    # 首頁側欄吃的是頂層 moves(跨球員),球員頁與預渲染吃的是這裡的 p["moves"]。
    by_player = {}
    for m in moves:
        by_player.setdefault(str(m["id"]), []).append(
            {"date": m["date"], "type": m["type"], "text": m["text"]})
    n_move = 0
    for p in players:
        ms = by_player.get(str(p["id"]))
        if ms:
            p["moves"] = ms
            n_move += 1
    print(f"掛上近期異動:{n_move} 人")

    # 一致性檢查:有本季出賽紀錄、季累積卻是空的 —— 這是上游抓取失敗把好資料
    # 清空的徵兆,不是正常狀態。2026-10-21 起 npb.jp 連三天逾時,12 位日職球員
    # 就是這樣變成「本季尚無出賽紀錄。最近一場出賽在 10月16日」—— 兩句在同一段
    # meta description 裡互相矛盾,而那是 Google 直接拿去當搜尋摘要的句子,靜默
    # 壞了三天都沒被發現。抓取端已各自改成失敗時沿用既有資料,這裡是最後一道網:
    # 不論哪個聯盟、哪支腳本出問題都會在 Actions 執行摘要上示警。
    # 只示警不中斷 —— 中斷會讓整條流程停住、線上資料跟著停更,那更糟。
    contradict = [
        p["name"] for p in players
        if not p.get("season_stats")
        and any(str(g.get("date", "")).startswith(str(season)) for g in (p.get("game_logs") or []))
    ]
    if contradict:
        print(f"⚠ 有本季出賽但季累積為空:{len(contradict)} 人 — {'、'.join(contradict)}")
        print(f"::warning title=季累積與逐場紀錄矛盾::{len(contradict)} 位球員有 {season} 球季的逐場"
              f"紀錄,季累積卻是空的({'、'.join(contradict[:8])}),球員頁會寫成「本季尚無出賽紀錄」。"
              f"多半是上游來源抓取失敗,請查該聯盟的抓取日誌。")

    result = {"updated_at": updated_at, "season": season, "players": players, "moves": moves}
    out = DATA / "players.json"
    out.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")
    from collections import Counter
    c = Counter(p.get("league") for p in players)
    mlb = c.get("mlb", 0) + c.get("milb", 0)
    print(f"完成:{out} — 共 {len(players)} 人(旅美 {mlb}、旅日 {c.get('npb', 0)}、旅韓 {c.get('kbo', 0)})")


if __name__ == "__main__":
    main()
