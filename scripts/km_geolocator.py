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


def _chain_segments_anchored(
    segments: list[list[tuple[float, float]]],
    anchor_lat: float,
    anchor_lng: float,
    max_dist_km: float = 80.0,
) -> list[tuple[float, float]]:
    """
    Encadena solo los segmentos dentro de max_dist_km del punto ancla,
    ordenándolos por proximidad al ancla primero y luego greedy entre sí.
    """
    # Filtrar segmentos cercanos al ancla
    nearby = [
        s for s in segments
        if _nearest_point_on_segment(anchor_lat, anchor_lng, s) <= max_dist_km
    ]

    if not nearby:
        # Ampliar el radio si no hay nada cercano
        nearby = sorted(segments, key=lambda s: _nearest_point_on_segment(anchor_lat, anchor_lng, s))
        nearby = nearby[:min(20, len(nearby))]

    if not nearby:
        return []

    # Ordenar por distancia al ancla
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

        # No encadenar si el salto es demasiado grande (> 5 km → probable ramal)
        if best_dist > 5.0:
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
# Recorte por segmento conocido
# ---------------------------------------------------------------------------

def _clip_polyline_to_segment(
    polyline: list[tuple[float, float]],
    cum_dists: list[float],
    km_start: float,
    km_end: float,
) -> tuple[list[tuple[float, float]], list[float]]:
    """
    Recorta la polilínea al rango [km_start, km_end].
    Útil cuando el KM del tweet es relativo al segmento, no a la carretera completa.
    """
    clipped = []
    clipped_dists = []

    for i, (point, d) in enumerate(zip(polyline, cum_dists)):
        if km_start <= d <= km_end:
            clipped.append(point)
            clipped_dists.append(d - km_start)  # relativo al inicio del segmento

    return clipped, clipped_dists


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

    Args:
        road:          Número de carretera (ej. 57)
        km:            Kilómetro a localizar (relativo al segmento si known_segment existe)
        city_coords:   (lat1, lon1, lat2, lon2) de las ciudades del tramo — usado como ancla
        known_segment: Dict con 'km_start', 'km_end' y 'cities' si el KM es relativo

    Returns:
        (lat, lng) o None si no se pudo localizar
    """
    from data.cities import cities as cities_dict

    segments = list(_load_segments_cached(road))
    if not segments:
        print(f"[km_geolocator] Sin GeoJSON para carretera {road}")
        return None

    # Determinar punto ancla para filtrar segmentos relevantes
    anchor_lat, anchor_lng = None, None

    if city_coords and len(city_coords) == 4:
        # Promedio de las dos ciudades del tramo
        anchor_lat = (city_coords[0] + city_coords[2]) / 2
        anchor_lng = (city_coords[1] + city_coords[3]) / 2

    elif known_segment:
        # Usar coordenadas de las ciudades del segmento conocido
        c1, c2 = known_segment["cities"]
        coord1 = cities_dict.get(c1)
        coord2 = cities_dict.get(c2)
        if coord1 and coord2:
            anchor_lat = (coord1[0] + coord2[0]) / 2
            anchor_lng = (coord1[1] + coord2[1]) / 2
        elif coord1:
            anchor_lat, anchor_lng = coord1
        elif coord2:
            anchor_lat, anchor_lng = coord2

    if anchor_lat is None:
        # Sin ancla: usar centroide de México como fallback
        anchor_lat, anchor_lng = 23.5, -102.0

    # Construir polilínea anclada al tramo de interés
    polyline = _chain_segments_anchored(segments, anchor_lat, anchor_lng)
    if not polyline:
        print(f"[km_geolocator] No se pudo construir polilínea para MEX-{road}")
        return None

    cum_dists = _cumulative_distances(polyline)
    total_km  = cum_dists[-1]

    print(f"[km_geolocator] MEX-{road}: {len(polyline)} puntos, {total_km:.1f} km (tramo anclado)")

    # Convertir KM relativo a absoluto dentro de la polilínea anclada
    # La polilínea ya está recortada al tramo → el KM relativo se usa directo
    if known_segment:
        # km ya viene relativo al km_start del segmento desde main.py
        km_target = km
        print(f"[km_geolocator] Buscando KM relativo {km_target:.1f} en tramo de {total_km:.1f} km")
    else:
        km_target = km
        print(f"[km_geolocator] Buscando KM {km_target:.1f} en tramo de {total_km:.1f} km")

    result = _find_km_on_polyline(polyline, cum_dists, km_target)

    if result:
        print(f"[km_geolocator] Localizado: {result[0]:.5f}, {result[1]:.5f}")
    else:
        print(f"[km_geolocator] KM {km_target} fuera de rango (máx {total_km:.1f} km)")

    return result