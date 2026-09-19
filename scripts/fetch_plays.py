"""
精彩打席與 Statcast → public/data/plays.json
===========================================
MLB Stats API 的 /game/{pk}/playByPlay 有逐打席的結果與 Statcast(擊球初速、
仰角、飛行距離)。這支把站上旅美球員最近幾場的「值得做成圖卡」的打席抓出來,
供球員頁/表現頁產生可分享的 highlight 圖卡。

只收真正值得分享的:全壘打、三安以上的場次裡的安打、投手的勝投/救援場次。
逐打席全收會讓檔案爆掉,而且大部分打席(滾地出局)沒有分享價值。

**描述文字由結構化欄位自己組中文**(事件類型 + 局數 + 打點 + 比分),不翻譯
API 的英文句子 —— 同 fetch_transactions 的原則。

旅日/旅韓沒有等價的逐打席來源,那邊的圖卡只能用逐場數據(無 Statcast)。

執行:python3 scripts/fetch_plays.py [--days N]
"""

import json
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "public" / "data"
OUT = DATA / "plays.json"
API = "https://statsapi.mlb.com/api/v1"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
TW = timezone(timedelta(hours=8))
TIMEOUT = 30
DEFAULT_DAYS = 21
TEAM_ZH_PATH = ROOT / "scripts" / "team_zh.json"


def team_zh_map():
    try:
        d = json.loads(TEAM_ZH_PATH.read_text(encoding="utf-8"))
        return d.get("球隊", {}), d.get("球隊暱稱", {}), d.get("複合聯盟前綴", [])
    except Exception:
        return {}, {}, []


TEAMS, NICKS, PREFIXES = team_zh_map()


def zh_team(name):
    """查不到就留英文原名 —— 與 team_zh.json 的原則一致,不自己音譯。"""
    if not name:
        return ""
    if name in TEAMS:
        return TEAMS[name]
    for p in PREFIXES:
        if name.startswith(p + " ") and name[len(p) + 1:] in NICKS:
            return f"{p} {NICKS[name[len(p) + 1:]]}"
    return name

# 值得做成圖卡的事件。key 是 API 的 result.event
EVENT_ZH = {
    "Home Run": "全壘打", "Triple": "三壘安打", "Double": "二壘安打",
    "Single": "一壘安打", "Sac Fly": "高飛犧牲打", "Walk": "保送",
    "Strikeout": "三振", "Grand Slam": "滿貫全壘打",
}
BIG_EVENTS = {"Home Run", "Triple", "Grand Slam"}


def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=TIMEOUT) as r:
            return json.loads(r.read())
    except Exception:
        return None


def half_zh(h, inning):
    return f"{'上' if h == 'top' else '下'}{inning}局"


def describe(p, name, ev_zh, stat):
    """用結構化欄位組中文,不翻譯 API 的英文描述。"""
    res = p.get("result", {})
    rbi = res.get("rbi") or 0
    about = p.get("about", {})
    where = half_zh(about.get("halfInning"), about.get("inning"))
    if res.get("event") in ("Home Run", "Grand Slam"):
        n = stat.get("hr_no")
        tail = f"（本季第 {n} 轟）" if n else ""
        return f"{where}，{name}擊出{ev_zh}{tail}" + (f"，帶有 {rbi} 分打點" if rbi else "") + "。"
    if rbi:
        return f"{where}，{name}擊出{ev_zh}，帶有 {rbi} 分打點。"
    return f"{where}，{name}擊出{ev_zh}。"


