#!/usr/bin/env python3
"""Generator strony „Prasówka” (GitHub Pages) z danych w katalogu dane/.

Użycie:
    python3 narzedzia/build.py            # walidacja + budowa strony w katalogu repozytorium
    python3 narzedzia/build.py --sprawdz  # tylko walidacja
    python3 narzedzia/build.py --dane INNY_KATALOG --wyjscie INNY_KATALOG  # np. test

Znaczniki w tekstach:
    **słowo**         wyróżnione słowo kluczowe
    {{o:id}}          osoba z dane/osoby.json (link do karty; przy pierwszym użyciu z funkcją)
    {{o:id|tekst}}    osoba, własny tekst linku
    {{p:id}}          pojęcie z dane/pojecia.json
    {{p:id|tekst}}    pojęcie, własny tekst linku
"""
import argparse
import datetime as dt
import html
import json
import math
import re
import shutil
import sys
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

REPO = Path(__file__).resolve().parent.parent
BASE_URL = "https://raa82892-bot.github.io/prasowka/"
TYTUL = "Prasówka"
PODTYTUL = "Przegląd sytuacji międzynarodowej"

BLOKI = [
    ("wojna", "Wojna i sankcje"),
    ("polska", "Polska"),
    ("instytucje", "Instytucje i Europa"),
    ("swiat", "Świat"),
    ("gospodarka", "Gospodarka"),
]
# Do zarysu wchodzą wyłącznie informacje potwierdzone; pola „status” nie ma (walidacja je odrzuca).
# Pozycje oznaczone tak przed 01.10.2026 przeszły rewizję — zapis w dane/rewizje.json.
ETAPY = {None, "PROPOZYCJA", "ZAPOWIEDŹ", "PRZYJĘTE", "W TOKU"}
PROGI = {"dokumentacja", "następstwo", "kompletność"}
WERDYKTY = {"POTWIERDZONE", "SPROSTOWANE", "NADAL OTWARTE"}
MAPA_TLO = ["#F1F3F6", "#C9D3E6", "#6F86B3", "#1F2A44"]
DNI = ["poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"]
DNI_KROTKO = ["pon", "wt", "śr", "czw", "pt", "sob", "nd"]
MIESIACE = ["stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca",
            "sierpnia", "września", "października", "listopada", "grudnia"]
MIESIACE_MIAN = ["Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec", "Lipiec",
                 "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień"]
# mapa wątków: hashtag-miejsce -> kontury z narzedzia/europa.json (pierwszy kod = miejsce etykiety)
MAPA_TAGI = {
    "ukraina": ["UA"], "rosja": ["RU"], "kaliningrad": ["KAL"], "bialorus": ["BY"], "niemcy": ["DE"],
    "czechy": ["CZ"], "slowacja": ["SK"], "wegry": ["HU"], "litwa": ["LT"], "lotwa": ["LV"],
    "estonia": ["EE"], "nordyckie": ["SE", "NO", "FI", "DK", "IS"], "francja": ["FR"],
    "wielka-brytania": ["GB"], "rumunia": ["RO"], "balkany": ["RS", "BA", "ME", "MK", "AL", "XK", "HR"],
}
EUROPA = json.loads((Path(__file__).resolve().parent / "europa.json").read_text("utf-8"))
GENEROWANE = ["index.html", "wydania", "watki", "osoby", "pojecia", "korekty.html", "zrodla.html",
              "jak-weryfikujemy.html", "szukaj.html", "szukaj.json", "feed.xml",
              "robots.txt", ".nojekyll", "assets", "404.html"]


# ---------------------------------------------------------------- dane

def wczytaj(katalog: Path):
    tagi = json.loads((katalog / "tagi.json").read_text("utf-8"))["tagi"]
    osoby = json.loads((katalog / "osoby.json").read_text("utf-8"))["osoby"]
    pojecia = json.loads((katalog / "pojecia.json").read_text("utf-8"))["pojecia"]
    wydania = []
    for p in sorted((katalog / "wydania").glob("*.json")):
        w = json.loads(p.read_text("utf-8"))
        w["_plik"] = p.name
        w["_slug"] = p.stem
        wydania.append(w)
    wydania.sort(key=lambda w: (w["data"], w.get("godzina", "")))
    p = katalog / "rewizje.json"
    rewizje = json.loads(p.read_text("utf-8"))["rewizje"] if p.exists() else []
    return ({t["id"]: t for t in tagi}, {o["id"]: o for o in osoby},
            {x["id"]: x for x in pojecia}, wydania, rewizje)


# ---------------------------------------------------------------- ranking źródeł

class Ranking:
    """Ranking wiarygodności z dane/zrodla.json: dopasowanie po początku nazwy, potem po domenie."""

    def __init__(self, dane):
        self.dane = dane
        self.poziomy = {p["poziom"]: p for p in dane["poziomy"]}
        self.zrodla = dane["zrodla"]
        wz = [(w, z) for z in self.zrodla for w in z.get("wzorce", [])]
        wz.sort(key=lambda x: -len(x[0]))
        self.wzorce = [(re.compile(r"^" + re.escape(w) + r"(?![\w])"), z) for w, z in wz]
        self.domeny = sorted(((d, z) for z in self.zrodla for d in z.get("domeny", [])), key=lambda x: -len(x[0]))

    def ocen(self, nazwa, url):
        nazwa = (nazwa or "").strip()
        for r, z in self.wzorce:
            if r.match(nazwa):
                return z
        host = re.sub(r"^www\.", "", re.sub(r"^https?://([^/]+).*$", r"\1", url or "")).lower()
        for d, z in self.domeny:
            if host == d or host.endswith("." + d):
                return z
        return None


RANKING = None
# Od tej daty walidacja wymaga przy każdej pozycji zarysu: źródła z poziomu 1 albo dwóch niezależnych
# źródeł z poziomów 1–2 (poziomy 3–5 się nie liczą do podstawy).
DWA_ZRODLA_OD = "2026-10-01"


def podstawa_ok(zrodla, ranking=None):
    r = ranking or RANKING
    oc = [r.ocen(z.get("nazwa"), z.get("url")) for z in zrodla]
    oc = [o for o in oc if o]
    if any(o["poziom"] == 1 for o in oc):
        return True
    niezalezne = {o["id"] for o in oc if o["poziom"] <= 2}
    return len(niezalezne) >= 2


def wczytaj_ranking(katalog: Path):
    p = katalog / "zrodla.json"
    return Ranking(json.loads(p.read_text("utf-8"))) if p.exists() else None


def kropka(z, prefix="", ranking=None):
    """Kolorowy znacznik wiarygodności przed nazwą źródła."""
    r = ranking or RANKING
    if not r:
        return ""
    o = r.ocen(z.get("nazwa"), z.get("url"))
    if not o:
        return ""
    p = r.poziomy[o["poziom"]]
    return (f'<span class="wz wz{o["poziom"]}" title="Wiarygodność {o["poziom"]}/5 – {e(p["nazwa"])} ({e(o["nazwa"])})" '
            f'aria-label="wiarygodność {o["poziom"]} z 5: {e(p["nazwa"])}"></span>')


def wszystkie_zrodla(o):
    """Generator wszystkich źródeł (słowników z url) w strukturze danych."""
    if isinstance(o, dict):
        if "url" in o and ("nazwa" in o or "tytul" in o):
            yield {"nazwa": o.get("nazwa") or o.get("wydawca") or "", "url": o["url"]}
        for k, v in o.items():
            if k not in ("bylo_zrodla", "pozycja"):
                yield from wszystkie_zrodla(v)
    elif isinstance(o, list):
        for v in o:
            yield from wszystkie_zrodla(v)


def data_(s):
    return dt.date.fromisoformat(s)


# ---------------------------------------------------------------- walidacja

class Bledy(list):
    def dodaj(self, gdzie, co):
        self.append(f"{gdzie}: {co}")


URL_RE = re.compile(r"^https?://[^\s]+$")
ZNACZNIK_RE = re.compile(r"\{\{([op]):([a-z0-9-]+)(?:\|([^}]*))?\}\}")


def sprawdz_zrodla(zrodla, gdzie, b: Bledy, wymagane=True):
    if not zrodla:
        if wymagane:
            b.dodaj(gdzie, "brak źródeł — pozycja bez źródła nie może trafić na stronę")
        return
    for i, z in enumerate(zrodla):
        if not z.get("nazwa"):
            b.dodaj(gdzie, f"źródło {i+1}: brak nazwy serwisu")
        elif "tytuł" in z["nazwa"].lower():
            b.dodaj(gdzie, f"źródło {i+1} ({z['nazwa']}): sam tytuł nie jest źródłem — otwórz artykuł albo znajdź inne")
        if not URL_RE.match(z.get("url", "")):
            b.dodaj(gdzie, f"źródło {i+1}: brak poprawnego linku (http/https)")
        try:
            data_(z.get("data", ""))
        except ValueError:
            b.dodaj(gdzie, f"źródło {i+1}: brak daty publikacji RRRR-MM-DD")


def sprawdz_tekst(tekst, gdzie, osoby, pojecia, b: Bledy):
    if not tekst or not tekst.strip():
        b.dodaj(gdzie, "pusty tekst")
        return
    for m in ZNACZNIK_RE.finditer(tekst):
        rodzaj, ident = m.group(1), m.group(2)
        if rodzaj == "o" and ident not in osoby:
            b.dodaj(gdzie, f"osoba „{ident}” nie ma karty w dane/osoby.json")
        if rodzaj == "p" and ident not in pojecia:
            b.dodaj(gdzie, f"pojęcie „{ident}” nie ma hasła w dane/pojecia.json")


def sprawdz_tagi(lista, gdzie, tagi, b: Bledy, wymagane=True):
    if wymagane and not lista:
        b.dodaj(gdzie, "brak hashtagów")
    for t in lista or []:
        if t not in tagi:
            b.dodaj(gdzie, f"hashtag „{t}” spoza słownika dane/tagi.json")


