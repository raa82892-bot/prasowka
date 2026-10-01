# Prasówka

Przegląd sytuacji międzynarodowej: codzienne wydania ze źródłami i weryfikacją faktów, powiązane hashtagami wątków.

Strona: https://raa82892-bot.github.io/prasowka/

## Jak to działa

Treść każdego wydania jest zapisywana raz, jako dane, a strona i mail powstają z nich automatycznie.

```
dane/
  wydania/RRRR-MM-DD.json   jedno wydanie (zarys, analizy, kalendarz, korekty)
  tagi.json                 słownik hashtagów + „Na czym stoimy” dla każdego wątku
  osoby.json                karty „Kto jest kim” (funkcja ze źródłem i datą weryfikacji)
  pojecia.json              słownik pojęć
narzedzia/
  build.py                  walidacja + budowa strony (pliki HTML w katalogu głównym)
  mail.py                   mail HTML i tekstowy dla danego wydania
  styl.css                  wygląd strony
```

Pliki HTML w katalogu głównym (`index.html`, `wydania/`, `watki/`, `osoby/`, `pojecia/` …) są generowane — nie edytuj ich ręcznie.

## Publikacja wydania

```
python3 narzedzia/build.py            # walidacja i budowa; przy błędzie nic nie powstaje
python3 narzedzia/mail.py RRRR-MM-DD  # build/mail-RRRR-MM-DD.html i .txt
git add -A && git commit -m "Wydanie nr N, RRRR-MM-DD" && git push
```

Do zarysu wchodzą **wyłącznie informacje potwierdzone** (komunikat instytucji, dane urzędowe albo dwa niezależne serwisy). Niepotwierdzone i sporne idą do `czego_nie_ma` z progiem `dokumentacja`; pola `status` nie ma (walidacja odrzuca je w wydaniach od 01.10.2026).

Walidacja odrzuca wydanie, jeśli którakolwiek pozycja nie ma źródła z linkiem i datą, ma hashtag spoza słownika, osobę bez karty albo analizę bez autora.

## Format wydania (dane/wydania/RRRR-MM-DD.json)

```json
{
  "nr": 12, "data": "2026-10-01", "godzina": "20:30", "typ": "dzienne",
  "w_skrocie": ["3–5 zdań. **słowo kluczowe**, {{o:id-osoby}}, {{p:id-pojecia}}"],
  "korekty": [{"dotyczy": "2026-09-30#z3", "bylo": "…", "jest": "…", "zrodla": [ZRODLO]}],
  "zarys": [{
    "id": "z1", "blok": "wojna|polska|instytucje|swiat|gospodarka", "data": "2026-10-01",
    "tagi": ["kaliningrad", "nato"], "etap": "PROPOZYCJA|ZAPOWIEDŹ|PRZYJĘTE|W TOKU (opcjonalnie)",
    "tekst": "1–2 zdania: co się stało i co się zmieniło.",
    "zrodla": [{"nazwa": "Reuters", "url": "https://…", "data": "2026-10-01"}]
  }],
  "analizy": [{"tytul": "…", "autor": "OSW (J. Kowalski)", "tekst": "…", "dla_polski": "…", "tagi": ["…"], "zrodla": [ZRODLO]}],
  "kalendarz": [{"data": "2026-10-03", "tekst": "…", "tagi": ["lotwa", "wybory"]}],
  "poza_oknem": [{"data": "2026-11-03", "tekst": "…"}],
  "zrodla_analityczne": {"osw": [{"tytul": "…", "autor": "…", "data": "…", "url": "…"}], "pism": [{"tytul": "…", "numer": "Biuletyn nr 65 (2697)", "data": "…", "url": "…"}]},
  "czego_nie_ma": [{"tekst": "…", "prog": "dokumentacja|następstwo|kompletność"}],
  "nota": "Kiedy powstało, co zweryfikowano dziś, czego nie, kontrola niezależna."
}
```

Przy każdym wydaniu aktualizuj też w `dane/tagi.json` pola `stan`, `stan_data`, `stan_zrodla` dla wątków, których dotyczyło.

## Wydanie tygodniowe (dodatkowe pola)

`"typ": "tygodniowe"`, `"okres": "26.09–02.10.2026"`; `zarys` to 5 przesunięć tygodnia, każde może mieć `"dla_polski"`.

```json
"weryfikacja": [{"dotyczy": "2026-09-29#z1", "bylo": "…", "jest": "…", "werdykt": "POTWIERDZONE|SPROSTOWANE|NADAL OTWARTE", "zrodla": [ZRODLO]}],
"mapa_ciepla": {"kolumny": ["2026-09-26", "…"], "wiersze": [{"tag": "kaliningrad", "wartosci": [0,1,2,3,…], "odnosniki": ["", "", "9/1.2", …], "sprostowane": [false, …]}]},
"tracker": [{"tag": "slowacja", "tydzien_temu": "…", "dzis": "…", "kierunek": "↑|↓|→"}],
"czytelnia": [{"tytul": "…", "autor": "…", "wydawca": "OSW|PISM", "numer": "…", "data": "…", "url": "…", "po_co": "…"}]
```

Werdykt SPROSTOWANE z polem `dotyczy` oznacza oryginalną pozycję znakiem ▲ i trafia do rejestru korekt.

## Grafiki

`build.py` rysuje dwie grafiki SVG z tych samych danych (bez JavaScriptu poza przewinięciem osi do końca):

- **Mapa Europy** — na stronie głównej (pozycje z 7 dni) i w każdym wydaniu. Kraj z hashtagiem-miejscem jest zabarwiony liczbą pozycji (1 / 2–3 / 4+) i prowadzi do strony wątku; Polska liczy pozycje z bloku „Polska”. Przypisanie hashtagów do krajów: `MAPA_TAGI` w `build.py`; miejsca poza kadrem (USA, Iran, Chiny) są wymienione pod mapą.
- **Oś czasu wątku** — na każdej stronie `watki/<tag>.html`: kropka = pozycja w dniu zdarzenia (pełna – pozycja, czerwona – sprostowana; pusta tylko w archiwum sprzed 01.10.2026), romb = termin z kalendarza; kliknięcie przenosi do pozycji na liście.

Kontury (`narzedzia/europa.json`, Natural Earth 1:50m, Krym w granicach Ukrainy) generuje jednorazowo `narzedzia/mapa_dane.py`; nowy hashtag-miejsce w Europie wymaga dopisania do `MAPA_TAGI` (i ewentualnie etykiety w `mapa_dane.py`).
