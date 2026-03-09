import requests
import xml.etree.ElementTree as ET
import json
import re
import unicodedata
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from km_geolocator import locate_km
from city_locator import detect_segment, segment_coords, interpolate
from data.cities import cities
from data.routes import routes
from data.road_segments import road_segments

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

incidents = []

TWITTER_RSS = [
    "https://nitter.net/GN_Carreteras/rss",
    "https://nitter.net/CAPUFE/rss",
]

RISK_WORDS = [
    "balacera",
    "robo",
    "asalto",
    "bloqueo",
    "enfrentamiento",
    "incendio",
    "violencia",
    "accidente",
    "obras",
]

# ---------------------------------------------------------------------------
# Normalización
# ---------------------------------------------------------------------------

def split_hashtags(text: str) -> str:
    """
    Convierte hashtags CamelCase en palabras separadas antes de normalizar.
    '#AutMéxicoCuernavaca' → 'Aut México Cuernavaca'
    '#EdoMéx'             → 'Edo Méx'
    """
    def expand(m):
        tag = m.group(1)
        return re.sub(r'(?<=[a-záéíóúüñ])(?=[A-ZÁÉÍÓÚÜÑ])', ' ', tag)
    return re.sub(r'#([A-Za-záéíóúüñ][^\s]*)', expand, text)


def normalize(text: str) -> str:
    """Minúsculas, sin acentos, sin puntuación, espacios simples."""
    text = split_hashtags(text)
    text = text.lower()
    text = text.replace("-", " ").replace("#", " ")
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

# ---------------------------------------------------------------------------
# Detección de ciudades
# ---------------------------------------------------------------------------

def detect_cities(text: str) -> list[str]:
    """
    Busca cada clave del diccionario cities como subcadena normalizada.
    Devuelve la lista ordenada de mayor a menor longitud para que
    "san luis potosi" tenga precedencia sobre "san luis".
    """
    text_norm = normalize(text)
    found = [city for city in cities if normalize(city) in text_norm]
    found.sort(key=len, reverse=True)
    return found


def detect_city(text: str) -> tuple[float, float] | None:
    """Devuelve las coordenadas de la primera ciudad detectada, o None."""
    found = detect_cities(text)
    if found:
        return cities[found[0]]
    return None

# ---------------------------------------------------------------------------
# Detección de KM
# ---------------------------------------------------------------------------

def detect_km(text: str) -> float | None:
    """
    Detecta expresiones como 'km 45', 'km45', 'km 45+300'.
    Devuelve el valor como float (ej. 45.3) o None.
    """
    m = re.search(r"km\s*(\d+)(?:[+\-](\d+))?", text.lower())
    if m:
        km = int(m.group(1))
        if m.group(2):
            km += int(m.group(2)) / 1000
        return km
    return None

# ---------------------------------------------------------------------------
# Detección de riesgo
# ---------------------------------------------------------------------------

def detect_risk(text: str) -> str:
    text_norm = normalize(text)
    for word in RISK_WORDS:
        if word in text_norm:
            return "high"
    return "normal"

# ---------------------------------------------------------------------------
# Detección de carretera
# ---------------------------------------------------------------------------

def detect_city_pair(text: str) -> tuple[str, str] | None:
    """
    Extrae el par de ciudades de expresiones como 'carretera Puebla-Oaxaca'.
    Busca ANTES de normalizar para que el guión siga presente.
    Fallback: detecta ciudades conocidas dentro del texto tras 'carretera'.
    """
    # 1. Buscar patrón "carretera X-Y" en texto solo lowercased (guión intacto)
    m = re.search(
        r"carretera\s+([a-záéíóúüñ\s]+?)\s*[-–]\s*([a-záéíóúüñ\s]+?)(?:\s|,|\.|$)",
        text.lower(),
    )
    if m:
        c1 = normalize(m.group(1).strip())
        c2 = normalize(m.group(2).strip())
        return c1, c2

    # 2. Fallback: ciudades conocidas consecutivas tras "carretera"
    text_norm = normalize(text)
    m2 = re.search(r"carretera\s+([a-z\s]+)", text_norm)
    if m2:
        segment_text = m2.group(1)
        cities_in_segment = [c for c in cities if normalize(c) in segment_text]
        cities_in_segment.sort(key=len, reverse=True)
        if len(cities_in_segment) >= 2:
            return cities_in_segment[0], cities_in_segment[1]

    return None


def detect_road_from_cities(city_pair: tuple[str, str]) -> int | None:
    """
    Busca la carretera dado un par de ciudades.
    Maneja ambas direcciones sin necesitar entradas duplicadas en routes.
    """
    c1, c2 = city_pair
    for (a, b), road in routes.items():
        if (c1 == a and c2 == b) or (c1 == b and c2 == a):
            return road
    return None


