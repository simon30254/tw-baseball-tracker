"""
20-80 球探評分(本站自算)
=========================
球探報告上那種 50/40/60 的數字。**真正的球探評分是人看出來的未來潛力**(工具、
身體、年齡曲線),而這裡算的是**已發生成績在聯盟裡的相對位置** —— 兩件事不一樣,
頁面上必須標明「本站依聯盟分布計算,非球探目測」。誠實標示反而是差異化:別人給
一個不知道怎麼來的數字,我們給算式與樣本數。

  評分 = 50 + 10 × z 分數,取 5 分級距,夾在 20–80
  常模 = 當季該層級的實際分布(逐年逐層級重算 —— 3A 的 50 分跟大聯盟的不是同一件事)

兩個刻意的設計:
- **用率值不用累積量**:李灝宇 364 打席對上合格門檻的 545 打數,用全壘打「支數」
  會被不公平低估
- **接觸與控球取負號**:三振率、四壞率越低越好,z 分數要反向

常模不用官方的 playerPool=qualified —— 投手那個門檻太嚴(3A 只剩 20 位,標準差
estimate 太吵),改抓全部再用自訂的最低出賽量篩。

輸出:public/data/grades.json
執行: python3 scripts/fetch_grades.py
"""

import json
import statistics as stats
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAYERS = ROOT / "public" / "data" / "players.json"
OUT = ROOT / "public" / "data" / "grades.json"
API = "https://statsapi.mlb.com/api/v1"
SEASON = datetime.now().year
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
SPORT = {"MLB": 1, "AAA": 11, "AA": 12, "High-A": 13, "A": 14, "Rookie": 16}
# 常模的最低量。20-80 制的「50 分」慣例上是指**聯盟平均的先發/固定班底**,
# 不是把所有上過場的人混在一起算,所以門檻訂在接近正規出賽量的水準。
MIN_PA, MIN_OUTS = 300, 150          # 常模:300 打席 / 50 局
# 被評分的球員自己也要有樣本。先前只篩常模沒篩球員,結果費爾柴德在新人聯盟打
# 幾場復健賽就拿到「力量 80、整體 80」—— 那種數字會讓整個評分失去可信度。
GRADE_PA, GRADE_OUTS = 100, 60       # 評分門檻:100 打席 / 20 局


def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30) as r:
            return json.load(r)
    except Exception:
        return None


def f(v):
    try:
        return float(v)
    except Exception:
        return None


def outs(ip):
    w, _, fr = str(ip or "0").partition(".")
    try:
        return int(w) * 3 + int(fr or 0)
    except Exception:
        return 0


def pick(s, *keys):
    """API 的欄位名與 players.json 的不一樣(plateAppearances vs pa),兩邊都要吃。"""
    for k in keys:
        v = f(s.get(k))
        if v is not None:
            return v
    return None


def bat_tools(s):
    pa = pick(s, "plateAppearances", "pa") or 0
    avg, ops, obp = pick(s, "avg"), pick(s, "ops"), pick(s, "obp")
    slg = pick(s, "slg")
    if slg is None and None not in (ops, obp):
        slg = ops - obp               # players.json 沒存 slg,由 OPS 減 OBP 還原
    bb, so = pick(s, "baseOnBalls", "bb"), pick(s, "strikeOuts", "so")
    if pa < 1 or None in (avg, slg, ops, bb, so):
        return None
    return {"打擊": avg, "力量": slg - avg, "選球": bb / pa,
            "接觸": -so / pa, "整體": ops}


def pit_tools(s):
    o = outs(s.get("inningsPitched") or s.get("ip"))
    so, bb = pick(s, "strikeOuts", "so"), pick(s, "baseOnBalls", "bb")
    hr = pick(s, "homeRuns", "hr")
    era, whip = pick(s, "era"), pick(s, "whip")
    if o < 1 or None in (so, bb, era, whip):
        return None
    ip = o / 3
    return {"三振": so * 9 / ip, "控球": -bb * 9 / ip, "壓制": -era,
            "被長打": -(hr or 0) * 9 / ip, "整體": -whip}


def norms(sid, group):
    """抓該層級全部球員,用最低出賽量篩出常模。"""
    d = get(f"{API}/stats?stats=season&group={group}&season={SEASON}&sportId={sid}&limit=2000&playerPool=all")
    if not d or not d.get("stats"):
        return None
    rows = []
    for x in d["stats"][0].get("splits") or []:
        s = x.get("stat") or {}
        if group == "hitting":
            if (pick(s, "plateAppearances", "pa") or 0) < MIN_PA:
                continue
            t = bat_tools(s)
        else:
            if outs(s.get("inningsPitched") or s.get("ip")) < MIN_OUTS:
                continue
            t = pit_tools(s)
        if t:
            rows.append(t)
    if len(rows) < 30:                 # 樣本太小算出來的標準差不可信
        return None
    return {k: {"mean": stats.mean([r[k] for r in rows]),
                "sd": stats.pstdev([r[k] for r in rows]) or 1e-9,
                "n": len(rows)} for k in rows[0]}


def grade(v, nm):
    z = (v - nm["mean"]) / nm["sd"]
    return max(20, min(80, round((50 + 10 * z) / 5) * 5))


def main():
    players = json.loads(PLAYERS.read_text(encoding="utf-8"))["players"]
    cache, out = {}, {}
    for p in players:
        if not str(p["id"]).isdigit():
            continue                   # 旅日/旅韓沒有可比的聯盟常模
        group = "pitching" if p.get("role") == "pitcher" else "hitting"
        for lv, s in (p.get("season_stats") or {}).items():
            sid = SPORT.get(lv)
            if not sid:
                continue
            # 樣本不足就不給評分 —— 寧可少一個層級,也不要給一個看起來很厲害的假數字
            if group == "hitting":
                sample = pick(s, "plateAppearances", "pa") or 0
                if sample < GRADE_PA:
                    continue
            else:
                sample = outs(s.get("inningsPitched") or s.get("ip"))
                if sample < GRADE_OUTS:
                    continue
            tools = pit_tools(s) if group == "pitching" else bat_tools(s)
            if not tools:
                continue
            key = (sid, group)
            if key not in cache:
                cache[key] = norms(sid, group)
                time.sleep(0.3)
            nm = cache[key]
            if not nm:
                continue
            out.setdefault(str(p["id"]), {}).setdefault(str(SEASON), {})[lv] = {
                "grades": {k: grade(v, nm[k]) for k, v in tools.items() if k in nm},
                "n": nm["整體"]["n"],          # 常模樣本數,頁面要標出來
                "sample": round(sample) if group == "hitting" else f"{sample//3}.{sample%3}",
                "unit": "打席" if group == "hitting" else "局",
            }
    if not out:
        print("算不出任何評分,保留既有檔案不覆寫")
        sys.exit(0)
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    n = sum(len(v) for y in out.values() for v in y.values())
    print(f"20-80 評分:{len(out)} 位球員、{n} 個層級 → {OUT.name}")


if __name__ == "__main__":
    main()
