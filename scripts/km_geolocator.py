import json
import math
import os

# cargar carreteras
roads = []

folder = "roads"

for file in os.listdir(folder):

    if file.endswith(".json") or file.endswith(".geojson"):

        with open(os.path.join(folder, file)) as f:

            geo = json.load(f)

            roads.extend(geo["features"])

def haversine(a, b):
    R = 6371
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    h = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(h))


def point_along_line(coords, km):
    """encuentra punto a X km dentro de la línea"""

    total = 0

    for i in range(len(coords)-1):

        a = coords[i]
        b = coords[i+1]

        segment = haversine(a, b)

        if total + segment >= km:

            ratio = (km - total) / segment

            lat = a[0] + ratio * (b[0] - a[0])
            lon = a[1] + ratio * (b[1] - a[1])

            return lat, lon

        total += segment

    return None


def locate_km(road_number, km):

    print("Searching road:", road_number)

    for feature in roads["features"]:

        ref = str(feature["properties"].get("ref","")).lower()

        if str(road_number) in str(ref):

            coords = feature["geometry"]["coordinates"]

            # GeoJSON usa lon,lat → convertir
            coords = [(c[1], c[0]) for c in coords]

            point = point_along_line(coords, km)

            if point:
                return point

    return None