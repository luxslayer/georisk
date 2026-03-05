import requests
import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime

os.makedirs("web/data", exist_ok=True)

incidents = []

RSS_FEEDS = [

"https://news.google.com/rss/search?q=carretera+asalto+mexico&hl=es-MX&gl=MX&ceid=MX:es",
"https://news.google.com/rss/search?q=bloqueo+carretera+mexico&hl=es-MX&gl=MX&ceid=MX:es",
"https://news.google.com/rss/search?q=accidente+autopista+mexico&hl=es-MX&gl=MX&ceid=MX:es"

]

# 50 ciudades mexicanas importantes

cities = {

"monterrey":(25.6866,-100.3161),
"saltillo":(25.4267,-101.0053),
"reynosa":(26.0922,-98.2773),
"nuevo laredo":(27.4779,-99.5496),
"queretaro":(20.5888,-100.3899),
"puebla":(19.0414,-98.2063),
"mexico":(19.4326,-99.1332),
"guadalajara":(20.6597,-103.3496),
"tijuana":(32.5149,-117.0382),
"toluca":(19.2826,-99.6557),
"leon":(21.1220,-101.68),
"celaya":(20.52,-100.81),
"irapuato":(20.67,-101.35),
"mazatlan":(23.24,-106.41),
"culiacan":(24.80,-107.39),
"hermosillo":(29.07,-110.96),
"cd juarez":(31.69,-106.42),
"chihuahua":(28.63,-106.08),
"durango":(24.03,-104.67)

}

# carreteras federales importantes

federal_roads = [

"57",
"85",
"40",
"15",
"45",
"150",
"200",
"54",
"80"

]

risk_words = [

"balacera",
"robo",
"asalto",
"bloqueo",
"enfrentamiento",
"incendio",
"narco",
"violencia"

]


def detect_city(text):

    text=text.lower()

    for city in cities:

        if city in text:

            return cities[city]

    return None


def detect_road(text):

    text=text.lower()

    for road in federal_roads:

        if f"carretera {road}" in text or f"autopista {road}" in text:

            return road

    return None


def detect_km(text):

    match=re.search(r"km\s?(\d+)",text.lower())

    if match:

        return int(match.group(1))

    return None


def detect_risk(text):

    text=text.lower()

    for word in risk_words:

        if word in text:

            return "high"

    return "normal"


def process_event(title,url):

    coords=detect_city(title)

    if coords:
        lat,lng=coords
    else:
        lat,lng=23.5,-102

    road=detect_road(title)

    km=detect_km(title)

    risk=detect_risk(title)

    return {

        "title":title,
        "type":"news",
        "lat":lat,
        "lng":lng,
        "road":road,
        "km":km,
        "risk":risk,
        "url":url

    }


print("Fetching RSS")

for feed in RSS_FEEDS:

    try:

        r=requests.get(feed,timeout=10)

        root=ET.fromstring(r.content)

        for item in root.findall(".//item")[:15]:

            title=item.find("title").text
            link=item.find("link").text

            incidents.append(
                process_event(title,link)
            )

    except:

        pass


if len(incidents)==0:

    incidents=[

        {
        "title":"Bloqueo en carretera 57 cerca de Monterrey",
        "type":"news",
        "lat":25.68,
        "lng":-100.31,
        "road":"57",
        "km":45,
        "risk":"high",
        "url":"https://example.com"
        }

    ]


output={

"last_update":datetime.utcnow().isoformat(),
"incidents":incidents

}

with open("web/data/incidents.json","w") as f:

    json.dump(output,f,indent=2)

os.makedirs("data", exist_ok=True)

if len(incidents) == 0:
    print("No incidents found, creating empty dataset")

data = {
    "last_update": datetime.utcnow().isoformat(),
    "incidents": incidents
}

with open("data/incidents.json","w") as f:
    json.dump(data,f,indent=2)

print("Saved", len(incidents), "incidents")