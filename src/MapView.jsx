import React, { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { TEAM_GEO } from "./teamGeo.js";

const LEAGUE_OF = { npb: "旅日", kbo: "旅韓" };
const playerLeague = (p) => LEAGUE_OF[p.league] || "旅美";
const LEVEL_LABEL = {
  MLB: "MLB", AAA: "3A", AA: "2A", "High-A": "高階1A", A: "1A", Rookie: "新人",
  一軍: "一軍", 二軍: "二軍",
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
    L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
      attribution: "&copy; OpenStreetMap &copy; CARTO",
      subdomains: "abcd",
      maxZoom: 18,
    }).addTo(map);

    // 依球隊分組(套用聯盟篩選),一隊一個標記
    const groups = {};
    players
      .filter((p) => leagueChip === "全部" || playerLeague(p) === leagueChip)
      .forEach((p) => {
        const geo = TEAM_GEO[p.org];
        if (!geo) return;
        (groups[p.org] = groups[p.org] || { geo, org: p.org, players: [] }).players.push(p);
      });

    const base = import.meta.env.BASE_URL;
    const bounds = [];
    Object.values(groups).forEach((g) => {
      bounds.push([g.geo.lat, g.geo.lng]);
      const icon = L.divIcon({
        className: "map-pin",
        html: `<span class="map-pin-badge">${g.players.length}</span>`,
        iconSize: [28, 28],
        iconAnchor: [14, 14],
        popupAnchor: [0, -14],
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
        .bindPopup(`<b>${esc(g.org)}</b>　<span class="mp-city">${esc(g.geo.city)}</span><br>${list}`);
    });

    if (bounds.length) map.fitBounds(bounds, { padding: [40, 40], maxZoom: 6 });
    else map.setView([35, 150], 2);
    setTimeout(() => map.invalidateSize(), 120);

    return () => map.remove();
  }, [players, leagueChip]);

  return (
    <section className="mapview">
      <p className="map-note">點地圖上的標記可看該球隊的台灣旅外球員與連結。</p>
      <div ref={ref} className="map" />
    </section>
  );
}
