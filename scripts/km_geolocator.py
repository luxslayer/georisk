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

    La búsqueda se hace relativa a la ciudad de inicio del segmento conocido,
    no desde el inicio absoluto de la polilínea — esto corrige el desfase
    cuando la carretera tiene cientos de km antes del tramo de interés.

    Args:
        road:          Número de carretera (ej. 57)
        km:            Kilómetro a localizar (relativo al segmento si known_segment existe)
        city_coords:   (lat1, lon1, lat2, lon2) de las ciudades del tramo
        known_segment: Dict con 'km_start', 'km_end' y 'cities'

    Returns:
        (lat, lng) o None si no se pudo localizar
    """
    from data.cities import cities as cities_dict

    segments = list(_load_segments_cached(road))
    if not segments:
        print(f"[km_geolocator] Sin GeoJSON para carretera {road}")
        return None

    # ── 1. Determinar ciudades ancla origen y destino ─────────────────────
    anchor_lat, anchor_lng = None, None
    end_lat,    end_lng    = None, None
    anchor_city_name = None

    if known_segment:
        c1, c2 = known_segment["cities"]
        coord1 = cities_dict.get(c1)
        coord2 = cities_dict.get(c2)
        if coord1:
            anchor_lat, anchor_lng = coord1
            anchor_city_name = c1
        if coord2:
            end_lat, end_lng = coord2
        if not anchor_lat and coord2:
            anchor_lat, anchor_lng = coord2
            anchor_city_name = c2
            end_lat, end_lng = coord1 if coord1 else (None, None)
        filter_lat = ((anchor_lat or 0) + (end_lat or anchor_lat or 0)) / 2
        filter_lng = ((anchor_lng or 0) + (end_lng or anchor_lng or 0)) / 2

    elif city_coords and len(city_coords) == 4:
        anchor_lat, anchor_lng = city_coords[0], city_coords[1]
        end_lat,    end_lng    = city_coords[2], city_coords[3]
        filter_lat = (anchor_lat + end_lat) / 2
        filter_lng = (anchor_lng + end_lng) / 2
    else:
        anchor_lat, anchor_lng = 23.5, -102.0
        filter_lat, filter_lng = anchor_lat, anchor_lng

    # ── 2. Construir polilínea usando corredor entre las dos ciudades ──────
    polyline = _chain_segments_anchored(
        segments,
        anchor_lat, anchor_lng,
        end_lat, end_lng,
    )
    if not polyline:
        print(f"[km_geolocator] No se pudo construir polilínea para MEX-{road}")
        return None

    cum_dists = _cumulative_distances(polyline)
    total_km  = cum_dists[-1]

    print(f"[km_geolocator] MEX-{road}: {len(polyline)} puntos, {total_km:.1f} km (tramo anclado)")

    # ── 3. Encontrar posición de la ciudad ancla en la polilínea ──────────
    # El KM del tweet es relativo a la ciudad de inicio del tramo,
    # no desde el km 0 de la polilínea.
    anchor_idx = _find_nearest_idx(polyline, anchor_lat, anchor_lng)
    anchor_km_in_polyline = cum_dists[anchor_idx]

    print(f"[km_geolocator] Ciudad ancla '{anchor_city_name}' → idx {anchor_idx}, "
          f"km {anchor_km_in_polyline:.1f} en polilínea")

    # ── 4. Buscar KM relativo a la ciudad ancla ───────────────────────────
    km_target = anchor_km_in_polyline + km
    print(f"[km_geolocator] Buscando KM {anchor_km_in_polyline:.1f} + {km:.1f} = {km_target:.1f} "
          f"en polilínea de {total_km:.1f} km")

    result = _find_km_on_polyline(polyline, cum_dists, km_target)

    if result:
        print(f"[km_geolocator] Localizado: {result[0]:.5f}, {result[1]:.5f}")
    else:
        print(f"[km_geolocator] KM {km_target:.1f} fuera de rango (máx {total_km:.1f} km)")

    return result