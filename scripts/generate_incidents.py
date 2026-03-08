import requests
import xml.etree.ElementTree as ET
import json
import re
import unicodedata
from datetime import datetime
from km_geolocator import locate_km
from city_locator import detect_segment, segment_coords, interpolate
from data.cities import cities
from data.routes import routes

incidents = []

TWITTER_RSS = [
    "https://nitter.net/GN_Carreteras/rss",
    "https://nitter.net/CAPUFE/rss"
]

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

def detect_city(tweet):

    cities_found = detect_cities(tweet)

    if cities_found:

        city = cities_found[0]

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

    words = set(text.split())

    found = []

    for city in cities:

        city_words = city.split()

        if all(w in words for w in city_words):
            found.append(city)

    return found


def detect_road_from_cities(city_list):

    if len(city_list) < 2:
        return None

    c1 = city_list[0]
    c2 = city_list[1]

    for (a,b),road in routes.items():

        if (c1 == a and c2 == b) or (c1 == b and c2 == a):
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

    segment = detect_segment(title)

    road = None

    if segment:
        road = detect_road_from_cities(segment)

    if not road:
        road = detect_road(title)

    km = detect_km(title)
    risk = detect_risk(title)

    print("TWEET:", title)
    print("ROAD:", road, "KM:", km)

    # intentar localizar km exacto en carretera
    if road and km:

        if segment:
            cityA, cityB = segment
            lat1, lon1, lat2, lon2 = segment_coords(cityA, cityB)
            city_coords = (lat1, lon1, lat2, lon2)
        else:
            city_coords = None

        p = locate_km(road, km, city_coords)

        print("LOCATE RESULT:", p)

        if p:

            lat, lng = p

        elif segment:

            lat = (lat1 + lat2) / 2
            lng = (lon1 + lon2) / 2

        else:

            lat, lng = ciudad_lat, ciudad_lng

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