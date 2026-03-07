import json
import os

roads = {}

folder = "roads"

for file in os.listdir(folder):

    if not file.endswith(".geojson"):
        continue

    with open(os.path.join(folder,file)) as f:

        geo = json.load(f)

        for feature in geo["features"]:

            ref = feature["properties"].get("ref")

            if not ref:
                continue

            coords = feature["geometry"]["coordinates"]

            if ref not in roads:
                roads[ref] = []

            roads[ref].append(coords)


with open("data/road_index.json","w") as f:

    json.dump(roads,f)

print("Indexed",len(roads),"roads")