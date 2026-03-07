import requests
import xml.etree.ElementTree as ET
import json
import re
from datetime import datetime

incidents = []

TWITTER_RSS = [
    "https://nitter.net/GN_Carreteras/rss",
    "https://nitter.net/CAPUFE/rss"
]

# ciudades con coordenadas
cities = {
"monterrey":(25.6866,-100.3161),
"saltillo":(25.4267,-101.0053),
"reynosa":(26.0922,-98.2773),
"nuevo laredo":(27.4779,-99.5496),
"queretaro":(20.5888,-100.3899),
"puebla":(19.0414,-98.2063),
"mexico":(19.4326,-99.1332),
"cdmx":(19.4326,-99.1332),
"guadalajara":(20.6597,-103.3496),
"tijuana":(32.5149,-117.0382),
"toluca":(19.2826,-99.6557),
"leon":(21.1220,-101.68),
"celaya":(20.52,-100.81),
"irapuato":(20.67,-101.35),
"mazatlan":(23.24,-106.41),
"culiacan":(24.80,-107.39),
"hermosillo":(29.07,-110.96),
"juarez":(31.69,-106.42),
"chihuahua":(28.63,-106.08),
"durango":(24.03,-104.67)
}

risk_words = [
"balacera",
"robo",
"asalto",
"bloqueo",
"enfrentamiento",
"incendio",
"violencia"
]


def detect_city(text):

    text = text.lower()

    for city in cities:
        if city in text:
            return cities[city]

    return None


def detect_road(text):

    text = text.lower()

    match = re.search(r"(carretera|autopista|mex)[\s\-]?(\d+)", text)

    if match:
        return match.group(2)

    return None


def detect_km(text):

    match = re.search(r"km[\s]?(\d+)", text.lower())

    if match:
        return int(match.group(1))

    return None


def detect_risk(text):

    text = text.lower()

    for word in risk_words:
        if word in text:
            return "high"

    return "normal"


def process_tweet(title, url):

    coords = detect_city(title)

    if coords:
        lat, lng = coords
    else:
        lat, lng = 23.5, -102

    road = detect_road(title)
    km = detect_km(title)
    risk = detect_risk(title)

    incidents.append({
        "title": title,
        "type": "twitter",
        "lat": lat,
        "lng": lng,
        "road": road,
        "km": km,
        "risk": risk,
        "url": url
    })


print("Fetching Twitter RSS")

for feed in TWITTER_RSS:

    try:

        r = requests.get(feed, timeout=10)

        root = ET.fromstring(r.content)

        for item in root.findall(".//item")[:50]:

            title = item.find("title").text
            link = item.find("link").text

            process_tweet(title, link)

    except Exception as e:

        print("RSS error:", e)


data = {

"last_update": datetime.utcnow().isoformat(),
"incidents": incidents

}

with open("incidents.json","w") as f:

    json.dump(data,f,indent=2)


print("Saved", len(incidents), "incidents")