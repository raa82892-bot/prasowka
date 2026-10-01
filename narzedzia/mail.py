#!/usr/bin/env python3
"""Mail HTML i tekstowy z tych samych danych co strona.

Użycie: python3 narzedzia/mail.py RRRR-MM-DD [--dane KATALOG] [--wyjscie KATALOG]
Tworzy mail-RRRR-MM-DD.html (htmlBody) i mail-RRRR-MM-DD.txt (body) w katalogu wyjście (domyślnie ./build).
Wymaga, by dane przeszły walidację build.py.
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build as B  # noqa: E402

GRANAT, ZLOTY, MORZE, OCHRA, CZERW, SZARY = "#17243B", "#C9A227", "#1D5F86", "#9A5B12", "#A8261B", "#5C6673"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--dane", type=Path, default=B.REPO / "dane")
    ap.add_argument("--wyjscie", type=Path, default=Path("build"))
    a = ap.parse_args()
    B.RANKING = B.wczytaj_ranking(a.dane)
    tagi, osoby, pojecia, wydania, rewizje = B.wczytaj(a.dane)
    bledy = B.waliduj(tagi, osoby, pojecia, wydania, rewizje)
    if bledy:
        print("WALIDACJA NIE PRZESZŁA:\n  - " + "\n  - ".join(bledy), file=sys.stderr)
        sys.exit(1)
    w = next((x for x in wydania if x["_slug"] == a.slug), None)
    if not w:
        sys.exit(f"Brak wydania {a.slug}")
    url = f"{B.BASE_URL}wydania/{w['_slug']}.html"
    e = B.e

    def T(s):
        t = e(s)
        t = re.sub(r"\*\*(.+?)\*\*", r'<span style="background:#FFE9A3;font-weight:bold;">\1</span>', t)
        widziane = set()

        def zam(m):
            rodzaj, ident, wlasny = m.group(1), m.group(2), m.group(3)
            if rodzaj == "o":
                o = osoby[ident]
                napis = e(wlasny) if wlasny else e(o["imie"])
                if ident not in widziane and not wlasny:
                    widziane.add(ident)
                    return f'<b>{napis}</b> <span style="color:{SZARY};">({e(o["funkcja"])})</span>'
                return f"<b>{napis}</b>"
            p = pojecia[ident]
            return f'{e(wlasny) if wlasny else e(p["nazwa"])} <span style="color:{SZARY};">({e(p["pelna"])})</span>'
        return B.ZNACZNIK_RE.sub(zam, t)

    def tagi_html(lista):
        out = ""
        for t in lista or []:
            kol = MORZE if tagi[t]["grupa"] == "miejsce" else OCHRA
            out += (f'<a href="{B.BASE_URL}watki/{t}.html" style="display:inline-block;color:{kol};font-size:12px;'
                    f'text-decoration:none;margin-right:8px;">#{e(tagi[t]["nazwa"])}</a>')
        return out

    def kropka(z):
        o = B.RANKING.ocen(z.get("nazwa"), z.get("url")) if B.RANKING else None
        if not o:
            return ""
        p = B.RANKING.poziomy[o["poziom"]]
        return (f'<span title="Wiarygodność {o["poziom"]}/5 – {e(p["nazwa"])}" style="display:inline-block;width:9px;height:9px;'
                f'border-radius:5px;background:{p["kolor"]};margin:0 4px 0 1px;"></span>')

    def zrodla(lista):
        if not lista:
            return ""
        return (f'<div style="font-size:12px;font-style:italic;color:{SZARY};margin-top:3px;">Źródła: ' +
                "; ".join(f'{kropka(z)}<a href="{e(z["url"])}" style="color:{SZARY};">{e(z["nazwa"])}, {B.data_krotka(z["data"])}</a>' for z in lista)
                + "</div>")

    def legenda_wz():
        if not B.RANKING:
            return ""
        return ('<tr><td style="padding:6px 20px 0;font-size:12px;color:' + SZARY + ';">Kolor przy źródle: wiarygodność wg '
                f'<a href="{B.BASE_URL}zrodla.html" style="color:{SZARY};">rankingu źródeł</a> – ' +
                " ".join(f'<span style="display:inline-block;width:9px;height:9px;border-radius:5px;background:{p["kolor"]};margin:0 3px 0 6px;"></span>{e(p["nazwa"].lower())}'
                         for _, p in sorted(B.RANKING.poziomy.items())) + "</td></tr>")

    def pasek(t):
        return (f'<tr><td style="padding:16px 20px 4px;"><div style="background:{GRANAT};color:#fff;font-weight:bold;'
                f'font-size:14px;padding:7px 12px;">{t}</div></td></tr>')

    rodzaj = "Wydanie tygodniowe" if w.get("typ") == "tygodniowe" else "Wydanie"
    r = []
    r.append(f'<tr><td style="background:{GRANAT};padding:18px 20px;"><div style="font-family:Georgia,serif;font-size:24px;color:#fff;font-weight:bold;">Prasówka</div>'
             f'<div style="font-size:13px;color:#C9D1E3;margin-top:4px;">{rodzaj} nr {e(w["nr"])}, {B.data_pelna(w["data"])}, stan na godz. {e(w["godzina"])} CEST</div></td></tr>')
    r.append(f'<tr><td style="padding:16px 20px 4px;"><div style="border-left:4px solid {ZLOTY};background:#FBF8EE;padding:12px 14px;">'
             f'<div style="font-weight:bold;color:{GRANAT};margin-bottom:4px;">W skrócie</div>' +
             "".join(f'<p style="margin:0 0 6px;">{T(z)}</p>' for z in w["w_skrocie"]) +
             f'<p style="margin:8px 0 0;"><a href="{url}" style="color:{MORZE};font-weight:bold;">Czytaj na stronie, z osią wątków i wyszukiwarką</a></p></div></td></tr>')
    m = w.get("mapa_ciepla")
    if m:
        r.append(pasek("Mapa ciepła tygodnia"))
        glowa = "".join(f'<td style="font-size:10px;color:{SZARY};text-align:center;padding:2px;">{B.DNI_KROTKO[B.data_(d).weekday()]}<br>{B.data_krotka(d)}</td>' for d in m["kolumny"])
        wiersze = ""
        for rw in m["wiersze"]:
            kom = ""
            for j, v in enumerate(rw["wartosci"]):
                odn = (rw.get("odnosniki") or [""] * len(rw["wartosci"]))[j]
                spr = (rw.get("sprostowane") or [False] * len(rw["wartosci"]))[j]
                znak = '<span style="color:#F08A80;">▲</span>' if spr else ""
                tekst = e(odn) if v >= 2 and odn else ""
                kolor = "#fff" if v >= 2 else GRANAT
                kom += (f'<td style="background:{B.MAPA_TLO[v]};color:{kolor};font-size:10px;font-weight:bold;'
                        f'text-align:center;height:26px;width:40px;">{tekst}{znak}</td>')
            wiersze += (f'<tr><td style="font-size:11px;text-align:right;padding-right:6px;white-space:nowrap;">'
                        f'<a href="{B.BASE_URL}watki/{rw["tag"]}.html" style="color:{GRANAT};text-decoration:none;">#{e(tagi[rw["tag"]]["nazwa"])}</a></td>{kom}</tr>')
        r.append(f'<tr><td style="padding:6px 20px;"><table role="presentation" cellpadding="0" cellspacing="2" style="font-family:Arial,sans-serif;">'
                 f'<tr><td></td>{glowa}</tr>{wiersze}</table><div style="font-size:12px;color:{SZARY};margin-top:6px;">'
                 f'Skala: jasne 0 nic, 1 drobny rozwój, 2 istotne zdarzenie, najciemniejsze 3 przełom; liczby = nr wydania/punkt; ▲ sprostowane w tym tygodniu.</div></td></tr>')
    if w.get("weryfikacja"):
        r.append(pasek("Weryfikacja tygodnia"))
        for k in w["weryfikacja"]:
            kol = {"POTWIERDZONE": GRANAT, "SPROSTOWANE": CZERW, "NADAL OTWARTE": OCHRA}[k["werdykt"]]
            r.append(f'<tr><td style="padding:8px 20px;border-bottom:1px solid #EEF2F3;font-size:14px;">'
                     f'<span style="font-size:11px;font-weight:bold;border:1px solid {kol};color:{kol};padding:0 4px;">{e(k["werdykt"])}</span>'
                     f'<div style="margin-top:4px;"><b>Pisaliśmy:</b> {e(k["bylo"])}<br><b>Jak jest:</b> {e(k["jest"])}</div>{zrodla(k["zrodla"])}</td></tr>')
    if w.get("korekty"):
        r.append(f'<tr><td style="padding:8px 20px;"><div style="border-left:4px solid {CZERW};background:#FBECEA;padding:10px 14px;font-size:14px;">'
                 f'<b style="color:{CZERW};">Korekta</b>' +
                 "".join(f'<p style="margin:6px 0 0;"><b>Było:</b> {e(k["bylo"])}<br><b>Jest:</b> {e(k["jest"])}</p>{zrodla(k["zrodla"])}' for k in w["korekty"])
                 + "</div></td></tr>")
    r.append(pasek("I. Najważniejsze przesunięcia tygodnia" if w.get("typ") == "tygodniowe" else "I. Zarys wydarzeń"))
    r.append(legenda_wz())
    for kod, nazwa in B.BLOKI:
        poz = sorted([it for it in w["zarys"] if it["blok"] == kod], key=lambda x: x["data"])
        if not poz:
            continue
        r.append(f'<tr><td style="padding:10px 20px 0;font-size:13px;font-weight:bold;color:{GRANAT};border-bottom:1px solid #D3DCE1;">{nazwa}</td></tr>')
        for it in poz:
            odz = ""
            if it.get("etap"):
                odz += f'<span style="font-size:11px;font-weight:bold;border:1px solid {GRANAT};color:{GRANAT};padding:0 4px;margin-right:6px;">{e(it["etap"])}</span>'
            r.append(f'<tr><td style="padding:10px 20px 8px;border-bottom:1px solid #EEF2F3;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
                     f'<td valign="top" style="width:50px;font-weight:bold;font-size:13px;color:{GRANAT};">{B.data_krotka(it["data"])}</td>'
                     f'<td valign="top"><div>{tagi_html(it["tagi"])}{odz}</div><div style="margin-top:2px;">{T(it["tekst"])}</div>'
                     + (f'<div style="margin:4px 0 0;padding:5px 8px;background:#E1EEF5;border-left:3px solid {MORZE};font-size:14px;"><b>Dla Polski:</b> {T(it["dla_polski"])}</div>' if it.get("dla_polski") else "")
                     + f'{zrodla(it["zrodla"])}</td></tr></table></td></tr>')
    if w.get("analizy"):
        r.append(pasek("II. Analizy"))
        r.append(f'<tr><td style="padding:4px 20px;font-size:13px;color:{SZARY};font-style:italic;">Interpretacje, nie ustalenia. Każda ma autora.</td></tr>')
        for x in w["analizy"]:
            r.append(f'<tr><td style="padding:8px 20px;"><div style="font-family:Georgia,serif;font-size:17px;font-weight:bold;color:{GRANAT};">{e(x["tytul"])}</div>'
                     f'<div style="font-size:13px;color:{SZARY};">Ocena: {e(x["autor"])}</div><div style="margin-top:4px;">{T(x["tekst"])}</div>'
                     f'<div style="margin:6px 0 0 10px;padding:6px 10px;background:#E1EEF5;border-left:3px solid {MORZE};"><b>Dla Polski:</b> {T(x["dla_polski"])}</div>{zrodla(x.get("zrodla"))}</td></tr>')
    if w.get("tracker"):
        r.append(pasek("Tracker wątków"))
        r.append(f'<tr><td style="padding:6px 20px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="font-size:13px;">'
                 f'<tr><td style="color:{SZARY};font-weight:bold;">Wątek</td><td style="color:{SZARY};font-weight:bold;">Tydzień temu</td><td style="color:{SZARY};font-weight:bold;">Dziś</td><td></td></tr>' +
                 "".join(f'<tr><td style="padding:5px 6px 5px 0;border-top:1px solid #EEF2F3;vertical-align:top;">{tagi_html([t["tag"]])}</td>'
                         f'<td style="padding:5px 6px 5px 0;border-top:1px solid #EEF2F3;vertical-align:top;">{T(t["tydzien_temu"])}</td>'
                         f'<td style="padding:5px 6px 5px 0;border-top:1px solid #EEF2F3;vertical-align:top;">{T(t["dzis"])}</td>'
                         f'<td style="border-top:1px solid #EEF2F3;font-size:16px;font-weight:bold;color:{GRANAT};vertical-align:top;">{e(t["kierunek"])}</td></tr>' for t in w["tracker"])
                 + "</table></td></tr>")
    if w.get("czytelnia"):
        r.append(pasek("Czytelnia OSW i PISM"))
        for c in w["czytelnia"]:
            r.append(f'<tr><td style="padding:6px 20px;font-size:14px;border-bottom:1px solid #EEF2F3;"><a href="{e(c["url"])}" style="color:{MORZE};font-weight:bold;">{e(c["tytul"])}</a>'
                     f'<span style="color:{SZARY};"> · {", ".join(e(x) for x in (c.get("autor"), c.get("wydawca"), c.get("numer"), B.data_krotka(c["data"])) if x)}</span>'
                     f'<div>{T(c["po_co"])}</div></td></tr>')
    r.append(pasek("III. Kalendarz"))
    kal = "".join(f'<tr><td style="width:60px;font-weight:bold;color:{GRANAT};padding:4px 0;border-bottom:1px solid #EEF2F3;vertical-align:top;">{B.data_krotka(k["data"])}</td>'
                  f'<td style="padding:4px 0;border-bottom:1px solid #EEF2F3;">{T(k["tekst"])}</td></tr>' for k in sorted(w.get("kalendarz", []), key=lambda k: k["data"]))
    poza = ""
    if w.get("poza_oknem"):
        poza = (f'<div style="font-size:13px;color:{SZARY};margin-top:8px;"><b>Poza oknem, ale przesądzające:</b> ' +
                "; ".join(f'{B.data_dluga(k["data"])} – {T(k["tekst"])}' for k in w["poza_oknem"]) + "</div>")
    r.append(f'<tr><td style="padding:6px 20px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="font-size:14px;">{kal}</table>{poza}</td></tr>')
    za = w.get("zrodla_analityczne") or {}

    def pub(lst):
        if not lst:
            return "brak nowych publikacji w ostatnich 3 dniach"
        return "; ".join(f'<a href="{e(p["url"])}" style="color:{SZARY};">{e(p["tytul"])}</a>, {B.data_krotka(p["data"])}' for p in lst)
    nie_ma = ""
    if w.get("czego_nie_ma"):
        nie_ma = "<b>Czego tu nie ma.</b> " + "; ".join(f'{T(c["tekst"])} (próg: {e(c["prog"])})' for c in w["czego_nie_ma"]) + "<br><br>"
    r.append(f'<tr><td style="padding:14px 20px 18px;font-size:12px;color:{SZARY};border-top:1px solid #D3DCE1;">'
             f'<b>Stan źródeł analitycznych.</b> OSW: {pub(za.get("osw"))}. PISM: {pub(za.get("pism"))}.<br><br>{nie_ma}'
             f'<b>Nota.</b> {T(w.get("nota", ""))} Jak weryfikujemy: <a href="{B.BASE_URL}jak-weryfikujemy.html" style="color:{SZARY};">opis procedury</a>. '
             f'Archiwum i wątki: <a href="{B.BASE_URL}" style="color:{SZARY};">{B.BASE_URL}</a></td></tr>')
    html = ('<!DOCTYPE html><html lang="pl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head>'
            '<body style="margin:0;padding:0;background:#EEF2F3;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#EEF2F3;">'
            '<tr><td align="center" style="padding:12px 6px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            'style="max-width:640px;background:#FFFFFF;font-family:Arial,Helvetica,sans-serif;color:#1E2530;font-size:15px;line-height:1.5;">'
            + "".join(r) + "</table></td></tr></table></body></html>")

    # wersja tekstowa
    def C(s):
        return B.czysty(s, osoby, pojecia)
    t = [f"Prasówka – {rodzaj.lower()} nr {w['nr']}, {B.data_pelna(w['data'])}, stan na {w['godzina']} CEST", "", "W SKRÓCIE"]
    t += [C(z) for z in w["w_skrocie"]]
    t += ["", f"Całe wydanie na stronie: {url}", "", "ZARYS WYDARZEŃ"]
    for it in sorted(w["zarys"], key=lambda x: (dict((k, i) for i, (k, _) in enumerate(B.BLOKI))[x["blok"]], x["data"])):
        ozn = it.get("etap") or ""
        t.append(f"{B.data_krotka(it['data'])} {' '.join('#' + tagi[g]['nazwa'] for g in it['tagi'])}{(' [' + ozn + ']') if ozn else ''}: {C(it['tekst'])}")
        t.append("   Źródła: " + "; ".join(f"{z['nazwa']} {z['url']}" for z in it["zrodla"]))
    if w.get("analizy"):
        t += ["", "ANALIZY (interpretacje, nie ustalenia)"]
        for x in w["analizy"]:
            t += [f"{x['tytul']} (ocena: {x['autor']}): {C(x['tekst'])}", f"   Dla Polski: {C(x['dla_polski'])}"]
    t += ["", "KALENDARZ"] + [f"{B.data_krotka(k['data'])} {C(k['tekst'])}" for k in sorted(w.get("kalendarz", []), key=lambda k: k["data"])]
    tekst = "\n".join(t) + "\n"

    a.wyjscie.mkdir(parents=True, exist_ok=True)
    (a.wyjscie / f"mail-{a.slug}.html").write_text(html, "utf-8")
    (a.wyjscie / f"mail-{a.slug}.txt").write_text(tekst, "utf-8")
    print(f"mail-{a.slug}.html: {len(html)} znaków (limit 60 000); mail-{a.slug}.txt: {len(tekst)} znaków")
    if len(html) > 60000:
        print("UWAGA: HTML przekracza 60 000 znaków — podziel mail na dwie części.", file=sys.stderr)


if __name__ == "__main__":
    main()
