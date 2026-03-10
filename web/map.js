// ── Carreteras conocidas ──────────────────────────────────────────────────────
// Agrega aquí todas las rutas que quieras monitorear.
// "id" debe coincidir con el campo `road` en incidents.json
const KNOWN_ROADS = [
  { id: 1,   name: "MEX-1  Tijuana – Los Cabos" },
  { id: 2,   name: "MEX-2  Tijuana – Matamoros" },
  { id: 15,  name: "MEX-15  Nogales – Guadalajara" },
  { id: 40,  name: "MEX-40  Mazatlán – Monterrey" },
  {id: 45,  name: "MEX-45  León – Aguascalientes" },
  { id: 45,  name: "MEX-45  Juárez – Guadalajara" },
  { id: 57,  name: "MEX-57  CDMX – Piedras Negras" },
  { id: 85,  name: "MEX-85  CDMX – Nuevo Laredo" },
  { id: 95,  name: "MEX-95  CDMX – Acapulco" },
  { id: 130, name: "MEX-130  Pachuca – Tuxpan" },
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
function buildRoadPanel(incidents) {
  // Agrupa incidentes por carretera
  const byRoad = new Map();

  incidents.forEach((inc, idx) => {
    const roadId = inc.road ?? "unknown";
    if (!byRoad.has(roadId)) byRoad.set(roadId, []);
    byRoad.get(roadId).push({ ...inc, _idx: idx });
  });

  const totalEl = document.getElementById("incident-total");
  totalEl.textContent = `${incidents.length} incidente${incidents.length !== 1 ? "s" : ""}`;

  const listEl = document.getElementById("road-list");
  listEl.innerHTML = "";

  // Carreteras con incidentes primero, luego las conocidas sin incidentes
  const roadIdsWithIncidents = [...byRoad.keys()].filter(id => id !== "unknown");
  const knownIds = KNOWN_ROADS.map(r => r.id);
  const allIds = [
    ...roadIdsWithIncidents,
    ...knownIds.filter(id => !roadIdsWithIncidents.includes(id)),
  ];

  allIds.forEach(roadId => {
    const roadInfo = KNOWN_ROADS.find(r => r.id === roadId);
    const name = roadInfo ? roadInfo.name : `Carretera ${roadId}`;
    const incidents = byRoad.get(roadId) || [];
    const hasHigh = incidents.some(i => i.risk === "high");
    const hasAny  = incidents.length > 0;

    // ── Card ──
    const card = document.createElement("div");
    card.className = "road-card";
    card.dataset.roadId = roadId;

    // Determina clase del dot
    const dotClass = hasHigh ? "dot-high" : hasAny ? "dot-warn" : "dot-clear";
    const badgeExtra = hasHigh ? " has-high" : "";

    card.innerHTML = `
      <div class="road-card-header">
        <span class="road-badge${badgeExtra}">MEX-${roadId}</span>
        <span class="road-name">${roadInfo ? roadInfo.name.split("  ")[1] : name}</span>
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

    // Toggle expand
    card.querySelector(".road-card-header").addEventListener("click", () => {
      const isActive = card.classList.contains("active");
      document.querySelectorAll(".road-card.active").forEach(c => c.classList.remove("active"));
      if (!isActive) card.classList.add("active");
    });

    // Click en incidente → volar al marcador
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
  });

  // Si hay incidentes sin carretera conocida, agrégalos al final
  if (byRoad.has("unknown")) {
    const unknownInc = byRoad.get("unknown");
    const card = document.createElement("div");
    card.className = "road-card";
    card.innerHTML = `
      <div class="road-card-header">
        <span class="road-badge">???</span>
        <span class="road-name">Sin carretera detectada</span>
        <span class="road-status-dot dot-warn"></span>
      </div>
      <div class="road-incidents">
        ${unknownInc.map(inc => `
          <div class="incident-row" data-idx="${inc._idx}">
            <div class="inc-km">KM <span>—</span></div>
            <div class="inc-body">
              <div class="inc-title">${inc.title}</div>
              <div class="inc-risk ${inc.risk}">${inc.risk.toUpperCase()}</div>
            </div>
          </div>`).join("")}
      </div>
    `;
    card.querySelector(".road-card-header").addEventListener("click", () => {
      card.classList.toggle("active");
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