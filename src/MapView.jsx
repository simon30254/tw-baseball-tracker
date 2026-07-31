import React, { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { TEAM_GEO } from "./teamGeo.js";

const LEAGUE_OF = { npb: "旅日", kbo: "旅韓" };
const playerLeague = (p) => LEAGUE_OF[p.league] || "旅美";
const LEAGUE_COLOR = { 旅美: "#157a54", 旅日: "#c0392b", 旅韓: "#2f6ea5" };
const LEVEL_LABEL = {
  MLB: "MLB", AAA: "3A", AA: "2A", "High-A": "高階1A", A: "1A", Rookie: "新人",
  一軍: "一軍", 二軍: "二軍",
};
const TILES = {
  light: "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
  dark: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
};
const esc = (s) =>
  String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

export default function MapView({ players, leagueChip }) {
  const ref = useRef(null);

  useEffect(() => {
    if (!ref.current) return;
    const map = L.map(ref.current, {
      scrollWheelZoom: false,
      attributionControl: true,
      worldCopyJump: true,
    });

    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const tiles = L.tileLayer(mq.matches ? TILES.dark : TILES.light, {
      attribution: "&copy; OpenStreetMap &copy; CARTO",
      subdomains: "abcd",
      maxZoom: 18,
    }).addTo(map);
    const onTheme = (e) => tiles.setUrl(e.matches ? TILES.dark : TILES.light);
    mq.addEventListener?.("change", onTheme);

    // 依球隊分組(套用聯盟篩選),一隊一個標記
    const groups = {};
    players
      .filter((p) => leagueChip === "全部" || playerLeague(p) === leagueChip)
      .forEach((p) => {
        const geo = TEAM_GEO[p.org];
        if (!geo) return;
        const key = p.org;
        (groups[key] = groups[key] || { geo, org: p.org, league: playerLeague(p), players: [] }).players.push(p);
      });

    const base = import.meta.env.BASE_URL;
    const bounds = [];
    Object.values(groups).forEach((g) => {
      bounds.push([g.geo.lat, g.geo.lng]);
      const color = LEAGUE_COLOR[g.league] || LEAGUE_COLOR["旅美"];
      const icon = L.divIcon({
        className: "map-pin",
        html: `<span class="map-pin-badge" style="background:${color}">${g.players.length}</span>`,
        iconSize: [28, 28],
        iconAnchor: [14, 14],
        popupAnchor: [0, -15],
        tooltipAnchor: [0, -14],
      });
      const list = g.players
        .map(
          (p) =>
            `<a href="${base}player/${p.slug}/">${esc(p.name)}</a>` +
            ` <span class="mp-lv">${esc(LEVEL_LABEL[p.level] || p.level)}</span>`
        )
        .join("<br>");
      L.marker([g.geo.lat, g.geo.lng], { icon })
        .addTo(map)
        .bindTooltip(`${esc(g.org)}・${g.players.length} 人`, { direction: "top" })
        .bindPopup(`<b>${esc(g.org)}</b>　<span class="mp-city">${esc(g.geo.city)}</span><br>${list}`);
    });

    if (bounds.length) map.fitBounds(bounds, { padding: [45, 45], maxZoom: 6 });
    else map.setView([35, 150], 2);
    setTimeout(() => map.invalidateSize(), 120);

    return () => {
      mq.removeEventListener?.("change", onTheme);
      map.remove();
    };
  }, [players, leagueChip]);

  return (
    <section className="mapview">
      <div className="map-legend">
        <span className="map-note">點標記看該隊台將・移標記顯示球隊</span>
        <span className="map-keys">
          <span className="mk"><i style={{ background: LEAGUE_COLOR["旅美"] }} />旅美</span>
          <span className="mk"><i style={{ background: LEAGUE_COLOR["旅日"] }} />旅日</span>
          <span className="mk"><i style={{ background: LEAGUE_COLOR["旅韓"] }} />旅韓</span>
        </span>
      </div>
      <div ref={ref} className="map" />
    </section>
  );
}
