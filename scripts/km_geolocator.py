import json
import math
import os
import re
from collections import defaultdict
import heapq

# cargar carreteras
roads = []

folder = "roads"

for file in os.listdir(folder):

    if not file.endswith(".geojson"):
        continue

    path = os.path.join(folder, file)

    with open(path) as f:

        data = json.load(f)

        if data["type"] == "FeatureCollection":

            roads.extend(data["features"])

        elif data["type"] == "Feature":

            roads.append(data)

def haversine(a,b):

    R = 6371

    lat1,lon1 = map(math.radians,a)
    lat2,lon2 = map(math.radians,b)

    dlat = lat2-lat1
    dlon = lon2-lon1

    a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2

    c = 2*math.atan2(math.sqrt(a), math.sqrt(1-a))

    return R*c


def line_midpoint(coords):

    lats=[c[0] for c in coords]
    lngs=[c[1] for c in coords]

    return sum(lats)/len(lats),sum(lngs)/len(lngs)


def get_road_segments(road_number):

    segments = []

    for feature in roads:

        props = feature.get("properties", {})
        ref = props.get("ref")

        if not ref:
            continue

        try:
            road_ref = int(ref)
        except:
            continue

        if road_ref != road_number:
            continue

        geom = feature["geometry"]

        if geom["type"] == "LineString":

            coords = [(c[1], c[0]) for c in geom["coordinates"]]
            segments.append(coords)

        elif geom["type"] == "MultiLineString":

            for line in geom["coordinates"]:
                coords = [(c[1], c[0]) for c in line]
                segments.append(coords)

    return segments


def corridor_filter(segments, city1, city2):

    filtered = []

    dist_cities = haversine(city1, city2)

    for seg in segments:

        mid = line_midpoint(seg)

        d1 = haversine(city1, mid)
        d2 = haversine(city2, mid)

        if d1 + d2 < dist_cities * 1.3:
            filtered.append(seg)

    return filtered

def locate_km(road_number, km, city_coords=None):

    segments = get_road_segments(road_number)

    if not segments:
        return None
    
    city1 = None
    city2 = None

    # -------------------------
    # FILTRO POR TRAMO (NUEVO)
    # -------------------------
    if city_coords:

        lat1, lon1, lat2, lon2 = city_coords

        city1 = (lat1, lon1)
        city2 = (lat2, lon2)

        segments = corridor_filter(
            segments,
            city1,
            city2
        )

        
    # -------------------------
    # DETECTAR SUBTRAMO AUTOMÁTICO
    # -------------------------

    if city_coords:

        lat1, lon1, lat2, lon2 = city_coords

        city1 = (lat1, lon1)
        city2 = (lat2, lon2)

        # calcular distancia de cada segmento a las ciudades
        scored = []

        for seg in segments:

            mid = line_midpoint(seg)

            d = min(
                haversine(city1, mid),
                haversine(city2, mid)
            )

            scored.append((d, seg))

        scored.sort(key=lambda x: x[0])

        # quedarse con los más cercanos
        segments = [s for _, s in scored[:200]]

    # -------------------------
    # ORDENAR SEGMENTOS
    # -------------------------

    segments = sorted(
        segments,
        key=lambda s: (
            line_midpoint(s)[0],
            line_midpoint(s)[1]
        )
    )

    # -------------------------
    # INTERPOLAR KM
    # -------------------------

    total = 0

    for seg in segments:

        for i in range(len(seg) - 1):

            a = seg[i]
            b = seg[i + 1]

            d = haversine(a, b)

            if total + d >= km:

                ratio = (km - total) / d

                lat = a[0] + ratio * (b[0] - a[0])
                lon = a[1] + ratio * (b[1] - a[1])

                return lat, lon

            total += d

    return None