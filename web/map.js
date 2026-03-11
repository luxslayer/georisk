// ── Carreteras conocidas ──────────────────────────────────────────────────────
// Agrega aquí todas las rutas que quieras monitorear.
// "id" debe coincidir con el campo `road` en incidents.json
const KNOWN_ROADS = [
  { id: 1,   name: "MEX-1  Tijuana – Los Cabos" },
  { id: 2,   name: "MEX-2  Tijuana – Matamoros" },
  { id: 15,  name: "MEX-15  Tepic – Mazatlan" },
  { id: 40,  name: "MEX-40  Mazatlán – Monterrey" },
  {id: 45,  name: "MEX-45  León – Aguascalientes" },
  { id: 45,  name: "MEX-45  Juárez – Guadalajara" },
  { id: 57,  name: "MEX-57  Puerto México – Ojo Caliente"},
  { id: 57,  name: "MEX-57  Querétaro – San Luis Potosí"},
  { id: 57,  name: "MEX-57  Matehuala – Saltillo"},
  { id: 85,  name: "MEX-85  CDMX – Nuevo Laredo" },
  { id: 95,  name: "MEX-95  CDMX – Acapulco" },
  { id: 130, name: "MEX-130  Pachuca – Tuxpan" },
  { id: 150, name: "MEX-150  Puebla – Cordoba" },
  { id: 150, name: "MEX-150  CDMX – Veracruz" },
  { id: 180, name: "MEX-180  Tabasco – Cancún" },
  { id: 200, name: "MEX-200  Nayarit – Chiapas" },
];

// ── Mapa ──────────────────────────────────────────────────────────────────────
const map = L.map("map").setView([23.5, -102], 5);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: "© OpenStreetMap contributors",
  maxZoom: 18,
}).addTo(map);

const clusterGroup = L.markerClusterGroup();
let heatPoints = [];

// Guarda referencia a markers por incidente para hacer fly-to desde el panel
const markerMap = new Map(); // incidente index → marker

// ── Render del panel de carreteras ───────────────────────────────────────────
function roadKey(roadId, segment) {
  // Clave única: "57-queretaro-san luis potosi" o "57" si no hay segmento
  return segment ? `${roadId}-${segment[0]}-${segment[1]}` : String(roadId);
}

function buildRoadPanel(incidents) {
  // Agrupa incidentes por clave compuesta road+segment
  const byKey = new Map();

  incidents.forEach((inc, idx) => {
    const key = inc.road != null
      ? roadKey(inc.road, inc.segment)
      : "unknown";
    if (!byKey.has(key)) byKey.set(key, []);
    byKey.get(key).push({ ...inc, _idx: idx });
  });

  const totalEl = document.getElementById("incident-total");
  totalEl.textContent = `${incidents.length} incidente${incidents.length !== 1 ? "s" : ""}`;

  const listEl = document.getElementById("road-list");
  listEl.innerHTML = "";

  // Construir cards iterando KNOWN_ROADS directamente (permite duplicados de id)
  const renderedKeys = new Set();

  KNOWN_ROADS.forEach(roadInfo => {
    const key = roadInfo.segment
      ? roadKey(roadInfo.id, roadInfo.segment)
      : String(roadInfo.id);

    // Recoger incidentes: los que matchean por clave exacta
    // + los del mismo road sin segmento definido (compatibilidad)
    const exact   = byKey.get(key) || [];
    const generic = roadInfo.segment ? [] : (byKey.get(String(roadInfo.id)) || []);
    const cardIncidents = [...new Map(
      [...exact, ...generic].map(i => [i._idx, i])
    ).values()];

    renderedKeys.add(key);
    renderRoadCard(listEl, roadInfo.id, roadInfo.name, cardIncidents);
  });

  // Incidentes de carreteras no listadas en KNOWN_ROADS
  byKey.forEach((cardIncidents, key) => {
    if (renderedKeys.has(key) || key === "unknown") return;
    const roadId = cardIncidents[0]?.road;
    renderRoadCard(listEl, roadId, `Carretera ${roadId}`, cardIncidents);
  });

  // Sin carretera detectada
  if (byKey.has("unknown")) {
    renderRoadCard(listEl, "???", "Sin carretera detectada", byKey.get("unknown"));
  }
}
function renderRoadCard(listEl, roadId, name, incidents) {
  const hasHigh = incidents.some(i => i.risk === "high");
  const hasAny  = incidents.length > 0;
  const dotClass   = hasHigh ? "dot-high" : hasAny ? "dot-warn" : "dot-clear";
  const badgeExtra = hasHigh ? " has-high" : "";
  // Extraer subtítulo tras "MEX-XX  "
  const subtitle = name.includes("  ") ? name.split("  ")[1] : name;

  const card = document.createElement("div");
  card.className = "road-card";
  card.dataset.roadId = roadId;

  card.innerHTML = `
    <div class="road-card-header">
      <span class="road-badge${badgeExtra}">MEX-${roadId}</span>
      <span class="road-name">${subtitle}</span>
      <span class="road-status-dot ${dotClass}"></span>
    </div>
    <div class="road-incidents">
      ${incidents.length === 0
        ? `<div class="road-clear-msg">SIN AFECTACIONES</div>`
        : incidents.map(inc => `
            <div class="incident-row" data-idx="${inc._idx}">
              <div class="inc-km">KM <span>${inc.km != null ? Math.round(inc.km) : "—"}</span></div>
              <div class="inc-body">
                <div class="inc-title">${inc.title}</div>
                <div class="inc-meta">
                  <span class="inc-risk ${inc.risk}">${inc.risk.toUpperCase()}</span>
                  <span class="inc-time">${inc.timestamp_display || ""}</span>
                </div>
              </div>
            </div>`
          ).join("")
      }
    </div>
  `;

  card.querySelector(".road-card-header").addEventListener("click", () => {
    const isActive = card.classList.contains("active");
    document.querySelectorAll(".road-card.active").forEach(c => c.classList.remove("active"));
    if (!isActive) card.classList.add("active");
  });

  card.querySelectorAll(".incident-row").forEach(row => {
    row.addEventListener("click", e => {
      e.stopPropagation();
      const idx = parseInt(row.dataset.idx);
      const marker = markerMap.get(idx);
      if (marker) {
        map.flyTo(marker.getLatLng(), 12, { duration: 1.2 });
        setTimeout(() => marker.openPopup(), 1300);
      }
    });
  });

  listEl.appendChild(card);
}

