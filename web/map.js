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