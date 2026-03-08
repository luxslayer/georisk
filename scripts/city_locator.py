import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from data.cities import cities

def detect_cities(tweet):

    text = tweet.lower()

    found = []

    for city in cities:

        if city in text:
            found.append(city)

    return found

def detect_segment(tweet):

    cities_found = detect_cities(tweet)

    if len(cities_found) >= 2:

        return cities_found[0], cities_found[1]

    return None

def segment_coords(cityA, cityB):

    lat1, lon1 = cities[cityA]
    lat2, lon2 = cities[cityB]

    return lat1, lon1, lat2, lon2

def interpolate(lat1, lon1, lat2, lon2, km):

    # distancia aproximada del tramo
    total_km = 300

    ratio = min(km / total_km, 1)

    lat = lat1 + (lat2 - lat1) * ratio
    lon = lon1 + (lon2 - lon1) * ratio

    return lat, lon