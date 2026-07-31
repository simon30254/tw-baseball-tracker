// 球隊主場座標(key = players.json 的 org 字串)。用於「地圖」分頁標記球員所在地。
// 座標為各隊主場城市/球場,足夠標示所在地;新增球隊時補一筆即可。
export const TEAM_GEO = {
  // 旅美 MLB
  "Arizona Diamondbacks": { lat: 33.4455, lng: -112.0667, city: "Phoenix" },
  "Athletics": { lat: 38.5800, lng: -121.5169, city: "West Sacramento" },
  "Boston Red Sox": { lat: 42.3467, lng: -71.0972, city: "Boston" },
  "Cincinnati Reds": { lat: 39.0975, lng: -84.5069, city: "Cincinnati" },
  "Detroit Tigers": { lat: 42.339, lng: -83.0485, city: "Detroit" },
  "Houston Astros": { lat: 29.757, lng: -95.3555, city: "Houston" },
  "Los Angeles Dodgers": { lat: 34.0739, lng: -118.24, city: "Los Angeles" },
  "Milwaukee Brewers": { lat: 43.028, lng: -87.9712, city: "Milwaukee" },
  "New York Yankees": { lat: 40.8296, lng: -73.9262, city: "New York" },
  "Philadelphia Phillies": { lat: 39.9061, lng: -75.1665, city: "Philadelphia" },
  "Pittsburgh Pirates": { lat: 40.4469, lng: -80.0057, city: "Pittsburgh" },
  "San Diego Padres": { lat: 32.7073, lng: -117.1566, city: "San Diego" },
  "San Francisco Giants": { lat: 37.7786, lng: -122.3893, city: "San Francisco" },
  "Seattle Mariners": { lat: 47.5914, lng: -122.3325, city: "Seattle" },
  "St. Louis Cardinals": { lat: 38.6226, lng: -90.1928, city: "St. Louis" },
  // 旅日 NPB
  "巨人": { lat: 35.7056, lng: 139.7519, city: "東京" },
  "日本火腿": { lat: 42.9886, lng: 141.5085, city: "北廣島" },
  "樂天": { lat: 38.2565, lng: 140.9026, city: "仙台" },
  "歐力士": { lat: 34.6693, lng: 135.4762, city: "大阪" },
  "西武": { lat: 35.7717, lng: 139.4216, city: "所澤" },
  "軟銀": { lat: 33.5952, lng: 130.3623, city: "福岡" },
  "養樂多": { lat: 35.6748, lng: 139.717, city: "東京" },
  // 旅韓 KBO
  "韓華": { lat: 36.3172, lng: 127.429, city: "大田" },
};
