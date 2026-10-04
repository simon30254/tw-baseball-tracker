"""
打者的球探素材(預期數據／冷熱區／噴灑分布／面對球種)
====================================================
站上原本的打者資料只有成績與分項,寫不出球探報告。這四個端點 MLB 官方公開、
各層級都有(實測 3A 也拿得到),而且全是事實數據,不碰任何人的文字判斷:

- expectedStatistics  xBA / xSLG / xwOBA —— 判斷「這份成績能不能持續」
- hotColdZones        好球帶 13 區各自的打擊率,官方已標好 hot/cold
- sprayChart          五個方向的分布,看得出拉打或推打傾向
- pitchArsenal        他面對過哪些球種、各佔多少、均速 —— 對手怎麼對付他

**不寫進 players.json**:首頁每次載入都會下載那個檔,而這些只有球探報告頁用得到
(跟 gamelogs 同樣的理由)。輸出 public/data/profiles.json,由 prerender 在 build 時讀。

執行: python3 scripts/fetch_batting_profile.py
"""

import json
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAYERS = ROOT / "public" / "data" / "players.json"
OUT = ROOT / "public" / "data" / "profiles.json"
API = "https://statsapi.mlb.com/api/v1"
SEASON = datetime.now().year
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
SPORT = {"MLB": 1, "AAA": 11, "AA": 12, "High-A": 13, "A": 14, "Rookie": 16}


def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=25) as r:
            return json.load(r)
    except Exception:
        return None


def splits(pid, stat, group, sid):
    d = get(f"{API}/people/{pid}/stats?stats={stat}&group={group}&season={SEASON}&sportId={sid}")
    if not d or not d.get("stats"):
        return []
    return d["stats"][0].get("splits") or []


def profile(pid, sid, group):
    out = {}
    x = splits(pid, "expectedStatistics", group, sid)
    if x:
        s = x[0].get("stat") or {}
        out["expected"] = {k: s.get(k) for k in ("avg", "slg", "woba", "wobaCon") if s.get(k)}
    z = splits(pid, "hotColdZones", group, sid)
    for blk in z:                     # 回傳多種統計的分區,取打擊率那組
        s = blk.get("stat") or {}
        if s.get("name") == "battingAverage" and s.get("zones"):
            out["zones"] = [{"z": q.get("zone"), "t": q.get("temp"), "v": q.get("value")}
                            for q in s["zones"]]
            break
    sp = splits(pid, "sprayChart", group, sid)
    if sp:
        out["spray"] = {k: v for k, v in (sp[0].get("stat") or {}).items() if isinstance(v, (int, float))}
    ar = splits(pid, "pitchArsenal", group, sid)
    if ar:
        rows = []
        for a in ar:
            s = a.get("stat") or {}
            t = (s.get("type") or {}).get("description")
            if not t or not s.get("percentage"):
                continue
            rows.append({"type": t, "pct": round(float(s["percentage"]) * 100, 1),
                         "mph": round(float(s["averageSpeed"]), 1) if s.get("averageSpeed") else None,
                         "n": s.get("count")})
        rows.sort(key=lambda r: -r["pct"])
        if rows:
            out["faced"] = rows[:8]
    return out


def main():
    players = json.loads(PLAYERS.read_text(encoding="utf-8"))["players"]
    try:
        store = json.loads(OUT.read_text(encoding="utf-8"))
    except Exception:
        store = {}
    got = 0
    for p in players:
        pid = str(p["id"])
        if not pid.isdigit():
            continue                      # 旅日/旅韓沒有這些端點
        group = "pitching" if p.get("role") == "pitcher" else "hitting"
        if group == "pitching":
            continue                      # 投手的球種已由 fetch_arsenal 處理
        by_level = {}
        for lv, st in (p.get("season_stats") or {}).items():
            sid = SPORT.get(lv)
            if not sid or not st.get("ab"):
                continue
            pr = profile(p["id"], sid, group)
            if pr:
                by_level[lv] = pr
            time.sleep(0.15)
        if by_level:
            store.setdefault(pid, {})[str(SEASON)] = by_level
            got += 1
    if not got:
        print("一位都沒抓到,保留既有檔案不覆寫")
        sys.exit(0)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(store, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"打者球探素材:{got} 位 → {OUT.name}({OUT.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
