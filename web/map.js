const map = L.map("map").setView([23.5,-102],5)

L.tileLayer(
"https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
{
attribution:"OSM"
}
).addTo(map)


function getColor(type){

if(type=="authority") return "red"
if(type=="news") return "orange"
if(type=="traffic") return "blue"

return "gray"

}


const markers = L.markerClusterGroup()

fetch("../data/incidents.json")

.then(res => res.json())

.then(data => {

data.forEach(event => {

const marker = L.circleMarker(

[event.lat,event.lng],

{
radius:8,
color:getColor(event.type)
}

)

marker.bindPopup(`

<b>${event.title}</b><br>

Tipo: ${event.type}<br>

Riesgo: ${event.risk}<br>

Carretera: ${event.road || "N/A"}<br>

KM: ${event.km || "N/A"}<br>

<a href="${event.url}" target="_blank">Fuente</a>

`)

markers.addLayer(marker)

})

map.addLayer(markers)

})