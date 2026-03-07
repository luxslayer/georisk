import json
import math
import os

# cargar carreteras
roads = []

folder = "roads"

for file in os.listdir(folder):

    if file.endswith(".json") or file.endswith(".geojson"):

        with open(os.path.join(folder,file)) as f:

            geo = json.load(f)

            roads.extend(geo["features"])


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

        ref=str(feature["properties"].get("ref","")).lower()

        if str(road_number)==ref:

            coords=feature["geometry"]["coordinates"]

            coords=[(c[1],c[0]) for c in coords]

            segments.append(coords)

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