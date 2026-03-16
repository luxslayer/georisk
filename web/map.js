// ── Carreteras conocidas ──────────────────────────────────────────────────────
// Estructura jerárquica: cada carretera tiene segmentos opcionales.
// Si no hay segmentos, se trata como una sola unidad.
const KNOWN_ROADS = [
  { id: 2,   label: "MEX-2",  name: "Ciudad Juárez – Tijuana", segments: [
    { cities: ["ciudad juarez",    "janos"], name: "Ciudad Juárez – Janos"},
    { cities: ["janos",    "agua prieta"], name: "Janos – Agua Prieta"},
    { cities: ["agua prieta",    "imuris"], name: "Agua Prieta – Imuris"},
    { cities: ["santa ana",    "sonoyta"], name: "Santa Ana – Sonoyta"},
    { cities: ["sonoyta",    "san luis rio colorado"], name: "Sonoyta – San Luis Río Colorado"},
    { cities: ["san luis rio colorado", "mexicali"], name: "San Luis Río Colorado – Mexicali"},
  ]},

  { id: 15,  label: "MEX-15", name: "Nogales – Guadalajara" },

  { id: 40,  label: "MEX-40", name: "Mazatlán – Matamoros", segments: [
    { cities: ["saltillo",    "monterrey"], name: "Saltillo – Monterrey"},
  ]},

  { id: 40,  label: "MEX-40D", name: "Arco Norte", segments: [
    { cities: ["atlacomulco",    "jilotepec"], name: "Atlacomulco – Jilotepec"},
    { cities: ["jilotepec", "queretaro"],   name: "Jilotepec – Querétaro"},
    { cities: ["queretaro",    "tula"],        name: "Querétaro – Tula"},
    { cities: ["tula",    "atitalaquia"],        name: "Tula – Atitalaquia"},
    { cities: ["atitalaquia",    "apaxco"],        name: "Atitalaquia – Apaxco"},
    { cities: ["apaxco",    "ajoloapan"],        name: "Apaxco – Ajoloapan"},
    { cities: ["ajoloapan",    "pachuca"],        name: "Ajoloapan – Pachuca"},
    { cities: ["pachuca",    "tulancingo"],        name: "Pachuca – Tulancingo"},
    { cities: ["tulancingo",    "sahagun"],        name: "Tulancingo – Sahagun"},
    { cities: ["sahagun",    "calpulalpan"],        name: "Sahagun – Calpulalpan"},
    { cities: ["calpulalpan",    "sanctorum"],        name: "Calpulalpan – Sanctorum"},
    { cities: ["sanctorum",    "texmelucan"],        name: "Sanctorum – Texmelucan"}
  ]},

  { id: 45,  label: "MEX-45", name: "Juárez – Guadalajara", segments: [ 
    { cities: ["leon",    "aguascalientes"], name: "León – Aguascalientes" },
  ] },

  { id: 57,  label: "MEX-57", name: "México – Piedras Negras", segments: [
    { cities: ["mexico",    "queretaro"], name: "CDMX – Querétaro"       },
    { cities: ["queretaro",    "san luis potosi"], name: "Querétaro – SLP"       },
    { cities: ["san luis potosi", "matehuala"],   name: "SLP – Matehuala"        },
    { cities: ["matehuala",    "saltillo"],        name: "Matehuala – Saltillo"   },
    { cities: ["puerto mexico","ojo caliente"],    name: "Pto. México – Ojo Caliente" },
    { cities: ["saltillo","monclova"],    name: "Saltillo – Monclova" },
    { cities: ["monclova","piedras negras"],    name: "Monclova – Piedras Negras" },
  ]},

  { id: 85,  label: "MEX-85", name: "México – Nuevo Laredo", segments: [
    { cities: ["monterrey",    "nuevo laredo"],    name: "Monterrey – Nuevo Laredo" },
  ]},

  { id: 95,  label: "MEX-95",  name: "México – Acapulco" },

  { id: 130, label: "MEX-130", name: "Pachuca – Tuxpan", segments: [
    { cities: ["pachuca",   "tulancingo"], name: "Pachuca – Tulancingo" },
    { cities: ["tulancingo","poza rica"],  name: "Tulancingo – Poza Rica" },
    { cities: ["poza rica", "tuxpan"],    name: "Poza Rica – Tuxpan" },
  ]},

  {id: 145|, label: "MEX-145", name: "La Tinaja – Cosoleacaque", segments: [
    { cities: ["la tinaja", "acayucan"], name: "La Tinaja – Acayucan" },
    { cities: ["acayucan", "cosoleacaque"], name: "Acayucan – Cosoleacaque" },
  ]},

  { id: 150, label: "MEX-150", name: "CDMX – Veracruz", segments: [
    { cities: ["mexico", "puebla"],  name: "México – Puebla"  },
    { cities: ["puebla", "veracruz"],name: "Puebla – Veracruz"},
    { cities: ["cordoba", "veracruz"],name: "Córdoba – Veracruz"},
  ]},

  { id: 180, label: "MEX-180", name: "Tabasco – Cancún", segments: [
    { cities: ["nuevo teapa", "cosoleacaque"], name: "Nuevo Teapa – Cosoleacaque" },
    { cities: ["la ventosa", "tapanatepec"], name: "La Ventosa – Tapanatepec" },
  ]},

  { id: 200, label: "MEX-200", name: "Nayarit – Chiapas" },
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

// ── Helpers de agrupación ─────────────────────────────────────────────────────
function roadKey(roadId, segment) {
  return segment ? `${roadId}-${segment[0]}-${segment[1]}` : String(roadId);
}

function incidentsForSegment(byKey, roadId, segCities) {
  // Busca por clave exacta del segmento
  const key = roadKey(roadId, segCities);
  return byKey.get(key) || [];
}

function incidentsForRoad(byKey, roadId, segments) {
  // Todos los incidentes de la carretera (con y sin segmento detectado)
  const all = new Map();
  // Incidentes sin segmento detectado
  (byKey.get(String(roadId)) || []).forEach(i => all.set(i._idx, i));
  // Incidentes de cada segmento conocido
  if (segments) {
    segments.forEach(seg => {
      incidentsForSegment(byKey, roadId, seg.cities).forEach(i => all.set(i._idx, i));
    });
  }
  return [...all.values()];
}

// ── Panel jerárquico ──────────────────────────────────────────────────────────
function buildRoadPanel(incidents) {
  const byKey = new Map();
  incidents.forEach((inc, idx) => {
    const key = inc.road != null ? roadKey(inc.road, inc.segment) : "unknown";
    if (!byKey.has(key)) byKey.set(key, []);
    byKey.get(key).push({ ...inc, _idx: idx });
  });

  const totalEl = document.getElementById("incident-total");
  totalEl.textContent = `${incidents.length} incidente${incidents.length !== 1 ? "s" : ""}`;

  const listEl = document.getElementById("road-list");
  listEl.innerHTML = "";

  const renderedRoads = new Set();

  KNOWN_ROADS.forEach(road => {
    renderedRoads.add(road.id);
    const allInc = incidentsForRoad(byKey, road.id, road.segments);
    renderRoadGroup(listEl, road, byKey, allInc);
  });

  // Carreteras con incidentes no listadas en KNOWN_ROADS
  byKey.forEach((inc, key) => {
    if (key === "unknown") return;
    const roadId = inc[0]?.road;
    if (roadId != null && !renderedRoads.has(roadId)) {
      const syntheticRoad = { id: roadId, label: `MEX-${roadId}`, name: `Carretera ${roadId}` };
      renderRoadGroup(listEl, syntheticRoad, byKey, inc);
    }
  });

  // Sin carretera detectada
  if (byKey.has("unknown")) {
    const syntheticRoad = { id: "???", label: "???", name: "No operativas" };
    renderRoadGroup(listEl, syntheticRoad, byKey, byKey.get("unknown"));
  }
}

// ── Renderiza una carretera con sus segmentos ─────────────────────────────────
function renderRoadGroup(listEl, road, byKey, allIncidents) {
  const hasHigh = allIncidents.some(i => i.risk === "high");
  const hasAny  = allIncidents.length > 0;
  const dotClass   = hasHigh ? "dot-high" : hasAny ? "dot-warn" : "dot-clear";
  const badgeExtra = hasHigh ? " has-high" : "";
  const incCount   = hasAny ? `<span class="road-inc-count">${allIncidents.length}</span>` : "";

  const group = document.createElement("div");
  group.className = "road-group";

  // ── Cabecera de la carretera ──
  group.innerHTML = `
    <div class="road-group-header">
      <span class="road-chevron">▶</span>
      <span class="road-badge${badgeExtra}">${road.label}</span>
      <span class="road-name">${road.name}</span>
      <span class="road-status-dot ${dotClass}"></span>
      ${incCount}
    </div>
    <div class="road-group-body"></div>
  `;

  const header = group.querySelector(".road-group-header");
  const body   = group.querySelector(".road-group-body");
  const chevron = group.querySelector(".road-chevron");

  // ── Segmentos (si los hay) ──
  if (road.segments && road.segments.length > 0) {
    road.segments.forEach(seg => {
      const segInc = incidentsForSegment(byKey, road.id, seg.cities);
      const segHasHigh = segInc.some(i => i.risk === "high");
      const segHasAny  = segInc.length > 0;
      const segDot     = segHasHigh ? "dot-high" : segHasAny ? "dot-warn" : "dot-clear";

      const segEl = document.createElement("div");
      segEl.className = "road-segment";
      segEl.innerHTML = `
        <div class="seg-header">
          <span class="seg-line"></span>
          <span class="road-status-dot ${segDot}" style="width:6px;height:6px"></span>
          <span class="seg-name">${seg.name}</span>
          ${segHasAny ? `<span class="seg-count">${segInc.length}</span>` : ""}
        </div>
        <div class="seg-incidents" style="display:none">
          ${segInc.length === 0
            ? `<div class="road-clear-msg">SIN AFECTACIONES</div>`
            : segInc.map(inc => incidentRowHTML(inc)).join("")}
        </div>
      `;

      // Toggle incidentes del segmento
      segEl.querySelector(".seg-header").addEventListener("click", e => {
        e.stopPropagation();
        const panel = segEl.querySelector(".seg-incidents");
        const isOpen = panel.style.display !== "none";
        panel.style.display = isOpen ? "none" : "block";
        segEl.classList.toggle("seg-open", !isOpen);
      });

      attachIncidentClicks(segEl);
      body.appendChild(segEl);
    });

    // Incidentes sin segmento detectado (road genérico)
    const generic = byKey.get(String(road.id)) || [];
    if (generic.length > 0) {
      const segEl = document.createElement("div");
      segEl.className = "road-segment";
      segEl.innerHTML = `
        <div class="seg-header">
          <span class="seg-line"></span>
          <span class="road-status-dot dot-warn" style="width:6px;height:6px"></span>
          <span class="seg-name" style="color:var(--text-dim)">Tramo sin detectar</span>
          <span class="seg-count">${generic.length}</span>
        </div>
        <div class="seg-incidents" style="display:none">
          ${generic.map(inc => incidentRowHTML(inc)).join("")}
        </div>
      `;
      segEl.querySelector(".seg-header").addEventListener("click", e => {
        e.stopPropagation();
        const panel = segEl.querySelector(".seg-incidents");
        panel.style.display = panel.style.display !== "none" ? "none" : "block";
      });
      attachIncidentClicks(segEl);
      body.appendChild(segEl);
    }

  } else {
    // Sin segmentos: mostrar incidentes directamente
    body.innerHTML = allIncidents.length === 0
      ? `<div class="road-clear-msg" style="padding:8px 16px">SIN AFECTACIONES</div>`
      : allIncidents.map(inc => incidentRowHTML(inc)).join("");
    body.querySelectorAll && attachIncidentClicks(body);
  }

  // Toggle apertura del grupo
  header.addEventListener("click", () => {
    const isOpen = group.classList.contains("open");
    document.querySelectorAll(".road-group.open").forEach(g => {
      g.classList.remove("open");
      g.querySelector(".road-chevron").textContent = "▶";
    });
    if (!isOpen) {
      group.classList.add("open");
      chevron.textContent = "▼";
    }
  });

  listEl.appendChild(group);
}

// ── HTML de una fila de incidente ─────────────────────────────────────────────
function incidentRowHTML(inc) {
  return `
    <div class="incident-row" data-idx="${inc._idx}">
      <div class="inc-km">KM <span>${inc.km != null ? Math.round(inc.km) : "—"}</span></div>
      <div class="inc-body">
        <div class="inc-title">${inc.title}</div>
        <div class="inc-meta">
          <span class="inc-risk ${inc.risk}">${inc.risk.toUpperCase()}</span>
          <span class="inc-time">${inc.timestamp_display || ""}</span>
        </div>
      </div>
    </div>`;
}

function attachIncidentClicks(container) {
  container.querySelectorAll(".incident-row").forEach(row => {
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