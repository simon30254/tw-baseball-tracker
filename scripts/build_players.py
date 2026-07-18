"""
合併多來源 → public/data/players.json
=====================================
把旅美(mlb.json)與旅日(npb.json)合成前端唯一載入的 players.json。
任一來源缺失時,以另一來源為準(來源隔離:單一爬蟲失敗不會清空整站)。

執行: python3 scripts/build_players.py
"""

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "public" / "data"
SOURCES = ["mlb.json", "npb.json", "kbo.json"]
ACCOLADES_PATH = ROOT / "scripts" / "accolades.json"
BIO_EXTRA_PATH = ROOT / "scripts" / "bio_extra.json"

LEVEL_RANK = {"MLB": 0, "AAA": 1, "AA": 2, "High-A": 3, "A": 4, "Rookie": 5, "一軍": 0, "二軍": 1}
LEVEL_ZH = {"MLB": "大聯盟", "AAA": "3A", "AA": "2A", "High-A": "高階1A", "A": "1A",
            "Rookie": "新人聯盟", "一軍": "一軍", "二軍": "二軍"}


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
        if nl != ol and nl in LEVEL_RANK and ol in LEVEL_RANK:
            up = LEVEL_RANK[nl] < LEVEL_RANK[ol]
            fresh.append({"date": today, "id": p["id"], "name": p["name"], "league": p["league"],
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

    # 近期異動(需在覆寫 players.json 前比對舊檔)
    moves = detect_moves(players)

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
