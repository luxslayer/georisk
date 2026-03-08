import json
import math
import os
import re

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

    h = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2

    return 2*R*math.asin(math.sqrt(h))


def line_midpoint(coords):

    lats=[c[0] for c in coords]
    lngs=[c[1] for c in coords]

    return sum(lats)/len(lats),sum(lngs)/len(lngs)


def locate_km(road_number,km,city_coords=None):

    segments=[]

    for feature in roads:

        props = feature.get("properties", {})

        name = (
            str(props.get("name","")) + " " +
            str(props.get("ref","")) + " " +
            str(props.get("route",""))
        ).lower()

        m = re.search(r"mex[\s\-_]?(\d+)", name)

        if not m:
            continue

        if int(m.group(1)) != road_number:
            continue   

        geom = feature["geometry"]

        if geom["type"] == "LineString":

            coords = [(c[1],c[0]) for c in geom["coordinates"]]
            segments.append(coords)

        elif geom["type"] == "MultiLineString":

            for line in geom["coordinates"]:

                coords = [(c[1],c[0]) for c in line]
                segments.append(coords)
    
    print("ROAD MATCH:", name)
    print("SEARCH ROAD:", road_number)
    print("SEGMENTS FOUND:", len(segments))

    if not segments:
        return None


    # ordenar segmentos por cercanía a ciudad
    if city_coords:

        segments.sort(
            key=lambda s: haversine(
                city_coords,
                line_midpoint(s)
            )
        )

    total=0

    for coords in segments:

        for i in range(len(coords)-1):

            a=coords[i]
            b=coords[i+1]

            segment=haversine(a,b)

            if total+segment>=km:

                ratio=(km-total)/segment

                lat=a[0]+ratio*(b[0]-a[0])
                lng=a[1]+ratio*(b[1]-a[1])

                return lat,lng

            total+=segment


    return None