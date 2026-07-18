"""
合併多來源 → public/data/players.json
=====================================
把旅美(mlb.json)與旅日(npb.json)合成前端唯一載入的 players.json。
任一來源缺失時,以另一來源為準(來源隔離:單一爬蟲失敗不會清空整站)。

執行: python3 scripts/build_players.py
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "public" / "data"
SOURCES = ["mlb.json", "npb.json", "kbo.json"]
ACCOLADES_PATH = ROOT / "scripts" / "accolades.json"
BIO_EXTRA_PATH = ROOT / "scripts" / "bio_extra.json"


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

    result = {"updated_at": updated_at, "season": season, "players": players}
    out = DATA / "players.json"
    out.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")
    from collections import Counter
    c = Counter(p.get("league") for p in players)
    mlb = c.get("mlb", 0) + c.get("milb", 0)
    print(f"完成:{out} — 共 {len(players)} 人(旅美 {mlb}、旅日 {c.get('npb', 0)}、旅韓 {c.get('kbo', 0)})")


if __name__ == "__main__":
    main()
