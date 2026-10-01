#!/usr/bin/env python3
"""Jednorazowe przygotowanie konturów Europy do mapy wątków (narzedzia/europa.json).

Źródło: world-atlas 2.0.2, countries-50m.json (Natural Earth, domena publiczna):
    npm pack world-atlas@2 && tar xzf world-atlas-2.0.2.tgz
    python3 narzedzia/mapa_dane.py package/countries-50m.json

Rzutowanie: Lambert azymutalny równopolowy, środek 15°E 52°N; kontury przycięte do kadru.
Wynik: {"szer": W, "wys": H, "kraje": {"PL": "M…Z", …}} – ścieżki SVG gotowe do wstawienia.
"""
import json
import math
import sys
from pathlib import Path

SZER, WYS = 600, 520
LON0, LAT0 = math.radians(15), math.radians(52)
# kadr w stopniach (przybliżony): od Islandii i Portugalii po Moskwę i Krym
KADR_LON = (-11.0, 42.0)
KADR_LAT = (37.0, 70.5)

# ISO 3166 numeryczne -> kod używany w build.py
KRAJE = {
    "616": "PL", "804": "UA", "643": "RU", "112": "BY", "276": "DE", "203": "CZ", "703": "SK",
    "348": "HU", "440": "LT", "428": "LV", "233": "EE", "578": "NO", "752": "SE", "246": "FI",
    "208": "DK", "352": "IS", "250": "FR", "826": "GB", "642": "RO", "688": "RS", "070": "BA",
    "191": "HR", "499": "ME", "807": "MK", "008": "AL", "705": "SI", "100": "BG", "300": "GR",
    "040": "AT", "756": "CH", "380": "IT", "724": "ES", "620": "PT", "056": "BE", "528": "NL",
    "442": "LU", "372": "IE", "498": "MD", "792": "TR", "196": "CY", "438": "LI", "470": "MT",
    "268": "GE", "051": "AM", "031": "AZ", "398": "KZ", "012": "DZ", "504": "MA", "788": "TN",
    "434": "LY", "760": "SY", "368": "IQ", "364": "IR", "818": "EG", "376": "IL", "422": "LB",
    "400": "JO", "020": "AD", "492": "MC", "674": "SM",
}
# punkty etykiet (lon, lat) dla krajów i grup z mapy wątków
ETYKIETY = {
    "PL": (19.2, 52.1), "UA": (31.5, 49.2), "RU": (38.5, 56.5), "KAL": (21.2, 54.75), "BY": (28.0, 53.5),
    "DE": (10.3, 51.1), "CZ": (15.3, 49.85), "SK": (19.6, 48.75), "HU": (19.2, 47.1), "LT": (24.0, 55.3),
    "LV": (25.3, 56.85), "EE": (25.8, 58.7), "SE": (15.5, 62.5), "FR": (2.4, 46.6), "GB": (-1.9, 52.8),
    "RO": (24.9, 45.9), "RS": (20.8, 43.9),
}
NAZWY = {"Kosovo": "XK", "N. Cyprus": "CY"}


def rzut(lon, lat):
    l, p = math.radians(lon), math.radians(lat)
    k = math.sqrt(2 / (1 + math.sin(LAT0) * math.sin(p) + math.cos(LAT0) * math.cos(p) * math.cos(l - LON0)))
    x = k * math.cos(p) * math.sin(l - LON0)
    y = k * (math.cos(LAT0) * math.sin(p) - math.sin(LAT0) * math.cos(p) * math.cos(l - LON0))
    return x, y


def granice():
    pts = []
    for i in range(41):
        lon = KADR_LON[0] + (KADR_LON[1] - KADR_LON[0]) * i / 40
        for lat in KADR_LAT:
            pts.append(rzut(lon, lat))
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    # środek kadru na dolnej krawędzi wyznacza dół, górne narożniki – szerokość
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    return x0, x1, y0, y1


