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

    h = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2

    return 2*R*math.asin(math.sqrt(h))


def line_midpoint(coords):

    lats=[c[0] for c in coords]
    lngs=[c[1] for c in coords]

    return sum(lats)/len(lats),sum(lngs)/len(lngs)



def build_graph(segments):

    graph = defaultdict(list)

    for seg in segments:

        for i in range(len(seg) - 1):

            a = seg[i]
            b = seg[i + 1]

            dist = haversine(a, b)

            graph[a].append((b, dist))
            graph[b].append((a, dist))

    return graph

def nearest_node(city, graph):

    best = None
    best_dist = 999999

    for node in graph.keys():

        d = haversine(city, node)

        if d < best_dist:
            best = node
            best_dist = d

    return best


def shortest_path(graph, start, end):

    queue = [(0, start, [])]
    visited = set()

    while queue:

        cost, node, path = heapq.heappop(queue)

        if node in visited:
            continue

        path = path + [node]

        if node == end:
            return path

        visited.add(node)

        for neighbor, weight in graph[node]:

            if neighbor not in visited:

                heapq.heappush(
                    queue,
                    (cost + weight, neighbor, path)
                )

    return None

def interpolate_on_path(path, km):

    total = 0

    for i in range(len(path) - 1):

        a = path[i]
        b = path[i+1]

        d = haversine(a, b)

        if total + d >= km:

            ratio = (km - total) / d

            lat = a[0] + ratio * (b[0] - a[0])
            lon = a[1] + ratio * (b[1] - a[1])

            return lat, lon

        total += d

    return None

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

    if city_coords:

        lat1, lon1, lat2, lon2 = city_coords

        city1 = (lat1, lon1)
        city2 = (lat2, lon2)

        segments = corridor_filter(
            segments,
            city1,
            city2
        )

        print("SEGMENTS AFTER CORRIDOR:", len(segments))

    if not segments:
        return None

    graph = build_graph(segments)



    if city_coords and len(city_coords) == 4:

        lat1, lon1, lat2, lon2 = city_coords

        city1 = (lat1, lon1)
        city2 = (lat2, lon2)

        start = nearest_node(city1, graph)
        end = nearest_node(city2, graph)

        path = shortest_path(graph, start, end)

        if not path:
            return None

        return interpolate_on_path(path, km)

    # fallback si no hay ciudades
    all_nodes = list(graph.keys())

    total = 0

    for i in range(len(all_nodes)-1):

        a = all_nodes[i]
        b = all_nodes[i+1]

        d = haversine(a,b)

        if total + d >= km:

            ratio = (km - total)/d

            lat = a[0] + ratio*(b[0]-a[0])
            lon = a[1] + ratio*(b[1]-a[1])

            return lat, lon

        total += d

    return None