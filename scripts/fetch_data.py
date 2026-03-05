import requests
import json
import re
import snscrape.modules.twitter as sntwitter

incidents = []

NEWS_API = "YOUR_NEWSAPI_KEY"

cities = {
"monterrey": (25.6866,-100.3161),
"saltillo": (25.4267,-101.0053),
"reynosa": (26.0922,-98.2773),
"nuevo laredo": (27.4779,-99.5496),
"queretaro": (20.5888,-100.3899),
"puebla": (19.0414,-98.2063),
"mexico": (19.4326,-99.1332)
}

authority_accounts = [
"CAPUFE",
"GN_Carreteras"
]

risk_words = [
"balacera",
"robo",
"bloqueo",
"enfrentamiento",
"incendio"
]

def detect_city(text):

    text = text.lower()

    for city in cities:
        if city in text:
            return cities[city]

    return None


def extract_road_info(text):

    road_pattern = r"(carretera|autopista)\s?(\d+)?"
    km_pattern = r"km\s?(\d+)"

    road = re.search(road_pattern, text.lower())
    km = re.search(km_pattern, text.lower())

    result = {}

    if road:
        result["road"] = road.group()

    if km:
        result["km"] = int(km.group(1))

    return result


def detect_risk(text):

    for word in risk_words:
        if word in text.lower():
            return "high"

    return "normal"


def geocode(place):

    url = "https://nominatim.openstreetmap.org/search"

    params = {
        "q": place + ", Mexico",
        "format": "json"
    }

    try:

        r = requests.get(url, params=params).json()

        if r:
            return float(r[0]["lat"]), float(r[0]["lon"])

    except:
        pass

    return None


def process_event(text, source, url):

    coords = detect_city(text)

    road_info = extract_road_info(text)

    risk = detect_risk(text)

    if coords:
        lat, lng = coords
    else:
        lat, lng = 23.5, -102.0

    return {
        "title": text[:200],
        "type": source,
        "lat": lat,
        "lng": lng,
        "road": road_info.get("road"),
        "km": road_info.get("km"),
        "risk": risk,
        "url": url
    }


# -------- SCRAPE AUTORIDADES --------

for acc in authority_accounts:

    for tweet in sntwitter.TwitterUserScraper(acc).get_items():

        text = tweet.content

        if any(word in text.lower() for word in ["cierre","accidente","bloqueo"]):

            incidents.append(
                process_event(text,"authority",tweet.url)
            )

        if len(incidents) > 30:
            break


# -------- NEWS API --------

news_url = f"https://newsapi.org/v2/everything?q=carretera%20mexico%20asalto&language=es&apiKey={NEWS_API}"

try:

    news = requests.get(news_url).json()

    for article in news["articles"][:20]:

        incidents.append(
            process_event(
                article["title"],
                "news",
                article["url"]
            )
        )

except:
    pass


# -------- SAVE JSON --------

with open("data/incidents.json","w") as f:

    json.dump(incidents,f,indent=2)