import requests
import xml.etree.ElementTree as ET
import json
import re
from datetime import datetime
from km_geolocator import locate_km
from city_locator import detect_segment, segment_coords, interpolate
import unicodedata

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
"durango":(24.03,-104.67),
"pinotepa nacional": (16.34,-98.05),
"salina cruz": (16.17,-95.20),
"tapanatepec": (16.37,-94.19),
"tuxtla gutierrez": (16.75,-93.12),
"nuevo teapa": (18.03,-94.25),
"cosoleacaque": (18.00,-94.63)
}

risk_words = [
"balacera",
"robo",
"asalto",
"bloqueo",
"enfrentamiento",
"incendio",
"violencia",
"accidente",
"obras"
]

def normalize(text):

    text = text.lower()

    text = unicodedata.normalize("NFD", text)

    text = "".join(
        c for c in text
        if unicodedata.category(c) != "Mn"
    )

    return text

def detect_city(text):

    text = text.lower()

    for city in cities:
        if city in text:
            return cities[city]

    return None



def detect_km(text):

    text = text.lower()

    m = re.search(r"km\s*(\d+)(?:\+(\d+))?", text)

    if m:

        km = int(m.group(1))

        if m.group(2):
            km += int(m.group(2)) / 1000

        return km

    return None


def detect_risk(text):

    text = text.lower()

    for word in risk_words:
        if word in text:
            return "high"

    return "normal"

def detect_cities(text):

    text = normalize(text)

    found = []

    for city in cities:

        if city in text:
            found.append(city)

    return found


def detect_road_from_cities(city_list):

    if len(city_list) < 2:
        return None

    c1 = city_list[0]
    c2 = city_list[1]

    # heurísticas simples de carreteras federales
    routes = {
        ("chihuahua","juarez"):45,
        ("monterrey","saltillo"):40,
        ("saltillo","matehuala"):57,
        ("matehuala","san luis potosi"):57,
        ("queretaro","san luis potosi"):57,
        ("monterrey","reynosa"):40,
        ("mexico","queretaro"):57,
        ("queretaro","leon"):45,
        ("pinotepa nacional","salina cruz"):200,
        ("tapanatepec","tuxtla gutierrez"):190,
    }

    for (a,b),road in routes.items():

        if (a in c1 and b in c2) or (b in c1 and a in c2):
            return road

    return None

def detect_road(text):

    text = normalize(text)

    # 1 detectar numero directo
    m = re.search(r"(carretera|autopista|mex)[\s\-]?(\d+)", text)

    if m:
        return int(m.group(2))

    # 2 detectar ciudades
    found_cities = detect_cities(text)
    print("CITIES FOUND:", found_cities)

    road = detect_road_from_cities(found_cities)

    if road:
        return road

    return None


def process_tweet(title, url):

    if not title:
        return

    lat = 23.5
    lng = -102

    coords = detect_city(title)

    if coords:
        ciudad_lat, ciudad_lng = coords
    else:
        ciudad_lat, ciudad_lng = 23.5, -102

    try:
        segment = detect_segment(title)
    except:
        segment = None

    road = detect_road(title)
    km = detect_km(title)
    risk = detect_risk(title)

    print("TWEET:", title)
    print("ROAD:", road, "KM:", km)

    # intentar localizar km exacto en carretera
    if road and km:

        p = locate_km(road, km, (ciudad_lat, ciudad_lng))
        print("LOCATE RESULT:", p)

        if p:

            lat, lng = p

        elif segment:

            cityA, cityB = segment

            lat1, lon1, lat2, lon2 = segment_coords(cityA, cityB)

            lat, lng = interpolate(lat1, lon1, lat2, lon2, km)

        else:

            lat, lng = ciudad_lat, ciudad_lng


    elif segment and km:

        cityA, cityB = segment

        lat1, lon1, lat2, lon2 = segment_coords(cityA, cityB)

        lat, lng = interpolate(lat1, lon1, lat2, lon2, km)


    elif coords:

        lat, lng = coords

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

        headers = {
        "User-Agent":"Mozilla/5.0"
        }

        r = requests.get(feed, headers=headers, timeout=10)

        print("Status:", r.status_code)
        print("Response:", r.text[:200])

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