// ── Carga de datos ────────────────────────────────────────────────────────────
fetch("/georisk/incidents.json?nocache=" + Date.now())
  .then(res => res.json())
  .then(data => {

    data.incidents.forEach((event, idx) => {
      // Ícono según riesgo
      const color   = event.risk === "high" ? "#ff3d57" : "#00e5a0";
      const icon = L.divIcon({
        className: "",
        html: `<div style="
          width:12px; height:12px; border-radius:50%;
          background:${color};
          border: 2px solid rgba(255,255,255,0.3);
          box-shadow: 0 0 8px ${color};
        "></div>`,
        iconSize: [12, 12],
        iconAnchor: [6, 6],
      });

      const marker = L.marker([event.lat, event.lng], { icon });

      const riskClass = event.risk === "high" ? "popup-risk-high" : "popup-risk-normal";

      marker.bindPopup(`
        <b>${event.title}</b>
        <span class="${riskClass}">${event.risk.toUpperCase()}</span><br>
        Carretera: ${event.road != null ? "MEX-" + event.road : "N/A"}<br>
        KM: ${event.km != null ? Math.round(event.km) : "N/A"}<br>
        🕐 ${event.timestamp_display || "Fecha desconocida"}<br>
        <a href="${event.url}" target="_blank">→ Fuente</a>
      `);

      markerMap.set(idx, marker);
      clusterGroup.addLayer(marker);
      heatPoints.push([event.lat, event.lng, event.risk === "high" ? 1 : 0.4]);
    });

    map.addLayer(clusterGroup);

    L.heatLayer(heatPoints, {
      radius: 25,
      blur: 15,
      maxZoom: 10,
      gradient: { 0.4: "#00e5a0", 0.7: "#ffb800", 1.0: "#ff3d57" },
    }).addTo(map);

    buildRoadPanel(data.incidents);
  })
  .catch(err => {
    console.error("Error cargando incidents.json:", err);
    buildRoadPanel([]);
  });

// ── Countdown ─────────────────────────────────────────────────────────────────
const UPDATE_INTERVAL = 900;
let timeLeft = UPDATE_INTERVAL;
const countdownEl = document.getElementById("countdown");

function updateCountdown() {
  const m = Math.floor(timeLeft / 60);
  const s = timeLeft % 60;
  countdownEl.textContent = `${m}:${s.toString().padStart(2, "0")}`;
  if (timeLeft <= 0) {
    location.reload();
  } else {
    timeLeft--;
  }
}

setInterval(updateCountdown, 1000);
updateCountdown();