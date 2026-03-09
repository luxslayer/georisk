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

ROADS_DIR = os.path.join(os.path.dirname(__file__), "roads")


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


def _dist_endpoints(a: list, b: list) -> float:
    """Distancia mínima entre los extremos de dos segmentos."""
    return min(
        haversine(a[-1][0], a[-1][1], b[0][0],  b[0][1]),
        haversine(a[-1][0], a[-1][1], b[-1][0], b[-1][1]),
        haversine(a[0][0],  a[0][1],  b[0][0],  b[0][1]),
        haversine(a[0][0],  a[0][1],  b[-1][0], b[-1][1]),
    )


def _chain_segments(segments: list) -> list[tuple[float, float]]:
    """
    Une los segmentos en una sola polilínea ordenada conectando
    cada segmento al extremo más cercano del anterior.
    Invierte segmentos si es necesario para mantener continuidad.
    """
    if not segments:
        return []

    # Empezar con el segmento más largo como ancla
    remaining = sorted(segments, key=len, reverse=True)
    chain = list(remaining.pop(0))

    while remaining:
        best_idx = 0
        best_dist = float("inf")
        best_flip = False

        for i, seg in enumerate(remaining):
            # ¿conecta mejor al inicio o al final de la cadena actual?
            d_end_start = haversine(chain[-1][0], chain[-1][1], seg[0][0],  seg[0][1])
            d_end_end   = haversine(chain[-1][0], chain[-1][1], seg[-1][0], seg[-1][1])
            d = min(d_end_start, d_end_end)
            flip = d_end_end < d_end_start
            if d < best_dist:
                best_dist = d
                best_idx = i
                best_flip = flip

        seg = remaining.pop(best_idx)
        if best_flip:
            seg = list(reversed(seg))

        # Evitar duplicar el punto de unión si están muy cerca (< 50 m)
        if haversine(chain[-1][0], chain[-1][1], seg[0][0], seg[0][1]) < 0.05:
            chain.extend(seg[1:])
        else:
            chain.extend(seg)

    return chain


@lru_cache(maxsize=32)
def _build_polyline(road: int) -> list[tuple[float, float]]:
    """Carga y encadena la polilínea completa de una carretera (cacheada)."""
    segments = _load_geojson(road)
    return _chain_segments(segments)


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
    city_coords: tuple | None = None,   # mantenido por compatibilidad, no usado
    known_segment: dict | None = None,
) -> tuple[float, float] | None:
    """
    Devuelve (lat, lng) del KM dado en la carretera especificada.

    Args:
        road:          Número de carretera (ej. 57)
        km:            Kilómetro a localizar
        city_coords:   Ignorado (mantenido por compatibilidad con versión anterior)
        known_segment: Dict con 'km_start' y 'km_end' si el KM es relativo al segmento

    Returns:
        (lat, lng) o None si no se pudo localizar
    """
    polyline = _build_polyline(road)
    if not polyline:
        print(f"[km_geolocator] Sin GeoJSON para carretera {road}")
        return None

    cum_dists = _cumulative_distances(polyline)
    total_km  = cum_dists[-1]

    print(f"[km_geolocator] MEX-{road}: {len(polyline)} puntos, {total_km:.1f} km totales")

    # Si hay segmento conocido y el KM es relativo, convertir a absoluto
    if known_segment:
        km_abs = known_segment["km_start"] + km
        print(f"[km_geolocator] KM relativo {km} → absoluto {km_abs} (offset {known_segment['km_start']})")
    else:
        km_abs = km

    result = _find_km_on_polyline(polyline, cum_dists, km_abs)

    if result:
        print(f"[km_geolocator] Localizado: {result[0]:.5f}, {result[1]:.5f}")
    else:
        print(f"[km_geolocator] KM {km_abs} fuera de rango (máx {total_km:.1f} km)")

    return result