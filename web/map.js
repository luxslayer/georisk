//Map update based on incidents.json
const map = L.map("map").setView([23.5,-102],5);

L.tileLayer(
  "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
).addTo(map);

const markers = L.markerClusterGroup();
let heatPoints = [];

fetch("data/incidents.json")
  .then(res => res.json())
  .then(data => {

    data.incidents.forEach(event => {

      const marker = L.marker([event.lat,event.lng]);

      marker.bindPopup(`
        <b>${event.title}</b><br>
        Riesgo: ${event.risk}<br>
        Carretera: ${event.road || "N/A"}<br>
        KM: ${event.km || "N/A"}<br>
        <a href="${event.url}" target="_blank">Fuente</a>
      `);

      markers.addLayer(marker);
      heatPoints.push([event.lat,event.lng]);
    });

    map.addLayer(markers);

    const heat = L.heatLayer(heatPoints,{
      radius:25,
      blur:15,
      maxZoom:10
    });

    heat.addTo(map);
  });

//CRON UPDATE ON SCREEN 
const UPDATE_INTERVAL = 900; // 15 minutes = 900 seconds
let timeLeft = UPDATE_INTERVAL;

const countdownElement = document.getElementById("countdown");

function updateCountdown() {

    const minutes = Math.floor(timeLeft / 60);
    const seconds = timeLeft % 60;

    countdownElement.textContent =
        `${minutes}:${seconds.toString().padStart(2,"0")}`;

    if (timeLeft <= 0) {

        location.reload(); // recargar mapa cuando llegue a 0

    } else {

        timeLeft--;

    }
}

setInterval(updateCountdown, 1000);

updateCountdown();