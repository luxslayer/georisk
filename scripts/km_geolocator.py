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

def _load_geojson(road: str | int) -> list[list[tuple[float, float]]]:
    """
    Carga el GeoJSON de la carretera y devuelve lista de segmentos.
    Acepta IDs numéricos (57) o alfanuméricos (40M).
    GeoJSON usa [lng, lat] — se invierte aquí.
    """
    path = os.path.join(ROADS_DIR, f"mex_{road}.geojson")
    if not os.path.exists(path):
        # Intentar en minúsculas por si el archivo es "mex_40m.geojson"
        path_lower = os.path.join(ROADS_DIR, f"mex_{str(road).lower()}.geojson")
        if os.path.exists(path_lower):
            path = path_lower
        else:
            print(f"[km_geolocator] Archivo no encontrado: {path}")
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
def _load_segments_cached(road: str | int) -> tuple:
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
    road: str | int,
    km: float,
    city_coords: tuple | None = None,
    known_segment: dict | None = None,
) -> tuple[float, float] | None:
    """
    Devuelve (lat, lng) del KM dado en la carretera especificada.

    Estrategia:
    1. Encuentra el segmento GeoJSON más cercano a coord_start
    2. Encadena greedy solo segmentos contiguos (salto < 1 km) hacia coord_end
    3. Interpola el KM exacto sobre esa polilínea limpia
    """
    segments = list(_load_segments_cached(road))
    if not segments:
        print(f"[km_geolocator] Sin GeoJSON para carretera {road}")
        return None

    # ── 1. Coordenadas de inicio y fin del tramo ──────────────────────────
    if known_segment and "coord_start" in known_segment and "coord_end" in known_segment:
        origin = known_segment["coord_start"]
        dest   = known_segment["coord_end"]
    elif city_coords and len(city_coords) == 4:
        origin = (city_coords[0], city_coords[1])
        dest   = (city_coords[2], city_coords[3])
    else:
        print(f"[km_geolocator] Sin coord_start/coord_end para MEX-{road}")
        return None

    # ── 2. Segmento GeoJSON más cercano a coord_start ─────────────────────
    best_seg_idx = min(
        range(len(segments)),
        key=lambda i: _nearest_point_on_segment(origin[0], origin[1], segments[i])
    )
    snap_dist = _nearest_point_on_segment(origin[0], origin[1], segments[best_seg_idx])
    print(f"[km_geolocator] Segmento origen: idx {best_seg_idx}, snap {snap_dist:.2f} km")

    # Orientar el segmento origen: el final debe apuntar hacia coord_end
    seg0 = list(segments[best_seg_idx])
    d_end_to_dest   = haversine(dest[0], dest[1], seg0[-1][0], seg0[-1][1])
    d_start_to_dest = haversine(dest[0], dest[1], seg0[0][0],  seg0[0][1])
    if d_start_to_dest < d_end_to_dest:
        seg0 = list(reversed(seg0))
    print(f"[km_geolocator] Segmento origen orientado hacia dest "
          f"(d_tail_to_dest={min(d_end_to_dest, d_start_to_dest):.1f} km)")

    # ── 3. Encadenar segmentos contiguos hacia coord_end ──────────────────
    MAX_GAP_KM = 1.0   # máximo salto permitido entre segmentos contiguos
    MAX_TOTAL_KM = (known_segment["km_end"] - known_segment["km_start"]) * 1.5 \
                   if known_segment else 500.0

    chain = seg0
    used = {best_seg_idx}

    for _ in range(len(segments)):
        tail = chain[-1]
        best_next = None
        best_gap  = float("inf")

        for i, seg in enumerate(segments):
            if i in used:
                continue
            # Distancia del final de la cadena al inicio o fin del candidato
            d_start = haversine(tail[0], tail[1], seg[0][0],  seg[0][1])
            d_end   = haversine(tail[0], tail[1], seg[-1][0], seg[-1][1])
            d = min(d_start, d_end)
            if d < best_gap:
                best_gap  = d
                best_next = (i, d_end < d_start)  # flip si conecta por el final

        if best_next is None or best_gap > MAX_GAP_KM:
            break

        next_idx, flip = best_next
        seg = list(segments[next_idx])
        if flip:
            seg = list(reversed(seg))

        # Evitar duplicar punto de unión
        if haversine(chain[-1][0], chain[-1][1], seg[0][0], seg[0][1]) < 0.01:
            chain = chain + seg[1:]
        else:
            chain = chain + seg

        used.add(next_idx)

        # Parar si ya llegamos cerca de coord_end
        dist_to_dest = haversine(dest[0], dest[1], chain[-1][0], chain[-1][1])
        cum_so_far   = sum(
            haversine(chain[i-1][0], chain[i-1][1], chain[i][0], chain[i][1])
            for i in range(1, min(len(chain), 10))  # estimación rápida
        )
        total_so_far = _cumulative_distances(chain)[-1]

        if dist_to_dest < 5.0 or total_so_far > MAX_TOTAL_KM:
            break

    cum_dists = _cumulative_distances(chain)
    total_km  = cum_dists[-1]
    print(f"[km_geolocator] Polilínea: {len(chain)} pts, {total_km:.1f} km "
          f"({len(used)} segmentos encadenados)")

    # ── 4. Interpolar KM exacto ───────────────────────────────────────────
    result = _find_km_on_polyline(chain, cum_dists, km)

    if result:
        print(f"[km_geolocator] Localizado: {result[0]:.5f}, {result[1]:.5f}")
    else:
        print(f"[km_geolocator] KM {km:.1f} fuera de rango (máx {total_km:.1f} km)")

    return result