def waliduj(tagi, osoby, pojecia, wydania, rewizje=()) -> Bledy:
    b = Bledy()
    for t in tagi.values():
        if t.get("stan"):
            try:
                data_(t.get("stan_data", ""))
            except ValueError:
                b.dodaj(f"tag {t['id']}", "stan bez daty stan_data")
            sprawdz_zrodla(t.get("stan_zrodla"), f"tag {t['id']} (stan)", b)
    for o in osoby.values():
        g = f"osoba {o.get('id')}"
        for pole in ("imie", "funkcja", "zweryfikowano"):
            if not o.get(pole):
                b.dodaj(g, f"brak pola {pole}")
        sprawdz_zrodla(o.get("zrodla"), g, b)
    klucze = set()
    for w in wydania:
        g0 = w["_plik"]
        for pole in ("nr", "data", "godzina", "w_skrocie", "zarys"):
            if pole not in w:
                b.dodaj(g0, f"brak pola {pole}")
        try:
            data_(w.get("data", ""))
        except ValueError:
            b.dodaj(g0, "zła data wydania")
        if w.get("typ", "dzienne") not in ("dzienne", "tygodniowe"):
            b.dodaj(g0, "typ musi być dzienne albo tygodniowe")
        ids = set()
        for it in w.get("zarys", []):
            g = f"{g0} zarys {it.get('id')}"
            if not it.get("id") or it["id"] in ids:
                b.dodaj(g, "brak lub powtórzone id pozycji")
            ids.add(it.get("id"))
            klucze.add(f"{w['_slug']}#{it.get('id')}")
            if it.get("blok") not in dict(BLOKI):
                b.dodaj(g, f"blok musi być jednym z: {', '.join(dict(BLOKI))}")
            try:
                data_(it.get("data", ""))
            except ValueError:
                b.dodaj(g, "brak daty zdarzenia RRRR-MM-DD")
            if RANKING and w.get("data", "") >= DWA_ZRODLA_OD and it.get("zrodla") and not podstawa_ok(it["zrodla"]):
                b.dodaj(g, "za słaba podstawa: potrzebne źródło urzędowe (poziom 1) albo dwa niezależne z poziomów 1–2 "
                           "(źródła z poziomów 3–5 nie liczą się do podstawy; zob. zrodla.html)")
            if "status" in it:
                b.dodaj(g, f"pole status ({it['status']}) — do zarysu wchodzą tylko informacje potwierdzone; "
                           "niepotwierdzone przenieś do „Czego tu nie ma” (próg: dokumentacja)")
            if it.get("etap") not in ETAPY:
                b.dodaj(g, f"etap musi być jednym z {sorted(s for s in ETAPY if s)}")
            sprawdz_tagi(it.get("tagi"), g, tagi, b)
            sprawdz_tekst(it.get("tekst"), g, osoby, pojecia, b)
            sprawdz_zrodla(it.get("zrodla"), g, b)
        for i, a in enumerate(w.get("analizy", [])):
            g = f"{g0} analiza {i+1}"
            for pole in ("tytul", "autor", "tekst", "dla_polski"):
                if not a.get(pole):
                    b.dodaj(g, f"brak pola {pole} (ocena zawsze z autorem i wnioskiem dla Polski)")
            sprawdz_tagi(a.get("tagi"), g, tagi, b)
            sprawdz_tekst(a.get("tekst"), g, osoby, pojecia, b)
            sprawdz_zrodla(a.get("zrodla"), g, b)
        for i, k in enumerate(w.get("kalendarz", []) + w.get("poza_oknem", [])):
            g = f"{g0} kalendarz {i+1}"
            try:
                data_(k.get("data", ""))
            except ValueError:
                b.dodaj(g, "brak daty RRRR-MM-DD")
            sprawdz_tagi(k.get("tagi"), g, tagi, b, wymagane=False)
            sprawdz_zrodla(k.get("zrodla"), g, b, wymagane=False)
        for strona in ("osw", "pism"):
            for i, p in enumerate((w.get("zrodla_analityczne") or {}).get(strona, [])):
                sprawdz_zrodla([{"nazwa": strona.upper(), "url": p.get("url", ""), "data": p.get("data", "")}],
                               f"{g0} {strona} {i+1}", b)
        for i, c in enumerate(w.get("czego_nie_ma", [])):
            if c.get("prog") not in PROGI:
                b.dodaj(f"{g0} czego_nie_ma {i+1}", f"prog musi być jednym z {sorted(PROGI)}")
        # pola tygodniówki
        m = w.get("mapa_ciepla")
        if m:
            g = f"{g0} mapa_ciepla"
            kol = m.get("kolumny", [])
            for d in kol:
                try:
                    data_(d)
                except ValueError:
                    b.dodaj(g, f"kolumna „{d}” nie jest datą RRRR-MM-DD")
            for r in m.get("wiersze", []):
                if r.get("tag") not in tagi:
                    b.dodaj(g, f"wiersz z hashtagiem spoza słownika: {r.get('tag')}")
                wart = r.get("wartosci", [])
                if len(wart) != len(kol) or any(v not in (0, 1, 2, 3) for v in wart):
                    b.dodaj(g, f"wiersz {r.get('tag')}: wartości 0–3, tyle ile kolumn")
                for pole in ("odnosniki", "sprostowane"):
                    if pole in r and len(r[pole]) != len(kol):
                        b.dodaj(g, f"wiersz {r.get('tag')}: {pole} musi mieć tyle elementów, ile kolumn")
        for i, t in enumerate(w.get("tracker", [])):
            g = f"{g0} tracker {i+1}"
            if t.get("tag") not in tagi:
                b.dodaj(g, "hashtag spoza słownika")
            if t.get("kierunek") not in ("↑", "↓", "→"):
                b.dodaj(g, "kierunek musi być ↑, ↓ albo →")
            for pole in ("tydzien_temu", "dzis"):
                if not t.get(pole):
                    b.dodaj(g, f"brak pola {pole}")
        for i, c in enumerate(w.get("czytelnia", [])):
            g = f"{g0} czytelnia {i+1}"
            for pole in ("tytul", "po_co"):
                if not c.get(pole):
                    b.dodaj(g, f"brak pola {pole}")
            sprawdz_zrodla([{"nazwa": c.get("wydawca", "?"), "url": c.get("url", ""), "data": c.get("data", "")}], g, b)
    for w in wydania:
        for i, k in enumerate(w.get("weryfikacja", [])):
            g = f"{w['_plik']} weryfikacja {i+1}"
            if k.get("werdykt") not in WERDYKTY:
                b.dodaj(g, f"werdykt musi być jednym z {sorted(WERDYKTY)}")
            if k.get("dotyczy") and k["dotyczy"] not in klucze:
                b.dodaj(g, f"dotyczy nieistniejącej pozycji {k['dotyczy']}")
            for pole in ("bylo", "jest"):
                if not k.get(pole):
                    b.dodaj(g, f"brak pola {pole}")
            sprawdz_zrodla(k.get("zrodla"), g, b)
        for i, k in enumerate(w.get("korekty", [])):
            g = f"{w['_plik']} korekta {i+1}"
            if k.get("dotyczy") and k["dotyczy"] not in klucze:
                b.dodaj(g, f"dotyczy nieistniejącej pozycji {k['dotyczy']} (format RRRR-MM-DD#id)")
            for pole in ("bylo", "jest"):
                if not k.get(pole):
                    b.dodaj(g, f"brak pola {pole}")
            sprawdz_zrodla(k.get("zrodla"), g, b)
    if RANKING:
        braki = {}
        for nazwa_pliku, dane in ([(w["_plik"], w) for w in wydania] + [("tagi.json", list(tagi.values())),
                                  ("osoby.json", list(osoby.values())), ("rewizje.json", list(rewizje))]):
            for z in wszystkie_zrodla(dane):
                if not RANKING.ocen(z["nazwa"], z["url"]):
                    braki.setdefault((z["nazwa"], re.sub(r"^https?://([^/]+).*$", r"\1", z["url"])), nazwa_pliku)
        for (n, d), f in sorted(braki.items()):
            b.dodaj(f, f"źródło spoza rankingu: „{n}” ({d}) — dodaj je do dane/zrodla.json z poziomem i uzasadnieniem")
    slugi = {w["_slug"] for w in wydania}
    for i, r in enumerate(rewizje):
        g = f"rewizje.json {i+1}"
        wycofane = r.get("wynik") == "WYCOFANE"
        if wycofane:
            if (r.get("dotyczy") or "#").split("#")[0] not in slugi or r.get("dotyczy") in klucze:
                b.dodaj(g, "wycofana pozycja musi wskazywać istniejące wydanie i nie może już być w jego zarysie")
        elif r.get("dotyczy") not in klucze:
            b.dodaj(g, f"dotyczy nieistniejącej pozycji {r.get('dotyczy')}")
        if r.get("wynik") not in ("POTWIERDZONE PO REWIZJI", "WYCOFANE"):
            b.dodaj(g, "wynik musi być POTWIERDZONE PO REWIZJI albo WYCOFANE")
        for pole in ("data", "bylo", "zmiana") + (() if wycofane else ("jest",)):
            if not r.get(pole):
                b.dodaj(g, f"brak pola {pole}")
        sprawdz_zrodla(r.get("zrodla"), g, b)
    return b


# ---------------------------------------------------------------- formatowanie

def e(s):
    return html.escape(str(s), quote=True)


def data_pelna(s):
    d = data_(s)
    return f"{DNI[d.weekday()]}, {d.day} {MIESIACE[d.month-1]} {d.year}"


def data_krotka(s):
    d = data_(s)
    return f"{d.day:02d}.{d.month:02d}"


