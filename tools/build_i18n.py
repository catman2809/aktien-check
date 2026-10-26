"""Erzeugt static/i18n_en.json aus den Übersetzungsdateien tools/i18n_en_*.py.

Aufruf: python tools/build_i18n.py
Prüft dabei, dass jede englische Vorlage dieselben Platzhalter ({0}, {1} … bzw. {*}) nutzt wie die deutsche.
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import i18n_en_a as a  # noqa: E402
import i18n_en_b as b  # noqa: E402
import i18n_en_c as c  # noqa: E402
import i18n_en_d as d  # noqa: E402


def norm(t):
    return re.sub(r"\s+", " ", t.strip())


def main():
    tpl, problems = {}, []
    for part in (a.ADJ, a.COUNTRIES, a.SECTORS, a.A, b.B, c.C, d.PROFILES, d.D):
        for de, en in part.items():
            k = norm(de)
            if k in tpl and tpl[k] != en:
                problems.append(f"unterschiedlich doppelt: {k!r}")
            tpl[k] = en
    wild = list(d.WILD)
    # Geschäftsmodell-Sätze mit Firmennamen: „{Name} <Erlösmodell>.“
    for de, en in d.PROFILES.items():
        if de[:1].islower():
            wild.append((f"{{*}} {de}.", f"{{*}} {en}."))
    # Hauptsitz „Stadt, Land“
    for de, en in a.COUNTRIES.items():
        if de not in ("Sonstige", "Weitere") and " " not in de:
            wild.append((f"{{*}}, {de}", f"{{*}}, {en}"))
    for de, en in list(tpl.items()) + [(x, y) for x, y in wild]:
        ph_de = sorted(re.findall(r"\{\d+\}", de))
        ph_en = sorted(re.findall(r"\{\d+\}", en))
        if set(ph_en) - set(ph_de):
            problems.append(f"Platzhalter fehlen im Deutschen: {de!r} -> {en!r}")
        if de.count("{*") != en.count("{*") and "{*1}" not in en:
            problems.append(f"freie Teile ungleich: {de!r} -> {en!r}")
    out = {"tpl": tpl, "wild": [[norm(x), y] for x, y in wild]}
    dst = HERE.parent / "static" / "i18n_en.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(tpl)} Einträge, {len(wild)} Muster -> {dst} ({dst.stat().st_size // 1024} KB)")
    for p_ in problems:
        print("WARNUNG:", p_)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