def main():
    days = DEFAULT_DAYS
    if "--days" in sys.argv:
        days = int(sys.argv[sys.argv.index("--days") + 1])
    try:
        players = json.loads((DATA / "players.json").read_text(encoding="utf-8"))["players"]
    except Exception as e:
        print(f"讀不到 players.json:{e}")
        sys.exit(1)
    us = [p for p in players if str(p["id"]).isdigit()]
    today = datetime.now(TW).date()
    cutoff = (today - timedelta(days=days)).isoformat()

    out = []
    for i, p in enumerate(us, 1):
        pid = int(p["id"])
        grp = "pitching" if p["role"] == "pitcher" else "hitting"
        # gameLog 給 gamePk;逐層級查(一個球員可能同季跨層級)
        # 逐層級分開收 —— 轟數是「同層級第幾轟」,跨層級加總會把李灝宇的大聯盟
        # 第 10 轟寫成第 13 轟(他本季在 3A、1A 也打過)。
        by_level = {}
        for sid in (1, 11, 12, 13, 14, 16):
            r = get(f"{API}/people/{pid}/stats?stats=gameLog&group={grp}&season={today.year}&sportId={sid}")
            lv = []
            for st in (r or {}).get("stats", []):
                lv += st.get("splits", [])
            if lv:
                by_level[sid] = sorted(lv, key=lambda x: x.get("date") or "")
        logs = []
        hr_before = {}
        for lv in by_level.values():
            run = 0
            for g in lv:
                hr_before[id(g)] = run
                run += (g.get("stat", {}).get("homeRuns") or 0)
            logs += lv
        logs = [g for g in logs if (g.get("date") or "") >= cutoff]
        if not logs:
            continue
        for g in logs:
            hr_seen = hr_before[id(g)]
            s = g.get("stat", {})
            pk = (g.get("game") or {}).get("gamePk")
            if not pk:
                continue
            # 投手不逐個三振收 —— 一場 7 次三振就 7 張卡,全是雜訊。投手的圖卡
            # 用整場數據(勝投/好投)就夠,那個逐場資料本來就有,不需要 playByPlay。
            if grp != "hitting":
                continue
            worth = (s.get("homeRuns") or 0) or (s.get("hits") or 0) >= 3
            if not worth:
                continue
            pbp = get(f"{API}/game/{pk}/playByPlay")
            time.sleep(0.12)
            if not pbp:
                continue
            for play in pbp.get("allPlays", []):
                m = play.get("matchup", {})
                who = m.get("batter", {}).get("id")
                if who != pid:
                    continue
                res = play.get("result", {})
                ev = res.get("event")
                if ev not in BIG_EVENTS:
                    continue
                hd = next((e["hitData"] for e in play.get("playEvents", []) if e.get("hitData")), None)
                if ev in ("Home Run", "Grand Slam"):
                    hr_seen += 1
                about = play.get("about", {})
                out.append({
                    "id": str(pid), "name": p["name"], "slug": p.get("slug"),
                    "date": g.get("date"), "level": g.get("sport", {}).get("abbreviation", ""),
                    "opponent": zh_team((g.get("opponent") or {}).get("name", "")),
                    "home": bool(g.get("isHome")),
                    "event": ev, "event_zh": EVENT_ZH.get(ev, ev),
                    "inning": about.get("inning"), "half": about.get("halfInning"),
                    "rbi": res.get("rbi") or 0,
                    "away_score": res.get("awayScore"), "home_score": res.get("homeScore"),
                    "text": describe(play, p["name"], EVENT_ZH.get(ev, ev),
                                     {"hr_no": hr_seen if ev in ("Home Run", "Grand Slam") else None}),
                    # 距離偶爾是 None(小聯盟球場未裝設),有才寫。
                    # coordX/coordY 是 Gameday 的落點座標,用來畫球場示意圖 ——
                    # 本壘約在 (125.42, 203.5),X 往右增、Y 往外野方向遞減。
                    **({k: v for k, v in (("ev", hd.get("launchSpeed")),
                                          ("angle", hd.get("launchAngle")),
                                          ("dist", hd.get("totalDistance")),
                                          ("traj", hd.get("trajectory")),
                                          ("loc", hd.get("location")),
                                          ("cx", (hd.get("coordinates") or {}).get("coordX")),
                                          ("cy", (hd.get("coordinates") or {}).get("coordY")))
                        if v is not None} if hd else {}),
                })
        if i % 5 == 0:
            print(f"  已查 {i}/{len(us)}")

    out.sort(key=lambda x: (x.get("date") or "", x.get("inning") or 0), reverse=True)
    OUT.write_text(json.dumps(
        {"updated_at": datetime.now(TW).isoformat(timespec="seconds"), "plays": out},
        ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    withsc = sum(1 for x in out if x.get("ev"))
    print(f"完成:{OUT} — {len(out)} 個打席、{len({x['id'] for x in out})} 位球員"
          f"(其中 {withsc} 個有 Statcast)")


if __name__ == "__main__":
    main()
