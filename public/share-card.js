/**
 * 精彩表現分享圖卡 —— 在瀏覽器端用 canvas 畫,按一下就下載 PNG。
 *
 * 為什麼在前端畫而不是 build 時產圖:圖卡是每場比賽都有的東西,若在 build 產出
 * 並進 git,每天幾十張 PNG 的二進位差異會把 repo 撐爆(scripts/make_og.py 的
 * 說明裡already 記過這個教訓);而且 CI 上沒有中文字型。前端畫零 repo 成本、
 * 用使用者自己的系統字型,而且要分享時才產生。
 *
 * 設計刻意走本站品牌(綠底、圖釘 logo、網址),不模仿任何聯盟官方圖卡的識別;
 * 也不放球員照片或轉播截圖 —— 那些不是我們的素材。
 */
(function () {
  const W = 1080, H = 1080;
  const GREEN = "#0f5138", GREEN_D = "#0a3a28", CREAM = "#f6f8f6";
  const MUTED = "#8fc4ac", ACCENT = "#6ec8a0";
  const FONT = '"PingFang TC","Noto Sans TC","Microsoft JhengHei",system-ui,sans-serif';
  const MONO = '"SF Mono",ui-monospace,Menlo,Consolas,monospace';

  const f = (size, weight) => `${weight || 400} ${size}px ${FONT}`;
  const fm = (size, weight) => `${weight || 400} ${size}px ${MONO}`;

  // 中英數混排時逐字換行(中文沒有空格,不能用 split(" "))
  function wrap(ctx, text, maxW) {
    const lines = [];
    let line = "";
    for (const ch of text) {
      if (ctx.measureText(line + ch).width > maxW && line) {
        lines.push(line);
        line = ch;
      } else line += ch;
    }
    if (line) lines.push(line);
    return lines;
  }

  function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  function draw(d) {
    const c = document.createElement("canvas");
    c.width = W; c.height = H;
    const ctx = c.getContext("2d");

    const g = ctx.createLinearGradient(0, 0, 0, H);
    g.addColorStop(0, GREEN); g.addColorStop(1, GREEN_D);
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);

    const PAD = 72;
    let y = PAD + 24;

    // 事件標籤 + 局數
    ctx.font = f(30, 700);
    const tag = d.event_zh || "精彩表現";
    const tw = ctx.measureText(tag).width;
    ctx.fillStyle = ACCENT;
    roundRect(ctx, PAD, y - 4, tw + 44, 54, 27); ctx.fill();
    ctx.fillStyle = GREEN_D;
    ctx.fillText(tag, PAD + 22, y + 34);
    if (d.inning) {
      ctx.fillStyle = MUTED; ctx.font = f(30, 500);
      ctx.fillText(`${d.half === "top" ? "上" : "下"} ${d.inning} 局`, PAD + tw + 68, y + 34);
    }
    y += 104;

    // 球員名
    ctx.fillStyle = CREAM; ctx.font = f(84, 700);
    ctx.fillText(d.name, PAD, y + 62);
    if (d.roman) {
      ctx.fillStyle = MUTED; ctx.font = f(30, 400);
      ctx.fillText(d.roman, PAD + ctx.measureText("").width, y + 106);
    }
    y += d.roman ? 152 : 112;

    // 敘述。開頭的「上8局，」拿掉 —— 局數上方的標籤列已經顯示過了
    const body = (d.text || "").replace(/^[上下]\s*\d+\s*局，/, "");
    ctx.fillStyle = CREAM; ctx.font = f(40, 400);
    for (const line of wrap(ctx, body, W - PAD * 2)) {
      ctx.fillText(line, PAD, y + 40);
      y += 58;
    }
    y += 18;

    // 對手／層級／日期
    ctx.fillStyle = MUTED; ctx.font = f(28, 400);
    const meta = [d.date, d.level, d.opponent ? `對 ${d.opponent}` : "",
      (d.away_score != null && d.home_score != null) ? `比分 ${d.away_score}:${d.home_score}` : ""]
      .filter(Boolean).join("　·　");
    ctx.fillText(meta, PAD, y + 28);
    y += 76;

    // Statcast 三欄
    const cells = [
      d.ev != null ? ["擊球初速", d.ev.toFixed ? d.ev.toFixed(1) : d.ev, "mph"] : null,
      d.dist != null ? ["飛行距離", Math.round(d.dist), "ft"] : null,
      d.angle != null ? ["擊球仰角", Math.round(d.angle), "°"] : null,
    ].filter(Boolean);
    if (cells.length) {
      const boxH = 176;
      ctx.fillStyle = "rgba(255,255,255,0.06)";
      roundRect(ctx, PAD, y, W - PAD * 2, boxH, 24); ctx.fill();
      const cw = (W - PAD * 2) / cells.length;
      cells.forEach((cell, i) => {
        const cx = PAD + cw * i + cw / 2;
        ctx.textAlign = "center";
        ctx.fillStyle = MUTED; ctx.font = f(26, 500);
        ctx.fillText(cell[0], cx, y + 54);
        ctx.textAlign = "left";
        // 「值 + 單位」當成一整組置中量寬再畫,不能各自以中心點對齊 —— 那會讓
        // 單位直接疊在數字上(100.2 與 mph 重疊)。
        const val = String(cell[1]);
        ctx.font = fm(62, 700);
        const vw = ctx.measureText(val).width;
        ctx.font = f(26, 500);
        const uw = ctx.measureText(cell[2]).width;
        const x0 = cx - (vw + 10 + uw) / 2;
        ctx.fillStyle = CREAM; ctx.font = fm(62, 700);
        ctx.fillText(val, x0, y + 128);
        ctx.fillStyle = MUTED; ctx.font = f(26, 500);
        ctx.fillText(cell[2], x0 + vw + 10, y + 128);
      });
      y += boxH;
    }

    // 本季累積(prerender 從 players.json 帶進來)。原本 Statcast 區塊下方留一大片
    // 空白,補這行既填滿版面也讓看到卡片的人知道他整季打得如何。
    if (d.season) {
      y += 42;
      ctx.fillStyle = MUTED; ctx.font = f(26, 500);
      ctx.fillText("本季累積", PAD, y + 26);
      ctx.fillStyle = CREAM; ctx.font = f(34, 600);
      for (const line of wrap(ctx, d.season, W - PAD * 2)) {
        ctx.fillText(line, PAD, y + 76);
        y += 48;
      }
    }

    // 頁尾:品牌 + 網址
    ctx.fillStyle = "rgba(255,255,255,0.14)";
    ctx.fillRect(PAD, H - 150, W - PAD * 2, 1);
    ctx.fillStyle = CREAM; ctx.font = f(32, 700);
    ctx.fillText("旅外球員情報站", PAD, H - 92);
    ctx.fillStyle = MUTED; ctx.font = f(26, 400);
    ctx.fillText("players.clutchgtime.com", PAD, H - 52);
    ctx.textAlign = "right";
    ctx.fillStyle = MUTED; ctx.font = f(22, 400);
    ctx.fillText("數據來源：MLB Stats API", W - PAD, H - 52);
    ctx.textAlign = "left";
    return c;
  }

  function download(d) {
    const c = draw(d);
    c.toBlob(function (blob) {
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${d.name}-${d.date}.png`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 3000);
    }, "image/png");
  }

  window.ShareCard = { draw, download };
})();