def data_dluga(s):
    d = data_(s)
    return f"{d.day:02d}.{d.month:02d}.{d.year}"


class Tekst:
    """Zamienia znaczniki na HTML; pamięta osoby już przedstawione na danej stronie."""

    def __init__(self, osoby, pojecia, prefix):
        self.osoby, self.pojecia, self.prefix = osoby, pojecia, prefix
        self.przedstawione = set()

    def __call__(self, s):
        wynik = e(s)
        wynik = re.sub(r"\*\*(.+?)\*\*", r'<mark>\1</mark>', wynik)

        def zam(m):
            rodzaj, ident, wlasny = m.group(1), m.group(2), m.group(3)
            if rodzaj == "o":
                o = self.osoby[ident]
                napis = e(wlasny) if wlasny else e(o["imie"])
                link = f'<a class="osoba" href="{self.prefix}osoby/{ident}.html" title="{e(o["funkcja"])}">{napis}</a>'
                if ident not in self.przedstawione and not wlasny:
                    self.przedstawione.add(ident)
                    return f'{link} <span class="funkcja">({e(o["funkcja"])})</span>'
                return link
            p = self.pojecia[ident]
            napis = e(wlasny) if wlasny else e(p["nazwa"])
            return f'<a class="pojecie" href="{self.prefix}pojecia/{ident}.html" title="{e(p["pelna"])}">{napis}</a>'

        return ZNACZNIK_RE.sub(zam, wynik)


def czysty(s, osoby, pojecia):
    """Tekst bez znaczników (do wyszukiwarki, RSS, tytułów)."""
    def zam(m):
        rodzaj, ident, wlasny = m.group(1), m.group(2), m.group(3)
        if wlasny:
            return wlasny
        return osoby[ident]["imie"] if rodzaj == "o" else pojecia[ident]["nazwa"]
    return re.sub(r"\*\*(.+?)\*\*", r"\1", ZNACZNIK_RE.sub(zam, s))


def html_zrodla(zrodla, etykieta="Źródła"):
    if not zrodla:
        return ""
    czesci = [f'{kropka(z)}<a href="{e(z["url"])}" rel="noopener noreferrer" target="_blank">{e(z["nazwa"])}, {data_krotka(z["data"])}</a>'
              for z in zrodla]
    return f'<p class="zrodla">{etykieta}: ' + "; ".join(czesci) + "</p>"


def html_tagi(lista, tagi, prefix):
    return "".join(f'<a class="tag tag-{tagi[t]["grupa"]}" href="{prefix}watki/{t}.html">#{e(tagi[t]["nazwa"])}</a>'
                   for t in lista or [])


def html_odznaki(it):
    s = ""
    if it.get("etap"):
        s += f'<span class="odznaka etap">{e(it["etap"])}</span>'
    return s


def strona(tytul, tresc, prefix="", opis="", aktywne=""):
    nav = [("index.html", "Wydania", "wydania"), ("watki/index.html", "Wątki", "watki"),
           ("osoby/index.html", "Kto jest kim", "osoby"), ("pojecia/index.html", "Pojęcia", "pojecia"),
           ("korekty.html", "Korekty", "korekty"), ("zrodla.html", "Źródła", "zrodla"), ("jak-weryfikujemy.html", "Jak weryfikujemy", "jak"),
           ("szukaj.html", "Szukaj", "szukaj")]
    akt = ' aria-current="page"'
    menu = "".join(f'<a href="{prefix}{h}"{akt if k == aktywne else ""}>{n}</a>' for h, n, k in nav)
    return f"""<!doctype html>
<html lang="pl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow, noarchive">
<title>{e(tytul)} · {TYTUL}</title>
<meta name="description" content="{e(opis or PODTYTUL)}">
<link rel="stylesheet" href="{prefix}assets/styl.css">
<link rel="alternate" type="application/rss+xml" title="{TYTUL}" href="{prefix}feed.xml">
</head>
<body>
<header class="gora">
  <div class="wrap">
    <a class="marka" href="{prefix}index.html"><span class="marka-t">{TYTUL}</span><span class="marka-p">{PODTYTUL}</span></a>
    <nav class="menu">{menu}</nav>
  </div>
</header>
<main class="wrap">
{tresc}
</main>
<footer class="stopka">
  <div class="wrap">
    <p>Każda pozycja ma źródło z linkiem i przeszła <a href="{prefix}jak-weryfikujemy.html">procedurę weryfikacji</a>. Oceny analityczne są podpisane autorem i oddzielone od faktów. Błędy prostujemy jawnie w <a href="{prefix}korekty.html">rejestrze korekt</a>.</p>
    <p class="wz-leg">Kolor przy źródle to jego wiarygodność według <a href="{prefix}zrodla.html">rankingu źródeł</a>: <span class="wz wz1"></span>urzędowe <span class="wz wz2"></span>wysoka <span class="wz wz3"></span>z zastrzeżeniami <span class="wz wz4"></span>niska <span class="wz wz5"></span>strona zainteresowana</p>
    <p><a href="{prefix}feed.xml">Kanał RSS</a> · Strona nie jest indeksowana przez wyszukiwarki.</p>
  </div>
</footer>
</body>
</html>
"""


# ---------------------------------------------------------------- budowa

