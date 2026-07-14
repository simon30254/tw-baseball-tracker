# 旅外戰報|台灣棒球員追蹤

每日自動追蹤旅美台灣棒球員(MLB + 小聯盟全層級)的出賽表現與球季數據。
零成本架構:GitHub Actions 抓資料 → 靜態 JSON → React 前端 → Cloudflare Pages 免費託管。

## 架構

```
GitHub Actions(每天台灣時間 06:00)
  └─ scripts/fetch_data.py
       ├─ 掃描 MLB Stats API 各層級名單,自動找出台灣球員(birthCountry)
       ├─ 抓每人球季數據 + 逐場 game log(含季中升降的跨層級紀錄)
       └─ 寫入 public/data/players.json 並 commit
            └─ push 觸發 Cloudflare Pages 自動重新部署
```

不需要伺服器、不需要資料庫、不需要 API 金鑰。

## 部署步驟

### 1. 推上 GitHub

```bash
git init && git add -A && git commit -m "init"
# 在 GitHub 建立 repo 後:
git remote add origin https://github.com/<你的帳號>/tw-baseball-tracker.git
git push -u origin main
```

### 2. 手動跑第一次資料更新

GitHub repo → Actions → 「每日更新球員數據」→ Run workflow。
跑完後 `public/data/players.json` 會被真實資料覆蓋(目前是示範假資料)。
之後每天台灣早上 6 點自動更新。

> 注意:repo Settings → Actions → General → Workflow permissions
> 要設成 **Read and write permissions**,Actions 才能 commit。

### 3. 補中文名

第一次跑完後,打開 `players.json` 找到每位球員的 `id` 和 `name_en`,
到 `scripts/name_map.json` 補上中文名:

```json
{ "666666": { "zh": "王小明" } }
```

沒補的球員會顯示英文名,不影響運作。

### 4. 部署 Cloudflare Pages

Cloudflare Dashboard → Workers & Pages → Create → Pages → 連接 GitHub repo:

- Build command:`npm run build`
- Build output directory:`dist`

完成後每次 push(包括 Actions 的資料 commit)都會自動重新部署。

### 5. 綁子網域(可選)

Pages 專案 → Custom domains → 加入例如 `players.clutchgtime.com`,
照指示在 DNS 加一筆 CNAME 即可。

## 本機開發

```bash
npm install
npm run dev        # http://localhost:5173
python3 scripts/fetch_data.py   # 手動抓一次真實資料(約 2-4 分鐘)
```

## 資料來源

- **旅美(MLB)**:`fetch_data.py` → MLB Stats API(官方 JSON)→ `mlb.json`
- **旅日(NPB)**:`fetch_npb.py` → npb.jp 官方 box score / 成績頁(爬蟲,需瀏覽器 UA)→ `npb.json`
  - 台灣球員名單手動維護於 `scripts/npb_roster.json`(NPB 無法用出生地自動篩選)
  - 一軍 + 二軍逐場 game log + 季賽累積;支配下球員資料完整,育成/傷兵球員待其出賽後累積
- `build_players.py` 合併兩者為前端載入的 `players.json`

## Roadmap

- [ ] 旅韓(KBO):官方無 API,需另寫爬蟲或先用手動 JSON 維護
- [ ] NPB 育成球員季賽數據(目前僅支配下球員成績頁涵蓋)
- [ ] 球員獨立頁 + SEO(資料結構已預留,加一層靜態頁產生即可)
- [ ] 傷兵名單 / 升降異動偵測(比對前一天 JSON 的 level 變化)
