"""
km_geolocator.py
----------------
Localiza la coordenada exacta de un KM dado sobre una carretera mexicana,
interpolando sobre el GeoJSON de la ruta.

Uso:
    from km_geolocator import locate_km
    lat, lng = locate_km(57, 130)          # carretera 57, km 130
    lat, lng = locate_km(57, 130, known_segment=seg)  # con segmento acotado
"""

import json
import math
import os
from functools import lru_cache

ROADS_DIR = os.path.join(os.path.dirname(__file__), "..", "roads")


# ---------------------------------------------------------------------------
# Haversine
# ---------------------------------------------------------------------------

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia en km entre dos puntos geográficos."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi  = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ---------------------------------------------------------------------------
# Carga y ordenamiento de segmentos GeoJSON
# ---------------------------------------------------------------------------

def _load_geojson(road: int) -> list[list[tuple[float, float]]]:
    """
    Carga el GeoJSON de la carretera y devuelve lista de segmentos.
    Cada segmento es una lista de (lat, lng).
    GeoJSON usa [lng, lat] — se invierte aquí.
    """
    path = os.path.join(ROADS_DIR, f"mex_{road}.geojson")
    if not os.path.exists(path):
        return []

    with open(path, encoding="utf-8") as f:
        geojson = json.load(f)

    segments = []
    for feature in geojson.get("features", []):
        geom = feature.get("geometry", {})
        if geom.get("type") == "LineString":
            coords = [(lat, lng) for lng, lat in geom["coordinates"]]
            if coords:
                segments.append(coords)
        elif geom.get("type") == "MultiLineString":
            for line in geom["coordinates"]:
                coords = [(lat, lng) for lng, lat in line]
                if coords:
                    segments.append(coords)

    return segments


def _nearest_point_on_segment(
    lat: float, lng: float,
    seg: list[tuple[float, float]]
) -> float:
    """Distancia mínima en km desde (lat,lng) al segmento más cercano."""
    return min(haversine(lat, lng, p[0], p[1]) for p in seg)


def _point_to_segment_dist(
    lat: float, lng: float,
    p1: tuple[float, float],
    p2: tuple[float, float],
) -> float:
    """Distancia aproximada de un punto al segmento de línea p1-p2 (en km)."""
    # Proyección simple en coordenadas planas (válida para distancias cortas)
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    if dx == 0 and dy == 0:
        return haversine(lat, lng, p1[0], p1[1])
    t = max(0.0, min(1.0, ((lat - p1[0]) * dx + (lng - p1[1]) * dy) / (dx*dx + dy*dy)))
    proj_lat = p1[0] + t * dx
    proj_lng = p1[1] + t * dy
    return haversine(lat, lng, proj_lat, proj_lng)