def detect_road(text: str) -> int | None:
    """
    Detecta número de carretera por:
    1. Número explícito ('carretera 57', 'autopista 15', 'mex 130')
    2. Par de ciudades mencionadas ('carretera Querétaro-SLP')
    """
    text_norm = normalize(text)

    # 1. Número directo
    m = re.search(r"(?:carretera|autopista|mex)\s*(\d+)", text_norm)
    if m:
        return int(m.group(1))

    # 2. Par de ciudades
    pair = detect_city_pair(text_norm)
    if pair:
        road = detect_road_from_cities(pair)
        if road:
            return road

    return None

# ---------------------------------------------------------------------------
# Segmento conocido
# ---------------------------------------------------------------------------

def detect_known_segment(road: int | None, cities_found: list[str]) -> dict | None:
    """
    Dado un número de carretera y una lista de ciudades detectadas,
    devuelve el segmento de road_segments que contenga ambas ciudades.
    """
    if road is None or road not in road_segments:
        return None

    cities_set = set(cities_found)
    for seg in road_segments[road]:
        c1, c2 = seg["cities"]
        if c1 in cities_set and c2 in cities_set:
            return seg

    return None


def km_relative(km: float, segment: dict) -> float:
    """Convierte un KM absoluto de la carretera a relativo dentro del segmento."""
    return max(km - segment["km_start"], 0)

# ---------------------------------------------------------------------------
# Procesamiento de tweet
# ---------------------------------------------------------------------------

DEFAULT_LAT, DEFAULT_LNG = 23.5, -102.0  # centro aproximado de México


def parse_pubdate(raw: str | None) -> datetime | None:
    """
    Parsea la fecha RSS (RFC 2822) y la devuelve como datetime UTC aware.
    Ej: 'Mon, 09 Mar 2026 14:32:00 +0000' → datetime(2026, 3, 9, 14, 32, tzinfo=UTC)
    """
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def process_tweet(title: str, url: str, pub_date: str | None = None) -> None:
    if not title:
        return

    # Fecha/hora del tweet
    dt = parse_pubdate(pub_date)
    now_utc = datetime.now(timezone.utc)

    # Filtrar incidentes con más de 24 horas
    if dt and (now_utc - dt) > timedelta(hours=24):
        print(f"SKIP (>24h): {title}")
        return

    timestamp_iso = dt.isoformat() if dt else None
    timestamp_display = dt.strftime("%d/%m/%Y %H:%M UTC") if dt else "Fecha desconocida"

    # Coordenadas por defecto
    lat, lng = DEFAULT_LAT, DEFAULT_LNG

    # Ciudad más probable
    city_coords = detect_city(title)
    if city_coords:
        lat, lng = city_coords

    # Segmento entre dos ciudades (de city_locator externo)
    try:
        segment = detect_segment(title)
    except Exception:
        segment = None

    # Ciudades mencionadas
    cities_found = detect_cities(title)

    # Carretera
    road = None
    if segment:
        road = detect_road_from_cities(segment)
    if road is None:
        road = detect_road(title)

    # KM
    km = detect_km(title)

    # Segmento conocido en road_segments
    known_segment = detect_known_segment(road, cities_found)
    if km is not None and known_segment:
        km = km_relative(km, known_segment)
        print("RELATIVE KM:", km)

    # Riesgo
    risk = detect_risk(title)

    print(f"TWEET : {title}")
    print(f"ROAD  : {road}  |  KM: {km}")

    # Geolocalización fina
    if road is not None and km is not None:
        seg_coords = None
        if segment:
            cityA, cityB = segment
            lat1, lon1, lat2, lon2 = segment_coords(cityA, cityB)
            seg_coords = (lat1, lon1, lat2, lon2)

        print("KNOWN SEGMENT:", known_segment)
        point = locate_km(road, km, seg_coords, known_segment)

        if point:
            lat, lng = point
        elif segment:
            lat  = (lat1 + lat2) / 2
            lng = (lon1 + lon2) / 2
        # si no hay nada, lat/lng ya tiene la ciudad detectada o el default

        print("LOCATE RESULT:", point)

    incidents.append({
        "title":             title,
        "type":              "twitter",
        "lat":               lat,
        "lng":               lng,
        "road":              road,
        "km":                km,
        "risk":              risk,
        "url":               url,
        "timestamp":         timestamp_iso,
        "timestamp_display": timestamp_display,
    })

# ---------------------------------------------------------------------------
# Ingesta RSS
# ---------------------------------------------------------------------------

def fetch_rss(feed_url: str) -> None:
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(feed_url, headers=headers, timeout=10)
        print(f"Status [{feed_url}]: {r.status_code}")

        root = ET.fromstring(r.content)
        for item in root.findall(".//item")[:50]:
            title    = item.findtext("title")
            link     = item.findtext("link")
            pub_date = item.findtext("pubDate")
            process_tweet(title, link, pub_date)

    except Exception as e:
        print(f"RSS error ({feed_url}): {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Fetching Twitter RSS")
    for feed in TWITTER_RSS:
        fetch_rss(feed)

    data = {
        "last_update": datetime.utcnow().isoformat(),
        "incidents":   incidents,
    }

    with open("incidents.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Saved {len(incidents)} incidents")