def main(src):
    topo = json.loads(Path(src).read_text())
    sx, sy = topo["transform"]["scale"]
    tx, ty = topo["transform"]["translate"]
    arcs = []
    for a in topo["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in a:
            x += dx
            y += dy
            pts.append((x * sx + tx, y * sy + ty))
        arcs.append(pts)

    def arc(i):
        return arcs[i] if i >= 0 else list(reversed(arcs[~i]))

    def pierscien(idx):
        pts = []
        for i in idx:
            a = arc(i)
            pts.extend(a if not pts else a[1:])
        return pts

    x0, x1, y0, y1 = granice()
    # dopasuj skalę do kadru, zachowując proporcje
    skala = min(SZER / (x1 - x0), WYS / (y1 - y0))
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2

    def px(lon, lat):
        x, y = rzut(lon, lat)
        return (SZER / 2 + (x - cx) * skala, WYS / 2 - (y - cy) * skala)

    def przytnij(poly):
        """Sutherland–Hodgman do prostokąta kadru (z marginesem)."""
        m = 4
        for kraw in ((0, -m, 1), (0, SZER + m, -1), (1, -m, 1), (1, WYS + m, -1)):
            os_, gr, zn = kraw
            if not poly:
                return poly
            wyn = []
            for i in range(len(poly)):
                a, b = poly[i - 1], poly[i]
                wa, wb = (a[os_] - gr) * zn >= 0, (b[os_] - gr) * zn >= 0
                if wb:
                    if not wa:
                        t = (gr - a[os_]) / (b[os_] - a[os_])
                        wyn.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
                    wyn.append(b)
                elif wa:
                    t = (gr - a[os_]) / (b[os_] - a[os_])
                    wyn.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
            poly = wyn
        return poly

    def sciezka(polys):
        d = []
        for poly in polys:
            poly = przytnij(poly)
            if len(poly) < 3:
                continue
            prost, last = [], None
            for x, y in poly:
                p = (round(x), round(y))
                if last and abs(p[0] - last[0]) < 1.5 and abs(p[1] - last[1]) < 1.5:
                    continue
                prost.append(p)
                last = p
            if len(prost) < 3:
                continue
            d.append("M" + "L".join(f"{x:g},{y:g}" for x, y in prost) + "Z")
        return "".join(d)

    kraje = {}
    geoms = topo["objects"]["countries"]["geometries"]
    for g in geoms:
        kod = KRAJE.get(str(g.get("id"))) or NAZWY.get(g.get("properties", {}).get("name"))
        if not kod or g["type"] not in ("Polygon", "MultiPolygon"):
            continue
        wielo = [g["arcs"]] if g["type"] == "Polygon" else g["arcs"]
        polys, kalin, krym = [], [], []
        for poly in wielo:
            zew = pierscien(poly[0])
            lon_s = sum(p[0] for p in zew) / len(zew)
            lat_s = sum(p[1] for p in zew) / len(zew)
            if not any(KADR_LON[0] - 15 < lo < KADR_LON[1] + 15 and KADR_LAT[0] - 8 < la < KADR_LAT[1] + 5
                       for lo, la in zew):
                continue
            pp = [px(lo, la) for lo, la in zew]
            if kod == "RU" and lon_s < 23 and 54 < lat_s < 56:
                kalin.append(pp)
            elif kod == "RU" and 32 < lon_s < 37 and 44 < lat_s < 46.3:
                # Krym: w Natural Earth 50m przypisany Rosji; rysujemy w granicach Ukrainy uznanych przez ONZ
                krym.append(pp)
            else:
                polys.append(pp)
        s = sciezka(polys)
        if s:
            kraje[kod] = kraje.get(kod, "") + s
        if kalin:
            kraje["KAL"] = sciezka(kalin)
        if krym:
            kraje["UA_KRYM"] = sciezka(krym)
    if "UA_KRYM" in kraje:
        kraje["UA"] += kraje.pop("UA_KRYM")
    etykiety = {k: [round(c) for c in px(lo, la)] for k, (lo, la) in ETYKIETY.items()}
    wyj = Path(__file__).resolve().parent / "europa.json"
    wyj.write_text(json.dumps({"szer": SZER, "wys": WYS, "zrodlo": "Natural Earth 1:50m via world-atlas 2.0.2",
                               "kraje": kraje, "etykiety": etykiety}, ensure_ascii=False, separators=(",", ":")))
    print(f"{len(kraje)} konturów, {wyj.stat().st_size // 1024} KB -> {wyj}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "package/countries-50m.json")