class Budowa:
    def __init__(self, tagi, osoby, pojecia, wydania, wyjscie: Path, rewizje=()):
        self.tagi, self.osoby, self.pojecia, self.wydania = tagi, osoby, pojecia, wydania
        self.rewizje = list(rewizje)
        self.rewizje_poz = {r["dotyczy"]: r for r in self.rewizje}
        self.out = wyjscie
        # korekty: klucz pozycji -> lista (wydanie korygujące, korekta)
        self.korekty_poz = {}
        for w in wydania:
            for k in self.wszystkie_korekty(w):
                if k.get("dotyczy"):
                    self.korekty_poz.setdefault(k["dotyczy"], []).append((w, k))

    @staticmethod
    def wszystkie_korekty(w):
        """Korekty wydania dziennego plus sprostowania z weryfikacji tygodniowej."""
        return w.get("korekty", []) + [k for k in w.get("weryfikacja", []) if k.get("werdykt") == "SPROSTOWANE"]

    def mapa_html(self, w, prefix):
        m = w.get("mapa_ciepla")
        if not m:
            return ""
        glowa = "".join(f'<th>{DNI_KROTKO[data_(d).weekday()]}<br>{data_krotka(d)}</th>' for d in m["kolumny"])
        wiersze = ""
        for r in m["wiersze"]:
            kom = ""
            for j, v in enumerate(r["wartosci"]):
                odn = (r.get("odnosniki") or [""] * len(r["wartosci"]))[j]
                spr = (r.get("sprostowane") or [False] * len(r["wartosci"]))[j]
                kolor = "#fff" if v >= 2 else "#17243B"
                znak = '<span class="m-spr">▲</span>' if spr else ""
                tekst = e(odn) if v >= 2 and odn else ""
                kom += f'<td style="background:{MAPA_TLO[v]};color:{kolor}" title="{v}">{tekst}{znak}</td>'
            t = self.tagi[r["tag"]]
            wiersze += f'<tr><th class="m-tag"><a href="{prefix}watki/{t["id"]}.html">#{e(t["nazwa"])}</a></th>{kom}</tr>'
        legenda = "".join(f'<span><i style="background:{MAPA_TLO[i]}"></i>{i} {n}</span>'
                          for i, n in enumerate(["nic", "drobny rozwój", "istotne zdarzenie", "przełom"]))
        return (f'<h2 class="pasek">Mapa ciepła tygodnia</h2><div class="mapa-wrap"><table class="mapa"><tr><th></th>{glowa}</tr>{wiersze}</table></div>'
                f'<p class="m-leg">{legenda}<span><b class="m-spr">▲</b> sprostowane w tym tygodniu</span></p>'
                f'<p class="uwaga">Im ciemniej, tym ważniejsze zdarzenie danego dnia. Liczby w ciemnych polach to numer wydania i punktu. '
                f'Wartości przyznano tylko za zdarzenia zweryfikowane.</p>')

    def tygodniowe_html(self, w, T, prefix):
        """Sekcje tygodniówki po analizach: tracker i czytelnia."""
        cz = []
        if w.get("tracker"):
            cz.append('<h2 class="pasek">Tracker wątków</h2><div class="mapa-wrap"><table class="kal tracker"><tr><th>Wątek</th><th>Tydzień temu</th><th>Dziś</th><th></th></tr>' + "".join(
                f'<tr><td>{html_tagi([t["tag"]], self.tagi, prefix)}</td><td>{T(t["tydzien_temu"])}</td><td>{T(t["dzis"])}</td><td class="kier">{e(t["kierunek"])}</td></tr>'
                for t in w["tracker"]) + "</table></div>")
        if w.get("czytelnia"):
            cz.append('<h2 class="pasek">Czytelnia OSW i PISM</h2>' + "".join(
                f'<article class="poz"><div class="poz-data">{data_krotka(c["data"])}</div><div class="poz-tresc">'
                f'<p class="poz-tekst"><a href="{e(c["url"])}" target="_blank" rel="noopener noreferrer"><strong>{e(c["tytul"])}</strong></a>'
                f'{(" · " + e(c["autor"])) if c.get("autor") else ""}{(" · " + e(c["wydawca"])) if c.get("wydawca") else ""}{(", " + e(c["numer"])) if c.get("numer") else ""}</p>'
                f'<p class="poz-tekst">{T(c["po_co"])}</p></div></article>' for c in w["czytelnia"]))
        return "\n".join(cz)

    def zapisz(self, sciezka, tresc):
        p = self.out / sciezka
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(tresc, "utf-8")

    # ---- grafiki

    @staticmethod
    def stopien(n):
        return 0 if n <= 0 else 1 if n == 1 else 2 if n <= 3 else 3

    def mapa_europy(self, pozycje, prefix, naglowek, opis):
        """Mapa Europy: kraje z hashtagów-miejsc zabarwione liczbą pozycji, klikalne do stron wątków."""
        licz = {}
        for it in pozycje:
            for t in it["tagi"]:
                licz[t] = licz.get(t, 0) + 1
        polska = sum(1 for it in pozycje if it["blok"] == "polska")
        na_mapie = {t: n for t, n in licz.items() if t in MAPA_TAGI}
        poza = {t: n for t, n in licz.items() if t not in MAPA_TAGI and self.tagi[t]["grupa"] == "miejsce"}
        if not na_mapie and not poza:
            return ""
        kontury, ety = EUROPA["kraje"], EUROPA["etykiety"]
        zajete = {k for t in MAPA_TAGI for k in MAPA_TAGI[t]} | {"PL"}
        tlo = "".join(f'<path d="{d}"/>' for k, d in kontury.items() if k not in zajete)
        warstwa, znaczniki = "", ""
        for t, kody in MAPA_TAGI.items():
            n, cel = na_mapie.get(t, 0), t
            if t == "kaliningrad" and not n and na_mapie.get("rosja"):
                n, cel = na_mapie["rosja"], "rosja"  # obwód bez własnych pozycji dziedziczy kolor Rosji
            sciezki = "".join(f'<path d="{kontury[k]}"/>' for k in kody if k in kontury)
            if not sciezki:
                continue
            nazwa = self.tagi[cel]["nazwa"]
            if n:
                opis_ = f"#{nazwa}: {n} poz."
                warstwa += (f'<a href="{prefix}watki/{cel}.html" aria-label="{e(opis_)}"><title>{e(opis_)}</title>'
                            f'<g class="m{self.stopien(n)}">{sciezki}</g></a>')
                if cel == t and kody[0] in ety:
                    x, y = ety[kody[0]]
                    znaczniki += (f'<g class="lic" aria-hidden="true"><circle cx="{x}" cy="{y}" r="12"/>'
                                  f'<text x="{x}" y="{y + 5}">{n}</text></g>')
            else:
                warstwa += f'<g class="m0">{sciezki}</g>'
        if "PL" in kontury:
            px_, py_ = ety["PL"]
            warstwa += f'<g class="pl"><title>Polska: {polska} poz. w bloku „Polska”</title><path d="{kontury["PL"]}"/></g>'
            if polska:
                znaczniki += (f'<g class="lic lic-pl" aria-hidden="true"><circle cx="{px_}" cy="{py_}" r="12"/>'
                              f'<text x="{px_}" y="{py_ + 5}">{polska}</text></g>')
        svg = (f'<svg class="europa" viewBox="0 0 {EUROPA["szer"]} {EUROPA["wys"]}" role="img" aria-label="{e(naglowek)}">'
               f'<rect class="morze" width="100%" height="100%"/><g class="lad">{tlo}</g>{warstwa}{znaczniki}</svg>')
        ranking = sorted(list(na_mapie.items()) + list(poza.items()), key=lambda x: (-x[1], self.tagi[x[0]]["nazwa"]))
        lista = "".join(f'<a class="tag tag-miejsce" href="{prefix}watki/{t}.html">#{e(self.tagi[t]["nazwa"])} <span>{n}</span></a>'
                        for t, n in ranking)
        poza_txt = ""
        if poza:
            poza_txt = ('<p class="uwaga">Poza kadrem: ' + ", ".join(f'#{e(self.tagi[t]["nazwa"])} ({n})' for t, n in
                        sorted(poza.items(), key=lambda x: -x[1])) + ".</p>")
        legenda = "".join(f'<span><i class="m{i}"></i>{n}</span>' for i, n in
                          ((1, "1 poz."), (2, "2–3"), (3, "4 i więcej")))
        return (f'<h2 class="pasek">{e(naglowek)}</h2><figure class="mapa-eu">{svg}'
                f'<figcaption class="m-leg">{legenda}<span><i class="pl"></i>Polska (blok „Polska”)</span></figcaption></figure>'
                f'<p class="uwaga">{e(opis)} Kliknij kraj, żeby zobaczyć historię wątku.</p>'
                f'<div class="chmura">{lista}</div>{poza_txt}')

    def os_czasu(self, wystapienia, przyszle, dzis, prefix):
        """Oś czasu wątku: kropka = pozycja z wydania (stos w dniu zdarzenia), romb = termin z kalendarza."""
        if not wystapienia:
            return ""
        daty = [data_(it["data"]) for _, it in wystapienia]
        start = min(daty)
        koniec = max([dzis] + daty + [data_(k["data"]) for k in przyszle])
        start = min(start, koniec - dt.timedelta(days=6))
        dni = (koniec - start).days + 1
        krok, lewy, prawy = 24, 18, 24
        szer = max(560, lewy + prawy + (dni - 1) * krok)
        krok = (szer - lewy - prawy) / max(dni - 1, 1)
        stosy = {}
        for w, it in wystapienia:
            stosy.setdefault(it["data"], []).append((w, it))
        wys_stosu = min(max(len(v) for v in stosy.values()), 6)
        r, odstep = 7, 17
        os_y = 30 + wys_stosu * odstep
        wys = os_y + 52

        def x(d):
            return round(lewy + (d - start).days * krok, 1)

        cz = [f'<line class="os-linia" x1="{lewy - 8}" y1="{os_y}" x2="{szer - prawy + 8}" y2="{os_y}"/>']
        co = max(1, math.ceil(dni / 10))
        for i in range(dni):
            d = start + dt.timedelta(days=i)
            xx = x(d)
            dlugi = i % co == 0 or d == dzis
            cz.append(f'<line class="os-tik" x1="{xx}" y1="{os_y}" x2="{xx}" y2="{os_y + (6 if dlugi else 3)}"/>')
            if dlugi:
                cz.append(f'<text class="os-data" x="{xx}" y="{os_y + 20}">{d.day:02d}.{d.month:02d}</text>')
        xd = x(dzis)
        cz.append(f'<line class="os-dzis" x1="{xd}" y1="16" x2="{xd}" y2="{os_y + 8}"/>'
                  f'<text class="os-dzis-t" x="{xd - 4}" y="12">ostatnie wydanie</text>')
        for dzien, lista in stosy.items():
            xx = x(data_(dzien))
            lista = sorted(lista, key=lambda p: p[0]["data"])
            for j, (w, it) in enumerate(lista[:6]):
                y = os_y - 12 - j * odstep
                klucz = f"{w['_slug']}#{it['id']}"
                if klucz in self.korekty_poz:
                    klasa, stan = "k-spr", "sprostowane"
                else:
                    klasa, stan = "k-ok", "potwierdzone"
                tytul = f"{data_krotka(it['data'])} · {czysty(it['tekst'], self.osoby, self.pojecia)[:140]} ({stan}; wyd. nr {w['nr']})"
                cz.append(f'<a href="#{w["_slug"]}-{it["id"]}"><title>{e(tytul)}</title>'
                          f'<circle class="{klasa}" cx="{xx}" cy="{y}" r="{r}"/></a>')
            if len(lista) > 6:
                cz.append(f'<text class="os-wiecej" x="{xx}" y="{os_y - 12 - 6 * odstep + 4}">+{len(lista) - 6}</text>')
        for k in przyszle:
            xx, y = x(data_(k["data"])), os_y + 36
            tytul = f"{data_dluga(k['data'])} · {czysty(k['tekst'], self.osoby, self.pojecia)[:140]}"
            cz.append(f'<g><title>{e(tytul)}</title><path class="k-kal" d="M{xx},{y - 7} L{xx + 7},{y} L{xx},{y + 7} L{xx - 7},{y} Z"/></g>')
        svg = (f'<svg class="os-czasu" width="{round(szer)}" height="{wys}" viewBox="0 0 {round(szer)} {wys}" role="img" '
               f'aria-label="Oś czasu wątku: {len(wystapienia)} pozycji od {data_dluga(start.isoformat())}">{"".join(cz)}</svg>')
        leg = ['<span><i class="k-ok"></i>pozycja</span>']
        leg += ['<span><i class="k-spr"></i>sprostowana później</span>', '<span><i class="k-kal"></i>termin z kalendarza</span>']
        legenda = '<p class="m-leg">' + "".join(leg) + "</p>"
        return (f'<h2 class="pasek">Oś czasu</h2><div class="os-wrap" data-na-koniec>{svg}</div>{legenda}'
                '<p class="uwaga">Każda kropka to pozycja z wydania w dniu zdarzenia; kliknij, żeby przejść do niej na liście poniżej.</p>'
                "<script>document.querySelectorAll('[data-na-koniec]').forEach(function(el){el.scrollLeft=el.scrollWidth;});</script>")

    # ---- elementy

    def pozycja(self, w, it, T, prefix, z_wydaniem=False, kotwica=None):
        klucz = f"{w['_slug']}#{it['id']}"
        kor = ""
        for (wk, k) in self.korekty_poz.get(klucz, []):
            kor += (f'<p class="kor-znak">▲ Sprostowano w wydaniu <a href="{prefix}wydania/{wk["_slug"]}.html#korekty">nr {wk["nr"]} '
                    f'({data_dluga(wk["data"])})</a>: {e(k["jest"])}</p>')
        r = self.rewizje_poz.get(klucz)
        if r:
            kor += (f'<p class="rew-znak">Zweryfikowano ponownie {data_dluga(r["data"])}: {e(r["zmiana"])}. '
                    f'<a href="{prefix}korekty.html#rewizja">Wersja pierwotna</a></p>')
        skad = (f'<a class="z-wydania" href="{prefix}wydania/{w["_slug"]}.html#{it["id"]}">wyd. nr {w["nr"]}</a>'
                if z_wydaniem else "")
        return f"""<article class="poz{' skorygowana' if klucz in self.korekty_poz else ''}" id="{e(kotwica or it['id'])}">
  <div class="poz-data">{data_krotka(it['data'])}</div>
  <div class="poz-tresc">
    <div class="poz-meta">{html_tagi(it['tagi'], self.tagi, prefix)}{html_odznaki(it)}{skad}</div>
    <p class="poz-tekst">{T(it['tekst'])}</p>
    {('<p class="dla-polski"><strong>Dla Polski:</strong> ' + T(it['dla_polski']) + '</p>') if it.get('dla_polski') else ''}
    {kor}
    {html_zrodla(it['zrodla'])}
  </div>
</article>"""

    def analiza(self, w, a, T, prefix, z_wydaniem=False):
        skad = (f' · <a href="{prefix}wydania/{w["_slug"]}.html#analizy">wyd. nr {w["nr"]}, {data_dluga(w["data"])}</a>'
                if z_wydaniem else "")
        return f"""<article class="analiza">
  <h3>{e(a['tytul'])}</h3>
  <p class="autor">Ocena: {e(a['autor'])}{skad}</p>
  <div class="poz-meta">{html_tagi(a.get('tagi'), self.tagi, prefix)}</div>
  <p>{T(a['tekst'])}</p>
  <p class="dla-polski"><strong>Dla Polski:</strong> {T(a['dla_polski'])}</p>
  {html_zrodla(a.get('zrodla'))}
</article>"""

    # ---- strony

    def wydanie(self, i, w):
        prefix = "../"
        T = Tekst(self.osoby, self.pojecia, prefix)
        rodzaj = "Wydanie tygodniowe" if w.get("typ") == "tygodniowe" else "Wydanie"
        cz = []
        cz.append(f"""<section class="winieta">
  <p class="w-nr">{rodzaj} nr {e(w['nr'])}</p>
  <h1>{data_pelna(w['data']).capitalize()}</h1>
  <p class="w-stan">stan na godz. {e(w['godzina'])} CEST{(' · okres ' + e(w['okres'])) if w.get('okres') else ''}</p>
</section>""")
        cz.append('<section class="skrot"><h2>W skrócie</h2>' +
                  "".join(f"<p>{T(z)}</p>" for z in w["w_skrocie"]) + "</section>")
        cz.append(self.mapa_html(w, prefix))
        cz.append(self.mapa_europy(w["zarys"], prefix, "Mapa wydania",
                                   "Liczba przy kraju to liczba pozycji zarysu z hashtagiem tego miejsca."))
        if w.get("weryfikacja"):
            li = ""
            for k in w["weryfikacja"]:
                cel = ""
                if k.get("dotyczy"):
                    s_, pid = k["dotyczy"].split("#")
                    cel = f' <a href="{s_}.html#{pid}">(pozycja z {data_dluga(s_)})</a>'
                klasa = {"POTWIERDZONE": "etap", "SPROSTOWANE": "sprzeczne", "NADAL OTWARTE": "niepotw"}[k["werdykt"]]
                li += (f'<article class="poz{" skorygowana" if k["werdykt"] == "SPROSTOWANE" else ""}"><div class="poz-data"></div><div class="poz-tresc">'
                       f'<p class="poz-meta"><span class="odznaka {klasa}">{e(k["werdykt"])}</span>{cel}</p>'
                       f'<p class="poz-tekst"><strong>Pisaliśmy:</strong> {e(k["bylo"])}</p><p class="poz-tekst"><strong>Jak jest:</strong> {e(k["jest"])}</p>'
                       f'{html_zrodla(k["zrodla"])}</div></article>')
            cz.append(f'<h2 class="pasek" id="korekty">Weryfikacja tygodnia</h2>{li}')
        if w.get("korekty"):
            li = ""
            for k in w["korekty"]:
                cel = ""
                if k.get("dotyczy"):
                    s, pid = k["dotyczy"].split("#")
                    cel = f' <a href="{s}.html#{pid}">(pozycja z {data_dluga(s)})</a>'
                li += f"<li><strong>Było:</strong> {e(k['bylo'])}{cel}<br><strong>Jest:</strong> {e(k['jest'])}{html_zrodla(k['zrodla'])}</li>"
            cz.append(f'<section class="korekta" id="korekty"><h2>Korekta</h2><ul>{li}</ul></section>')
        cz.append('<h2 class="pasek">' + ("I. Najważniejsze przesunięcia tygodnia" if w.get("typ") == "tygodniowe" else "I. Zarys wydarzeń") + '</h2>')
        for kod, nazwa in BLOKI:
            poz = sorted([it for it in w["zarys"] if it["blok"] == kod], key=lambda x: x["data"])
            if not poz:
                continue
            cz.append(f'<h3 class="blok">{nazwa}</h3>')
            cz.extend(self.pozycja(w, it, T, prefix) for it in poz)
        wyc = [r for r in self.rewizje if r.get("wynik") == "WYCOFANE" and r["dotyczy"].split("#")[0] == w["_slug"]]
        if wyc:
            cz.append('<div class="nota wycofane"><h3>Wycofane po rewizji</h3><ul>' + "".join(
                f'<li id="{e(r["dotyczy"].split("#")[1])}">{data_dluga(r["data"])}: wycofano pozycję o treści „{e(czysty(r["bylo"], self.osoby, self.pojecia))}” – '
                f'{e(r["zmiana"])}. <a href="{prefix}korekty.html#rewizja">Rejestr korekt</a></li>' for r in wyc) + "</ul></div>")
        if w.get("analizy"):
            cz.append('<h2 class="pasek" id="analizy">II. Analizy</h2><p class="uwaga">Poniżej interpretacje, nie ustalenia. Każda ma autora.</p>')
            cz.extend(self.analiza(w, a, T, prefix) for a in w["analizy"])
        cz.append(self.tygodniowe_html(w, T, prefix))
        cz.append('<h2 class="pasek">III. Kalendarz i zastrzeżenia</h2>')
        if w.get("kalendarz"):
            cz.append('<table class="kal">' + "".join(
                f'<tr><td class="kal-d">{data_krotka(k["data"])}</td><td>{T(k["tekst"])} {html_tagi(k.get("tagi"), self.tagi, prefix)}</td></tr>'
                for k in sorted(w["kalendarz"], key=lambda k: k["data"])) + "</table>")
        if w.get("poza_oknem"):
            cz.append('<p class="poza"><strong>Poza oknem, ale przesądzające:</strong> ' +
                      "; ".join(f'{data_dluga(k["data"])} – {T(k["tekst"])}' for k in w["poza_oknem"]) + "</p>")
        za = w.get("zrodla_analityczne") or {}
        def lista_pub(pub):
            if not pub:
                return "brak nowych publikacji w ostatnich 3 dniach"
            return "; ".join(f'<a href="{e(p["url"])}" target="_blank" rel="noopener noreferrer">{e(p["tytul"])}</a>'
                             f'{(" (" + e(p["autor"]) + ")") if p.get("autor") else ""}, {data_krotka(p["data"])}'
                             f'{(", " + e(p["numer"])) if p.get("numer") else ""}' for p in pub)
        cz.append(f'<div class="nota"><h3>Stan źródeł analitycznych</h3><p><strong>OSW:</strong> {lista_pub(za.get("osw"))}.</p>'
                  f'<p><strong>PISM:</strong> {lista_pub(za.get("pism"))}.</p></div>')
        if w.get("czego_nie_ma"):
            cz.append('<div class="nota"><h3>Czego tu nie ma</h3><ul>' + "".join(
                f'<li>{T(c["tekst"])} <span class="prog">odpadło na progu: {e(c["prog"])}</span></li>' for c in w["czego_nie_ma"]) + "</ul></div>")
        if w.get("nota"):
            cz.append(f'<div class="nota"><h3>Nota metodyczna</h3><p>{T(w["nota"])}</p></div>')
        prev = self.wydania[i-1] if i > 0 else None
        nxt = self.wydania[i+1] if i + 1 < len(self.wydania) else None
        cz.append('<nav class="kolejne">' +
                  (f'<a href="{prev["_slug"]}.html">← nr {prev["nr"]}, {data_dluga(prev["data"])}</a>' if prev else "<span></span>") +
                  (f'<a href="{nxt["_slug"]}.html">nr {nxt["nr"]}, {data_dluga(nxt["data"])} →</a>' if nxt else "<span></span>") + "</nav>")
        opis = czysty(" ".join(w["w_skrocie"]), self.osoby, self.pojecia)[:200]
        self.zapisz(f"wydania/{w['_slug']}.html",
                    strona(f"{rodzaj} nr {w['nr']} – {data_dluga(w['data'])}", "\n".join(cz), prefix, opis, "wydania"))

    def index(self):
        cz = []
        if self.wydania:
            w = self.wydania[-1]
            T = Tekst(self.osoby, self.pojecia, "")
            cz.append(f"""<section class="winieta">
  <p class="w-nr">Najnowsze · wydanie nr {e(w['nr'])}</p>
  <h1><a href="wydania/{w['_slug']}.html">{data_pelna(w['data']).capitalize()}</a></h1>
  <p class="w-stan">stan na godz. {e(w['godzina'])} CEST</p>
</section>
<section class="skrot"><h2>W skrócie</h2>{''.join(f'<p>{T(z)}</p>' for z in w['w_skrocie'])}
<p class="dalej"><a href="wydania/{w['_slug']}.html">Czytaj całe wydanie</a></p></section>""")
            koniec = data_(w["data"])
            ostatnie = [it for x in self.wydania for it in x["zarys"] if 0 <= (koniec - data_(it["data"])).days < 7]
            cz.append(self.mapa_europy(ostatnie, "", "Mapa wątków z ostatnich 7 dni",
                                       f"Pozycje z wydań z datą zdarzenia od {data_dluga((koniec - dt.timedelta(days=6)).isoformat())} do {data_dluga(w['data'])}."))
            gorace = self.gorace_watki(7)
            if gorace:
                cz.append('<h2 class="pasek">Gorące wątki z ostatnich 7 dni</h2><div class="chmura">' + "".join(
                    f'<a class="tag tag-{self.tagi[t]["grupa"]} duzy" href="watki/{t}.html">#{e(self.tagi[t]["nazwa"])} <span>{n}</span></a>'
                    for t, n in gorace) + "</div>")
            cz.append('<h2 class="pasek">Archiwum wydań</h2>')
            miesiac = None
            lista = ""
            for w in reversed(self.wydania):
                d = data_(w["data"])
                if (d.year, d.month) != miesiac:
                    if lista:
                        lista += "</ul>"
                    miesiac = (d.year, d.month)
                    lista += f'<h3 class="blok">{MIESIACE_MIAN[d.month-1]} {d.year}</h3><ul class="archiwum">'

                rodzaj = " · tygodniowe" if w.get("typ") == "tygodniowe" else ""
                tg = sorted({t for it in w["zarys"] for t in it["tagi"]})[:6]
                lista += (f'<li><a href="wydania/{w["_slug"]}.html"><span class="a-d">{DNI_KROTKO[d.weekday()]} {data_krotka(w["data"])}</span> '
                          f'nr {w["nr"]}{rodzaj}</a> {html_tagi(tg, self.tagi, "")}</li>')
            cz.append(lista + "</ul>")
        else:
            cz.append("""<section class="winieta"><h1>Archiwum rusza wkrótce</h1>
<p class="w-stan">Pierwsze wydanie pojawi się tu po najbliższej wieczornej publikacji.</p></section>
<section class="skrot"><h2>Jak czytać tę stronę</h2>
<p>Każde wydanie ma trzy części: <strong>zarys</strong> udokumentowanych wydarzeń, <strong>analizy</strong> z podpisanym autorem oceny i <strong>kalendarz</strong>.</p>
<p><strong>Hashtagi</strong> łączą wydania: kliknięcie <span class="tag tag-miejsce">#Słowacja</span> pokazuje całą historię wątku na jednej stronie, z aktualnym stanem na górze.</p>
<p>Osoby i pojęcia w tekście są klikalne i prowadzą do kart w działach „Kto jest kim” i „Pojęcia”.</p></section>""")
        self.zapisz("index.html", strona("Wydania", "\n".join(cz), "", "", "wydania"))

    def gorace_watki(self, dni):
        if not self.wydania:
            return []
        koniec = data_(self.wydania[-1]["data"])
        licz = {}
        for w in self.wydania:
            for it in w["zarys"]:
                if (koniec - data_(it["data"])).days < dni:
                    for t in it["tagi"]:
                        licz[t] = licz.get(t, 0) + 1
        return sorted(licz.items(), key=lambda x: (-x[1], self.tagi[x[0]]["nazwa"]))[:12]

    def watki(self):
        prefix = "../"
        wystapienia = {t: [] for t in self.tagi}
        analizy = {t: [] for t in self.tagi}
        kalendarz = {t: {} for t in self.tagi}
        dzis = data_(self.wydania[-1]["data"]) if self.wydania else dt.date.today()
        for w in self.wydania:
            for it in w["zarys"]:
                for t in it["tagi"]:
                    wystapienia[t].append((w, it))
            for a in w.get("analizy", []):
                for t in a.get("tagi", []):
                    analizy[t].append((w, a))
            for k in w.get("kalendarz", []) + w.get("poza_oknem", []):
                for t in k.get("tagi", []):
                    if data_(k["data"]) >= dzis:
                        kalendarz[t][(k["data"], k["tekst"])] = k
        for t, tag in self.tagi.items():
            T = Tekst(self.osoby, self.pojecia, prefix)
            cz = [f"""<section class="winieta"><p class="w-nr">Wątek · {'miejsce' if tag['grupa'] == 'miejsce' else 'temat'}</p>
<h1>#{e(tag['nazwa'])}</h1><p class="w-stan">{e(tag['opis'])}</p></section>"""]
            if tag.get("stan"):
                cz.append(f'<section class="skrot"><h2>Na czym stoimy · {data_dluga(tag["stan_data"])}</h2><p>{T(tag["stan"])}</p>'
                          f'{html_zrodla(tag.get("stan_zrodla"))}</section>')
            przyszle = sorted(kalendarz[t].values(), key=lambda k: k["data"])
            if przyszle:
                cz.append('<div class="nota"><h3>Najbliższe terminy</h3><table class="kal">' + "".join(
                    f'<tr><td class="kal-d">{data_dluga(k["data"])}</td><td>{T(k["tekst"])}</td></tr>' for k in przyszle) + "</table></div>")
            if wystapienia[t]:
                cz.append(self.os_czasu(wystapienia[t], przyszle, dzis, prefix))
                cz.append(f'<h2 class="pasek">Wszystkie pozycje · {len(wystapienia[t])}</h2><div class="os">')
                for w, it in sorted(wystapienia[t], key=lambda x: (x[1]["data"], x[0]["data"]), reverse=True):
                    cz.append(self.pozycja(w, it, T, prefix, z_wydaniem=True, kotwica=f"{w['_slug']}-{it['id']}"))
                cz.append("</div>")
            else:
                cz.append('<p class="uwaga">W wydaniach nie ma jeszcze pozycji z tym hashtagiem.</p>')
            if analizy[t]:
                cz.append('<h2 class="pasek">Analizy w tym wątku</h2>')
                cz.extend(self.analiza(w, a, T, prefix, z_wydaniem=True) for w, a in reversed(analizy[t]))
            self.zapisz(f"watki/{t}.html", strona(f"#{tag['nazwa']}", "\n".join(cz), prefix, tag["opis"], "watki"))
        # lista wątków
        def blok(grupa, naglowek):
            pozycje = sorted([x for x in self.tagi.values() if x["grupa"] == grupa], key=lambda x: (-len(wystapienia[x["id"]]), x["nazwa"]))
            return (f'<h2 class="pasek">{naglowek}</h2><ul class="lista-watkow">' + "".join(
                f'<li><a class="tag tag-{x["grupa"]} duzy" href="{x["id"]}.html">#{e(x["nazwa"])} <span>{len(wystapienia[x["id"]])}</span></a>'
                f'<span class="lw-opis">{e(x["opis"])}</span>'
                + (f'<span class="lw-stan">Stan na {data_dluga(x["stan_data"])}: {e(czysty(x["stan"], self.osoby, self.pojecia))}</span>' if x.get("stan") else "")
                + "</li>" for x in pozycje) + "</ul>")
        tresc = ('<section class="winieta"><h1>Wątki</h1><p class="w-stan">Każdy hashtag to jedna strona z całą historią tematu. '
                 'Liczba przy tagu to liczba pozycji we wszystkich wydaniach.</p></section>'
                 + blok("miejsce", "Miejsca") + blok("temat", "Tematy"))
        self.zapisz("watki/index.html", strona("Wątki", tresc, prefix, "", "watki"))

    def osoby_strony(self):
        prefix = "../"
        wyst = {o: [] for o in self.osoby}
        for w in self.wydania:
            elementy = [(it["tekst"], it.get("id")) for it in w["zarys"]] + [(a["tekst"] + a["dla_polski"], "analizy") for a in w.get("analizy", [])]
            for tekst, kotwica in elementy:
                for m in ZNACZNIK_RE.finditer(tekst):
                    if m.group(1) == "o":
                        wyst[m.group(2)].append((w, kotwica))
        for oid, o in self.osoby.items():
            T = Tekst(self.osoby, self.pojecia, prefix)
            T.przedstawione.add(oid)
            hist = ""
            if o.get("historia"):
                hist = "<h3>Wcześniejsze funkcje</h3><ul>" + "".join(f"<li>{e(h)}</li>" for h in o["historia"]) + "</ul>"
            widziane = {}
            for w, k in wyst[oid]:
                widziane[(w["_slug"], k)] = w
            lista = "".join(f'<li><a href="../wydania/{s}.html#{k}">wyd. nr {w["nr"]}, {data_dluga(w["data"])}</a></li>'
                            for (s, k), w in sorted(widziane.items(), reverse=True))
            tresc = f"""<section class="winieta"><p class="w-nr">Kto jest kim</p><h1>{e(o['imie'])}</h1>
<p class="w-stan">{e(o['funkcja'])} · zweryfikowano {data_dluga(o['zweryfikowano'])}</p></section>
<section class="skrot">{f"<p>{T(o['dlaczego'])}</p>" if o.get('dlaczego') else ''}{hist}{html_zrodla(o['zrodla'])}</section>
<h2 class="pasek">Występuje w wydaniach</h2><ul class="archiwum">{lista or '<li>jeszcze nie</li>'}</ul>"""
            self.zapisz(f"osoby/{oid}.html", strona(o["imie"], tresc, prefix, o["funkcja"], "osoby"))
        pozycje = sorted(self.osoby.values(), key=lambda o: o["imie"].split()[-1])
        tresc = ('<section class="winieta"><h1>Kto jest kim</h1><p class="w-stan">Osoby z przeglądów: funkcja ze źródłem i datą weryfikacji.</p></section>'
                 + ('<ul class="lista-watkow">' + "".join(
                     f'<li><a href="{o["id"]}.html"><strong>{e(o["imie"])}</strong></a><span class="lw-opis">{e(o["funkcja"])}</span></li>'
                     for o in pozycje) + "</ul>" if pozycje else '<p class="uwaga">Karty osób pojawią się wraz z pierwszymi wydaniami.</p>'))
        self.zapisz("osoby/index.html", strona("Kto jest kim", tresc, prefix, "", "osoby"))

    def pojecia_strony(self):
        prefix = "../"
        for pid, p in self.pojecia.items():
            tresc = f"""<section class="winieta"><p class="w-nr">Pojęcie</p><h1>{e(p['nazwa'])}</h1><p class="w-stan">{e(p['pelna'])}</p></section>
<section class="skrot"><p>{e(p['definicja'])}</p>{html_zrodla(p.get('zrodla'))}</section>"""
            self.zapisz(f"pojecia/{pid}.html", strona(p["nazwa"], tresc, prefix, p["pelna"], "pojecia"))
        pozycje = sorted(self.pojecia.values(), key=lambda p: p["nazwa"].lower())
        tresc = ('<section class="winieta"><h1>Pojęcia</h1><p class="w-stan">Skróty i terminy używane w przeglądach.</p></section><ul class="lista-watkow">'
                 + "".join(f'<li><a href="{p["id"]}.html"><strong>{e(p["nazwa"])}</strong></a><span class="lw-opis">{e(p["pelna"])} – {e(p["definicja"])}</span></li>'
                           for p in pozycje) + "</ul>")
        self.zapisz("pojecia/index.html", strona("Pojęcia", tresc, prefix, "", "pojecia"))

    def korekty(self):
        wiersze = []
        for w in reversed(self.wydania):
            for k in self.wszystkie_korekty(w):
                cel = ""
                if k.get("dotyczy"):
                    s, pid = k["dotyczy"].split("#")
                    cel = f'<a href="wydania/{s}.html#{pid}">pozycja z {data_dluga(s)}</a>'
                wiersze.append(f"""<article class="poz skorygowana"><div class="poz-data">{data_krotka(w['data'])}</div><div class="poz-tresc">
<p class="poz-meta">Sprostowanie w <a href="wydania/{w['_slug']}.html#korekty">wyd. nr {w['nr']}</a>{(' · dotyczy: ' + cel) if cel else ''}</p>
<p><strong>Było:</strong> {e(k['bylo'])}</p><p><strong>Jest:</strong> {e(k['jest'])}</p>{html_zrodla(k['zrodla'])}</div></article>""")
        if self.rewizje:
            wiersze.append('<h2 class="pasek" id="rewizja">Rewizja archiwum · tylko informacje potwierdzone</h2>'
                           '<p class="uwaga">Od 01.10.2026 do zarysu wchodzą wyłącznie informacje potwierdzone. Pozycje oznaczone wcześniej '
                           'jako NIEPOTWIERDZONE lub SPRZECZNE ŹRÓDŁA oraz oparte na samych tytułach sprawdzono ponownie; w wydaniu została wersja potwierdzona, '
                           'tu – pierwotna. Czego nie dało się potwierdzić, wycofano.</p>')
            for r in sorted(self.rewizje, key=lambda r: r["dotyczy"], reverse=True):
                s_, pid = r["dotyczy"].split("#")
                wiersze.append(f"""<article class="poz"><div class="poz-data">{data_krotka(r['data'])}</div><div class="poz-tresc">
<p class="poz-meta"><span class="odznaka {'sprzeczne' if r['wynik'] == 'WYCOFANE' else 'etap'}">{e(r['wynik'])}</span> <a href="wydania/{s_}.html#{pid}">pozycja z {data_dluga(s_)}</a> · pierwotnie: {e(r.get('pierwotny_status', ''))}</p>
<p><strong>Było:</strong> {e(czysty(r['bylo'], self.osoby, self.pojecia))}</p>{html_zrodla(r.get('bylo_zrodla'), 'Źródła pierwotne')}
{('<p><strong>Jest:</strong> ' + e(czysty(r['jest'], self.osoby, self.pojecia)) + '</p>') if r.get('jest') else '<p><strong>Jest:</strong> pozycja wycofana z wydania.</p>'}<p class="poz-tekst"><strong>{'Powód' if r['wynik'] == 'WYCOFANE' else 'Zmiana'}:</strong> {e(r['zmiana'])}</p>{html_zrodla(r['zrodla'], 'Źródła rewizji')}</div></article>""")
        tresc = ('<section class="winieta"><h1>Rejestr korekt</h1><p class="w-stan">Każdy wykryty błąd: co napisaliśmy, jak jest naprawdę i na jakiej podstawie. '
                 'Sprostowana pozycja zostaje w wydaniu z wyraźnym znakiem ▲.</p></section>'
                 + ("".join(wiersze) if wiersze else '<p class="uwaga">Brak korekt.</p>'))
        self.zapisz("korekty.html", strona("Korekty", tresc, "", "", "korekty"))

    def ranking_strona(self):
        if not RANKING:
            return
        uzycia = {}
        for w in self.wydania:
            for z in wszystkie_zrodla(w):
                o = RANKING.ocen(z["nazwa"], z["url"])
                if o:
                    uzycia[o["id"]] = uzycia.get(o["id"], 0) + 1
        razem = sum(uzycia.values()) or 1
        cz = ['<section class="winieta"><h1>Ranking źródeł</h1><p class="w-stan">Na jakich źródłach opiera się Prasówka i jak bardzo im ufamy. '
              'Kolor przy każdym źródle w wydaniach odpowiada poziomowi z tej strony.</p></section>']
        # rozkład cytowań
        rozklad = {p: 0 for p in RANKING.poziomy}
        for zid, n in uzycia.items():
            rozklad[next(z for z in RANKING.zrodla if z["id"] == zid)["poziom"]] += n
        pasek = "".join(f'<span class="rk-seg wzt{p}" style="flex:{n}" title="Poziom {p}: {n} cytowań"></span>' for p, n in rozklad.items() if n)
        leg = "".join(f'<span><span class="wz wz{p}"></span>{p}. {e(RANKING.poziomy[p]["nazwa"])}: <strong>{n}</strong> ({round(100 * n / razem)}%)</span>'
                      for p, n in rozklad.items())
        cz.append(f'<section class="skrot"><h2>Na czym stoją wydania · {razem} cytowań źródeł</h2><div class="rk-pasek">{pasek}</div>'
                  f'<p class="m-leg">{leg}</p></section>')
        cz.append('<h2 class="pasek">Jak oceniamy</h2><section class="skrot">' + "".join(
            f'<p><strong>{e(n)}:</strong> {e(o)}.</p>' for n, o in RANKING.dane["kryteria"]) +
            '<p>Ranking to <strong>ocena redakcji Prasówki</strong>, nie obiektywna miara: mówi, ile potwierdzenia potrzebuje informacja z danego źródła. '
            'Poziom dotyczy typowej informacji; źródło z poziomu 5 jest rozstrzygające co do tego, co twierdzi jego rząd, a urzędowe (1) – co do decyzji instytucji, nie co do ocen.</p>'
            '<p><strong>Zasada publikacji (od 01.10.2026 sprawdzana automatycznie):</strong> pozycja zarysu wymaga źródła urzędowego (poziom 1) '
            'albo dwóch niezależnych źródeł z poziomów 1–2. Poziomy 3–5 mogą towarzyszyć, ale nie liczą się do podstawy. '
            'Przy przedruku depeszy kolor bierze się z agencji, którą wskazujemy w nazwie, np. „Reuters (za U.S. News)”.</p></section>')
        for p, poz in sorted(RANKING.poziomy.items()):
            lista = sorted([z for z in RANKING.zrodla if z["poziom"] == p], key=lambda z: (-uzycia.get(z["id"], 0), z["nazwa"].lower()))
            cz.append(f'<h2 class="pasek rk-nag wzb{p}" id="poziom-{p}"><span class="wz wz{p}"></span>{p}. {e(poz["nazwa"])}</h2><p class="uwaga">{e(poz["opis"])}</p>'
                      '<div class="mapa-wrap"><table class="kal rk"><tr><th>Źródło</th><th>Typ · kraj</th><th>Cytowań</th><th>Dlaczego ten poziom</th></tr>' + "".join(
                          f'<tr id="{e(z["id"])}"><td><span class="wz wz{p}"></span><strong>{e(z["nazwa"])}</strong></td><td>{e(z["typ"])} · {e(z["kraj"])}</td>'
                          f'<td class="rk-n">{uzycia.get(z["id"], 0) or "–"}</td><td>{e(z["uzasadnienie"])}</td></tr>' for z in lista) + "</table></div>")
        self.zapisz("zrodla.html", strona("Ranking źródeł", "\n".join(cz), "", "Ranking wiarygodności źródeł", "zrodla"))

    def jak_weryfikujemy(self):
        tresc = """<section class="winieta"><h1>Jak weryfikujemy</h1>
<p class="w-stan">Co musi się stać, żeby informacja trafiła do przeglądu, i jak czytać oznaczenia.</p></section>
<h2 class="pasek">Trzy progi</h2>
<section class="skrot">
<p><strong>1. Dokumentacja.</strong> Komunikat instytucji, dane urzędowe albo dwa niezależne serwisy. Sam nagłówek z wyszukiwarki nie wystarcza: strona źródła jest otwierana i czytana.</p>
<p><strong>2. Następstwo.</strong> Coś się zmieniło: zapadła decyzja, powstał termin, zmienił się stan rzeczy. Zdarzenie potwierdzone, ale bez skutku, nie wchodzi do zarysu; trafia do noty „Czego tu nie ma” z podaniem powodu.</p>
<p><strong>3. Kompletność.</strong> Osoba zawsze z funkcją, uzbrojenie z nazwą systemu, liczbą i jednostką, skróty rozwinięte, liczby z datą i źródłem.</p>
</section>
<h2 class="pasek">Co sprawdzamy szczególnie</h2>
<section class="skrot">
<p><strong>Statusy</strong> (kto pełni funkcję, kto jest więziony lub wolny, co obowiązuje) są sprawdzane w dniu wydania osobnym wyszukiwaniem, a nie przenoszone z poprzednich wydań.</p>
<p><strong>Daty</strong> zdarzeń są porównywane z datą publikacji; „wtorek” czy „wczoraj” zamieniamy na datę kalendarzową.</p>
<p><strong>Etap decyzji</strong> nazywamy wprost: propozycja, zapowiedź, przyjęte. Uzgodnienie to jeszcze nie wypłata.</p>
<p><strong>Wyniki wyborów</strong>: wynik oficjalny, z zaznaczeniem, że wcześniejszy był wstępny.</p>
<p><strong>Źródła strony zainteresowanej</strong> (rosyjskie, białoruskie, irańskie) przytaczamy z oznaczeniem.</p>
<p><strong>Kontrola niezależna:</strong> przed publikacją tekst sprawdza osobny agent, który nie brał udziału w pisaniu, samodzielnie wyszukując statusy, daty, etapy decyzji i dane o uzbrojeniu.</p>
<p><strong>Poprzednie wydania nie są źródłem.</strong> Każda informacja jest sprawdzana w źródle zewnętrznym.</p>
</section>
<h2 class="pasek">Oznaczenia</h2>
<section class="skrot">
<p><strong>Tylko informacje potwierdzone.</strong> Do zarysu nie wchodzą informacje z jednego źródła ani takie, których nie da się udokumentować; trafiają do noty „Czego tu nie ma” z podaniem powodu. Wypowiedź strony zainteresowanej podajemy tylko jako udokumentowany fakt, że padła, z atrybucją w treści („według Kremla…”).</p>
<p><strong>Rewizja archiwum.</strong> Do 30.09.2026 używaliśmy oznaczeń NIEPOTWIERDZONE i SPRZECZNE ŹRÓDŁA. 01.10.2026 wszystkie takie pozycje, a także oparte na samych tytułach, sprawdzono ponownie: zostawiono tylko część potwierdzoną, a niepotwierdzone wycofano; wersje pierwotne są w <a href="korekty.html#rewizja">rejestrze korekt</a>.</p>
<p><span class="odznaka etap">PROPOZYCJA</span> <span class="odznaka etap">ZAPOWIEDŹ</span> <span class="odznaka etap">PRZYJĘTE</span> etap decyzji.</p>
<p><strong>Ocena: autor</strong> przy analizach oznacza interpretację (OSW, PISM, ISW jako think tank albo redakcja), nie ustalenie.</p>
<p><span class="kor-znak">▲</span> pozycja sprostowana później; link prowadzi do sprostowania.</p>
<p><mark>wyróżnienie</mark> słowo kluczowe pozycji.</p>
</section>
<h2 class="pasek">Źródła stałe</h2>
<section class="skrot">
<p>OSW i PISM (publikacje z ostatnich 3 dni), agencje: Reuters, AP, AFP, PAP, Al Jazeera, Kyiv Independent; przy uzbrojeniu komunikaty MON i Dowództwa Operacyjnego RSZ; gospodarka: GUS, NBP; front: ISW, zawsze jako ocena think tanku.</p>
</section>"""
        self.zapisz("jak-weryfikujemy.html", strona("Jak weryfikujemy", tresc, "", "", "jak"))

    def szukaj(self):
        idx = []
        for w in self.wydania:
            for it in w["zarys"]:
                idx.append({"t": czysty(it["tekst"], self.osoby, self.pojecia), "d": it["data"],
                            "g": [self.tagi[t]["nazwa"] for t in it["tagi"]],
                            "u": f"wydania/{w['_slug']}.html#{it['id']}", "w": w["nr"]})
            for a in w.get("analizy", []):
                idx.append({"t": a["tytul"] + ". " + czysty(a["tekst"], self.osoby, self.pojecia) + " (ocena: " + a["autor"] + ")",
                            "d": w["data"], "g": [self.tagi[t]["nazwa"] for t in a.get("tagi", [])],
                            "u": f"wydania/{w['_slug']}.html#analizy", "w": w["nr"]})
        for o in self.osoby.values():
            idx.append({"t": f"{o['imie']} – {o['funkcja']}", "d": o["zweryfikowano"], "g": ["Kto jest kim"], "u": f"osoby/{o['id']}.html", "w": ""})
        for p in self.pojecia.values():
            idx.append({"t": f"{p['nazwa']} – {p['pelna']}: {p['definicja']}", "d": "", "g": ["Pojęcia"], "u": f"pojecia/{p['id']}.html", "w": ""})
        self.zapisz("szukaj.json", json.dumps(idx, ensure_ascii=False))
        tresc = """<section class="winieta"><h1>Szukaj</h1><p class="w-stan">Przeszukuje wszystkie wydania, analizy, osoby i pojęcia.</p></section>
<input id="q" class="szukaj" type="search" placeholder="np. Kaliningrad, Patriot, Fico…" autofocus>
<p id="ile" class="uwaga"></p><div id="wyniki"></div>
<script>
(function(){
  var dane=[], q=document.getElementById('q'), out=document.getElementById('wyniki'), ile=document.getElementById('ile');
  function norm(s){return s.toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').replace(/ł/g,'l');}
  function esc(s){return s.replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
  function szukaj(){
    var s=norm(q.value.trim()); out.innerHTML='';
    if(s.length<2){ile.textContent='';return;}
    var slowa=s.split(/\\s+/), wyn=dane.filter(function(x){var t=norm(x.t+' '+x.g.join(' '));return slowa.every(function(w){return t.indexOf(w)>=0;});});
    wyn.sort(function(a,b){return (b.d||'').localeCompare(a.d||'');});
    ile.textContent=wyn.length+' wyników';
    out.innerHTML=wyn.slice(0,100).map(function(x){
      var d=x.d?x.d.split('-').reverse().slice(0,2).join('.'):'';
      return '<article class="poz"><div class="poz-data">'+d+'</div><div class="poz-tresc"><p class="poz-meta">'+x.g.map(function(g){return '<span class="tag">#'+esc(g)+'</span>';}).join('')+(x.w?' <span class="z-wydania">wyd. nr '+x.w+'</span>':'')+'</p><p><a href="'+x.u+'">'+esc(x.t)+'</a></p></div></article>';
    }).join('');
  }
  fetch('szukaj.json').then(function(r){return r.json();}).then(function(j){dane=j; var p=new URLSearchParams(location.search).get('q'); if(p){q.value=p;} szukaj();});
  q.addEventListener('input',szukaj);
})();
</script>"""
        self.zapisz("szukaj.html", strona("Szukaj", tresc, "", "", "szukaj"))

    def rss(self):
        items = ""
        for w in list(reversed(self.wydania))[:30]:
            url = f"{BASE_URL}wydania/{w['_slug']}.html"
            opis = " ".join(czysty(z, self.osoby, self.pojecia) for z in w["w_skrocie"])
            d = data_(w["data"])
            gg, mm = (w.get("godzina") or "20:00").split(":")
            pub = dt.datetime(d.year, d.month, d.day, int(gg), int(mm), tzinfo=dt.timezone(dt.timedelta(hours=2)))
            rodzaj = "Wydanie tygodniowe" if w.get("typ") == "tygodniowe" else "Wydanie"
            items += f"""<item><title>{xml_escape(f"{rodzaj} nr {w['nr']} – {data_dluga(w['data'])}")}</title><link>{url}</link><guid>{url}</guid>
<pubDate>{pub.strftime('%a, %d %b %Y %H:%M:%S %z')}</pubDate><description>{xml_escape(opis)}</description></item>\n"""
        self.zapisz("feed.xml", f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>{TYTUL} – {PODTYTUL}</title><link>{BASE_URL}</link>
<description>Codzienny przegląd sytuacji międzynarodowej ze źródłami i weryfikacją faktów.</description><language>pl</language>
{items}</channel></rss>
""")

    def statyczne(self):
        self.zapisz("robots.txt", "User-agent: *\nDisallow: /\n")
        self.zapisz(".nojekyll", "")
        self.zapisz("404.html", strona("Nie znaleziono", '<section class="winieta"><h1>Nie ma takiej strony</h1><p class="w-stan"><a href="/prasowka/index.html">Wróć do wydań</a></p></section>', "/prasowka/"))
        src = REPO / "narzedzia" / "styl.css"
        (self.out / "assets").mkdir(parents=True, exist_ok=True)
        shutil.copy(src, self.out / "assets" / "styl.css")

    def wszystko(self):
        for sciezka in ("wydania", "watki", "osoby", "pojecia"):
            p = self.out / sciezka
            if p.exists():
                shutil.rmtree(p)
        for i, w in enumerate(self.wydania):
            self.wydanie(i, w)
        self.index()
        self.watki()
        self.osoby_strony()
        self.pojecia_strony()
        self.korekty()
        self.ranking_strona()
        self.jak_weryfikujemy()
        self.szukaj()
        self.rss()
        self.statyczne()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dane", type=Path, default=REPO / "dane")
    ap.add_argument("--wyjscie", type=Path, default=REPO)
    ap.add_argument("--sprawdz", action="store_true")
    a = ap.parse_args()
    global RANKING
    RANKING = wczytaj_ranking(a.dane)
    tagi, osoby, pojecia, wydania, rewizje = wczytaj(a.dane)
    bledy = waliduj(tagi, osoby, pojecia, wydania, rewizje)
    if bledy:
        print("WALIDACJA NIE PRZESZŁA — strona nie została zbudowana:", file=sys.stderr)
        for x in bledy:
            print("  - " + x, file=sys.stderr)
        sys.exit(1)
    print(f"Walidacja OK: {len(wydania)} wydań, {sum(len(w['zarys']) for w in wydania)} pozycji, "
          f"{len(tagi)} hashtagów, {len(osoby)} osób, {len(pojecia)} pojęć.")
    if a.sprawdz:
        return
    Budowa(tagi, osoby, pojecia, wydania, a.wyjscie, rewizje).wszystko()
    print(f"Strona zbudowana w {a.wyjscie}")


if __name__ == "__main__":
    main()