def _segment_in_corridor(
    seg: list[tuple[float, float]],
    lat_a: float, lng_a: float,
    lat_b: float, lng_b: float,
    corridor_width_km: float = 25.0,
) -> bool:
    """
    Devuelve True si algún punto del segmento está dentro del corredor
    definido por la línea recta entre ciudad A y ciudad B.
    También acepta segmentos cercanos a cualquiera de las dos ciudades.
    """
    # Cerca de ciudad A o B
    for p in seg[::max(1, len(seg)//5)]:  # muestra ~5 puntos del segmento
        if haversine(p[0], p[1], lat_a, lng_a) < corridor_width_km * 2:
            return True
        if haversine(p[0], p[1], lat_b, lng_b) < corridor_width_km * 2:
            return True
        if _point_to_segment_dist(p[0], p[1], (lat_a, lng_a), (lat_b, lng_b)) < corridor_width_km:
            return True
    return False


def _chain_segments_anchored(
    segments: list[list[tuple[float, float]]],
    anchor_lat: float,
    anchor_lng: float,
    end_lat: float | None = None,
    end_lng: float | None = None,
    max_dist_km: float = 80.0,
) -> list[tuple[float, float]]:
    """
    Encadena los segmentos relevantes para el tramo entre dos ciudades.
    Si se proveen coordenadas de ciudad destino (end_lat/end_lng), usa
    filtrado por corredor geográfico en lugar de radio fijo desde el ancla.
    """
    if end_lat is not None and end_lng is not None:
        # Filtrado por corredor entre ciudad origen y ciudad destino
        nearby = [
            s for s in segments
            if _segment_in_corridor(s, anchor_lat, anchor_lng, end_lat, end_lng)
        ]
        if not nearby:
            # Fallback: radio amplio desde el punto medio
            mid_lat = (anchor_lat + end_lat) / 2
            mid_lng = (anchor_lng + end_lng) / 2
            dist_cities = haversine(anchor_lat, anchor_lng, end_lat, end_lng)
            radius = max(dist_cities, 50.0)
            nearby = [
                s for s in segments
                if _nearest_point_on_segment(mid_lat, mid_lng, s) <= radius
            ]
    else:
        # Sin ciudad destino: radio desde ancla
        nearby = [
            s for s in segments
            if _nearest_point_on_segment(anchor_lat, anchor_lng, s) <= max_dist_km
        ]
        if not nearby:
            nearby = sorted(
                segments,
                key=lambda s: _nearest_point_on_segment(anchor_lat, anchor_lng, s)
            )[:min(20, len(segments))]

    if not nearby:
        return []

    # Ordenar por distancia a la ciudad ancla (origen del tramo)
    nearby.sort(key=lambda s: _nearest_point_on_segment(anchor_lat, anchor_lng, s))

    # Encadenar greedy desde el más cercano al ancla
    chain = list(nearby[0])
    remaining = nearby[1:]

    while remaining:
        best_idx = 0
        best_dist = float("inf")
        best_flip = False

        for i, seg in enumerate(remaining):
            d_start = haversine(chain[-1][0], chain[-1][1], seg[0][0],  seg[0][1])
            d_end   = haversine(chain[-1][0], chain[-1][1], seg[-1][0], seg[-1][1])
            d = min(d_start, d_end)
            if d < best_dist:
                best_dist = d
                best_idx = i
                best_flip = d_end < d_start

        if best_dist > 10.0:
            break

        seg = remaining.pop(best_idx)
        if best_flip:
            seg = list(reversed(seg))

        if haversine(chain[-1][0], chain[-1][1], seg[0][0], seg[0][1]) < 0.05:
            chain.extend(seg[1:])
        else:
            chain.extend(seg)

    return chain


@lru_cache(maxsize=32)
def _load_segments_cached(road: int) -> tuple:
    """Carga los segmentos del GeoJSON (cacheado). Devuelve tuple para hashability."""
    return tuple(_load_geojson(road))


# ---------------------------------------------------------------------------
# Acumulación de distancias
# ---------------------------------------------------------------------------

def _cumulative_distances(polyline: list[tuple[float, float]]) -> list[float]:
    """
    Devuelve lista de distancias acumuladas en km para cada punto.
    El primer punto siempre es 0.0.
    """
    dists = [0.0]
    for i in range(1, len(polyline)):
        d = haversine(
            polyline[i-1][0], polyline[i-1][1],
            polyline[i][0],   polyline[i][1],
        )
        dists.append(dists[-1] + d)
    return dists


# ---------------------------------------------------------------------------
# Interpolación
# ---------------------------------------------------------------------------

def _interpolate(p1: tuple, p2: tuple, t: float) -> tuple[float, float]:
    """Interpolación lineal entre dos puntos, t ∈ [0, 1]."""
    lat = p1[0] + t * (p2[0] - p1[0])
    lng = p1[1] + t * (p2[1] - p1[1])
    return lat, lng


def _find_km_on_polyline(
    polyline: list[tuple[float, float]],
    cum_dists: list[float],
    target_km: float,
) -> tuple[float, float] | None:
    """
    Busca el punto en la polilínea que corresponde a target_km km
    desde el inicio de la misma.
    """
    total = cum_dists[-1]
    if target_km < 0 or target_km > total:
        return None

    # Búsqueda binaria del segmento
    lo, hi = 0, len(cum_dists) - 1
    while lo < hi - 1:
        mid = (lo + hi) // 2
        if cum_dists[mid] <= target_km:
            lo = mid
        else:
            hi = mid

    seg_len = cum_dists[hi] - cum_dists[lo]
    if seg_len == 0:
        return polyline[lo]

    t = (target_km - cum_dists[lo]) / seg_len
    return _interpolate(polyline[lo], polyline[hi], t)


# ---------------------------------------------------------------------------
# Búsqueda del punto más cercano a una coordenada en la polilínea
# ---------------------------------------------------------------------------

def _find_nearest_idx(
    polyline: list[tuple[float, float]],
    lat: float,
    lng: float,
) -> int:
    """Devuelve el índice del punto de la polilínea más cercano a (lat, lng)."""
    best_idx = 0
    best_dist = float("inf")
    for i, (p_lat, p_lng) in enumerate(polyline):
        d = haversine(lat, lng, p_lat, p_lng)
        if d < best_dist:
            best_dist = d
            best_idx = i
    return best_idx


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def locate_km(
    road: int,
    km: float,
    city_coords: tuple | None = None,
    known_segment: dict | None = None,
) -> tuple[float, float] | None:
    """
    Devuelve (lat, lng) del KM dado en la carretera especificada.

    Estrategia:
    1. Carga todos los segmentos del GeoJSON y los concatena en una sola lista de puntos
    2. Encuentra el punto más cercano a la ciudad ORIGEN del tramo
    3. Determina la dirección hacia la ciudad DESTINO
    4. Camina exactamente `km` kilómetros desde el origen en esa dirección

    Args:
        road:          Número de carretera (ej. 57)
        km:            Kilómetro a localizar relativo a la ciudad origen del segmento
        city_coords:   (lat1, lon1, lat2, lon2) de las ciudades del tramo
        known_segment: Dict con 'km_start', 'km_end' y 'cities'
    """
    from data.cities import cities as cities_dict

    segments = list(_load_segments_cached(road))
    if not segments:
        print(f"[km_geolocator] Sin GeoJSON para carretera {road}")
        return None

    # Aplanar todos los segmentos en una sola lista de puntos
    all_points = [p for seg in segments for p in seg]
    if not all_points:
        return None

    # ── 1. Obtener coordenadas de ciudad origen y destino ─────────────────
    origin_lat, origin_lng = None, None
    dest_lat,   dest_lng   = None, None
    origin_name = None

    if known_segment:
        c1, c2 = known_segment["cities"]
        coord1 = cities_dict.get(c1)
        coord2 = cities_dict.get(c2)
        if coord1:
            origin_lat, origin_lng = coord1
            origin_name = c1
        if coord2:
            dest_lat, dest_lng = coord2
        if not origin_lat and coord2:
            origin_lat, origin_lng = coord2
            origin_name = c2
            dest_lat, dest_lng = coord1 if coord1 else (None, None)

    elif city_coords and len(city_coords) == 4:
        origin_lat, origin_lng = city_coords[0], city_coords[1]
        dest_lat,   dest_lng   = city_coords[2], city_coords[3]

    if origin_lat is None:
        print(f"[km_geolocator] Sin coordenadas de ciudad origen")
        return None

    # ── 2. Encontrar el punto del GeoJSON más cercano a la ciudad origen ──
    origin_idx = _find_nearest_idx(all_points, origin_lat, origin_lng)
    dist_to_origin = haversine(origin_lat, origin_lng,
                               all_points[origin_idx][0], all_points[origin_idx][1])
    print(f"[km_geolocator] Origen '{origin_name}' → punto idx {origin_idx}, "
          f"distancia {dist_to_origin:.2f} km")

    # ── 3. Determinar dirección: ¿avanzar o retroceder en all_points? ─────
    # Comparar distancia de los extremos de la polilínea local a la ciudad destino
    forward = True
    if dest_lat is not None:
        # Tomar una muestra 50 puntos adelante y atrás del origen
        sample_fwd  = all_points[min(origin_idx + 50, len(all_points) - 1)]
        sample_back = all_points[max(origin_idx - 50, 0)]
        d_fwd  = haversine(dest_lat, dest_lng, sample_fwd[0],  sample_fwd[1])
        d_back = haversine(dest_lat, dest_lng, sample_back[0], sample_back[1])
        forward = d_fwd < d_back
        print(f"[km_geolocator] Dirección {'→ forward' if forward else '← backward'} "
              f"(d_fwd={d_fwd:.1f} km, d_back={d_back:.1f} km)")

    # ── 4. Construir polilínea desde origen en la dirección correcta ──────
    if forward:
        polyline = all_points[origin_idx:]
    else:
        polyline = list(reversed(all_points[:origin_idx + 1]))

    if len(polyline) < 2:
        print(f"[km_geolocator] Polilínea demasiado corta desde origen")
        return None

    cum_dists = _cumulative_distances(polyline)
    total_km  = cum_dists[-1]
    print(f"[km_geolocator] Polilínea desde origen: {len(polyline)} puntos, {total_km:.1f} km")

    # ── 5. Interpolar el KM exacto ────────────────────────────────────────
    result = _find_km_on_polyline(polyline, cum_dists, km)

    if result:
        print(f"[km_geolocator] Localizado: {result[0]:.5f}, {result[1]:.5f}")
    else:
        print(f"[km_geolocator] KM {km:.1f} fuera de rango (máx {total_km:.1f} km)")

    return result