#!/usr/bin/env python3
"""Aktien-Check – lokale Kaufen/Halten/Verkaufen-Einschätzung für beliebige Aktien.

Start:  python aktien_check.py   ->  öffnet http://localhost:8765 im Browser.
Datenquellen: Yahoo Finance (via yfinance), Google-News-RSS, Yahoo-Finance-RSS.
Keine Anlageberatung – regelbasiertes Modell auf Basis öffentlich verfügbarer Daten.
"""
import hashlib
import hmac
import http.cookies
import json
import logging
import math
import os
import re
import secrets
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    import yfinance as yf
except ImportError:
    print("Fehlendes Paket. Bitte ausführen:  python -m pip install yfinance")
    sys.exit(1)

logging.getLogger("yfinance").setLevel(logging.CRITICAL)
LOG = logging.getLogger("aktien-check")
if not LOG.handlers:
    _h = logging.StreamHandler(sys.stdout)  # StreamHandler schreibt jede Zeile sofort (flush)
    _h.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S"))
    LOG.addHandler(_h)
    LOG.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())
    LOG.propagate = False
START_TIME = time.time()
from collections import deque  # noqa: E402
LOG_BUFFER = deque(maxlen=400)


class _BufferHandler(logging.Handler):
    def emit(self, record):
        try:
            LOG_BUFFER.append({"t": int(record.created), "level": record.levelname, "msg": record.getMessage()[:400]})
        except Exception:
            pass


LOG.addHandler(_BufferHandler())
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PORT = 8765
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}

# ---------------------------------------------------------------------------
# Skalen & Adjektiv-Listen (Vorgaben)
# ---------------------------------------------------------------------------
RATING_SCALE = [  # (Mindest-Score, Label, Gruppe)
    (55, "Strong Buy", "Kaufen"), (42, "Buy", "Kaufen"), (32, "Outperform", "Kaufen"),
    (23, "Overweight", "Kaufen"), (15, "Accumulate", "Kaufen"),
    (9, "Market Perform", "Halten"), (3, "Equal-weight", "Halten"),
    (-5, "Neutral", "Halten"), (-15, "Hold", "Halten"),
    (-25, "Underperform", "Verkaufen"), (-33, "Underweight", "Verkaufen"),
    (-42, "Reduce", "Verkaufen"), (-55, "Sell", "Verkaufen"), (-999, "Strong Sell", "Verkaufen"),
]

ADJ = {
    "valuation": ["unterbewertet", "günstig", "preiswert", "attraktiv bewertet", "unterschätzt",
                  "fair bewertet", "angemessen bewertet", "marktgerecht", "überbewertet", "teuer",
                  "ambitioniert bewertet", "heißgelaufen", "überhitzt"],
    "quality": ["solide", "robust", "stabil", "profitabel", "margenstark", "cashflowstark",
                "marktführend", "dominant", "wettbewerbsstark (mit „Burggraben“)", "schwach",
                "angeschlagen", "defizitär", "verschuldet", "strauchelnd"],
    "growth": ["wachstumsstark", "dynamisch", "expansiv", "aufstrebend", "innovativ", "reif",
               "gesättigt", "stagnierend", "rückläufig"],
    "risk": ["defensiv", "konservativ", "krisenfest", "schwankungsarm", "berechenbar", "volatil",
             "spekulativ", "riskant", "zyklisch", "konjunkturabhängig"],
    "dividend": ["dividendenstark", "ausschüttungsfreudig", "verlässlich", "renditestark",
                 "dividendenschwach", "unzuverlässig (bei Kürzungen)"],
    "chart": ["aufwärtsgerichtet", "bullish", "ausbruchsverdächtig", "erholt", "überverkauft",
              "abwärtsgerichtet", "bearish", "angeschlagen", "überkauft", "seitwärts tendierend"],
    "sentiment": ["gefragt", "beliebt", "gehypt", "übersehen", "vernachlässigt", "umstritten", "unbeliebt"],
    "summary": ["aussichtsreich", "chancenreich", "kaufenswert", "empfehlenswert", "neutral",
                "abwartend", "unattraktiv", "meidenswert"],
}

WEIGHTS = {"valuation": .25, "quality": .20, "growth": .15, "risk": .10,
           "dividend": .05, "chart": .10, "sentiment": .10, "macro": .05}

# Näherungswerte für langfristige Branchen-Mediane (KGV, EV/EBITDA)
SECTOR_REF = {
    "Technology": (28, 20), "Communication Services": (20, 12), "Consumer Cyclical": (22, 14),
    "Consumer Defensive": (21, 14), "Healthcare": (23, 15), "Financial Services": (14, 10),
    "Industrials": (22, 14), "Energy": (12, 6), "Utilities": (18, 11), "Real Estate": (30, 18),
    "Basic Materials": (16, 9),
}
DEFENSIVE = {"Consumer Defensive", "Utilities", "Healthcare"}
CYCLICAL = {"Consumer Cyclical", "Industrials", "Basic Materials", "Energy", "Financial Services", "Real Estate"}
RATE_SENSITIVE = {"Real Estate", "Utilities"}

# Branchenspezifische Bewertungsmodelle: klassische Kennzahlen (KGV, EV/EBITDA, FCF) passen nicht für jedes Geschäft
BIZ_MODELS = {
    "standard": ("Standardmodell", ""),
    "bank": ("Bank-Modell",
             "Banken werden über Kurs-Buchwert im Verhältnis zur Eigenkapitalrendite, ROE, ROA und Eigenkapitalquote "
             "bewertet – EV/EBITDA, Free Cashflow und Nettoverschuldung sind bei Banken nicht aussagekräftig."),
    "insurance": ("Versicherer-Modell",
                  "Versicherer werden über Kurs-Buchwert im Verhältnis zur Eigenkapitalrendite, ROE und Eigenkapital-"
                  "quote bewertet – EV/EBITDA, Free Cashflow und Nettoverschuldung sind hier nicht aussagekräftig."),
    "real_estate": ("Immobilien-Modell",
                    "Immobilienwerte/REITs werden über Kurs/FFO (Näherung: operativer Cashflow), Kurs-Buchwert (≈ NAV) "
                    "und Beleihungsquote bewertet – das KGV ist durch Abschreibungen und Neubewertungen verzerrt."),
    "loss_growth": ("Wachstum-mit-Verlust-Modell",
                    "Statt KGV (bei Verlusten nicht vorhanden) zählen EV/Umsatz im Verhältnis zum Wachstum, "
                    "die „Rule of 40“, Bruttomarge, Margentrend und die Cash-Reichweite."),
    "pre_revenue": ("Vorumsatz-Modell",
                    "Das Unternehmen erzielt (noch) kaum Umsatz – klassische Bewertung ist nicht möglich. Bewertet "
                    "werden Cash-Reichweite, Börsenwert im Verhältnis zur Kasse und Analystenziele; Empfehlung "
                    "höchstens im Halten-Bereich, da der Wert an Studien/Zulassungen/Durchbrüchen hängt."),
    "cyclical": ("Zykliker-Modell",
                 "Bei Rohstoff- und Zyklikerwerten täuscht das aktuelle KGV: am Gewinnhoch wirken sie billig. Zusätzlich "
                 "zählen das KGV auf Durchschnittsgewinne (normalisiert) und der Abstand der Marge zum Zyklusmittel."),
}
CYCLICAL_INDUSTRIES = {"Auto Manufacturers", "Auto Parts", "Marine Shipping", "Building Materials", "Airlines",
                       "Semiconductor Equipment & Materials", "Trucking", "Farm & Heavy Construction Machinery",
                       "Residential Construction", "Paper & Paper Products", "Lumber & Wood Production"}
NON_CYCLICAL_MATERIALS = {"Specialty Chemicals", "Packaging & Containers"}


def classify_business(m):
    ind, sec = re.sub(r"\s*[—–]\s*", " - ", m["industry"] or ""), m["sector"] or ""
    if ind.startswith("Banks") or ind in ("Capital Markets", "Mortgage Finance"):
        return "bank"
    if ind.startswith("Insurance") and ind != "Insurance Brokers":
        return "insurance"
    if sec == "Real Estate" or ind.startswith("REIT"):
        return "real_estate"
    rev = m["revenue"]
    losing = (m["net_m"] is not None and m["net_m"] < 0) or (m["pe"] is None and (m["net_incomes"] or [0])[0] is not None
                                                             and (m["net_incomes"] or [0])[0] < 0)
    if losing and (rev is None or (m["mcap"] and rev < m["mcap"] * 0.01) or rev < 5e7):
        return "pre_revenue"
    g = growth_estimate(m)
    if losing and g is not None and g >= 0.15:
        return "loss_growth"
    if (sec in ("Energy", "Basic Materials") and ind not in NON_CYCLICAL_MATERIALS) or ind in CYCLICAL_INDUSTRIES:
        return "cyclical"
    return "standard"

# Quellen-Tiers
TIER_DOMAINS = {
    1: ["reuters.com", "apnews.com", "cnbc.com", "marketwatch.com", "finance.yahoo.com", "yahoo.com",
        "investing.com", "finanzen.net", "onvista.de", "tagesschau.de", "n-tv.de", "nasdaq.com",
        "boerse-frankfurt.de", "bbc.com", "bbc.co.uk", "cnn.com", "finanznachrichten.de", "ariva.de"],
    2: ["bloomberg.com", "ft.com", "wsj.com", "barrons.com", "economist.com", "handelsblatt.com",
        "faz.net", "wiwo.de", "manager-magazin.de", "nytimes.com", "seekingalpha.com", "morningstar.com",
        "morningstar.de", "fortune.com", "forbes.com", "businessinsider.com", "businessinsider.de",
        "spiegel.de", "zeit.de", "sueddeutsche.de", "boersen-zeitung.de", "deraktionaer.de", "fool.com",
        "fool.de", "techcrunch.com", "theverge.com", "theinformation.com", "axios.com", "washingtonpost.com",
        "welt.de", "capital.de", "investors.com", "zacks.com", "benzinga.com", "thestreet.com",
        "coindesk.com", "theblock.co", "cointelegraph.com", "decrypt.co", "blockworks.co", "btc-echo.de",
        "bitcoinmagazine.com", "dlnews.com"],
    3: ["businesswire.com", "prnewswire.com", "globenewswire.com", "accesswire.com", "newsfilecorp.com",
        "eqs-news.com", "dgap.de", "pressetext.com", "openai.com", "deepmind.google", "blog.google",
        "anthropic.com", "newsroom", "investor", "ir."],
}
TIER_NAMES = {
    "reuters": 1, "associated press": 1, "ap news": 1, "cnbc": 1, "marketwatch": 1, "yahoo": 1,
    "investing.com": 1, "finanzen.net": 1, "onvista": 1, "tagesschau": 1, "n-tv": 1, "nasdaq": 1,
    "bloomberg": 2, "financial times": 2, "wall street journal": 2, "the wall street journal": 2, "barron": 2,
    "handelsblatt": 2, "faz": 2, "frankfurter allgemeine": 2, "wirtschaftswoche": 2, "seeking alpha": 2,
    "morningstar": 2, "forbes": 2, "fortune": 2, "business insider": 2, "der spiegel": 2, "der aktionär": 2,
    "the motley fool": 2, "motley fool": 2, "benzinga": 2, "zacks": 2, "investor's business daily": 2,
    "business wire": 3, "pr newswire": 3, "globenewswire": 3, "accesswire": 3, "eqs": 3, "dgap": 3,
}
TIER_WEIGHT = {1: 1.0, 2: 0.9, 3: 0.5, 0: 0.3}
TIER_LABEL = {
    1: "Tier 1 – Originäre, sehr zuverlässige Quellen",
    2: "Tier 2 – Glaubwürdige Quellen mit (weicher) Paywall",
    3: "Tier 3 – Pressemitteilungen & Unternehmensquellen (prüfbedürftig)",
    0: "Sonstige Quellen (geringe Gewichtung)",
}

JOB_AD = re.compile(r"\b(m/w/d|m/f/d|f/m/d|w/m/d|m/f/x|jobs?|careers?|karriere|stellenangebot|internship|"
                    r"praktikum|werkstudent|trainee|vacancy|hiring)\b|\(m/f/d\)|\(m/w/d\)")

# ---------------------------------------------------------------------------
# Tonalität von Schlagzeilen (Deutsch/Englisch): gewichtetes Lexikon + Regeln für Verneinung,
# Gegensätze ("trotz", "aber"), Verstärker, Prozentangaben und Fragen
# ---------------------------------------------------------------------------
SENT_PHRASES = [  # (Muster, Gewicht) – werden vor Einzelwörtern geprüft
    (r"(hebt|erhöht|hievt)( das)? (kurs)?ziel|(kurs)?ziel (erhöht|angehoben)", 2.0),
    (r"(senkt|kappt|reduziert|streicht)( das)? (kurs)?ziel|(kurs)?ziel (gesenkt|gekappt)", -2.0),
    (r"price target (raised|lifted|boosted|increased|hiked)|(raises|lifts|boosts|ups|hikes) (its )?(price )?target", 2.0),
    (r"price target (cut|lowered|slashed|trimmed|reduced)|(cuts|lowers|slashes|trims) (its )?(price )?target", -2.0),
    (r"(hebt|erhöht) (die )?(jahres)?prognose|prognose (angehoben|erhöht)|(raises|lifts|boosts|hikes) (its )?"
     r"(guidance|outlook|forecast)|(guidance|outlook|forecast) (raised|lifted)", 2.0),
    (r"(senkt|kappt|kassiert) (die )?(jahres)?prognose|prognose (gesenkt|gekappt)|(cuts|lowers|slashes|trims) (its )?"
     r"(guidance|outlook|forecast)|(guidance|outlook|forecast) (cut|lowered)|(weak|soft|disappointing) (guidance|outlook)|"
     r"(schwache[rn]?|enttäuschende[rn]?) (ausblick|prognose)", -2.0),
    (r"(beats?|tops?|exceeds?|surpass(es)?) (analyst |wall street )?(estimates|expectations|forecasts)|"
     r"übertrifft (die )?erwartungen", 1.8),
    (r"miss(es|ed)? (analyst |wall street )?(estimates|expectations|forecasts)|verfehlt (die )?erwartungen", -1.8),
    (r"nicht (mehr )?zu stoppen", 2.0),
    (r"legt (deutlich |kräftig )?zu", 1.0),
    (r"bricht (deutlich )?ein", -1.8),
    (r"unter druck", -1.0),
    (r"auf talfahrt", -1.6),
    (r"fallen weg|streicht (\S+ )?(stellen|jobs)|cuts? (\S+ )?jobs", -1.3),
    (r"short[- ]seller|leerverkäufer", -1.6),
    (r"(rekord|record)[- ]?(hoch|high|gewinn|profit|umsatz|revenue|quartal|quarter)|all[- ]time high|allzeithoch", 1.5),
    # Börsendeutsch der Kursmeldungen
    (r"gibt (deutlich |kräftig )?nach|mit abschlag|im minus|rote zahlen|in den roten zahlen", -1.0),
    (r"mit aufschlag|im plus|schwarze zahlen|in den schwarzen zahlen|gesucht\s*$", 0.8),
    (r"(not even|nicht einmal|selbst) .{0,60}(can't|cannot|can|could|kann|können) (lift|help|save|stützen|retten|helfen)"
     r"|(can't|cannot|fails to|unable to) (lift|help|save|boost)", -1.3),
    (r"dividend (hike|increase|raise)|(raises|hikes|boosts) (its |the )?dividend|erhöht (die )?dividende", 1.5),
    (r"(cuts|slashes|suspends) (its |the )?dividend|dividend (cut|suspension)|streicht (die )?dividende", -2.0),
    (r"(\d+[- ]year|multi[- ]year|\d+-jahres|mehrjahres)[- ]?(low|tief)|tiefststand|lowest (level )?since|"
     r"(jahres|mehrjahres)tief", -1.4),
    (r"(\d+[- ]year|multi[- ]year)[- ]?high|höchststand|highest (level )?since|(jahres|mehrjahres)hoch", 1.3),
]
SENT_NEUTRAL = r"weight[- ]loss|stop[- ]loss|abnehm\w*|was anleger (jetzt )?wissen|should you (buy|sell)|buy or sell|" \
               r"kaufen oder verkaufen|is (it )?time to buy|(\w+ ){0,3}stock (to )?watch"
SENT_WORDS = {  # exakte Wörter
    # Englisch positiv
    "surge": 1.5, "surges": 1.5, "surged": 1.5, "soar": 1.6, "soars": 1.6, "soared": 1.6, "jump": 1.2, "jumps": 1.2,
    "jumped": 1.2, "rally": 1.2, "rallies": 1.2, "rallied": 1.2, "rise": 1.0, "rises": 1.0, "rose": 1.0, "rising": 0.8,
    "gain": 0.9, "gains": 0.9, "gained": 0.9, "climb": 1.0, "climbs": 1.0, "climbed": 1.0, "beat": 1.3, "beats": 1.3,
    "tops": 1.0, "exceeds": 1.0, "strong": 0.8, "stronger": 0.8, "upgrade": 1.8, "upgrades": 1.8, "upgraded": 1.8,
    "outperform": 1.2, "outperforms": 1.2, "bullish": 1.2, "boost": 1.0, "boosts": 1.0, "boosted": 1.0, "wins": 1.0,
    "win": 0.8, "won": 0.8, "approval": 1.2, "approved": 1.2, "breakthrough": 1.3, "growth": 0.6, "grows": 0.8,
    "grew": 0.8, "recovery": 1.0, "rebound": 1.0, "rebounds": 1.0, "relief": 0.8, "higher": 0.5, "buyback": 0.8,
    "raises": 0.8, "raised": 0.8, "expands": 0.6, "optimistic": 1.0, "profit": 0.4, "profits": 0.4, "record": 1.0,
    "surging": 1.4, "soaring": 1.5, "jumping": 1.1, "rallying": 1.1, "climbing": 0.9, "gaining": 0.8,
    "lift": 1.0, "lifts": 1.0, "lifted": 1.0, "repurchase": 0.8, "buybacks": 0.8, "outperforming": 1.0,
    "upbeat": 1.0, "strength": 0.6, "tumbling": -1.5, "plunging": -1.7, "sinking": -1.3, "slumping": -1.4,
    "sliding": -1.0, "dropping": -1.0, "dip": -0.9, "dips": -0.9, "dipped": -0.9, "slips": -0.9, "slipped": -0.9,
    "underperforming": -1.0, "downbeat": -1.0, "selling": -0.3, "sells": -0.3,
    # Englisch negativ
    "plunge": -1.8, "plunges": -1.8, "plunged": -1.8, "plummet": -2.0, "plummets": -2.0, "tumble": -1.6,
    "tumbles": -1.6, "tumbled": -1.6, "sink": -1.4, "sinks": -1.4, "sank": -1.4, "slump": -1.5, "slumps": -1.5,
    "crash": -2.0, "crashes": -2.0, "fall": -1.1, "falls": -1.1, "fell": -1.1, "falling": -1.0, "drop": -1.1,
    "drops": -1.1, "dropped": -1.1, "decline": -1.0, "declines": -1.0, "declined": -1.0, "slide": -1.0, "slides": -1.0,
    "lower": -0.5, "miss": -1.4, "misses": -1.4, "missed": -1.4, "weak": -1.0, "weaker": -1.0, "downgrade": -1.8,
    "downgrades": -1.8, "downgraded": -1.8, "underperform": -1.2, "bearish": -1.2, "cut": -0.8, "cuts": -0.8,
    "loss": -1.0, "losses": -1.0, "lawsuit": -1.0, "lawsuits": -1.2, "probe": -1.2, "investigation": -1.2,
    "fraud": -2.5, "recall": -1.2, "warning": -1.3, "warns": -1.3, "layoffs": -1.2, "bankruptcy": -3.0,
    "default": -2.0, "concerns": -0.8, "fears": -0.8, "selloff": -1.5, "sell-off": -1.5, "disappoints": -1.3,
    "disappointing": -1.3, "disappointed": -1.3, "scandal": -2.0, "halts": -0.8, "delay": -0.8, "delayed": -0.8,
    "fine": -0.8, "fined": -1.2, "sued": -1.2, "slashes": -1.0, "struggles": -1.0, "slowdown": -1.0,
    # Deutsch positiv
    "steigt": 1.0, "steigen": 1.0, "gestiegen": 1.0, "stieg": 1.0, "springt": 1.3, "klettert": 1.1, "zieht": 0.3,
    "hebt": 0.8, "erhöht": 0.8, "übertrifft": 1.5, "überzeugt": 1.2, "stark": 0.8, "starke": 0.8, "starken": 0.8,
    "starkes": 0.8, "starker": 0.8, "gewinnt": 1.0, "zulegen": 1.0, "plus": 0.8, "erholt": 1.0, "erholung": 1.0,
    "hochgestuft": 1.8, "optimistisch": 1.0, "wächst": 0.8, "wachstum": 0.6, "zulassung": 1.0, "durchbruch": 1.3,
    "aufwärts": 0.8, "gefragt": 0.6, "boomt": 1.2, "glänzt": 1.2, "jubel": 1.0, "rally": 1.2,
    # Deutsch negativ
    "fällt": -1.1, "fallen": -1.0, "gefallen": -1.0, "fiel": -1.1, "sinkt": -1.1, "gesunken": -1.1, "sank": -1.1,
    "rutscht": -1.3, "stürzt": -1.8, "senkt": -0.9, "gesenkt": -0.9, "abgestuft": -1.8, "herabgestuft": -1.8,
    "schwach": -1.0, "schwache": -1.0, "schwachen": -1.0, "schwacher": -1.0, "schwaches": -1.0, "klage": -1.0,
    "klagen": -1.0, "warnt": -1.3, "minus": -0.8, "verfehlt": -1.4, "belastet": -1.0, "sorgen": -0.8, "pleite": -3.0,
    "attackiert": -0.8, "streicht": -0.8, "abwärts": -0.8, "rückläufig": -1.0, "tiefrot": -1.5, "flop": -1.5,
    "schwächelt": -1.0, "schwächer": -0.8, "verliert": -1.0, "verlieren": -1.0, "abverkauft": -1.3, "leichter": -0.5,
    "fester": 0.6, "freundlich": 0.5, "erholt": 1.0, "zieht": 0.3, "haussiert": 1.3, "gebrochen": -0.6,
}
SENT_STEMS = {  # Wortanfänge für deutsche Zusammensetzungen (Kursrutsch, Gewinnsprung, ...)
    "kurssprung": 1.5, "gewinnsprung": 1.6, "umsatzsprung": 1.4, "rekord": 1.2, "allzeithoch": 1.4,
    "kaufempfehlung": 1.5, "großauftrag": 1.5, "milliardenauftrag": 1.5, "dividendenerhöh": 1.5,
    "aktienrückkauf": 0.8, "rückkaufprogramm": 0.8, "hochstuf": 1.8, "kurssteigerung": 1.2, "aufwärtstrend": 1.0,
    "kursrutsch": -1.8, "kurseinbruch": -1.8, "einbruch": -1.6, "absturz": -1.8, "talfahrt": -1.6,
    "gewinnwarnung": -2.5, "umsatzwarnung": -2.3, "warnung": -1.3, "gewinnrückgang": -1.3, "umsatzrückgang": -1.2,
    "rückgang": -1.0, "verlust": -1.0, "enttäusch": -1.4, "ermittlung": -1.3, "betrug": -2.5, "skandal": -2.0,
    "insolvenz": -3.0, "stellenabbau": -1.2, "rückruf": -1.2, "verkaufsempfehlung": -1.5, "herabstuf": -1.8,
    "abstufung": -1.8, "dividendenkürz": -2.0, "abwärtstrend": -1.0, "leerverkäufer": -1.6, "kursverlust": -1.3,
    "schock": -1.3, "tiefststand": -1.4, "jahrestief": -1.3, "sparprogramm": -0.6,
    "höchststand": 1.2, "jahreshoch": 1.2, "kaufsignal": 1.2, "verkaufssignal": -1.2, "ausverkauf": -1.4,
}
SENT_NEGATORS = {"nicht", "kein", "keine", "keinen", "keiner", "keines", "nie", "ohne", "weder",
                 "no", "not", "never", "without", "nor", "isn't", "doesn't", "didn't", "won't", "can't"}
SENT_INTENS = {"deutlich", "massiv", "kräftig", "kräftige", "kräftigen", "dramatisch", "drastisch", "sehr", "extrem",
               "sharply", "massively", "heavily", "steeply", "significantly", "hugely", "big", "huge", "massive"}



# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------
def json_safe(o):
    """Ersetzt NaN/Unendlich rekursiv durch None – Browser akzeptieren kein NaN in JSON."""
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {k: json_safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [json_safe(v) for v in o]
    return o


def num(x):
    try:
        v = float(x)
        return None if math.isnan(v) or math.isinf(v) else v
    except (TypeError, ValueError):
        return None


def clamp(v, lo=-1.0, hi=1.0):
    return max(lo, min(hi, v))


def safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def row(df, *names):
    """Zeile aus einem yfinance-DataFrame (Spalten = Jahre, neueste zuerst)."""
    if df is None or getattr(df, "empty", True):
        return []
    for n in names:
        if n in df.index:
            return [num(v) for v in df.loc[n].tolist()]
    return []


def first(values):
    for v in values or []:
        if v is not None:
            return v
    return None


def wavg(parts):
    """Gewichteter Mittelwert aus (score, gewicht)-Paaren; None wird ignoriert."""
    parts = [(s, w) for s, w in parts if s is not None]
    if not parts:
        return None
    return sum(s * w for s, w in parts) / sum(w for _, w in parts)


def pct(x, d=1):
    return "–" if x is None else f"{x * 100:.{d}f} %".replace(".", ",")


def fnum(x, d=1, suffix=""):
    return "–" if x is None else f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".") + suffix


def money(x, cur=""):
    if x is None:
        return "–"
    a = abs(x)
    if a >= 1e12:
        s = fnum(x / 1e12, 2) + " Bio."
    elif a >= 1e9:
        s = fnum(x / 1e9, 2) + " Mrd."
    elif a >= 1e6:
        s = fnum(x / 1e6, 1) + " Mio."
    else:
        s = fnum(x, 2)
    return f"{s} {cur}".strip()


def http_get(url, timeout=10):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def domain_of(url):
    try:
        d = urllib.parse.urlparse(url).netloc.lower()
        return d[4:] if d.startswith("www.") else d
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Symbol-Suche
# ---------------------------------------------------------------------------
def search_symbols(q, include_crypto=False):
    out = []
    res = safe(lambda: yf.Search(q, max_results=10, news_count=0).quotes, [])
    if not res:
        url = "https://query2.finance.yahoo.com/v1/finance/search?" + urllib.parse.urlencode(
            {"q": q, "quotesCount": 10, "newsCount": 0})
        res = safe(lambda: json.loads(http_get(url)).get("quotes", []), [])
    for it in res or []:
        if include_crypto and it.get("quoteType") == "CRYPTOCURRENCY" and it.get("symbol"):
            base = re.sub(r"\d+$", "", it["symbol"].split("-")[0])
            nm = re.sub(r"\s+(USD|EUR)$", "", (it.get("shortname") or it.get("longname") or base).strip())
            out.append({"symbol": f"{base}-EUR", "name": nm, "exchange": "Krypto", "crypto": True})
            continue
        if it.get("quoteType") == "ETF" and it.get("symbol"):
            out.append({"symbol": it["symbol"], "etf": True,
                        "name": (it.get("longname") or it.get("shortname") or it["symbol"]).strip(),
                        "exchange": it.get("exchDisp") or it.get("exchange", ""), "sector": "ETF", "industry": ""})
            continue
        if it.get("quoteType") == "EQUITY" and it.get("symbol"):
            out.append({"symbol": it["symbol"],
                        "name": (it.get("longname") or it.get("shortname") or it["symbol"]).strip(),
                        "exchange": it.get("exchDisp") or it.get("exchange", ""),
                        "sector": it.get("sectorDisp") or it.get("sector") or "",
                        "industry": (it.get("industryDisp") or it.get("industry") or "").replace("�", " - ")})
    return out


def current_price(info):
    return num(info.get("currentPrice")) or num(info.get("regularMarketPrice")) or num(info.get("previousClose"))


def ttm(q_df, a_df, *names, flow=True):
    """TTM-Wert: Summe der letzten 4 Quartale (Fluss) bzw. letzter Stand (Bestand); sonst Jahreswert."""
    q = [v for v in row(q_df, *names)[:4] if v is not None]
    if flow and len(q) == 4:
        return sum(q)
    if not flow and q:
        return q[0]
    return first(row(a_df, *names))


# Bilanzwährung ≠ Kurswährung (z. B. Novo Nordisk in USD gehandelt, Bilanz in DKK) -> Bilanzwerte umrechnen
NON_MONEY_ROWS = {"Tax Rate For Calcs", "Diluted Average Shares", "Basic Average Shares", "Ordinary Shares Number",
                  "Share Issued", "Treasury Shares Number"}
FIN_CUR_CACHE = {}


def financial_currency(symbol, info=None):
    """Währung der Geschäftsberichte (Yahoo-'info' oder Zeitreihen-Schnittstelle, die auch auf Servern antwortet)."""
    if info and info.get("financialCurrency"):
        return info["financialCurrency"]
    if symbol in FIN_CUR_CACHE:
        return FIN_CUR_CACHE[symbol]
    url = (f"https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{urllib.parse.quote(symbol)}"
           f"?type=annualTotalRevenue&period1=1500000000&period2={int(time.time()) + 86400}")
    pts = safe(lambda: json.loads(http_get(url))["timeseries"]["result"][0].get("annualTotalRevenue")) or []
    cur = next((p.get("currencyCode") for p in reversed(pts) if p and p.get("currencyCode")), None)
    FIN_CUR_CACHE[symbol] = cur
    return cur


def fx_rate(frm, to):
    """Umrechnungsfaktor von Währung frm in Währung to (1.0, wenn gleich oder unbekannt)."""
    if not frm or not to or frm == to:
        return 1.0
    a_, b_ = usd_rate(frm), usd_rate(to)
    return a_ / b_ if a_ and b_ else 1.0


def convert_df(df, k):
    """Geldbeträge einer Bilanz-/GuV-/Cashflow-Tabelle mit Faktor k umrechnen (Stückzahlen bleiben)."""
    if df is None or getattr(df, "empty", True) or abs(k - 1.0) < 1e-12:
        return df
    df = df.copy()
    money = [i for i in df.index if i not in NON_MONEY_ROWS]
    df.loc[money] = df.loc[money].astype(float) * k
    return df


def fill_info(t, info, hint=None):
    """Ergänzt fehlende Yahoo-'info'-Felder aus Kursverlauf und Geschäftsberichten.

    Yahoo sperrt die info-Schnittstelle für manche Server (z. B. Cloud-Hoster); Kurse und
    Finanzberichte kommen über andere Endpunkte meist trotzdem an."""
    info = dict(info or {})
    if os.environ.get("FORCE_FALLBACK"):
        info = {}
    if current_price(info) and info.get("marketCap"):
        return info
    hint = hint or {}
    info["_fallback"] = True

    def put(key, val):
        if info.get(key) is None and val is not None:
            info[key] = val

    fi = safe(lambda: t.fast_info)
    hist = safe(lambda: t.history(period="1y", auto_adjust=False))
    price = num(safe(lambda: fi.last_price)) or (float(hist["Close"].iloc[-1]) if hist is not None and len(hist) else None)
    put("currentPrice", price)
    put("currency", safe(lambda: fi.currency))
    put("marketCap", num(safe(lambda: fi.market_cap)))
    put("longName", hint.get("name"))
    put("shortName", hint.get("name"))
    put("sector", hint.get("sector") or None)
    put("industry", hint.get("industry") or None)
    put("fullExchangeName", hint.get("exchange") or safe(lambda: fi.exchange))
    put("quoteType", "ETF" if hint.get("etf") else "EQUITY")

    inc, qinc = safe(lambda: t.income_stmt), safe(lambda: t.quarterly_income_stmt)
    cf, qcf = safe(lambda: t.cashflow), safe(lambda: t.quarterly_cashflow)
    bs, qbs = safe(lambda: t.balance_sheet), safe(lambda: t.quarterly_balance_sheet)
    fin_cur = financial_currency(t.ticker, info)
    k = fx_rate(fin_cur, info.get("currency"))
    inc, qinc, cf, qcf, bs, qbs = (convert_df(x, k) for x in (inc, qinc, cf, qcf, bs, qbs))
    if fin_cur:
        info["financialCurrency"] = fin_cur
    info["_fx_done"] = True  # Bilanzwerte in info liegen bereits in Kurswährung vor
    rev = ttm(qinc, inc, "Total Revenue")
    ni = ttm(qinc, inc, "Net Income")
    op = ttm(qinc, inc, "Operating Income")
    gp = ttm(qinc, inc, "Gross Profit")
    ebitda = ttm(qinc, inc, "EBITDA", "Normalized EBITDA")
    eps = ttm(qinc, inc, "Diluted EPS", "Basic EPS")
    fcf = ttm(qcf, cf, "Free Cash Flow")
    debt = ttm(qbs, bs, "Total Debt", flow=False)
    cash = ttm(qbs, bs, "Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments", flow=False)
    equity = ttm(qbs, bs, "Stockholders Equity", "Common Stock Equity", flow=False)
    assets = ttm(qbs, bs, "Total Assets", flow=False)
    divs_paid = ttm(qcf, cf, "Cash Dividends Paid", "Common Stock Dividend Paid")
    mcap = info.get("marketCap")
    if mcap is None and price:
        shares = num(safe(lambda: fi.shares)) or ttm(qbs, bs, "Ordinary Shares Number", "Share Issued", flow=False)
        mcap = price * shares if shares else None
        put("marketCap", mcap)

    put("totalRevenue", rev)
    put("ebitda", ebitda)
    put("freeCashflow", fcf)
    put("totalDebt", debt)
    put("totalCash", cash)
    put("trailingEps", eps)
    if rev:
        put("profitMargins", ni / rev if ni is not None else None)
        put("operatingMargins", op / rev if op is not None else None)
        put("grossMargins", gp / rev if gp is not None else None)
    if equity and equity > 0 and ni is not None:
        put("returnOnEquity", ni / equity)
    if assets and ni is not None:
        put("returnOnAssets", ni / assets)
    if price and eps and eps > 0:
        put("trailingPE", price / eps)
    if mcap:
        ev = mcap + (debt or 0) - (cash or 0)
        put("enterpriseValue", ev)
        if ebitda and ebitda > 0:
            put("enterpriseToEbitda", ev / ebitda)
        if equity and equity > 0:
            put("priceToBook", mcap / equity)
        if rev:
            put("priceToSalesTrailing12Months", mcap / rev)
    if divs_paid is not None and ni and ni > 0:
        put("payoutRatio", abs(divs_paid) / ni)
    # Wachstum: letztes Quartal ggü. Vorjahresquartal
    qr, qn = row(qinc, "Total Revenue"), row(qinc, "Net Income")
    if len(qr) >= 5 and qr[0] and qr[4]:
        put("revenueGrowth", qr[0] / qr[4] - 1)
    if len(qn) >= 5 and qn[0] and qn[4] and qn[4] > 0:
        put("earningsGrowth", qn[0] / qn[4] - 1)
    # Beta ggü. S&P 500 (1 Jahr, Tagesrenditen)
    if hist is not None and len(hist) > 100:
        idx = safe(lambda: yf.Ticker("^GSPC").history(period="1y")["Close"])
        if idx is not None and len(idx) > 100:
            def norm(series):
                r = series.pct_change()
                r.index = (r.index.tz_localize(None) if r.index.tz is not None else r.index).normalize()
                return r
            j = norm(hist["Close"]).to_frame("a").join(norm(idx).to_frame("b"), how="inner").dropna()
            if len(j) > 60 and j["b"].var() > 0:
                put("beta", float(j["a"].cov(j["b"]) / j["b"].var()))
    return info


def resolve(query):
    q = query.strip()
    is_isin = bool(re.fullmatch(r"[A-Za-z]{2}[A-Za-z0-9]{9}\d", q))  # ISIN -> über die Suche zur Börsennotierung
    if re.fullmatch(r"[A-Za-z0-9.\-^=]{1,15}", q) and not is_isin:
        sym = q.upper()
        t = yf.Ticker(sym)
        info = safe(lambda: t.info, {}) or {}
        found = search_symbols(info.get("longName") or q)
        hint = next((a for a in found if a["symbol"] == sym), None)
        if current_price(info) or hint:
            info = fill_info(t, info, hint)
        if current_price(info) and info.get("quoteType", "EQUITY") in ("EQUITY", "ETF"):
            return sym, t, info, [a for a in found if a["symbol"] != sym][:6]
    found = search_symbols(q)
    if not found:
        raise ValueError(f"Keine Aktie zu „{q}“ gefunden.")
    ql = q.lower()
    found.sort(key=lambda a: 0 if clean_company_name(a["name"]).lower() == ql
               else 1 if a["name"].lower().startswith(ql) else 2)  # stabil: Yahoo-Reihenfolge bleibt sonst erhalten
    for cand in found[:3]:
        t = yf.Ticker(cand["symbol"])
        info = fill_info(t, safe(lambda: t.info, {}) or {}, cand)
        if current_price(info):
            return cand["symbol"], t, info, [a for a in found if a["symbol"] != cand["symbol"]][:6]
    raise ValueError(f"Keine Kursdaten zu „{q}“ verfügbar.")


# ---------------------------------------------------------------------------
# News (Tier 1–3)
# ---------------------------------------------------------------------------
def classify_tier(url, source_name, company_domain):
    d = domain_of(url)
    if company_domain and d and (d == company_domain or d.endswith("." + company_domain)):
        return 3
    for tier in (1, 2, 3):
        for dom in TIER_DOMAINS[tier]:
            if dom in ("newsroom", "investor", "ir."):
                if d.startswith(dom) or f".{dom}" in d:
                    return 3
            elif d == dom or d.endswith("." + dom):
                return tier
    n = (source_name or "").lower()
    for key, tier in TIER_NAMES.items():
        if key in n:
            return tier
    return 0


def parse_rss(xml_bytes):
    items = []
    root = ET.fromstring(xml_bytes)
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        pub = it.findtext("pubDate")
        src = it.find("source")
        src_name = src.text.strip() if src is not None and src.text else ""
        src_url = src.get("url", "") if src is not None else ""
        try:
            dt = parsedate_to_datetime(pub) if pub else None
            if dt and dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            dt = None
        if src_name and title.endswith(" - " + src_name):
            title = title[: -len(src_name) - 3]
        items.append({"title": title, "link": link, "date": dt, "source": src_name, "source_url": src_url})
    return items


def google_news(query, lang, days=30):
    loc = {"de": ("de", "DE", "DE:de"), "en": ("en-US", "US", "US:en")}[lang]
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": query + f" when:{days}d", "hl": loc[0], "gl": loc[1], "ceid": loc[2]})
    return parse_rss(http_get(url))


def yahoo_rss(symbol):
    url = "https://feeds.finance.yahoo.com/rss/2.0/headline?" + urllib.parse.urlencode(
        {"s": symbol, "region": "US", "lang": "en-US"})
    items = parse_rss(http_get(url))
    for i in items:
        i["source"], i["source_url"] = i["source"] or "Yahoo Finance", "https://finance.yahoo.com"
    return items


def _sentiment_segments(t):
    """Zerlegt nach Gegensatz-Wörtern: 'trotz X' zählt kaum, nach 'aber' zählt stärker."""
    m = re.search(r"\b(trotz|despite|in spite of|ungeachtet|obwohl|although|even though)\b", t)
    if m:
        after = t[m.end():]
        brk = re.search(r"[,:;–]|\s-\s", after)
        conc, rest = (after[:brk.start()], after[brk.end():]) if brk else (after, "")
        return [(t[:m.start()], 1.0), (conc, 0.25), (rest, 1.0)]
    m = re.search(r"\b(aber|doch|jedoch|but|however|yet)\b", t)
    if m:
        return [(t[:m.start()], 0.4), (t[m.end():], 1.3)]
    return [(t, 1.0)]


def _segment_score(seg):
    total = 0.0
    for pat, w in SENT_PHRASES:  # Wortgruppen zuerst, danach aus dem Text entfernen (keine Doppelzählung)
        for mm in list(re.finditer(pat, seg)):
            pre = re.findall(r"[a-zäöüß']+", seg[:mm.start()])[-3:]
            total += -0.8 * w if any(x in SENT_NEGATORS for x in pre) else w
        seg = re.sub(pat, " ", seg)
    for sign, num_ in re.findall(r"([+\-−])\s?(\d+(?:[.,]\d+)?)\s?(?:%|prozent|percent)", seg):  # "+9 %", "-7%"
        v = float(num_.replace(",", "."))
        total += (1 if sign == "+" else -1) * min(2.0, 0.6 + v / 5)
    # Verneinung und Verstärker wirken nur innerhalb eines Satzteils (nicht über ":", "–", "," hinweg)
    for clause in re.split(r"\s[–\-]\s|[:;,.!?–|]", seg):
        total += _clause_score(re.findall(r"[a-zäöüß][a-zäöüß'\-]*", clause))
    return total


def _clause_score(toks):
    total = 0.0
    for i, tok in enumerate(toks):
        parts = [tok] + (tok.split("-") if "-" in tok else [])
        w = 0.0
        for part in parts:
            w = SENT_WORDS.get(part)
            if w is None:
                w = next((v for st, v in SENT_STEMS.items() if len(part) >= len(st) and part.startswith(st)), 0.0)
                if not w:  # Zusammensetzung mit Stamm am Ende, z. B. "SAP-Kursrutsch", "Q3-Gewinnsprung"
                    w = next((v for st, v in SENT_STEMS.items() if len(st) >= 6 and st in part), 0.0)
            if w:
                break
        if not w:
            continue
        window = toks[max(0, i - 3):i]
        if any(x in SENT_NEGATORS for x in window) or (i + 1 < len(toks) and toks[i + 1] in ("nicht", "kaum")):
            w *= -0.8  # Verneinung: "nicht gestiegen", "wächst nicht", "no growth"
        if any(x in SENT_INTENS for x in toks[max(0, i - 1):i + 2]):
            w *= 1.5
        total += w
    return total


def headline_sentiment(title):
    """Tonalität einer Schlagzeile zwischen -1 (negativ) und +1 (positiv)."""
    t = " " + title.lower().replace("’", "'") + " "
    t = re.sub(SENT_NEUTRAL, " ", t)
    total = sum(f * _segment_score(seg) for seg, f in _sentiment_segments(t))
    if "?" in title:
        total *= 0.4  # Fragen ("Is X a buy?") sind meist Klickköder, keine Nachricht
    return clamp(total / 2.5)


def words(title):
    return {w for w in re.findall(r"[a-zäöüß0-9]{4,}", title.lower())}


def sibling_names(company, symbol):
    """Namen anderer börsennotierter Firmen, die mit unserem Firmennamen beginnen."""
    own = company.lower()
    sibs = set()
    for a in search_symbols(company):
        n = clean_company_name(a["name"]).lower()
        if a["symbol"].split(".")[0] != symbol.split(".")[0] and n != own and n.startswith(own + " "):
            sibs.add(n)
    return sorted(sibs, key=len, reverse=True)


def mentions_sibling(title, siblings):
    tl = title.lower().replace("-", " ")
    return any(sib in tl for sib in siblings)


def clean_company_name(name):
    n = re.sub(r"[,.]", " ", name or "")
    n = re.sub(r"\b(Inc|Incorporated|Corp|Corporation|Company|Co|AG|Aktiengesellschaft|SE|KGaA|plc|PLC|Ltd|Limited|N V|NV|SA|S A|"
               r"Holding|Holdings|Group|Class [A-C]|& Co|GmbH|ASA|AB|Oyj|SpA)\b", " ", n)
    return re.sub(r"\s+", " ", n).strip() or name


def collect_news(symbol, company, website, siblings=(), terms=("stock", "Aktie")):
    company_domain = domain_of(website) if website else ""
    base_sym = symbol.split(".")[0]
    jobs = {
        "en": lambda: google_news(f'"{company}" {terms[0]}', "en"),
        "de": lambda: google_news(f'"{company}" {terms[1]}', "de"),
        "press": lambda: google_news(f'"{company}" (site:businesswire.com OR site:prnewswire.com OR '
                                     f'site:globenewswire.com OR site:eqs-news.com'
                                     + (f" OR site:{company_domain}" if company_domain else "") + ")", "en"),
        "yahoo": lambda: yahoo_rss(base_sym if "." not in symbol else symbol),
    }
    raw, errors = [], []
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {k: ex.submit(fn) for k, fn in jobs.items()}
        for k, f in futs.items():
            try:
                raw.extend(f.result(timeout=20))
            except Exception as e:
                errors.append(f"{k}: {type(e).__name__}")
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    name_tokens = [w for w in re.findall(r"[a-zäöüß0-9]{3,}", company.lower())][:2] or [company.lower()]
    seen, items = set(), []
    for it in raw:
        key = re.sub(r"\W+", "", it["title"].lower())[:80]
        if not key or key in seen:
            continue
        if it["date"] and it["date"] < cutoff:
            continue
        tl = it["title"].lower()
        if JOB_AD.search(tl) or mentions_sibling(it["title"], siblings):
            continue
        if not (any(tok in tl for tok in name_tokens) or re.search(r"\b" + re.escape(base_sym.lower()) + r"\b", tl)):
            continue
        seen.add(key)
        tier = classify_tier(it["source_url"] or it["link"], it["source"], company_domain)
        items.append({**it, "tier": tier, "sentiment": headline_sentiment(it["title"])})
    items.sort(key=lambda x: x["date"] or cutoff, reverse=True)

    # Tier-3-Prüfung: gilt als bestätigt, wenn eine Tier-1/2-Schlagzeile inhaltlich übereinstimmt
    trusted = [words(i["title"]) for i in items if i["tier"] in (1, 2)]
    for i in items:
        if i["tier"] == 3:
            w = words(i["title"])
            best = max((len(w & t) / max(1, len(w | t)) for t in trusted), default=0)
            i["verified"] = best >= 0.25
    by_tier = {t: [] for t in (1, 2, 3, 0)}
    for i in items:
        if len(by_tier[i["tier"]]) < 12:
            by_tier[i["tier"]].append({
                "title": i["title"], "link": i["link"], "source": i["source"] or domain_of(i["source_url"]),
                "date": i["date"].strftime("%d.%m.%Y") if i["date"] else "",
                "sentiment": round(i["sentiment"], 2), "verified": i.get("verified"),
            })
    num_w = sum(TIER_WEIGHT[i["tier"]] * (0.5 if i["tier"] == 3 and not i.get("verified") else 1) for i in items)
    sent = (sum(TIER_WEIGHT[i["tier"]] * (0.5 if i["tier"] == 3 and not i.get("verified") else 1) * i["sentiment"]
                for i in items) / num_w) if num_w else None
    pos = sum(1 for i in items if i["sentiment"] > 0)
    neg = sum(1 for i in items if i["sentiment"] < 0)
    return {
        "by_tier": {str(k): v for k, v in by_tier.items()},
        "labels": {str(k): v for k, v in TIER_LABEL.items()},
        "count": len(items), "count_trusted": sum(1 for i in items if i["tier"] in (1, 2)),
        "sentiment": sent, "pos": pos, "neg": neg, "errors": errors,
    }


# ---------------------------------------------------------------------------
# Kennzahlen sammeln
# ---------------------------------------------------------------------------
def reverse_dcf(fcf, ev, r, g_term=0.025, years=10):
    """Welche jährliche FCF-Wachstumsrate (10 J.) rechtfertigt den heutigen Unternehmenswert?"""
    if not fcf or fcf <= 0 or not ev or ev <= 0 or r <= g_term:
        return None

    def value(g):
        v, f = 0.0, fcf
        for t in range(1, years + 1):
            f *= 1 + g
            v += f / (1 + r) ** t
        return v + f * (1 + g_term) / (r - g_term) / (1 + r) ** years

    lo, hi = -0.5, 1.0
    if value(hi) < ev:
        return hi
    if value(lo) > ev:
        return lo
    for _ in range(80):
        mid = (lo + hi) / 2
        if value(mid) < ev:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def est_growth(m, key):
    """Ø erwartetes Wachstum (dieses + nächstes Geschäftsjahr) laut Analysten; EPS nur bei positivem Vorjahreswert."""
    e = m.get(key) or {}
    vals = []
    for per in ("0y", "+1y"):
        x = e.get(per) or {}
        if x.get("growth") is None:
            continue
        if key == "est_eps" and (x.get("ago") is None or x["ago"] <= 0):
            continue  # Wachstum aus Verlust/Null ist nicht aussagekräftig
        vals.append(clamp(x["growth"], -0.6, 1.0))
    return sum(vals) / len(vals) if vals else None


def est_analysts(m):
    return int(max([(m.get("est_rev") or {}).get(p_, {}).get("n") or 0 for p_ in ("0y", "+1y")]
                   + [(m.get("est_eps") or {}).get(p_, {}).get("n") or 0 for p_ in ("0y", "+1y")]))


def balance_quality(m, inc, bs, cf):
    """Piotroski F-Score, Altman Z-Score, Zinsdeckung, Gewinnqualität (Accruals) und um Aktienvergütung
    bereinigter Free Cashflow – alles aus den Jahresabschlüssen."""
    def pair(df, *names):  # (aktuelles, vorheriges Geschäftsjahr), fehlende Spalten übersprungen
        vals = [v for v in row(df, *names) if v is not None]
        return (vals[0] if vals else None, vals[1] if len(vals) > 1 else None)
    ni, ni1 = pair(inc, "Net Income")
    rev, rev1 = pair(inc, "Total Revenue")
    gp, gp1 = pair(inc, "Gross Profit")
    ebit, _ = pair(inc, "EBIT", "Operating Income")
    intexp, _ = pair(inc, "Interest Expense", "Interest Expense Non Operating")
    ta, ta1 = pair(bs, "Total Assets")
    ca, ca1 = pair(bs, "Current Assets")
    cl, cl1 = pair(bs, "Current Liabilities")
    ltd, ltd1 = pair(bs, "Long Term Debt")
    re_, _ = pair(bs, "Retained Earnings")
    tl, _ = pair(bs, "Total Liabilities Net Minority Interest")
    sh, sh1 = pair(bs, "Ordinary Shares Number", "Share Issued")
    ocf, _ = pair(cf, "Operating Cash Flow")
    sbc, _ = pair(cf, "Stock Based Compensation")
    da, _ = pair(cf, "Depreciation And Amortization", "Depreciation Amortization Depletion")
    # Owner Earnings: operativer Cashflow minus Abschreibungen (≈ Erhaltungsinvestitionen) – blendet Wachstumsinvestitionen aus
    m["owner_earnings"] = ocf - da if ocf is not None and da is not None else None
    m["lease_obl"], _ = pair(bs, "Capital Lease Obligations")   # Leasingverbindlichkeiten (IFRS 16)
    m["minority"], _ = pair(bs, "Minority Interest")             # Anteile anderer Aktionäre an Töchtern

    def div(a_, b_):
        return a_ / b_ if a_ is not None and b_ else None

    # Piotroski: 9 Ja/Nein-Prüfungen zu Profitabilität, Finanzierung und Effizienz
    tests = [
        ("Gewinn positiv", None if ni is None else ni > 0),
        ("Operativer Cashflow positiv", None if ocf is None else ocf > 0),
        ("Gesamtkapitalrendite gestiegen", None if None in (ni, ni1) or not ta or not ta1 else ni / ta > ni1 / ta1),
        ("Cashflow über Gewinn", None if None in (ocf, ni) else ocf > ni),
        ("Langfristige Schuldenquote nicht gestiegen",
         None if None in (ltd, ltd1) or not ta or not ta1 else ltd / ta <= ltd1 / ta1),
        ("Liquidität (Current Ratio) gestiegen",
         None if None in (ca, ca1) or not cl or not cl1 else ca / cl > ca1 / cl1),
        ("Keine Verwässerung", None if None in (sh, sh1) else sh <= sh1 * 1.005),
        ("Bruttomarge gestiegen", None if None in (gp, gp1) or not rev or not rev1 else gp / rev > gp1 / rev1),
        ("Kapitalumschlag gestiegen", None if None in (rev, rev1) or not ta or not ta1 else rev / ta > rev1 / ta1),
    ]
    done = [(n, ok) for n, ok in tests if ok is not None]
    m["piotroski"] = round(sum(ok for _, ok in done) / len(done) * 9, 1) if len(done) >= 7 else None
    m["piotroski_n"] = len(done)
    m["piotroski_fail"] = [n for n, ok in done if not ok]
    # Altman Z (klassisch für Industrie-/Handelsunternehmen)
    if None not in (ca, cl, re_, ebit, rev) and ta and tl and m["mcap"]:
        m["altman_z"] = (1.2 * (ca - cl) / ta + 1.4 * re_ / ta + 3.3 * ebit / ta
                         + 0.6 * m["mcap"] / tl + 1.0 * rev / ta)
    else:
        m["altman_z"] = None
    m["int_cov"] = div(ebit, abs(intexp)) if intexp and ebit is not None else None
    m["accruals"] = div(ni - ocf, ta) if None not in (ni, ocf) else None
    m["sbc"] = sbc
    m["sbc_ratio"] = div(sbc, rev)
    fcf = m["fcf"]
    m["fcf_adj"] = fcf - sbc if fcf is not None and sbc else fcf
    m["fcf_yield_adj"] = m["fcf_adj"] / m["mcap"] if m["fcf_adj"] is not None and m["mcap"] else None
    m["fcf_m_adj"] = m["fcf_adj"] / m["revenue"] if m["fcf_adj"] is not None and m["revenue"] else None


def pd_ts(v):
    """Datum aus pandas/str -> naive datetime."""
    import pandas as pd
    ts = pd.Timestamp(v)
    return ts.tz_localize(None).to_pydatetime() if ts.tzinfo else ts.to_pydatetime()


def expectations(m, t):
    """Gewinnrevisionen, Gewinnüberraschungen und Insidergeschäfte (Yahoo; Finnhub als Ersatz in finnhub_enrich)."""
    m["eps_rev"] = m["rev_breadth"] = m["surprises"] = m["insider"] = m["eps_quarters"] = None
    m["est_rev"], m["est_eps"] = {}, {}
    tr = safe(lambda: t.eps_trend)
    if tr is not None and not tr.empty and "current" in tr and "90daysAgo" in tr:
        ch = []
        for per in ("0y", "+1y"):
            if per in tr.index:
                cur, old = num(tr.loc[per, "current"]), num(tr.loc[per, "90daysAgo"])
                if cur is not None and old and old > 0:
                    ch.append(cur / old - 1)
        m["eps_rev"] = sum(ch) / len(ch) if ch else None
    rv = safe(lambda: t.eps_revisions)
    if rv is not None and not rv.empty and "upLast30days" in rv:
        sub = rv.loc[[p_ for p_ in ("0y", "+1y") if p_ in rv.index]]
        up, dn = int(sub["upLast30days"].fillna(0).sum()), int(sub["downLast30days"].fillna(0).sum())
        m["rev_breadth"] = (up, dn) if up + dn else None
    def est(df, col_growth="growth"):
        out = {}
        if df is None or getattr(df, "empty", True):
            return out
        for per in ("0y", "+1y"):
            if per in df.index:
                r_ = df.loc[per]
                out[per] = {"avg": num(r_.get("avg")), "low": num(r_.get("low")), "high": num(r_.get("high")),
                            "growth": num(r_.get(col_growth)), "n": num(r_.get("numberOfAnalysts")),
                            "ago": num(r_.get("yearAgoRevenue")) if "yearAgoRevenue" in r_ else num(r_.get("yearAgoEps"))}
        return out
    m["est_rev"] = est(safe(lambda: t.revenue_estimate))
    m["est_eps"] = est(safe(lambda: t.earnings_estimate))
    eh = safe(lambda: t.earnings_history)
    if eh is not None and not eh.empty and "epsActual" in eh:
        m["eps_quarters"] = [{"q": str(getattr(q_, "date", lambda: q_)())[:10], "est": num(r_.get("epsEstimate")),
                              "act": num(r_.get("epsActual"))} for q_, r_ in eh.iterrows()][-8:]
    if eh is not None and not eh.empty and "surprisePercent" in eh:
        vals = [num(v) for v in eh["surprisePercent"].tolist()]
        vals = [v for v in vals if v is not None][-4:]
        m["surprises"] = vals or None
    it = safe(lambda: t.insider_transactions)
    if it is not None and not it.empty and "Text" in it:
        since = datetime.now() - timedelta(days=183)
        buys = sells = 0.0
        buyers = set()
        for _, r in it.iterrows():
            d = safe(lambda: pd_ts(r.get("Start Date")))
            if d is None or d < since:
                continue
            txt, val = str(r.get("Text") or ""), num(r.get("Value")) or 0
            if txt.startswith("Purchase at price"):
                buys += val
                buyers.add(r.get("Insider"))
            elif txt.startswith("Sale at price"):
                sells += val
        m["insider"] = {"buys": buys, "sells": sells, "buyers": len(buyers), "src": "Yahoo", "cur": m["currency"]}
    elif it is not None and getattr(it, "empty", False):
        m["insider"] = None  # keine Meldungen (z. B. außerhalb der USA) -> Finnhub probieren


def _ind_frame(df):
    """Indikatoren auf einem OHLC-DataFrame (Open/High/Low/Close)."""
    import pandas as pd
    c, h, l_ = df["Close"], df["High"], df["Low"]
    out = {}
    d = c.diff()
    up, dn = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean(), (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    out["rsi"] = 100 - 100 / (1 + up / dn.replace(0, float("nan")))
    lo14, hi14 = l_.rolling(14).min(), h.rolling(14).max()
    k = 100 * (c - lo14) / (hi14 - lo14).replace(0, float("nan"))
    out["stoch"] = k.rolling(3).mean()
    out["willr"] = -100 * (hi14 - c) / (hi14 - lo14).replace(0, float("nan"))
    e12, e26 = c.ewm(span=12, adjust=False).mean(), c.ewm(span=26, adjust=False).mean()
    out["macd"], out["macd_sig"] = e12 - e26, (e12 - e26).ewm(span=9, adjust=False).mean()
    tp = (h + l_ + c) / 3
    md = tp.rolling(20).apply(lambda x: (abs(x - x.mean())).mean(), raw=True)
    out["cci"] = (tp - tp.rolling(20).mean()) / (0.015 * md.replace(0, float("nan")))
    out["mom"] = c - c.shift(10)
    tr = pd.concat([h - l_, (h - c.shift()).abs(), (l_ - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean()
    upm, dnm = h.diff(), -l_.diff()
    pdm = upm.where((upm > dnm) & (upm > 0), 0.0)
    ndm = dnm.where((dnm > upm) & (dnm > 0), 0.0)
    pdi = 100 * pdm.ewm(alpha=1 / 14, adjust=False).mean() / atr.replace(0, float("nan"))
    ndi = 100 * ndm.ewm(alpha=1 / 14, adjust=False).mean() / atr.replace(0, float("nan"))
    dx = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, float("nan"))
    out["adx"], out["pdi"], out["ndi"] = dx.ewm(alpha=1 / 14, adjust=False).mean(), pdi, ndi
    for n in (10, 20, 50, 100, 200):
        out[f"sma{n}"] = c.rolling(n).mean()
        out[f"ema{n}"] = c.ewm(span=n, adjust=False).mean()
    return out


def tech_signals(df):
    """Einzelsignale (Kaufen/Neutral/Verkaufen) und Gesamturteil für einen Zeitrahmen."""
    n = len(df)
    if n < 30:
        return None
    I = _ind_frame(df)
    last = lambda k: num(I[k].iloc[-1]) if k in I else None
    price = float(df["Close"].iloc[-1])
    osc, mas = [], []

    def add(lst, name, val, sig, fmt=1):
        lst.append({"name": name, "value": None if val is None else round(val, fmt), "signal": sig})
    v = last("rsi")
    if v is not None:
        add(osc, "RSI (14)", v, "Kaufen" if v < 30 else "Verkaufen" if v > 70 else "Neutral")
    v = last("stoch")
    if v is not None:
        add(osc, "Stochastik (14, 3)", v, "Kaufen" if v < 20 else "Verkaufen" if v > 80 else "Neutral")
    v, sgl = last("macd"), last("macd_sig")
    if v is not None and sgl is not None:
        add(osc, "MACD (12, 26, 9)", v, "Kaufen" if v > sgl else "Verkaufen", 3)
    v, pdi, ndi = last("adx"), last("pdi"), last("ndi")
    if v is not None and pdi is not None:
        add(osc, "ADX (14)", v, ("Kaufen" if pdi > ndi else "Verkaufen") if v > 25 else "Neutral")
    v = last("willr")
    if v is not None:
        add(osc, "Williams %R (14)", v, "Kaufen" if v < -80 else "Verkaufen" if v > -20 else "Neutral")
    v = last("cci")
    if v is not None:
        add(osc, "CCI (20)", v, "Kaufen" if v < -100 else "Verkaufen" if v > 100 else "Neutral")
    v = last("mom")
    if v is not None:
        add(osc, "Momentum (10)", v, "Kaufen" if v > 0 else "Verkaufen", 2)
    for nn in (10, 20, 50, 100, 200):
        if n >= nn + 5:
            for kind in ("sma", "ema"):
                mv = last(f"{kind}{nn}")
                if mv:
                    add(mas, f"{'GD' if kind == 'sma' else 'EMA'} {nn}", mv, "Kaufen" if price > mv else "Verkaufen", 2)

    def verdict(lst):
        b = sum(1 for x in lst if x["signal"] == "Kaufen")
        s_ = sum(1 for x in lst if x["signal"] == "Verkaufen")
        tot = len(lst) or 1
        sc = (b - s_) / tot
        lab = ("Starker Kauf" if sc >= 0.5 else "Kaufen" if sc >= 0.1 else "Starker Verkauf" if sc <= -0.5
               else "Verkaufen" if sc <= -0.1 else "Neutral")
        return {"label": lab, "score": round(sc, 2), "buy": b, "sell": s_, "neutral": tot - b - s_}
    return {"osc": osc, "ma": mas, "osc_sum": verdict(osc), "ma_sum": verdict(mas), "sum": verdict(osc + mas),
            "atr": num(((df["High"] - df["Low"]).rolling(14).mean()).iloc[-1])}


def _pivots(c, w):
    hi, lo = [], []
    vals = c.values
    for i in range(w, len(vals) - w):
        win = vals[i - w:i + w + 1]
        if vals[i] == win.max():
            hi.append(i)
        if vals[i] == win.min():
            lo.append(i)
    return hi, lo


def chart_patterns(df):
    """Einfache, regelbasierte Erkennung klassischer Chartmuster (nur Hinweise, keine Signale)."""
    c = df["Close"].iloc[-260:]
    n = len(c)
    if n < 60:
        return []
    dates = [ts.strftime("%d.%m.%Y") for ts in c.index]
    vals = c.values
    last = float(vals[-1])
    w = max(4, n // 40)
    hi, lo = _pivots(c, w)
    out = []

    def add(name, kind, status, text, i0, i1):
        out.append({"name": name, "kind": kind, "status": status, "text": text, "from": dates[i0], "to": dates[i1]})
    # Doppeltop / Doppelboden (letzte zwei Hochs bzw. Tiefs)
    if len(hi) >= 2:
        a, b = hi[-2], hi[-1]
        if b - a >= 12 and abs(vals[a] - vals[b]) / max(vals[a], vals[b]) < 0.03 and n - b < 60                 and last < max(vals[a], vals[b]) * 1.02:  # über den Hochs ausgebrochen -> Muster hinfällig
            trough = float(vals[a:b].min())
            if trough < min(vals[a], vals[b]) * 0.95:
                conf = last < trough
                add("Doppeltop", "bear", "bestätigt" if conf else "in Bildung",
                    f"Zwei Hochs bei etwa {fnum((vals[a] + vals[b]) / 2, 2)}; Nackenlinie {fnum(trough, 2)}"
                    + (" wurde unterschritten" if conf else " – erst ein Bruch darunter bestätigt das Muster"), a, b)
    if len(lo) >= 2:
        a, b = lo[-2], lo[-1]
        if b - a >= 12 and abs(vals[a] - vals[b]) / max(vals[a], vals[b]) < 0.03 and n - b < 60                 and last > min(vals[a], vals[b]) * 0.98:  # unter die Tiefs gefallen -> Muster hinfällig
            peak = float(vals[a:b].max())
            if peak > max(vals[a], vals[b]) * 1.05:
                conf = last > peak
                add("Doppelboden", "bull", "bestätigt" if conf else "in Bildung",
                    f"Zwei Tiefs bei etwa {fnum((vals[a] + vals[b]) / 2, 2)}; Nackenlinie {fnum(peak, 2)}"
                    + (" wurde überschritten" if conf else " – erst ein Ausbruch darüber bestätigt das Muster"), a, b)
    # Schulter-Kopf-Schulter (oben) und invers (unten)
    if len(hi) >= 3:
        l_, k_, r_ = hi[-3], hi[-2], hi[-1]
        ls, hd, rs = vals[l_], vals[k_], vals[r_]
        if hd > max(ls, rs) * 1.03 and abs(ls - rs) / max(ls, rs) < 0.05 and n - r_ < 60 and last < hd:
            neck = (float(vals[l_:k_].min()) + float(vals[k_:r_].min())) / 2
            conf = last < neck
            add("Schulter-Kopf-Schulter", "bear", "bestätigt" if conf else "in Bildung",
                f"Kopf bei {fnum(hd, 2)}, Schultern bei {fnum(ls, 2)} / {fnum(rs, 2)}; Nackenlinie {fnum(neck, 2)}"
                + (" unterschritten – klassisches Umkehrsignal nach unten" if conf else ""), l_, r_)
    if len(lo) >= 3:
        l_, k_, r_ = lo[-3], lo[-2], lo[-1]
        ls, hd, rs = vals[l_], vals[k_], vals[r_]
        if hd < min(ls, rs) * 0.97 and abs(ls - rs) / max(ls, rs) < 0.05 and n - r_ < 60 and last > hd:
            neck = (float(vals[l_:k_].max()) + float(vals[k_:r_].max())) / 2
            conf = last > neck
            add("Inverse Schulter-Kopf-Schulter", "bull", "bestätigt" if conf else "in Bildung",
                f"Tiefster Punkt bei {fnum(hd, 2)}, Schultern bei {fnum(ls, 2)} / {fnum(rs, 2)}; Nackenlinie {fnum(neck, 2)}"
                + (" überschritten – klassisches Umkehrsignal nach oben" if conf else ""), l_, r_)
    # Dreiecke aus den Wendepunkten der letzten ~80 Handelstage
    recent_hi = [i for i in hi if i >= n - 80][-4:]
    recent_lo = [i for i in lo if i >= n - 80][-4:]
    if len(recent_hi) >= 2 and len(recent_lo) >= 2:
        import numpy as np
        sh = np.polyfit(recent_hi, vals[recent_hi], 1)[0] / last * 20     # Steigung in % je 20 Tage
        sl = np.polyfit(recent_lo, vals[recent_lo], 1)[0] / last * 20
        i0 = min(recent_hi[0], recent_lo[0])
        flat = 0.006
        if abs(sh) < flat and sl > flat:
            add("Aufsteigendes Dreieck", "bull", "in Bildung", "Hochs auf gleicher Höhe, steigende Tiefs – Ausbruch nach oben wahrscheinlicher", i0, n - 1)
        elif sh < -flat and abs(sl) < flat:
            add("Absteigendes Dreieck", "bear", "in Bildung", "Tiefs auf gleicher Höhe, fallende Hochs – Ausbruch nach unten wahrscheinlicher", i0, n - 1)
        elif sh < -flat and sl > flat:
            add("Symmetrisches Dreieck", "neutral", "in Bildung", "Hochs fallen, Tiefs steigen – die Spanne verengt sich, Ausbruchsrichtung offen", i0, n - 1)
    # Seitwärtsphase und Ausbruch
    box = vals[-45:-3]
    if len(box) >= 30:
        top, bot = float(box.max()), float(box.min())
        if (top - bot) / bot < 0.10:
            if last > top * 1.01:
                add("Ausbruch nach oben", "bull", "bestätigt", f"Kurs verlässt die Seitwärtsspanne {fnum(bot, 2)}–{fnum(top, 2)} nach oben", n - 45, n - 1)
            elif last < bot * 0.99:
                add("Ausbruch nach unten", "bear", "bestätigt", f"Kurs verlässt die Seitwärtsspanne {fnum(bot, 2)}–{fnum(top, 2)} nach unten", n - 45, n - 1)
            else:
                add("Seitwärtsphase", "neutral", "in Bildung", f"Kurs pendelt seit rund zwei Monaten zwischen {fnum(bot, 2)} und {fnum(top, 2)}", n - 45, n - 1)
    return out


def technicals(hist):
    """Technisches Gesamtsignal für Tag, Woche und Monat plus Chartmuster (aus Tageskursen mit OHLC)."""
    if hist is None or getattr(hist, "empty", True) or not all(k in hist for k in ("Open", "High", "Low", "Close")):
        return None
    df = hist[["Open", "High", "Low", "Close"]].dropna()
    df = df[df["Close"] > 0]
    if len(df) < 40:
        return None
    df.index = df.index.tz_localize(None) if df.index.tz is not None else df.index
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last"}
    frames = {"Tag": df.iloc[-400:], "Woche": df.resample("W").agg(agg).dropna(), "Monat": df.resample("ME").agg(agg).dropna()}
    out = {"frames": {}, "patterns": safe(lambda: chart_patterns(df), []) or []}
    for k, f in frames.items():
        sig = safe(lambda: tech_signals(f))
        if sig:
            out["frames"][k] = sig
    return out if out["frames"] else None


def chart_extras(m, t, inc, bs, divs):
    """Daten für Bewertungschart, KGV-Verlauf, Bilanz, Dividendenhistorie und Aktionärsstruktur."""
    import pandas as pd
    # Gewinn je Aktie je Geschäftsjahr (älteste zuerst)
    eps = []
    if inc is not None and not getattr(inc, "empty", True):
        r_ = next((n for n in ("Diluted EPS", "Basic EPS") if n in inc.index), None)
        if r_:
            for col in sorted(inc.columns):
                v = num(inc.loc[r_, col])
                if v is not None:
                    eps.append([col.strftime("%Y-%m-%d"), round(v, 4)])
    # Prognosen (dieses / nächstes GJ) – nur wenn Größenordnung zur Historie passt (Währung!)
    est = []
    if eps:
        last_d = datetime.strptime(eps[-1][0], "%Y-%m-%d")
        for i_, per in enumerate(("0y", "+1y"), start=1):
            avg = ((m.get("est_eps") or {}).get(per) or {}).get("avg")
            if avg and eps[-1][1] > 0 and 0.33 < avg / eps[-1][1] < 3:
                est.append([(last_d.replace(year=last_d.year + i_)).strftime("%Y-%m-%d"), round(avg, 4)])
    # Monatskurse (unbereinigt) für Bewertungschart und KGV-Verlauf
    h = safe(lambda: t.history(period="7y", interval="1mo", auto_adjust=False))
    prices = []
    if h is not None and not h.empty:
        for ts, c in h["Close"].dropna().items():
            prices.append([int(pd.Timestamp(ts).timestamp() * 1000), round(float(c), 4)])
    pe_norm = m.get("pe_hist_med") or m.get("peer_pe_med") or SECTOR_REF.get(m["sector"], (20, 13))[0]
    pe_norm = clamp(pe_norm, 8, 40)
    # KGV je Monat: Kurs / Gewinn des zuletzt abgeschlossenen Geschäftsjahres
    pe_series = []
    if prices and eps:
        eps_dt = [(datetime.strptime(d, "%Y-%m-%d").timestamp() * 1000, v) for d, v in eps]
        for ts, c in prices:
            cur = [v for d, v in eps_dt if d <= ts]
            if cur and cur[-1] > 0:
                pe_series.append([ts, round(c / cur[-1], 2)])
    m["valchart"] = {"eps": eps, "est": est, "prices": prices, "pe_norm": round(pe_norm, 1), "pe": pe_series,
                     "pe_avg": round(sum(x[1] for x in pe_series) / len(pe_series), 2) if pe_series else None}
    # Bilanz über die Jahre
    def brow(*names):
        return [num(v) for v in row(bs, *names)][::-1]
    if bs is not None and not getattr(bs, "empty", True):
        years = [c.strftime("%Y") for c in sorted(bs.columns)]
        m["balance"] = {"years": years, "debt": brow("Total Debt"), "cash": brow("Cash Cash Equivalents And Short Term Investments",
                        "Cash And Cash Equivalents"), "equity": brow("Stockholders Equity", "Common Stock Equity"),
                        "assets": brow("Total Assets"), "liab": brow("Total Liabilities Net Minority Interest"),
                        "ca": brow("Current Assets"), "cl": brow("Current Liabilities")}
    # Dividendenhistorie (volle Jahre)
    if divs is not None and len(divs):
        d = divs.copy()
        d.index = d.index.tz_localize(None) if d.index.tz is not None else d.index
        yearly = d.groupby(d.index.year).sum()
        this_year = datetime.now().year
        all_years = [(int(y), round(float(v), 4)) for y, v in yearly.items() if y < this_year and v > 0]
        streak = 0
        for i_ in range(len(all_years) - 1, 0, -1):  # Jahre in Folge ohne Kürzung (über die ganze Historie)
            if all_years[i_][1] >= all_years[i_ - 1][1] * 0.98 and all_years[i_][0] - all_years[i_ - 1][0] == 1:
                streak += 1
            else:
                break
        if streak > (m.get("div_streak") or 0):
            m["div_streak"] = streak
        full = all_years[-20:]
        ytd = float(yearly.get(this_year, 0) or 0)
        def cagr(n):
            if len(full) > n and full[-1 - n][1] > 0:
                return (full[-1][1] / full[-1 - n][1]) ** (1 / n) - 1
            return None
        eps_by_year = {int(dd[:4]): v for dd, v in eps}
        payout = [[y, round(v / eps_by_year[y], 3)] for y, v in full if eps_by_year.get(y) and eps_by_year[y] > 0]
        # Dividendensicherheit: Ausschüttung aus Gewinn und Free Cashflow, Historie, Verschuldung
        pts, why = 0, []
        po = m.get("payout")
        if po is not None:
            pts += 2 if po < 0.6 else 1 if po < 0.8 else -1 if po > 1 else 0
            why.append(f"Ausschüttungsquote {pct(po)} vom Gewinn")
        fcf, paid = m.get("fcf"), (m.get("div_paid") or 0) / (m.get("cf_years") or 1)
        if fcf is not None and paid:
            cov = fcf / paid
            pts += 2 if cov > 1.5 else 1 if cov > 1.1 else -2 if cov < 0.9 else 0
            why.append(f"Free Cashflow deckt die Dividende {fnum(cov, 1)}-fach")
        pts += 2 if streak >= 10 else 1 if streak >= 5 else 0
        why.append(f"{streak} Jahre in Folge ohne Kürzung")
        if m.get("div_cut"):
            pts -= 2
        if (m.get("nd_ebitda") or 0) > 3.5 and not m.get("is_financial"):
            pts -= 1
            why.append("hohe Verschuldung")
        label = "hoch" if pts >= 5 else "mittel" if pts >= 2 else "niedrig"
        m["divhist"] = {"years": [y for y, _ in full], "dps": [v for _, v in full], "ytd": round(ytd, 4) if ytd else None,
                        "g5": cagr(5), "g10": cagr(10), "payout": payout, "currency": m["currency"], "streak": streak,
                        "safety": {"label": label, "reasons": why} if full else None}
    # Aktionärsstruktur
    mh = safe(lambda: t.major_holders)
    if mh is not None and not getattr(mh, "empty", True):
        val = mh.iloc[:, 0] if mh.shape[1] else None
        get_ = lambda k: num(val.get(k)) if val is not None and k in val.index else None
        ins, inst = get_("insidersPercentHeld"), get_("institutionsPercentHeld")
        top = []
        ih = safe(lambda: t.institutional_holders)
        if ih is not None and not ih.empty and "pctHeld" in ih:
            for _, r_ in ih.sort_values("pctHeld", ascending=False).head(8).iterrows():
                if num(r_.get("pctHeld")):
                    top.append({"name": str(r_.get("Holder") or "").strip(), "pct": num(r_.get("pctHeld"))})
        if ins is not None or inst is not None:
            m["holders"] = {"insiders": ins, "institutions": inst, "count": get_("institutionsCount"),
                            "top": top if top and top[0]["pct"] >= 0.005 else []}


def gather(symbol, t, info):
    m = {"symbol": symbol}
    g = info.get
    m["name"] = g("longName") or g("shortName") or symbol
    m["currency"] = g("currency") or ""
    m["price"] = current_price(info)
    m["sector"], m["industry"] = g("sector") or "", g("industry") or ""
    m["country"], m["website"] = g("country") or "", g("website") or ""
    m["summary_text"] = g("longBusinessSummary") or ""
    m["exchange"] = g("fullExchangeName") or g("exchange") or ""
    m["mcap"] = num(g("marketCap"))

    # Bilanzwerte in die Kurswährung umrechnen (z. B. DKK-Bilanz bei USD-Notierung)
    m["fin_currency"] = financial_currency(symbol, info) or m["currency"]
    k = fx_rate(m["fin_currency"], m["currency"])
    inc = convert_df(safe(lambda: t.income_stmt), k)
    cf = convert_df(safe(lambda: t.cashflow), k)
    bs = convert_df(safe(lambda: t.balance_sheet), k)
    if abs(k - 1.0) > 1e-12 and not info.get("_fx_done"):
        info = dict(info)  # Yahoo-'info' liefert absolute Bilanzwerte in Berichtswährung
        for key_ in ("totalRevenue", "freeCashflow", "totalDebt", "totalCash", "ebitda", "operatingCashflow"):
            if num(info.get(key_)) is not None:
                info[key_] = num(info[key_]) * k
        g = info.get
    hist = safe(lambda: t.history(period="5y", auto_adjust=True))
    m["tech"] = safe(lambda: technicals(hist))
    if hist is not None and not hist.empty:
        hist = hist[hist["Close"].notna() & (hist["Close"] > 0)]  # laufender Tag ohne Schlusskurs
    divs = safe(lambda: t.dividends)

    # --- Bewertung
    m["pe"] = num(g("trailingPE"))
    m["fpe"] = num(g("forwardPE"))
    m["peg"] = num(g("trailingPegRatio")) or num(g("pegRatio"))
    m["pb"] = num(g("priceToBook"))
    m["ps"] = num(g("priceToSalesTrailing12Months"))
    m["ev_ebitda"] = num(g("enterpriseToEbitda"))
    m["ev"] = num(g("enterpriseValue"))
    fcf_hist = row(cf, "Free Cash Flow")
    qcf = convert_df(safe(lambda: t.quarterly_cashflow), k)
    m["fcf_hist"] = [v for v in fcf_hist if v is not None]
    # TTM aus den letzten 4 Quartalen; Yahoos „freeCashflow“ ist teils fehlerhaft (z. B. NVIDIA 42 statt 127 Mrd.)
    q_ocf = [v for v in row(qcf, "Operating Cash Flow")[:4] if v is not None]
    q_cap = [v for v in row(qcf, "Capital Expenditure")[:4] if v is not None]
    # 12-Monats-FCF nur, wenn Cashflow UND Investitionen aller 4 Quartale vorliegen (Yahoo lässt Capex teils weg)
    fcf_ttm = sum(q_ocf) + sum(q_cap) if len(q_ocf) == 4 and len(q_cap) == 4 else None
    m["fcf"] = fcf_ttm if fcf_ttm is not None else (first(fcf_hist) or num(g("freeCashflow")))
    m["fcf_yield"] = m["fcf"] / m["mcap"] if m["fcf"] is not None and m["mcap"] else None
    m["target"] = num(g("targetMeanPrice"))
    m["upside"] = (m["target"] / m["price"] - 1) if m["target"] and m["price"] else None
    m["rec_mean"] = num(g("recommendationMean"))
    m["rec_key"] = g("recommendationKey") or ""
    m["n_analysts"] = num(g("numberOfAnalystOpinions")) or 0

    # Historisches KGV (Jahresende-Kurs / verwässerter EPS)
    m["pe_hist"] = []
    eps_hist = row(inc, "Diluted EPS", "Basic EPS")
    if inc is not None and hist is not None and not hist.empty and eps_hist:
        closes = hist["Close"]
        idx = closes.index.tz_localize(None) if closes.index.tz is not None else closes.index
        closes = closes.copy()
        closes.index = idx
        for col, eps in zip(inc.columns, eps_hist):
            if eps and eps > 0:
                c = closes[closes.index <= col]
                if len(c):
                    m["pe_hist"].append(float(c.iloc[-1]) / eps)
    ph = sorted(m["pe_hist"])
    m["pe_hist_med"] = (ph[(len(ph) - 1) // 2] + ph[len(ph) // 2]) / 2 if ph else None

    # --- Qualität
    m["gross_m"] = num(g("grossMargins"))
    m["op_m"] = num(g("operatingMargins"))
    m["net_m"] = num(g("profitMargins"))
    m["roe"] = num(g("returnOnEquity"))
    m["roa"] = num(g("returnOnAssets"))
    m["revenue"] = num(g("totalRevenue")) or first(row(inc, "Total Revenue"))
    m["fcf_m"] = m["fcf"] / m["revenue"] if m["fcf"] is not None and m["revenue"] else None
    m["debt"] = num(g("totalDebt")) or first(row(bs, "Total Debt"))
    m["cash"] = num(g("totalCash")) or first(row(bs, "Cash And Cash Equivalents"))
    m["ebitda"] = num(g("ebitda")) or first(row(inc, "EBITDA"))
    m["net_debt"] = (m["debt"] or 0) - (m["cash"] or 0) if m["debt"] is not None else None
    m["nd_ebitda"] = (m["net_debt"] / m["ebitda"]) if m["net_debt"] is not None and m["ebitda"] and m["ebitda"] > 0 else None
    ebit = first(row(inc, "EBIT", "Operating Income"))
    tax = first(row(inc, "Tax Rate For Calcs")) or 0.21
    equity = first(row(bs, "Stockholders Equity", "Common Stock Equity"))
    invested = first(row(bs, "Invested Capital")) or ((m["debt"] or 0) + (equity or 0))
    m["roic"] = ebit * (1 - tax) / invested if ebit is not None and invested > 0 else None
    if abs(k - 1.0) > 1e-12 and m["mcap"]:
        # Yahoo mischt bei abweichender Bilanzwährung die Währungen -> mit umgerechneten Werten selbst berechnen
        m["ev"] = m["mcap"] + (m["debt"] or 0) - (m["cash"] or 0)
        m["ev_ebitda"] = m["ev"] / m["ebitda"] if m["ebitda"] and m["ebitda"] > 0 else None
        m["pb"] = m["mcap"] / equity if equity and equity > 0 else None
        if m["revenue"]:
            m["ps"] = m["mcap"] / m["revenue"]
    revs = row(inc, "Total Revenue")
    ops = row(inc, "Operating Income")
    nis = row(inc, "Net Income")
    m["revenues"], m["net_incomes"] = revs, nis
    om_hist = [o / r for o, r in zip(ops, revs) if o is not None and r]
    m["op_m_trend"] = (om_hist[0] - om_hist[-1]) if len(om_hist) >= 2 else None
    m["loss_years"] = sum(1 for n in nis if n is not None and n < 0)
    rd = first(row(inc, "Research And Development"))
    m["rd_ratio"] = rd / m["revenue"] if rd and m["revenue"] else None
    m["op_m_hist"] = om_hist
    m["equity"] = equity
    m["assets"] = first(row(bs, "Total Assets"))
    m["equity_ratio"] = equity / m["assets"] if equity and m["assets"] else None
    m["ltv"] = m["net_debt"] / m["assets"] if m["net_debt"] is not None and m["assets"] else None
    ni_ok = [n for n in nis if n is not None]
    m["avg_ni"] = sum(ni_ok) / len(ni_ok) if len(ni_ok) >= 3 else None
    m["norm_pe"] = m["mcap"] / m["avg_ni"] if m["mcap"] and m["avg_ni"] and m["avg_ni"] > 0 else None

    # --- Wachstum
    m["rev_g"] = num(g("revenueGrowth"))
    m["eps_g"] = num(g("earningsGrowth"))
    rv = [r for r in revs if r]
    m["rev_cagr"] = ((rv[0] / rv[-1]) ** (1 / (len(rv) - 1)) - 1) if len(rv) >= 2 and rv[-1] > 0 else None
    te, fe = num(g("trailingEps")), num(g("forwardEps"))
    m["fwd_eps_g"] = (fe / te - 1) if te and fe and te > 0 else None
    capex = first(row(cf, "Capital Expenditure"))
    m["capex_ratio"] = abs(capex) / m["revenue"] if capex and m["revenue"] else None

    # --- Kapitalallokation (Summe der verfügbaren Geschäftsjahre)
    def total(*names):
        vals = [v for v in row(cf, *names) if v is not None]
        return -sum(vals) if vals else None
    m["buybacks"] = total("Repurchase Of Capital Stock", "Common Stock Payments")
    m["div_paid"] = total("Cash Dividends Paid", "Common Stock Dividend Paid")
    m["acquisitions"] = total("Purchase Of Business", "Net Business Purchase And Sale")
    ocf = [v for v in row(cf, "Operating Cash Flow") if v is not None]
    m["ocf_sum"] = sum(ocf) if ocf else None
    m["cf_years"] = len(ocf)
    shares = [s for s in row(inc, "Diluted Average Shares") if s]
    m["share_change"] = (shares[0] / shares[-1] - 1) if len(shares) >= 2 else None
    last_bb = first(row(cf, "Repurchase Of Capital Stock", "Common Stock Payments"))
    last_dv = first(row(cf, "Cash Dividends Paid", "Common Stock Dividend Paid"))
    m["shareholder_yield"] = ((abs(last_bb or 0) + abs(last_dv or 0)) / m["mcap"]) if m["mcap"] else None
    balance_quality(m, inc, bs, cf)
    m["ocf"] = first(row(cf, "Operating Cash Flow")) or num(g("operatingCashflow"))
    m["p_ffo"] = m["mcap"] / m["ocf"] if m["mcap"] and m["ocf"] and m["ocf"] > 0 else None
    m["ev_sales"] = (m["ev"] or ((m["mcap"] or 0) + (m["net_debt"] or 0))) / m["revenue"]         if m["revenue"] and m["revenue"] > 0 and m["mcap"] else None
    m["runway"] = (m["cash"] / -m["fcf"]) if m["cash"] is not None and m["fcf"] is not None and m["fcf"] < 0 else None
    m["biz"] = classify_business(m)
    m["is_financial"] = m["biz"] in ("bank", "insurance")

    # --- Dividende
    m["div_yield"] = num(g("trailingAnnualDividendYield"))
    m["payout"] = num(g("payoutRatio"))
    m["div_cut"], m["div_streak"], m["div_years"] = False, 0, 0
    if divs is not None and len(divs):
        d = divs.copy()
        d.index = d.index.tz_localize(None) if d.index.tz is not None else d.index
        last_year = datetime.now() - timedelta(days=365)
        div_12m = float(d[d.index >= last_year].sum())
        if m["price"] and div_12m > 0:
            m["div_yield"] = div_12m / m["price"]
        yearly = d.groupby(d.index.year).sum()
        this_year = datetime.now().year
        yearly = yearly[yearly.index < this_year]
        vals = [float(v) for v in yearly.tail(11).values]
        m["div_years"] = len(vals)
        # Kürzung in den letzten 5 Jahren, die noch nicht wieder aufgeholt wurde
        recent_cut = False
        for i in range(max(1, len(vals) - 5), len(vals)):
            if vals[i] < vals[i - 1] * 0.9 and vals[-1] < max(vals[:i]) * 0.95:
                recent_cut = True
        m["div_cut"] = recent_cut
        streak = 0
        for i in range(len(vals) - 1, 0, -1):
            if vals[i] >= vals[i - 1] * 0.98:
                streak += 1
            else:
                break
        m["div_streak"] = streak
    if not m["div_yield"]:
        m["div_yield"] = 0.0 if divs is not None else None
    m["payout_eps"] = None
    if m["biz"] == "real_estate" and last_dv and m["ocf"] and m["ocf"] > 0:
        m["payout_eps"], m["payout"] = m["payout"], abs(last_dv) / m["ocf"]  # REIT-Ausschüttung gemessen an FFO

    # --- Kurs / Charttechnik
    m["beta"] = num(g("beta"))
    m["short_float"] = num(g("shortPercentOfFloat"))
    if hist is not None and not hist.empty and len(hist) > 60:
        c = hist["Close"]
        m["sma50"] = float(c.rolling(50).mean().iloc[-1])
        m["sma200"] = float(c.rolling(200).mean().iloc[-1]) if len(c) >= 200 else None
        m["sma200_3m"] = float(c.rolling(200).mean().iloc[-64]) if len(c) >= 264 else None
        last = float(c.iloc[-1])
        m["last"] = last
        m["price_3m_ago"] = float(c.iloc[-64]) if len(c) > 64 else None

        def perf(n):
            return last / float(c.iloc[-n - 1]) - 1 if len(c) > n else None
        m["perf_1m"], m["perf_3m"], m["perf_6m"], m["perf_1y"] = perf(21), perf(63), perf(126), perf(252)
        m["perf_5y"] = last / float(c.iloc[0]) - 1
        delta = c.diff()
        up = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
        dn = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
        rs = up / dn
        m["rsi"] = float(100 - 100 / (1 + rs.iloc[-1])) if dn.iloc[-1] else 100.0
        y = c.iloc[-252:]
        ret = y.pct_change().dropna()
        m["vol"] = float(ret.std() * math.sqrt(252))
        m["hi52"], m["lo52"] = float(y.max()), float(y.min())
        m["max_dd"] = float((y / y.cummax() - 1).min())
    else:
        for k in ("sma50", "sma200", "sma200_3m", "last", "price_3m_ago", "perf_1m", "perf_3m", "perf_6m",
                  "perf_1y", "perf_5y", "rsi", "vol", "hi52", "lo52", "max_dd"):
            m[k] = None

    # Analysten-Verteilung
    rec = safe(lambda: t.recommendations)
    m["rec_dist"] = None
    if rec is not None and not rec.empty:
        r0 = rec.iloc[0]
        dist = {k: int(r0.get(k, 0) or 0) for k in ("strongBuy", "buy", "hold", "sell", "strongSell")}
        if sum(dist.values()):
            m["rec_dist"] = dist
        m["rec_hist"] = [{"period": str(r_.get("period")), **{k: int(r_.get(k, 0) or 0) for k in
                          ("strongBuy", "buy", "hold", "sell", "strongSell")}} for _, r_ in rec.iterrows()][:6]
    m["target_low"], m["target_high"] = num(g("targetLowPrice")), num(g("targetHighPrice"))
    m["target_median"] = num(g("targetMedianPrice"))
    expectations(m, t)
    safe(lambda: chart_extras(m, t, inc, bs, divs))
    return m


def gather_macro(currency):
    mac = {"rf": None, "rf_chg": None, "fx_chg": None, "fx_pair": None}
    tnx = safe(lambda: yf.Ticker("^TNX").history(period="6mo")["Close"])
    if tnx is not None and len(tnx) > 20:
        conv = (lambda v: v / 10 if v > 20 else v)
        mac["rf"] = conv(float(tnx.iloc[-1]))
        mac["rf_chg"] = mac["rf"] - conv(float(tnx.iloc[0]))
    cur = {"GBp": "GBP", "GBX": "GBP", "ZAc": "ZAR", "ILA": "ILS"}.get(currency, currency)
    if cur and cur != "EUR":
        mac["fx_pair"] = f"EUR/{cur}"
        fx = safe(lambda: yf.Ticker(f"EUR{cur}=X").history(period="1y")["Close"])
        if fx is not None and len(fx) > 20:
            # positiv = Fremdwährung hat ggü. Euro aufgewertet (gut für Euro-Anleger)
            mac["fx_chg"] = float(fx.iloc[0]) / float(fx.iloc[-1]) - 1
    return mac


# ---------------------------------------------------------------------------
# Bewertungslogik: jede Kategorie -> Score (-1..+1), Adjektiv, Begründungen
# ---------------------------------------------------------------------------
def cost_of_equity(m, mac):
    return clamp((mac["rf"] or 4.0) / 100 + (m["beta"] or 1.0) * 0.05, 0.07, 0.13)


def growth_estimate(m):
    """Vorsichtige Wachstumsschätzung: der kleinere Wert aus mehrjähriger CAGR und letztem Quartal
    (die CAGR ist bei jungen Firmen durch winzige Anfangsumsätze stark überzeichnet)."""
    g = [x for x in (m["rev_cagr"], m["rev_g"]) if x is not None]
    return clamp(min(g), -0.5, 0.6) if g else None


def model_valuation(m, mac, ref_pe, why):
    """Zusätzliche Bewertungsbausteine je Geschäftsmodell -> Liste (Score, Gewicht)."""
    biz, parts = m["biz"], []
    if biz in ("bank", "insurance") and m["pb"] and m["pb"] > 0 and m["roe"] is not None and -0.5 < m["roe"] < 0.6:
        coe, g = cost_of_equity(m, mac), 0.025
        fair_pb = max(0.2, (m["roe"] - g) / (coe - g))
        parts.append((clamp((fair_pb / m["pb"] - 1) * 1.5), 1.3))
        why.append(f"Kurs-Buchwert {fnum(m['pb'], 2)} vs. fairer Wert {fnum(fair_pb, 2)} "
                   f"(aus ROE {pct(m['roe'])} und Eigenkapitalkosten {pct(coe)})")
    elif biz == "real_estate":
        if m["p_ffo"]:
            parts.append((clamp((1 - m["p_ffo"] / 15) * 1.5), 1.3))
            why.append(f"Kurs/FFO {fnum(m['p_ffo'])} (Näherung: operativer Cashflow; ~15 ≈ neutral)")
        if m["pb"] and m["pb"] > 0:
            parts.append((clamp((1.0 - m["pb"]) / 0.8), 0.6))
            why.append(f"Kurs-Buchwert {fnum(m['pb'], 2)} (≈ Abschlag/Aufschlag auf den Immobilienwert, 1,0 = neutral)")
    elif biz == "loss_growth" and m["ev_sales"]:
        g = growth_estimate(m) or 0
        gm = m["gross_m"] if m["gross_m"] is not None else 0.4
        # Umsatz ist umso mehr wert, je höher die Bruttomarge (Software ~75 %, Autos/Hardware ~10–20 %)
        fair = clamp(g * 30, 1.0, 20.0) * clamp(gm / 0.6, 0.15, 1.25)
        parts.append((clamp((fair / m["ev_sales"] - 1) * 1.0), 1.3))
        why.append(f"EV/Umsatz {fnum(m['ev_sales'], 1)} vs. ~{fnum(fair, 1)} angemessen bei {pct(g)} Umsatzwachstum "
                   f"und {pct(gm)} Bruttomarge")
    elif biz == "pre_revenue" and m["mcap"] and m["cash"]:
        ratio = m["mcap"] / m["cash"]
        parts.append((clamp((3 - ratio) / 3), 0.6))
        why.append(f"Börsenwert = {fnum(ratio, 1)}-fache der Kasse (unter 1 = Markt bewertet die Pipeline mit null)")
    elif biz == "cyclical":
        if m["norm_pe"]:
            parts.append((clamp((1 - m["norm_pe"] / ref_pe) * 1.5), 1.2))
            why.append(f"KGV auf Durchschnittsgewinn der letzten {len([n for n in m['net_incomes'] if n is not None])} "
                       f"Jahre: {fnum(m['norm_pe'])} (normalisiert, glättet Zyklusspitzen)")
        hist = [x for x in m["op_m_hist"] if x is not None]
        if m["op_m"] is not None and len(hist) >= 3:
            avg = sum(hist) / len(hist)
            if avg > 0 and m["op_m"] > avg * 1.35:
                parts.append((-0.5, 0.8))
                why.append(f"Marge {pct(m['op_m'])} deutlich über dem Mittel {pct(avg)} – Gewinne nahe Zyklushoch, "
                           "niedriges KGV kann trügen")
            elif avg > 0 and m["op_m"] < avg * 0.65:
                parts.append((0.3, 0.6))
                why.append(f"Marge {pct(m['op_m'])} unter dem Mittel {pct(avg)} – möglicherweise Zyklustief")
    return parts


def dcf_value(fcf, g1, r, g_term, net_debt, shares, years=10, fade_from=5):
    """Abgezinste Free Cashflows: Jahre 1–5 mit g1, danach linear auf g_term, Endwert nach Gordon."""
    pv, cf_ = 0.0, fcf
    for y in range(1, years + 1):
        g = g1 if y <= fade_from else g1 + (g_term - g1) * (y - fade_from) / (years - fade_from)
        cf_ *= 1 + g
        pv += cf_ / (1 + r) ** y
    tv = cf_ * (1 + g_term) / (r - g_term)
    pv += tv / (1 + r) ** years
    equity = pv - (net_debt or 0)
    return equity / shares if equity > 0 and shares else None


def fair_value(m, mac):
    """Fairer Wert je Aktie in drei Szenarien (vorsichtig / Basis / optimistisch)."""
    biz, price = m.get("biz", "standard"), m["price"]
    shares = m["mcap"] / price if m["mcap"] and price else None
    if not shares:
        return None
    coe = cost_of_equity(m, mac)
    out = {"method": "", "assumptions": [], "bear": None, "base": None, "bull": None}
    if biz in ("bank", "insurance"):
        if not (m["pb"] and m["pb"] > 0 and m["roe"] is not None and 0 < m["roe"] < 0.6):
            return None
        book, g = price / m["pb"], 0.025
        val = lambda roe_, r_: book * max(0.2, (roe_ - g) / (r_ - g))
        out.update(method="Kurs-Buchwert aus Eigenkapitalrendite",
                   bear=val(m["roe"] - 0.02, coe + 0.01), base=val(m["roe"], coe), bull=val(m["roe"] + 0.02, coe - 0.01))
        out["assumptions"] = [f"Buchwert je Aktie {fnum(book, 2)}", f"ROE {pct(m['roe'])} (±2 Prozentpunkte)",
                              f"Eigenkapitalkosten {pct(coe)} (±1 Prozentpunkt)"]
    elif biz == "real_estate":
        if not (m["ocf"] and m["ocf"] > 0):
            return None
        ffo_ps = m["ocf"] / shares
        out.update(method="Kurs/FFO-Vielfaches", bear=ffo_ps * 12, base=ffo_ps * 15, bull=ffo_ps * 18)
        out["assumptions"] = [f"FFO je Aktie ≈ {fnum(ffo_ps, 2)} (operativer Cashflow)", "Vielfaches 12 / 15 / 18"]
    elif biz in ("pre_revenue",):
        return {"method": "", "na": "Ohne nennenswerten Umsatz ist kein fairer Wert berechenbar – der Wert hängt an Studien, "
                "Zulassungen oder technologischen Durchbrüchen."}
    else:
        hist = [v for v in (m.get("fcf_hist") or []) if v is not None]
        base_fcf = (sum(hist) / len(hist)) if biz == "cyclical" and len(hist) >= 3 else m["fcf"]
        owner = m.get("owner_earnings")
        used_owner = biz != "cyclical" and owner is not None and base_fcf is not None and owner > base_fcf
        # IFRS (fast alle Nicht-US-Firmen): Leasingzahlungen stehen nicht im Free Cashflow, die Leasingschulden aber
        # in den Finanzschulden -> Zahlung (≈ Verbindlichkeit / 6 Jahre) abziehen und Schulden ohne Leasing rechnen
        ifrs = "." in m["symbol"] or (m.get("fin_currency") or m["currency"]) != "USD"
        lease = (m.get("lease_obl") or 0) if ifrs else 0
        lease_pay = lease / 6 if lease and not used_owner else 0
        if base_fcf is not None:
            base_fcf -= lease_pay
        nd = (m["net_debt"] or 0) - lease + (m.get("minority") or 0)
        if used_owner:
            base_fcf = owner  # hohe Wachstumsinvestitionen drücken den Free Cashflow nur vorübergehend
        if base_fcf is not None and m.get("sbc"):
            base_fcf -= m["sbc"]
        if base_fcf is None or base_fcf <= 0:
            return {"method": "", "na": "Der Free Cashflow ist (nach Aktienvergütung) negativ – ein Cashflow-Modell ist "
                    "noch nicht sinnvoll. Maßgeblich sind EV/Umsatz, Rule of 40 und Cash-Reichweite."}
        frg = est_growth(m, "est_rev")
        hist_g = m["rev_cagr"]
        parts_ = [(frg, 0.6), (hist_g, 0.4)] if frg is not None and hist_g is not None else [(frg if frg is not None else hist_g, 1)]
        g_base = wavg([(clamp(x, -0.1, 0.5), w) for x, w in parts_ if x is not None])
        if g_base is None:
            g_base = 0.04
        g_base = clamp(g_base, -0.05, 0.30)
        if biz == "cyclical":
            g_base = min(g_base, 0.10)  # Zykliker: Wachstum begrenzen, Basis ist der Durchschnitts-Cashflow
        r1 = (m.get("est_rev") or {}).get("+1y") or {}
        spread = ((r1["high"] - r1["low"]) / r1["avg"] / 2) if r1.get("avg") and r1.get("high") and r1.get("low") else 0
        d = clamp(max(0.04, spread), 0.04, 0.12)
        # Diskontsatz: angepasstes Beta (Blume: 2/3 Beta + 1/3) und 4,5 % Marktrisikoprämie
        beta_adj = 0.67 * clamp(m["beta"] or 1.0, 0.3, 2.5) + 0.33
        r = clamp((mac["rf"] or 4.0) / 100 + beta_adj * 0.045, 0.075, 0.12)  # Untergrenze: auch „sichere“ Aktien sind keine Anleihe
        out.update(method="Discounted-Cashflow (10 Jahre)",
                   bear=dcf_value(base_fcf, max(-0.10, g_base - d), r + 0.01, 0.02, nd, shares),
                   base=dcf_value(base_fcf, g_base, r, 0.025, nd, shares),
                   bull=dcf_value(base_fcf, min(0.40, g_base + d), max(0.07, r - 0.01), 0.03, nd, shares))
        out["assumptions"] = [
            ("Owner Earnings (operativer Cashflow minus Abschreibungen) " if used_owner else "Free Cashflow ")
            + money(base_fcf, m['currency']) + (" (Ø der Geschäftsjahre, Zykliker)" if biz == "cyclical" else "" if used_owner else " (12 Monate)")
            + (" nach Aktienvergütung" if m.get("sbc") else ""),
            f"Wachstum Jahre 1–5: {pct(g_base - d)} / {pct(g_base)} / {pct(g_base + d)}"
            + (" (aus Analystenprognose und Historie)" if frg is not None else " (aus der Historie)"),
            "danach schrittweise auf 2–3 % Dauerwachstum",
            *([f"Leasing: Zahlungen ≈ {money(lease_pay, m['currency'])} p. a. abgezogen, Leasingschulden nicht doppelt gezählt"]
              if lease_pay else []),
            *([f"Minderheitsanteile {money(m['minority'], m['currency'])} abgezogen"] if (m.get("minority") or 0) > 0.02 * (m["mcap"] or 1) else []),
            f"Diskontsatz {pct(r + 0.01)} / {pct(r)} / {pct(max(0.07, r - 0.01))}"]
    if out["base"] is None:
        return None
    out["upside"] = out["base"] / price - 1
    return out


def checklist(m, cats):
    """Stärken und Warnsignale als kompakte Liste (Typ, Text)."""
    biz, out = m.get("biz", "standard"), []
    add = lambda kind, text: out.append({"type": kind, "text": text})
    fin = m.get("is_financial")
    nd, cov = m.get("nd_ebitda"), m.get("int_cov")
    if not fin and biz != "real_estate":
        if nd is not None and nd < 0:
            add("plus", "Mehr Cash als Schulden (Netto-Cash)")
        elif nd is not None and nd > 3.5:
            add("risk", f"Hohe Verschuldung: Nettoschulden = {fnum(nd, 1)}-faches EBITDA")
        if cov is not None and (m.get("debt") or 0) > 0 and cov < 3:
            add("risk", f"Zinsen nur knapp gedeckt (Zinsdeckung {fnum(cov, 1)}x)")
        z = m.get("altman_z")
        if z is not None and z < 1.8:
            add("risk", f"Altman Z-Score {fnum(z, 1)}: erhöhtes Insolvenzrisiko")
    if biz == "real_estate" and (m.get("ltv") or 0) > 0.55:
        add("risk", f"Hohe Beleihungsquote ({pct(m['ltv'])})")
    sc = m.get("share_change")
    if sc is not None and sc > 0.05:
        add("risk", f"Aktionäre verwässert: Aktienanzahl +{fnum(sc * 100, 1)} % in {len(m.get('revenues') or [])} Jahren")
    elif sc is not None and sc < -0.02:
        add("plus", f"Aktienrückkäufe: Aktienanzahl {fnum(sc * 100, 1)} %")
    y, p_ = m.get("div_yield") or 0, m.get("payout")
    if y > 0 and p_ is not None and p_ > 0.9 and biz != "real_estate":
        add("risk", f"Dividende kaum durch Gewinn gedeckt (Ausschüttungsquote {pct(p_)})")
    if y > 0 and m.get("div_paid") and m.get("fcf") is not None and m.get("cf_years"):
        if m["fcf"] < (m["div_paid"] / m["cf_years"]) * 0.9:
            add("risk", "Dividende nicht durch den Free Cashflow gedeckt")
    if (m.get("div_streak") or 0) >= 10 and y > 0:
        add("plus", f"Dividende seit {m['div_streak']} Jahren stabil oder steigend")
    if m.get("div_cut"):
        add("risk", "Dividende in den letzten 5 Jahren gekürzt")
    if (m.get("loss_years") or 0) > 0 and biz not in ("loss_growth", "pre_revenue"):
        add("risk", f"{m['loss_years']} Verlustjahr(e) in den letzten Jahren")
    if m.get("fcf") is not None and m["fcf"] < 0:
        add("risk", "Negativer Free Cashflow")
    if (m.get("fcf_m_adj") or 0) >= 0.15:
        add("plus", f"Hohe Free-Cashflow-Marge ({pct(m['fcf_m_adj'])} nach Aktienvergütung)")
    if (m.get("roic") or 0) >= 0.15 and not fin:
        add("plus", f"Hohe Kapitalrendite (ROIC {pct(m['roic'])})")
    rc = m.get("rev_cagr")
    if rc is not None and rc < 0:
        add("risk", f"Umsatz schrumpft ({pct(rc)} p. a.)")
    elif rc is not None and rc >= 0.10:
        add("plus", f"Umsatz wächst stark ({pct(rc)} p. a.)")
    tr = m.get("op_m_trend")
    if tr is not None and tr <= -0.03:
        add("risk", f"Operative Marge sinkt ({fnum(tr * 100, 1)} Prozentpunkte)")
    elif tr is not None and tr >= 0.03:
        add("plus", f"Operative Marge steigt (+{fnum(tr * 100, 1)} Prozentpunkte)")
    pio = m.get("piotroski")
    if pio is not None and pio >= 7:
        add("plus", f"Piotroski F-Score {fnum(pio, 0)}/9: Fundamentaldaten verbessern sich")
    elif pio is not None and pio <= 3:
        add("risk", f"Piotroski F-Score {fnum(pio, 0)}/9: Fundamentaldaten verschlechtern sich")
    if (m.get("accruals") or 0) > 0.08:
        add("risk", "Gewinn kaum durch Cash gedeckt (Gewinnqualität)")
    er = m.get("eps_rev")
    if er is not None and er >= 0.03:
        add("plus", f"Analysten heben Gewinnschätzungen an (+{fnum(er * 100, 1)} % in 90 Tagen)")
    elif er is not None and er <= -0.03:
        add("risk", f"Analysten senken Gewinnschätzungen ({fnum(er * 100, 1)} % in 90 Tagen)")
    sp = m.get("surprises") or []
    if len(sp) >= 4 and all(x > 0 for x in sp[-4:]):
        add("plus", "Erwartungen in allen letzten 4 Quartalen übertroffen")
    ins = m.get("insider") or {}
    if ins.get("buyers", 0) >= 2:
        add("plus", f"Insiderkäufe: {ins['buyers']} Insider kauften in 6 Monaten")
    fv = m.get("fair") or {}
    if fv.get("upside") is not None and fv["upside"] >= 0.20:
        add("plus", f"Kurs {fnum(fv['upside'] * 100, 0)} % unter dem fairen Wert (Basisszenario)")
    elif fv.get("upside") is not None and fv["upside"] <= -0.30:
        add("risk", f"Kurs {fnum(-fv['upside'] * 100, 0)} % über dem fairen Wert (Basisszenario)")
    if (m.get("vol") or 0) > 0.45:
        add("risk", f"Sehr schwankungsanfällig (Volatilität {pct(m['vol'])})")
    if (m.get("short_float") or 0) > 0.10:
        add("risk", f"Viele Leerverkäufer ({pct(m['short_float'])} des Streubesitzes)")
    if m.get("sma200") and m.get("last"):
        if m["last"] > m["sma200"] * 1.02 and (m.get("perf_6m") or 0) > 0:
            add("plus", "Kurs im Aufwärtstrend (über der 200-Tage-Linie)")
        elif m["last"] < m["sma200"] * 0.95:
            add("risk", "Kurs im Abwärtstrend (unter der 200-Tage-Linie)")
    return out


def score_valuation(m, mac):
    ref_pe, ref_ev = SECTOR_REF.get(m["sector"], (20, 13))
    biz = m.get("biz", "standard")
    ref_pe = {"bank": 11, "insurance": 13}.get(biz, ref_pe)
    peer_ref = m.get("peer_pe_med")
    if peer_ref:
        ref_pe = round(peer_ref, 1)
    parts, why = [], []
    pe = m["pe"]
    pe_w = 0.5 if biz == "cyclical" else 1.0  # bei Zyklikern zählt das normalisierte KGV stärker
    if biz == "real_estate":
        if pe and pe > 0:
            why.append(f"KGV {fnum(pe)} – bei Immobilienwerten durch Abschreibungen und Neubewertungen verzerrt, nicht gewertet")
    elif pe and pe > 0:
        s = clamp((1 - pe / ref_pe) * 1.5)
        parts.append((s, pe_w))
        why.append(f"KGV {fnum(pe)} vs. Median von {m['peer_n']} Wettbewerbern {fnum(ref_pe)}" if peer_ref
                   else f"KGV {fnum(pe)} vs. Branchen-Referenz ~{ref_pe} ({m['sector'] or 'Markt'})")
    elif m["net_m"] is not None and m["net_m"] < 0:
        if biz in ("loss_growth", "pre_revenue"):
            why.append("Kein KGV (Verluste) – Bewertung stattdessen über Umsatz bzw. Kasse")
        else:
            parts.append((-0.4, 1.0))
            why.append("Kein positives KGV – Unternehmen schreibt Verluste")
    if pe and pe > 0 and m["pe_hist_med"] and biz != "real_estate":
        s = clamp((1 - pe / m["pe_hist_med"]) * 1.5)
        parts.append((s, pe_w))
        why.append(f"KGV vs. eigener Historie (Median {fnum(m['pe_hist_med'])}, {len(m['pe_hist'])} Jahre)")
    if m["fpe"] and m["fpe"] > 0 and biz != "real_estate":
        fw = 0.4 if biz == "cyclical" else 0.8  # bei Zyklikern beruht die Prognose oft auf Spitzengewinnen
        parts.append((clamp((1 - m["fpe"] / ref_pe) * 1.5), fw))
        why.append(f"Forward-KGV {fnum(m['fpe'])} auf den erwarteten Gewinn vs. Referenz {fnum(ref_pe)}"
                   + ("" if not (pe and pe > 0) else f" ({'Gewinnanstieg erwartet' if m['fpe'] < pe else 'Gewinnrückgang erwartet'})"))
    if m["ev_ebitda"] and m["ev_ebitda"] > 0 and not m["is_financial"]:
        parts.append((clamp((1 - m["ev_ebitda"] / ref_ev) * 1.5), 1.0))
        why.append(f"EV/EBITDA {fnum(m['ev_ebitda'])} vs. Branche ~{ref_ev}")
    if m["fcf_yield"] is not None and not m["is_financial"] and biz not in ("real_estate", "loss_growth", "pre_revenue"):
        fy = m["fcf_yield"]
        if m.get("fcf_yield_adj") is not None and (m.get("sbc_ratio") or 0) >= 0.02:
            fy = m["fcf_yield_adj"]  # Aktienvergütung ist echter Aufwand -> vom Free Cashflow abziehen
            why.append(f"Free-Cashflow-Rendite {pct(m['fcf_yield'])}, nach Aktienvergütung {pct(fy)} (4 % ≈ neutral)")
        else:
            why.append(f"Free-Cashflow-Rendite {pct(fy)} (4 % ≈ neutral)")
        parts.append((clamp((fy - 0.04) / 0.04), 1.0))
    if m["peg"] and m["peg"] > 0:
        parts.append((clamp((1.5 - m["peg"]) / 1.0), 0.7))
        why.append(f"PEG-Ratio {fnum(m['peg'], 2)} (unter 1 = günstig relativ zum Wachstum)")
    parts += model_valuation(m, mac, ref_pe, why)
    fv = m.get("fair") if "fair" in m else None
    if fv is None and m.get("price"):
        fv = m["fair"] = safe(lambda: fair_value(m, mac))
    if fv and fv.get("base"):
        parts.append((clamp(fv["upside"] / 0.35), 0.5))
        why.append(f"Fairer Wert ({fv['method']}, Basisszenario) {fnum(fv['base'], 2)} {m['currency']} → "
                   f"{'+' if fv['upside'] >= 0 else ''}{fnum(fv['upside'] * 100, 1)} % · Spanne "
                   f"{fnum(fv['bear'], 2) if fv.get('bear') else '–'} bis {fnum(fv['bull'], 2) if fv.get('bull') else '–'}")
    if m["upside"] is not None and (m["n_analysts"] >= 3 or m.get("target_n", 0) >= 2):
        w = 0.6 if not m.get("target_n") else 0.6 * min(1.0, m["target_n"] / 6)  # wenige Meldungen -> weniger Gewicht
        parts.append((clamp(m["upside"] / 0.3), w))
        src = f" ({m['target_src']})" if m.get("target_src") else ""
        why.append(f"Analysten-Kursziel {fnum(m['target'], 2)} {m['currency']} → {pct(m['upside'])} Potenzial{src}")
        if m.get("target_n"):
            why.append("Einzelziele: " + " · ".join(f"{t['firm']} {fnum(t['value'], 0)}" for t in m["target_items"][:8]))

    # Eingepreiste Erwartungen (Reverse-DCF)
    r = cost_of_equity(m, mac)
    ev = m["ev"] or ((m["mcap"] or 0) + (m["net_debt"] or 0))
    implied = None if m["is_financial"] or biz in ("real_estate", "pre_revenue") else reverse_dcf(m.get("fcf_adj", m["fcf"]), ev, r)
    def med(xs):
        xs = sorted(x for x in xs if x is not None)
        return (xs[(len(xs) - 1) // 2] + xs[len(xs) // 2]) / 2 if xs else None
    rev_e = med([m["rev_cagr"], m["rev_g"], est_growth(m, "est_rev")])
    eps_e = med([m["eps_g"], m["fwd_eps_g"], est_growth(m, "est_eps")])
    expected = wavg([(None if rev_e is None else clamp(rev_e, -0.15, 0.3), 0.6),
                     (None if eps_e is None else clamp(eps_e, -0.2, 0.25), 0.4)])
    m["implied_g"], m["expected_g"], m["disc_rate"] = implied, expected, r
    if implied is not None and expected is not None:
        gap = implied - expected
        parts.append((clamp(-gap / 0.10), 1.2))
        why.append(f"Reverse-DCF: Kurs preist {pct(implied)} FCF-Wachstum p.a. (10 J., Diskontsatz {pct(r)}) ein – "
                   f"erwartbar sind ca. {pct(expected)}")
    v = wavg(parts)
    if v is None:
        return {"score": None, "adjective": "fair bewertet", "reasons": why + ["Zu wenige Bewertungsdaten"]}

    hot = (m["rsi"] or 50) > 70 or (m["sma200"] and m["last"] and m["last"] / m["sma200"] > 1.3)
    if v >= 0.6:
        adj = "unterbewertet"
    elif v >= 0.15 and (m["perf_6m"] or 0) < -0.1 and (m["roe"] or 0) > 0.12:
        adj = "unterschätzt"
    elif v >= 0.45:
        adj = "günstig"
    elif v >= 0.3:
        adj = "preiswert"
    elif v >= 0.15:
        adj = "attraktiv bewertet"
    elif v >= 0.05:
        adj = "angemessen bewertet"
    elif v >= -0.05:
        adj = "fair bewertet"
    elif v >= -0.15:
        adj = "marktgerecht"
    elif v < -0.6 and hot:
        adj = "überhitzt"
    elif v < -0.3 and hot:
        adj = "heißgelaufen"
    elif v < -0.45:
        adj = "überbewertet"
    elif v < -0.3:
        adj = "teuer"
    else:
        adj = "ambitioniert bewertet"
    return {"score": v, "adjective": adj, "reasons": why}


def model_quality(m):
    """Qualitätsbausteine für Banken, Versicherer, Immobilien und Verlust-/Vorumsatzfirmen."""
    biz, parts, why = m["biz"], [], []
    if biz in ("bank", "insurance"):
        if m["roe"] is not None and -1 < m["roe"] < 1:
            parts.append((clamp((m["roe"] - 0.10) / 0.08), 1.3))
            why.append(f"Eigenkapitalrendite (ROE) {pct(m['roe'])} (10 % ≈ Kapitalkosten)")
        if biz == "bank" and m["roa"] is not None:
            parts.append((clamp((m["roa"] - 0.006) / 0.005), 0.8))
            why.append(f"Gesamtkapitalrendite (ROA) {pct(m['roa'], 2)} (Banken: ~0,6 % ≈ neutral)")
        if m["equity_ratio"] is not None:
            base_, span = (0.05, 0.03) if biz == "bank" else (0.07, 0.04)
            parts.append((clamp((m["equity_ratio"] - base_) / span), 0.8))
            why.append(f"Eigenkapitalquote {pct(m['equity_ratio'])} (Bilanz-Eigenkapital / Bilanzsumme)")
        if m["net_m"] is not None:
            base_, span = (0.20, 0.15) if biz == "bank" else (0.05, 0.07)
            parts.append((clamp((m["net_m"] - base_) / span), 0.6))
            why.append(f"Nettomarge {pct(m['net_m'])}")
    elif biz == "real_estate":
        if m["op_m"] is not None:
            parts.append((clamp((m["op_m"] - 0.35) / 0.25), 0.8))
            why.append(f"Operative Marge {pct(m['op_m'])} (Immobilien: ~35 % ≈ neutral)")
        if m["ocf"] and m["revenue"]:
            fm = m["ocf"] / m["revenue"]
            parts.append((clamp((fm - 0.30) / 0.25), 1.0))
            why.append(f"FFO-Marge (operativer Cashflow / Umsatz) {pct(fm)}")
        if m["ltv"] is not None:
            parts.append((clamp((0.45 - m["ltv"]) / 0.15), 1.0))
            why.append(f"Beleihungsquote (Nettoschulden / Bilanzsumme) {pct(m['ltv'])} (unter 45 % solide)")
    else:  # loss_growth / pre_revenue
        if biz == "loss_growth" and m["net_m"] is not None:
            parts.append((clamp(m["net_m"] / 0.25), 0.8))  # -25 % Nettomarge = -1
            why.append(f"Nettomarge {pct(m['net_m'])} (Verlustphase)")
        if biz == "pre_revenue":
            parts.append((-0.8, 1.5))
            why.append("Noch kein nennenswerter Umsatz – tragfähiges Geschäftsmodell nicht nachgewiesen")
        if biz == "loss_growth":
            if m["gross_m"] is not None:
                parts.append((clamp((m["gross_m"] - 0.45) / 0.25), 1.0))
                why.append(f"Bruttomarge {pct(m['gross_m'])} (hoch = späteres Gewinnpotenzial)")
            g = growth_estimate(m)
            fm = m.get("fcf_m_adj") if m.get("fcf_m_adj") is not None else m["fcf_m"]
            if g is not None and fm is not None:
                r40 = g + fm
                parts.append((clamp((r40 - 0.25) / 0.25), 1.2))
                why.append(f"„Rule of 40“: Wachstum {pct(g)} + FCF-Marge nach Aktienvergütung {pct(fm)} = {pct(r40)} "
                           "(≥ 40 % stark)")
            if m.get("piotroski") is not None:
                parts.append((clamp((m["piotroski"] - 5) / 3), 0.6))
                why.append(f"Piotroski F-Score {fnum(m['piotroski'], 0)}/9 (Richtung der Fundamentaldaten)")
            if m["op_m_trend"] is not None:
                parts.append((clamp(m["op_m_trend"] / 0.10), 0.8))
                why.append(f"Margentrend über {len(m['revenues'])} Jahre: {'+' if m['op_m_trend'] >= 0 else ''}"
                           f"{fnum(m['op_m_trend'] * 100)} Prozentpunkte (Weg Richtung Gewinnschwelle)")
        if m["runway"] is not None:
            parts.append((clamp((m["runway"] - 1.5) / 1.5), 1.5 if biz == "pre_revenue" else 1.0))
            why.append(f"Cash-Reichweite ≈ {fnum(m['runway'], 1)} Jahre beim aktuellen Mittelabfluss")
        elif m["fcf"] is not None and m["fcf"] >= 0:
            if (m.get("fcf_adj") or 0) >= 0:
                parts.append((0.5, 1.0))
                why.append("Free Cashflow bereits positiv – keine Finanzierungslücke")
            else:
                parts.append((0.0, 1.0))
                why.append("Free Cashflow nur dank Aktienvergütung positiv – bereinigt noch negativ")
    return parts, why


def score_quality(m):
    biz = m.get("biz", "standard")
    if biz in ("bank", "insurance", "real_estate", "loss_growth", "pre_revenue"):
        parts, why = model_quality(m)
    else:
        parts, why = standard_quality(m)
    q = wavg(parts)
    if q is None:
        return {"score": None, "adjective": "solide", "reasons": why + ["Zu wenige Qualitätsdaten"]}
    return {"score": q, "adjective": quality_adj(m, q), "reasons": why}


def quality_extras(m, parts, why):
    """Piotroski F-Score und Gewinnqualität – für Industrie-, Handels- und Wachstumsfirmen (nicht Banken/Immobilien)."""
    if m.get("piotroski") is not None:
        parts.append((clamp((m["piotroski"] - 5) / 3), 0.8))
        fails = m.get("piotroski_fail") or []
        why.append(f"Piotroski F-Score {fnum(m['piotroski'], 0)}/9 (≥ 7 stark, ≤ 3 schwach)"
                   + (f" – nicht erfüllt: {', '.join(fails[:3])}" if fails and m["piotroski"] < 7 else ""))
    if m.get("accruals") is not None:
        parts.append((clamp((0.02 - m["accruals"]) / 0.08), 0.5))
        why.append(f"Gewinnqualität: Gewinn minus operativer Cashflow = {pct(m['accruals'])} der Bilanzsumme "
                   + ("(Gewinn durch Cash gedeckt)" if m["accruals"] <= 0 else "(Gewinn höher als Cashzufluss)"
                      if m["accruals"] < 0.08 else "(Warnsignal: Gewinn kaum durch Cash gedeckt)"))


def standard_quality(m):
    parts, why = [], []
    if m["op_m"] is not None:
        parts.append((clamp((m["op_m"] - 0.10) / 0.15), 1.0))
        why.append(f"Operative Marge {pct(m['op_m'])}")
    if m["net_m"] is not None:
        parts.append((clamp(m["net_m"] / 0.15) if m["net_m"] >= 0 else clamp(m["net_m"] / 0.1), 1.0))
        why.append(f"Nettomarge {pct(m['net_m'])}")
    if m["roe"] is not None and -1 < m["roe"] < 1.0:
        parts.append((clamp((m["roe"] - 0.08) / 0.12), 0.8))
        why.append(f"Eigenkapitalrendite (ROE) {pct(m['roe'])}")
    elif m["roe"] is not None:
        why.append(f"ROE {pct(m['roe'])} (durch sehr kleines Eigenkapital verzerrt – nicht gewertet)")
    if m["roic"] is not None and not m["is_financial"]:
        parts.append((clamp((m["roic"] - 0.08) / 0.12), 1.0))
        why.append(f"Kapitalrendite (ROIC, approx.) {pct(m['roic'])}")
    if m["fcf_m"] is not None and not m["is_financial"]:
        fm = m["fcf_m"]
        if m.get("fcf_m_adj") is not None and (m.get("sbc_ratio") or 0) >= 0.02:
            fm = m["fcf_m_adj"]
            why.append(f"Free-Cashflow-Marge {pct(m['fcf_m'])}, nach Aktienvergütung ({pct(m['sbc_ratio'])} vom Umsatz) "
                       f"{pct(fm)}")
        else:
            why.append(f"Free-Cashflow-Marge {pct(fm)}")
        parts.append((clamp((fm - 0.03) / 0.12), 1.0))
    quality_extras(m, parts, why)
    if not m["is_financial"]:
        if m["nd_ebitda"] is not None:
            parts.append((clamp((2.0 - m["nd_ebitda"]) / 2.0), 1.0))
            why.append(f"Nettoverschuldung / EBITDA {fnum(m['nd_ebitda'], 2)}x"
                       + (" (Netto-Cash)" if m["nd_ebitda"] < 0 else ""))
        elif m["ebitda"] is not None and m["ebitda"] <= 0 and (m["net_debt"] or 0) > 0:
            parts.append((-1.0, 1.0))
            why.append("Negatives EBITDA bei Nettoverschuldung")
    if m["op_m_trend"] is not None:
        parts.append((clamp(m["op_m_trend"] / 0.05) * 0.6, 0.6))
        why.append(f"Margentrend über {len(m['revenues'])} Jahre: {'+' if m['op_m_trend'] >= 0 else ''}"
                   f"{fnum(m['op_m_trend'] * 100)} Prozentpunkte")
    return parts, why


def quality_adj(m, q):
    if m.get("biz") == "pre_revenue":
        return "defizitär"
    if m.get("biz") == "loss_growth":  # Verlustfirmen nie „marktführend/dominant“
        return "solide" if q >= 0.25 else "defizitär"
    rev_down = m["rev_cagr"] is not None and m["rev_cagr"] < -0.02
    margin_down = m["op_m_trend"] is not None and m["op_m_trend"] < -0.03
    mcap, om, roe = m["mcap"] or 0, m["op_m"] or 0, m["roe"] or 0
    if q >= 0.25 and m.get("biz") in ("bank", "insurance", "real_estate"):
        if mcap >= 100e9 and q >= 0.4:
            adj = "marktführend"
        elif m.get("biz") != "real_estate" and (m["equity_ratio"] or 0) >= 0.09:
            adj = "robust"
        else:
            adj = "profitabel"
    elif q >= 0.25:
        if mcap >= 300e9 and om >= 0.25 and roe >= 0.2:
            adj = "dominant"
        elif (m["gross_m"] or 0) >= 0.5 and (m["roic"] or 0) >= 0.15 and om >= 0.2 and not margin_down:
            adj = "wettbewerbsstark (mit „Burggraben“)"
        elif mcap >= 100e9 and q >= 0.4:
            adj = "marktführend"
        elif (m["fcf_m"] or 0) >= 0.18:
            adj = "cashflowstark"
        elif om >= 0.2:
            adj = "margenstark"
        elif m["nd_ebitda"] is not None and m["nd_ebitda"] < 1:
            adj = "robust"
        else:
            adj = "profitabel"
    elif q >= 0.1:
        adj = "solide"
    elif q >= 0:
        adj = "stabil" if not margin_down and m["loss_years"] == 0 else "profitabel" if (m["net_m"] or 0) > 0 else "solide"
    else:
        if rev_down and ((m["net_m"] or 0) < 0 or margin_down):
            adj = "strauchelnd"
        elif (m["net_m"] or 0) < 0:
            adj = "defizitär"
        elif (m["nd_ebitda"] or 0) > 3.5:
            adj = "verschuldet"
        elif margin_down:
            adj = "angeschlagen"
        else:
            adj = "schwach"
    return adj


def score_growth(m):
    why, vals = [], []
    if m["rev_cagr"] is not None:
        vals.append((clamp(m["rev_cagr"], -0.5, 0.6), 1.2))
        why.append(f"Umsatz-CAGR ({len([r for r in m['revenues'] if r]) - 1} J.) {pct(m['rev_cagr'])}")
    if m["rev_g"] is not None:
        vals.append((clamp(m["rev_g"], -0.5, 0.6), 1.0))
        why.append(f"Umsatzwachstum (letztes Quartal ggü. Vorjahr) {pct(m['rev_g'])}")
    if m["eps_g"] is not None:
        vals.append((clamp(m["eps_g"], -0.5, 0.6), 0.6))
        why.append(f"Gewinnwachstum (Quartal ggü. Vorjahr) {pct(m['eps_g'])}")
    frg, feg = est_growth(m, "est_rev"), est_growth(m, "est_eps")
    na_ = est_analysts(m)
    if frg is not None:
        vals.append((clamp(frg, -0.5, 0.6), 1.3))
        er = m["est_rev"]
        why.append("Umsatzprognose der Analysten: " + " · ".join(
            f"{'dieses' if p_ == '0y' else 'nächstes'} GJ {pct(er[p_]['growth'])}" for p_ in ("0y", "+1y")
            if er.get(p_, {}).get("growth") is not None) + (f" ({na_} Analysten)" if na_ else ""))
    if feg is not None:
        vals.append((clamp(feg, -0.5, 0.6), 0.7))
        why.append(f"Gewinnprognose (Gewinn je Aktie) Ø {pct(feg)} p. a. für dieses und nächstes Geschäftsjahr")
    elif m["fwd_eps_g"] is not None:
        vals.append((clamp(m["fwd_eps_g"], -0.5, 0.6), 0.8))
        why.append(f"Erwartetes EPS-Wachstum (Forward vs. Trailing) {pct(m['fwd_eps_g'])}")
    if m["rd_ratio"] is not None:
        why.append(f"F&E-Quote {pct(m['rd_ratio'])} vom Umsatz")
    gr = wavg(vals)
    if gr is None:
        return {"score": None, "adjective": "reif", "reasons": why + ["Keine Wachstumsdaten"]}
    s = clamp((gr - 0.04) / 0.12)
    # Adjektiv orientiert sich primär am Umsatz (Gewinnsprünge sind oft Basiseffekte)
    rev_vals = [x for x in (m["rev_cagr"], m["rev_g"], est_growth(m, "est_rev")) if x is not None]
    rg = sum(rev_vals) / len(rev_vals) if rev_vals else gr
    acq_heavy = (m["acquisitions"] or 0) > 0.2 * (m["ocf_sum"] or 1e30)
    if rg >= 0.08 and gr >= 0.05:
        if (m["mcap"] or 1e12) < 20e9 and rg >= 0.2:
            adj = "aufstrebend"
        elif rg >= 0.15:
            adj = "wachstumsstark"
        elif (m["rd_ratio"] or 0) >= 0.12:
            adj = "innovativ"
        elif acq_heavy or (m["capex_ratio"] or 0) >= 0.15:
            adj = "expansiv"
        else:
            adj = "dynamisch"
    elif rg >= 0.03:
        adj = "reif"
    elif rg >= 0.005:
        adj = "gesättigt"
    elif rg >= -0.02:
        adj = "stagnierend"
    else:
        adj = "rückläufig"
    if acq_heavy:
        why.append("Hohe Übernahmeaktivität (> 20 % des operativen Cashflows)")
    return {"score": s, "adjective": adj, "reasons": why}


def score_risk(m):
    parts, why = [], []
    if m["vol"] is not None:
        parts.append((clamp((0.30 - m["vol"]) / 0.15), 1.0))
        why.append(f"Volatilität (1 J., annualisiert) {pct(m['vol'])}")
    if m["beta"] is not None:
        parts.append((clamp((1.0 - m["beta"]) / 0.5), 0.8))
        why.append(f"Beta {fnum(m['beta'], 2)} (Marktschwankung = 1,0)")
    if m["max_dd"] is not None:
        parts.append((clamp((0.25 + m["max_dd"]) / 0.2), 0.6))
        why.append(f"Maximaler Rückgang im letzten Jahr {pct(m['max_dd'])}")
    biz = m.get("biz", "standard")
    if biz == "real_estate":
        if m["ltv"] is not None:
            parts.append((clamp((0.50 - m["ltv"]) / 0.15), 1.0))
            why.append(f"Beleihungsquote {pct(m['ltv'])} (über 55 % riskant)")
        elif m["nd_ebitda"] is not None:
            parts.append((clamp((8.0 - m["nd_ebitda"]) / 4.0), 0.8))
    elif m["nd_ebitda"] is not None and not m["is_financial"]:
        parts.append((clamp((2.5 - m["nd_ebitda"]) / 2.5), 0.8))
    if biz not in ("bank", "insurance", "real_estate"):
        z = m.get("altman_z")
        if z is not None:
            parts.append((-1.0 if z < 1.8 else clamp((z - 2.4) / 1.2) if z < 3 else 0.5, 0.9))
            why.append(f"Altman Z-Score {fnum(z, 1)} (" + ("Warnzone: erhöhtes Insolvenzrisiko" if z < 1.8 else
                       "Grauzone" if z < 3 else "sicher") + ")")
        cov = m.get("int_cov")
        if cov is not None and (m["debt"] or 0) > 0:
            parts.append((clamp((cov - 4) / 4), 0.7))
            why.append(f"Zinsdeckung: operativer Gewinn = {fnum(cov, 1)}-fache Zinskosten (unter 2 kritisch, über 8 komfortabel)")
    if biz == "bank" and m["equity_ratio"] is not None:
        parts.append((clamp((m["equity_ratio"] - 0.05) / 0.03), 0.6))
        why.append(f"Eigenkapitalquote {pct(m['equity_ratio'])} (Puffer gegen Kreditausfälle)")
    if biz in ("loss_growth", "pre_revenue") and m["runway"] is not None:
        parts.append((clamp((m["runway"] - 1.5) / 1.5), 1.0))
        why.append(f"Cash-Reichweite ≈ {fnum(m['runway'], 1)} Jahre – darunter drohen Kapitalerhöhungen/Verwässerung")
    if m["loss_years"]:
        parts.append((-0.6, 0.6))
        why.append(f"{m['loss_years']} Verlustjahr(e) in der Historie")
    sec = m["sector"]
    if sec in DEFENSIVE:
        parts.append((0.5, 0.5))
        why.append(f"Defensive Branche ({sec})")
    elif sec in CYCLICAL:
        parts.append((-0.3, 0.5))
        why.append(f"Zyklische Branche ({sec})")
    r = wavg(parts)
    if r is None:
        return {"score": None, "adjective": "berechenbar", "reasons": why}
    vol, beta = m["vol"] or 0.3, m["beta"] or 1.0
    lev = m["nd_ebitda"] or 0
    if biz == "real_estate":  # hohe Verschuldung ist bei Immobilien normal -> an der Beleihungsquote messen
        lev = 4 if (m["ltv"] or 0) > 0.55 else 0
    if r >= 0.2:
        if sec in DEFENSIVE and lev < 2:
            adj = "krisenfest" if r >= 0.5 else "defensiv"
        elif vol < 0.2:
            adj = "schwankungsarm"
        elif beta < 0.8 and lev < 1:
            adj = "konservativ"
        else:
            adj = "berechenbar"
    elif r >= -0.2:
        if sec in CYCLICAL:
            adj = "konjunkturabhängig" if beta > 1.1 else "zyklisch"
        else:
            adj = "berechenbar" if r >= 0 else "volatil"
    else:
        if (m["net_m"] or 0) < 0 and vol > 0.45:
            adj = "spekulativ"
        elif lev > 3:
            adj = "riskant"
        elif sec in CYCLICAL and beta > 1.2:
            adj = "konjunkturabhängig"
        elif vol > 0.35:
            adj = "volatil"
        else:
            adj = "riskant"
    return {"score": r, "adjective": adj, "reasons": why}


def score_dividend(m):
    y, p = m["div_yield"], m["payout"]
    why = [f"Dividendenrendite (12 Monate) {pct(y, 2)}",
           f"Ausschüttungsquote {pct(p)}" + (f" vom FFO (vom Gewinn: {pct(m['payout_eps'])})" if m.get("payout_eps") is not None else "")]
    if m["div_years"]:
        why.append(f"Dividende in {m['div_streak']} Jahren in Folge stabil/steigend"
                   + (" – Kürzung in den letzten 5 Jahren" if m["div_cut"] else ""))
    if m["shareholder_yield"] is not None:
        why.append(f"Aktionärsrendite inkl. Rückkäufe (letztes GJ) {pct(m['shareholder_yield'])}")
    y = y or 0
    sy = m["shareholder_yield"] or 0
    if y > 0 and m["div_cut"]:
        return {"score": -0.5, "adjective": "unzuverlässig (bei Kürzungen)", "reasons": why}
    if y >= 0.04:
        ok = p is None or p <= 0.9
        return {"score": 0.8 if ok else 0.1, "adjective": "dividendenstark" if ok else "ausschüttungsfreudig",
                "reasons": why + ([] if ok else ["Ausschüttungsquote > 90 % – Dividende ggf. nicht nachhaltig"])}
    if sy >= 0.05:
        return {"score": 0.7, "adjective": "renditestark", "reasons": why}
    if p is not None and p >= 0.6 and y >= 0.025:
        return {"score": 0.4, "adjective": "ausschüttungsfreudig", "reasons": why}
    if y >= 0.015 and m["div_streak"] >= 5:
        return {"score": 0.5, "adjective": "verlässlich", "reasons": why}
    if y >= 0.015:
        return {"score": 0.2, "adjective": "verlässlich", "reasons": why}
    if sy >= 0.03:
        return {"score": 0.3, "adjective": "dividendenschwach",
                "reasons": why + ["Geringe Dividende, aber Kapitalrückgabe über Aktienrückkäufe"]}
    return {"score": -0.1, "adjective": "dividendenschwach", "reasons": why}


def score_chart(m):
    if m["last"] is None:
        return {"score": None, "adjective": "seitwärts tendierend", "reasons": ["Keine Kursdaten"]}
    p, s50, s200, rsi = m["last"], m["sma50"], m["sma200"] or m["sma50"], m["rsi"] or 50
    why = [f"Kurs {fnum(p, 2)} | GD50 {fnum(s50, 2)} | GD200 {fnum(s200, 2)}", f"RSI(14) {fnum(rsi)}",
           f"Performance: 1M {pct(m['perf_1m'])} · 3M {pct(m['perf_3m'])} · 6M {pct(m['perf_6m'])} · 1J {pct(m['perf_1y'])}",
           f"52-Wochen-Spanne {fnum(m['lo52'], 2)} – {fnum(m['hi52'], 2)}"]
    p3, p6, p1 = m["perf_3m"] or 0, m["perf_6m"] or 0, m["perf_1m"] or 0
    near_high = m["hi52"] and p >= m["hi52"] * 0.97
    was_below = m["price_3m_ago"] and m["sma200_3m"] and m["price_3m_ago"] < m["sma200_3m"]
    if rsi > 72:
        adj, s = "überkauft", 0.1
    elif rsi < 28:
        adj, s = "überverkauft", -0.1
    elif near_high and p > s200 and p1 > 0 and not (p > s50 > s200 and p3 > 0.1):
        adj, s = "ausbruchsverdächtig", 0.6
    elif p > s50 > s200 and p3 > 0.1:
        adj, s = "bullish", 0.8
    elif p > s200 and was_below and m["lo52"] and p > m["lo52"] * 1.2:
        adj, s = "erholt", 0.3
    elif p > s200 and s50 >= s200:
        adj, s = "aufwärtsgerichtet", 0.5
    elif p < s50 < s200 and p3 < -0.1:
        adj, s = "bearish", -0.8
    elif abs(p6) < 0.07 and abs(p / s200 - 1) < 0.05:
        adj, s = "seitwärts tendierend", 0.0
    elif p < s200 and s50 < s200:
        adj, s = "abwärtsgerichtet", -0.5
    elif p < s200:
        adj, s = "angeschlagen", -0.3
    else:
        adj, s = "seitwärts tendierend", 0.0
    return {"score": s, "adjective": adj, "reasons": why}


def score_sentiment(m, news, val_score):
    why, parts = [], []
    rm, na = m["rec_mean"], m["n_analysts"]
    if rm and na:
        parts.append((clamp((3.0 - rm) / 1.5), 1.2))
        why.append(f"Analystenkonsens {fnum(rm, 2)} (1 = Strong Buy … 5 = Strong Sell) von {int(na)} Analysten")
    if m["rec_dist"]:
        d = m["rec_dist"]
        why.append(f"Verteilung: {d['strongBuy']} Strong Buy · {d['buy']} Buy · {d['hold']} Hold · "
                   f"{d['sell']} Sell · {d['strongSell']} Strong Sell")
    ns = news["sentiment"]
    if ns is not None and news["count"]:
        parts.append((clamp(ns * 2.5), 1.0))
        why.append(f"News-Tonalität (30 Tage, tier-gewichtet) {'+' if ns >= 0 else ''}{fnum(ns, 2)} "
                   f"aus {news['count']} Meldungen ({news['pos']} positiv / {news['neg']} negativ)")
    if m.get("eps_rev") is not None:
        parts.append((clamp(m["eps_rev"] / 0.05), 1.0))
        why.append(f"Gewinnrevisionen 90 Tage: Schätzungen für dieses/nächstes Jahr {'+' if m['eps_rev'] >= 0 else ''}"
                   f"{fnum(m['eps_rev'] * 100, 1)} % " + ("(Analysten heben an)" if m["eps_rev"] > 0.01 else
                                                       "(Analysten senken)" if m["eps_rev"] < -0.01 else "(stabil)"))
    if m.get("rev_breadth"):
        up, dn = m["rev_breadth"]
        if up + dn >= 2:
            parts.append((clamp((up - dn) / (up + dn)), 0.5))
        why.append(f"Letzte 30 Tage: {up} Anhebungen, {dn} Senkungen der Gewinnschätzungen")
    if m.get("surprises"):
        sp = m["surprises"]
        beats, avg = sum(1 for x in sp if x > 0), sum(sp) / len(sp)
        parts.append((0.5 * clamp((beats - len(sp) / 2) / (len(sp) / 2)) + 0.5 * clamp(avg / 0.05), 0.7))
        why.append(f"Gewinnüberraschungen: {beats} von {len(sp)} Quartalen über den Erwartungen, Ø {'+' if avg >= 0 else ''}"
                   f"{fnum(avg * 100, 1)} %")
    ins = m.get("insider")
    if ins:
        mcap = m["mcap"] or 0
        if ins["buyers"] >= 2 or (ins["buys"] >= 1e6 and ins["buyers"] >= 1):
            parts.append((clamp(0.4 + 0.2 * min(ins["buyers"], 3)), 0.7))
            why.append(f"Insiderkäufe (6 Monate): {ins['buyers']} Insider kauften für {money(ins['buys'], ins['cur'])} "
                       "eigene Aktien – starkes Vertrauenssignal")
        elif mcap and ins["sells"] / mcap > 0.005:
            parts.append((-0.4, 0.5))
            why.append(f"Insiderverkäufe (6 Monate) {money(ins['sells'], ins['cur'])} = {pct(ins['sells'] / mcap, 2)} "
                       "des Börsenwerts – auffällig hoch")
        else:
            why.append("Insidergeschäfte (6 Monate): " + (f"Verkäufe {money(ins['sells'], ins['cur'])}, keine nennenswerten "
                       "Käufe – Verkäufe sind oft planmäßig und wenig aussagekräftig" if ins["sells"] else
                       "keine nennenswerten Käufe oder Verkäufe"))
    if m["short_float"] is not None:
        why.append(f"Leerverkaufsquote {pct(m['short_float'])} des Streubesitzes")
        if m["short_float"] > 0.1:
            parts.append((-0.6, 0.5))
    s = wavg(parts)
    if s is None:
        s = 0.0
    cnt = news["count"]
    split = news["pos"] >= 3 and news["neg"] >= 3 and min(news["pos"], news["neg"]) / max(news["pos"], news["neg"]) > 0.6
    dist = m["rec_dist"] or {}
    tot = sum(dist.values()) or 1
    rating_split = dist and (dist.get("sell", 0) + dist.get("strongSell", 0)) / tot > 0.15 and \
        (dist.get("buy", 0) + dist.get("strongBuy", 0)) / tot > 0.4
    if not rm:  # keine Analystendaten verfügbar -> nur News-basiert
        n = ns or 0
        if cnt < 8:
            adj = "übersehen" if (val_score or 0) > 0.15 else "vernachlässigt"
        elif split:
            adj = "umstritten"
        elif n >= 0.08 and cnt >= 15:
            adj = "gefragt"
        elif n >= 0.03:
            adj = "beliebt"
        elif n <= -0.08:
            adj = "unbeliebt"
        else:
            adj = "umstritten"
    elif cnt >= 25 and (rm or 3) <= 1.9 and (val_score or 0) < -0.3:
        adj = "gehypt"
    elif na < 5 and cnt < 8:
        adj = "übersehen" if (val_score or 0) > 0.15 else "vernachlässigt"
    elif split or rating_split:
        adj = "umstritten"
    elif (rm or 3) <= 2.0 and (ns or 0) >= 0.05:
        adj = "gefragt"
    elif (rm or 3) <= 2.3 and s >= 0.15:
        adj = "beliebt"
    elif (rm or 3) >= 3.0 or (ns or 0) < -0.15 or s < -0.2:
        adj = "unbeliebt"
    elif (val_score or 0) > 0.25 and s < 0.2:
        adj = "übersehen"
    else:
        adj = "umstritten" if abs(s) < 0.15 else ("beliebt" if s > 0 else "unbeliebt")
    return {"score": s, "adjective": adj, "reasons": why}


def score_macro(m, mac):
    why, parts = [], []
    growthy = (m["pe"] or 0) > 30 or (m["rev_cagr"] or 0) > 0.15 or (m["net_m"] or 0) < 0
    rate_sens = (growthy and not m["is_financial"]) or m["sector"] in RATE_SENSITIVE
    if mac["rf"] is not None:
        why.append(f"US-10J-Rendite {fnum(mac['rf'], 2)} % ({'+' if (mac['rf_chg'] or 0) >= 0 else ''}"
                   f"{fnum(mac['rf_chg'], 2)} Pp. in 6 Monaten)")
        if rate_sens:
            s = -0.4 if mac["rf"] >= 4 else 0.0 if mac["rf"] >= 3 else 0.3
            if mac["rf_chg"] is not None:
                s += -0.3 if mac["rf_chg"] > 0.3 else 0.3 if mac["rf_chg"] < -0.3 else 0
            parts.append((clamp(s), 1.0))
            why.append("Zinssensitiv (Wachstumswert / zinsabhängige Branche) – hohe Zinsen belasten die Bewertung")
        else:
            parts.append((0.1, 0.5))
            why.append("Geringe Zinssensitivität")
    if m["is_financial"] and mac["rf"]:
        why.append("Banken/Versicherer profitieren tendenziell von höheren Zinsen")
        parts.append((0.3 if mac["rf"] >= 3.5 else 0, 0.5))
    if mac["fx_pair"]:
        if mac["fx_chg"] is not None:
            parts.append((clamp(mac["fx_chg"] / 0.1) * 0.6, 1.0))
            why.append(f"Währungsrisiko: {m['currency']} hat ggü. Euro in 12 Monaten "
                       f"{'aufgewertet' if mac['fx_chg'] >= 0 else 'abgewertet'} ({pct(mac['fx_chg'])}) – "
                       f"wirkt 1:1 auf die Euro-Rendite")
        else:
            why.append(f"Notiz in {m['currency']} – Wechselkursrisiko für Euro-Anleger")
    else:
        why.append("Notiz in Euro – kein direktes Währungsrisiko")
    if m["sector"] in CYCLICAL:
        why.append("Konjunkturabhängige Branche – Ergebnis schwankt mit dem Wirtschaftszyklus")
    s = wavg(parts)
    return {"score": s if s is not None else 0.0, "adjective": None, "reasons": why}


def map_rating(total):
    for thr, label, grp in RATING_SCALE:
        if total >= thr:
            return label, grp
    return "Strong Sell", "Verkaufen"


def summary_adj(total, cats):
    risk = cats["risk"]["score"] or 0
    val = cats["valuation"]["score"] or 0
    gro = cats["growth"]["score"] or 0
    if total >= 45:
        return "kaufenswert"
    if total >= 30:
        return "empfehlenswert"
    if total >= 15:
        return "aussichtsreich" if risk >= 0 else "chancenreich"
    if total >= 5:
        return "chancenreich" if (val > 0.25 or gro > 0.4) else "neutral"
    if total >= -5:
        return "neutral"
    if total >= -15:
        return "abwartend"
    if total >= -35:
        return "unattraktiv"
    return "meidenswert"


def build_fundamentals(m, mac):
    c = m["currency"]
    cy = m["cf_years"] or "?"
    rows_ = lambda *r: list(r)
    biz = m.get("biz", "standard")
    special = []
    if biz in ("bank", "insurance"):
        special = [["Kurs-Buchwert (KBV)", fnum(m["pb"], 2), "zentral für Banken/Versicherer"],
                   ["Eigenkapitalrendite (ROE)", pct(m["roe"]), "über ~10 % verdient die Kapitalkosten"],
                   ["Eigenkapitalquote", pct(m["equity_ratio"]), "Bilanz-Eigenkapital / Bilanzsumme"],
                   ["Bilanzsumme", money(m["assets"], c), ""]]
    elif biz == "real_estate":
        special = [["Kurs/FFO (Näherung)", fnum(m["p_ffo"]), "FFO ≈ operativer Cashflow; ~15 neutral"],
                   ["Kurs-Buchwert (≈ NAV)", fnum(m["pb"], 2), "unter 1 = Abschlag auf den Buchwert der Immobilien"],
                   ["Beleihungsquote (LTV)", pct(m["ltv"]), "Nettoschulden / Bilanzsumme; unter 45 % solide"],
                   ["Ausschüttung / FFO", pct(m["payout"]), f"bezogen auf den Gewinn: {pct(m.get('payout_eps'))}"]]
    elif biz in ("loss_growth", "pre_revenue"):
        g = growth_estimate(m)
        special = [["EV/Umsatz", fnum(m["ev_sales"], 1), ""],
                   ["„Rule of 40“", pct(g + m["fcf_m"]) if g is not None and m["fcf_m"] is not None else "–",
                    "Wachstum + FCF-Marge; ≥ 40 % stark"],
                   ["Cash-Reichweite", "–" if m["runway"] is None else fnum(m["runway"], 1) + " Jahre",
                    "Kasse / jährlicher Mittelabfluss"],
                   ["Kasse", money(m["cash"], c), ""]]
    elif biz == "cyclical":
        hist = [x for x in m["op_m_hist"] if x is not None]
        special = [["KGV normalisiert", fnum(m["norm_pe"]), "Börsenwert / Ø-Gewinn der Geschäftsjahre"],
                   ["Operative Marge aktuell / Ø", f"{pct(m['op_m'])} / {pct(sum(hist) / len(hist)) if hist else '–'}",
                    "weit über Ø = nahe Zyklushoch"]]
    head = [{"title": f"Branchenspezifisch: {BIZ_MODELS[biz][0]}", "rows": special}] if special else []
    return head + [
        {"title": "Geschäftsmodell & Wettbewerbsvorteil", "rows": rows_(
            ["Branche", f"{m['sector']} / {m['industry']}", ""],
            ["Marktkapitalisierung", money(m["mcap"], c), ""],
            ["Bruttomarge", pct(m["gross_m"]), "> 50 % deutet auf Preissetzungsmacht hin"],
            ["ROIC (approx.)", pct(m["roic"]), "> 15 % dauerhaft = Burggraben-Indiz"],
        )},
        {"title": "Wachstum, Margen & Free Cashflow", "rows": rows_(
            ["Umsatz (TTM)", money(m["revenue"], c), ""],
            ["Umsatz-CAGR (Geschäftsjahre)", pct(m["rev_cagr"]), ""],
            ["Operative Marge / Nettomarge", f"{pct(m['op_m'])} / {pct(m['net_m'])}", ""],
            ["Free Cashflow (TTM)", money(m["fcf"], c), f"FCF-Marge {pct(m['fcf_m'])}"],
        )},
        {"title": "Verschuldung & Kapitalrendite", "rows": rows_(
            ["Gesamtschulden / Cash", f"{money(m['debt'], c)} / {money(m['cash'], c)}", ""],
            ["Nettoverschuldung / EBITDA", "–" if m["nd_ebitda"] is None else fnum(m["nd_ebitda"], 2) + "x",
             "< 2x solide, > 3,5x hoch"],
            ["Eigenkapitalrendite (ROE)", pct(m["roe"]), ""],
            ["Gesamtkapitalrendite (ROA)", pct(m["roa"]), ""],
        )},
        {"title": "Management & Kapitalallokation – was passiert mit dem Gewinn?", "rows": rows_(
            [f"Dividenden gezahlt ({cy} GJ)", money(m["div_paid"], c), ""],
            [f"Aktienrückkäufe ({cy} GJ)", money(m["buybacks"], c), ""],
            [f"Übernahmen ({cy} GJ)", money(m["acquisitions"], c), ""],
            [f"Operativer Cashflow ({cy} GJ)", money(m["ocf_sum"], c), ""],
            ["Veränderung Aktienanzahl", pct(m["share_change"]),
             "negativ = Rückkäufe reduzieren Aktien, positiv = Verwässerung"],
        )},
        {"title": "Bilanzqualität & Erwartungen", "rows": [r for r in (
            ["Piotroski F-Score", "–" if m.get("piotroski") is None else f"{fnum(m['piotroski'], 0)} / 9",
             "≥ 7 stark, ≤ 3 schwach – Richtung der Fundamentaldaten"] if biz not in ("bank", "insurance") else None,
            ["Altman Z-Score", fnum(m.get("altman_z"), 1), "< 1,8 Insolvenzgefahr, > 3 sicher"]
            if biz not in ("bank", "insurance", "real_estate") else None,
            ["Zinsdeckung", "–" if m.get("int_cov") is None else fnum(m["int_cov"], 1) + "x",
             "operativer Gewinn / Zinskosten"] if not m["is_financial"] else None,
            ["Aktienvergütung", pct(m.get("sbc_ratio")), "vom Umsatz; FCF nach Abzug: " + money(m.get("fcf_adj"), c)]
            if m.get("sbc") else None,
            ["Gewinnrevisionen 90 Tage", "–" if m.get("eps_rev") is None else
             f"{'+' if m['eps_rev'] >= 0 else ''}{fnum(m['eps_rev'] * 100, 1)} %", "Änderung der Gewinnschätzungen"],
            ["Gewinnüberraschungen", "–" if not m.get("surprises") else
             f"{sum(1 for x in m['surprises'] if x > 0)} von {len(m['surprises'])} übertroffen", "letzte Quartale"],
            ["Insider (6 Monate)", "–" if not m.get("insider") else
             f"Käufe {money(m['insider']['buys'], m['insider']['cur'])} · Verkäufe {money(m['insider']['sells'], m['insider']['cur'])}",
             (m.get("insider") or {}).get("src", "")],
        ) if r]},
        {"title": "Bewertung – historisch & im Branchenvergleich", "rows": rows_(
            ["KGV (trailing / forward)", f"{fnum(m['pe'])} / {fnum(m['fpe'])}",
             f"Branche ~{SECTOR_REF.get(m['sector'], (20, 13))[0]}"],
            ["KGV historisch (Median)", fnum(m["pe_hist_med"]),
             ", ".join(fnum(x) for x in m["pe_hist"]) if m["pe_hist"] else ""],
            ["EV/EBITDA", fnum(m["ev_ebitda"]), f"Branche ~{SECTOR_REF.get(m['sector'], (20, 13))[1]}"],
            ["FCF-Rendite", pct(m["fcf_yield"]), ""],
            ["KBV / KUV / PEG", f"{fnum(m['pb'], 2)} / {fnum(m['ps'], 2)} / {fnum(m['peg'], 2)}", ""],
        )},
        {"title": "Prognosen & fairer Wert", "rows": [r for r in (
            ["Umsatzprognose dieses / nächstes GJ",
             " / ".join(pct(((m.get("est_rev") or {}).get(p_) or {}).get("growth")) for p_ in ("0y", "+1y")),
             f"{est_analysts(m)} Analysten" if est_analysts(m) else "Analystenschätzungen"],
            ["Gewinnprognose (EPS) dieses / nächstes GJ",
             " / ".join(pct(((m.get("est_eps") or {}).get(p_) or {}).get("growth")) for p_ in ("0y", "+1y")), "Wachstum ggü. Vorjahr"],
            ["Forward-KGV", fnum(m.get("fpe")), "Kurs / erwarteter Gewinn"],
            ["Fairer Wert (vorsichtig / Basis / optimistisch)",
             " / ".join(fnum((m.get("fair") or {}).get(k_), 2) for k_ in ("bear", "base", "bull")) if (m.get("fair") or {}).get("base") else "–",
             (m.get("fair") or {}).get("method") or (m.get("fair") or {}).get("na", "")[:60]],
        ) if r]},
        {"title": "Eingepreiste Erwartungen (Reverse-DCF)", "rows": rows_(
            ["Im Kurs eingepreistes FCF-Wachstum p.a.", pct(m.get("implied_g")),
             f"10 Jahre, danach 2,5 %, Diskontsatz {pct(m.get('disc_rate'))}"],
            ["Realistisch erwartbares Wachstum", pct(m.get("expected_g")), "Median aus Historie & Prognosen"],
            ["Analysten-Kursziel (Ø)", "–" if m["target"] is None else f"{fnum(m['target'], 2)} {c}",
             f"Potenzial {pct(m['upside'])}" + (f" · {m['target_src']}" if m.get("target_src") else "")],
        )},
        {"title": "Makro: Zinsen, Währung, Konjunktur", "rows": rows_(
            ["US-10J-Rendite", "–" if mac["rf"] is None else fnum(mac["rf"], 2) + " %",
             "hohe Zinsen belasten vor allem Wachstumswerte"],
            ["Währung", m["currency"] or "–",
             (f"{mac['fx_pair']}: Fremdwährung 12M {pct(mac['fx_chg'])} ggü. EUR" if mac["fx_pair"] else "Euro")],
            ["Beta", fnum(m["beta"], 2), "Konjunktur-/Marktabhängigkeit"],
        )},
    ]


# ---------------------------------------------------------------------------
# Kursziele aus Analysten-Schlagzeilen (z. B. dpa-AFX: "Jefferies hebt Ziel für SAP auf 300 Euro")
# ---------------------------------------------------------------------------
TARGET_CUR = {"euro": "EUR", "eur": "EUR", "€": "EUR", "us-dollar": "USD", "dollar": "USD", "usd": "USD",
              "franken": "CHF", "chf": "CHF", "pence": "GBp", "pfund": "GBP"}
DE_AMOUNT = re.compile(r"(\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:,\d{1,2})?)\s*(us-dollar|dollar|usd|euro|eur|€|franken|chf|pence|pfund)(?![a-zäöü])", re.I)
EN_AMOUNT = re.compile(r"(?:\$|US\$|USD\s?)\s?(\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)", re.I)
DE_FIRM = re.compile(r"^(?:[^:]{0,40}:\s*)?([A-Z][\w&.\-' ]{1,40}?)\s+(?:hebt|senkt|erhöht|belässt|bestätigt|startet|nimmt|"
                     r"stuft|reduziert|kappt|sieht|setzt|bewertet)\b")
EN_FIRM = [re.compile(r"\bby ([A-Z][\w&.\-' ]{1,30}?)(?:[,;:]|\s+(?:on|amid|after|as|despite|ahead)\b|$)"),
           re.compile(r"\bfrom ([A-Z][A-Za-z&.\-' ]{1,30}?)(?:[,;:]|\s+(?:on|amid|after|as|despite|ahead)\b|$)"),
           re.compile(r"^([A-Z][\w&.\-' ]{1,30}?)\s+(?:raises|lifts|cuts|lowers|boosts|trims|sets|adjusts|maintains|"
                      r"reiterates|hikes|ups|reduces|initiates|starts|keeps)\b", re.I)]


def _de_number(txt):
    return float(txt.replace(".", "").replace(",", "."))


def parse_target(title, lang):
    """(Analysehaus|None, Wert, Währung) aus einer Kursziel-Schlagzeile – oder None."""
    tl = title.lower()
    if re.search(r"\b(unser|unsere|our|we're|we are)\b", tl):  # eigene Ziele von Medien/Bloggern
        return None
    if lang == "de":
        if "ziel" not in tl:
            return None
        hits = list(DE_AMOUNT.finditer(title))
        if not hits:
            return None
        pick = next((h for h in hits if title[max(0, h.start() - 4):h.start()].lower().strip().endswith("auf")), hits[-1])
        value, cur = _de_number(pick.group(1)), TARGET_CUR[pick.group(2).lower()]
        fm = DE_FIRM.search(title)
    else:
        if "target" not in tl:
            return None
        hits = list(EN_AMOUNT.finditer(title))
        if not hits:
            return None
        pick = next((h for h in hits if title[max(0, h.start() - 4):h.start()].lower().strip().endswith("to")), hits[0])
        value, cur = float(pick.group(1).replace(",", "")), "USD"
        fm = next((r.search(title) for r in EN_FIRM if r.search(title)), None)
    firm = fm.group(1).strip() if fm else None
    if firm and (re.search(r"\d", firm) or re.search(r"(ziel|target|aktie|stock|shares|kurs)", firm.lower())):
        firm = None
    return firm, value, cur


def firm_key(firm):
    k = re.sub(r"[^a-z0-9]", "", firm.lower())
    for suffix in ("capitalmarkets", "capital", "securities", "research", "global", "co", "inc"):
        if k.endswith(suffix) and len(k) > len(suffix) + 2:
            k = k[: -len(suffix)]
    return {"bofa": "bankofamerica", "bankofamericasecurities": "bankofamerica", "jpm": "jpmorgan",
            "gs": "goldmansachs", "ms": "morganstanley"}.get(k, k)


def news_targets(company, currency, price, siblings=(), days=90):
    """Median der Analysten-Kursziele aus Schlagzeilen (nur Börsenwährung, je Analysehaus die neueste Meldung)."""
    out = {"median": None, "n": 0, "items": []}
    if not price:
        return out
    want = {"GBp": "GBp", "GBX": "GBp"}.get(currency, currency)
    jobs = {"de": lambda: google_news(f'"{company}" Kursziel', "de", days),
            "en": lambda: google_news(f'"{company}" "price target"', "en", days)}
    found = {}
    tokens = [w for w in re.findall(r"[a-zäöüß0-9]{3,}", company.lower())][:1] or [company.lower()]
    with ThreadPoolExecutor(max_workers=2) as ex:
        futs = {lang: ex.submit(fn) for lang, fn in jobs.items()}
        for lang, f in futs.items():
            for it in safe(lambda: f.result(timeout=20), []) or []:
                if not any(t in it["title"].lower() for t in tokens) or mentions_sibling(it["title"], siblings):
                    continue
                if re.search(r"dividend", it["title"].lower()):
                    continue
                parsed = parse_target(it["title"], lang)
                if not parsed:
                    continue
                firm, value, cur = parsed
                if cur == "GBP" and want == "GBp":
                    value, cur = value * 100, "GBp"
                if cur != want or not (0.5 * price <= value <= 2.5 * price):
                    continue
                key = firm_key(firm) if firm else f"#{value:g}"
                prev = found.get(key)
                if prev is None or (it["date"] and (prev["dt"] is None or it["date"] > prev["dt"])):
                    found[key] = {"firm": firm, "value": value, "dt": it["date"], "source": it["source"]}
    named = {k: v for k, v in found.items() if not k.startswith("#")}
    if len(named) >= 3:  # Meldungen ohne erkennbares Analysehaus sind oft Wiederholungen
        found = named
    vals = sorted(v["value"] for v in found.values())
    if vals:
        mid = len(vals) // 2
        out["median"] = vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2
        out["n"] = len(vals)
        out["items"] = sorted(({"firm": v["firm"] or "k. A.", "value": v["value"],
                                "date": v["dt"].strftime("%d.%m.") if v["dt"] else ""} for v in found.values()),
                              key=lambda x: -x["value"])
    return out


# ---------------------------------------------------------------------------
# Zweite Datenquelle: Finnhub (optional, Umgebungsvariable FINNHUB_API_KEY)
# ---------------------------------------------------------------------------
FINNHUB_CACHE = {}


def finnhub_key():
    return (os.environ.get("FINNHUB_API_KEY") or "").strip()


def finnhub(path, **params):
    """GET auf die Finnhub-API. Liefert JSON oder None (kein Schlüssel, kein Zugriff, Limit erreicht)."""
    key = finnhub_key()
    if not key:
        return None
    url = f"https://finnhub.io/api/v1/{path}?" + urllib.parse.urlencode(params)
    hit = FINNHUB_CACHE.get(url)
    if hit and time.time() - hit[0] < 3600:
        return hit[1]
    req = urllib.request.Request(url, headers={**UA, "X-Finnhub-Token": key})  # Schlüssel im Header, nicht in der URL
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
    except Exception:
        return None
    if isinstance(data, dict) and data.get("error"):
        return None
    FINNHUB_CACHE[url] = (time.time(), data)
    return data


def finnhub_enrich(m, symbol, alternatives):
    """Füllt fehlende Analysten- und Kennzahlen aus Finnhub. Vorhandene Yahoo-Werte bleiben unverändert.

    Der kostenlose Finnhub-Tarif deckt v. a. US-Börsen ab; für ausländische Titel wird daher
    zusätzlich eine US-Notierung (ADR) desselben Unternehmens aus den Suchtreffern probiert."""
    m["finnhub"] = []
    if not finnhub_key():
        return
    candidates = [symbol] + [a["symbol"] for a in alternatives if "." not in a["symbol"]][:2]
    for sym in dict.fromkeys(candidates):
        rec = finnhub("stock/recommendation", symbol=sym)
        if not (isinstance(rec, list) and rec):
            continue
        r0 = rec[0]
        dist = {k: int(r0.get(k) or 0) for k in ("strongBuy", "buy", "hold", "sell", "strongSell")}
        total = sum(dist.values())
        if not total:
            continue
        if not m.get("rec_mean"):
            m["rec_mean"] = (dist["strongBuy"] + 2 * dist["buy"] + 3 * dist["hold"]
                             + 4 * dist["sell"] + 5 * dist["strongSell"]) / total
            m["n_analysts"] = total
            m["rec_dist"] = dist
            m["finnhub"].append(f"Analystenempfehlungen ({sym}, {r0.get('period', '')})")
        # Kursziel: Potenzial in der Währung der gefundenen Notierung berechnen, dann auf unseren Kurs übertragen
        if m.get("upside") is None:
            pt = finnhub("stock/price-target", symbol=sym)
            q = finnhub("quote", symbol=sym)
            tgt = num((pt or {}).get("targetMean"))
            px = num((q or {}).get("c"))
            if tgt and px and m.get("price"):
                m["upside"] = tgt / px - 1
                m["target"] = m["price"] * (1 + m["upside"])
                m["finnhub"].append(f"Kursziel ({sym})")
        # Kennzahlen (Quoten sind währungsneutral, daher auch von einer ADR übertragbar)
        met = (finnhub("stock/metric", symbol=sym, metric="all") or {}).get("metric") or {}
        filled = []
        for key, src, scale in (("pe", "peTTM", 1), ("beta", "beta", 1), ("roe", "roeTTM", 100),
                                ("op_m", "operatingMarginTTM", 100), ("gross_m", "grossMarginTTM", 100),
                                ("net_m", "netProfitMarginTTM", 100), ("rev_g", "revenueGrowthTTMYoy", 100),
                                ("eps_g", "epsGrowthTTMYoy", 100)):
            v = num(met.get(src))
            if m.get(key) is None and v is not None:
                m[key] = v / scale
                filled.append(key)
        if filled:
            m["finnhub"].append("Kennzahlen")
        break
    for sym in dict.fromkeys(candidates):  # Gewinnüberraschungen / Insider, falls Yahoo sie nicht liefert
        if m.get("surprises") is None:
            ea = finnhub("stock/earnings", symbol=sym)
            if isinstance(ea, list) and ea:
                vals = [num(x.get("surprisePercent")) for x in ea[:4]]
                vals = [v / 100 for v in vals if v is not None][::-1]
                if vals:
                    m["surprises"] = vals
                    if not m.get("eps_quarters"):
                        m["eps_quarters"] = [{"q": str(x.get("period") or "")[:10], "est": num(x.get("estimate")),
                                              "act": num(x.get("actual"))} for x in ea[:8]][::-1]
                    m["finnhub"].append(f"Gewinnüberraschungen ({sym})")
        if m.get("insider") is None:
            frm = (datetime.now() - timedelta(days=183)).strftime("%Y-%m-%d")
            data = (finnhub("stock/insider-transactions", symbol=sym, **{"from": frm}) or {}).get("data")
            if isinstance(data, list) and data:
                buys = sells = 0.0
                buyers = set()
                for x in data:
                    val = abs(num(x.get("change")) or 0) * (num(x.get("transactionPrice")) or 0)
                    if x.get("transactionCode") == "P":
                        buys += val
                        buyers.add(x.get("name"))
                    elif x.get("transactionCode") == "S":
                        sells += val
                m["insider"] = {"buys": buys, "sells": sells, "buyers": len(buyers), "src": f"Finnhub ({sym})",
                                "cur": "USD" if "." not in sym else m["currency"]}
                m["finnhub"].append(f"Insidergeschäfte ({sym})")
        if m.get("surprises") is not None and m.get("insider") is not None:
            break


# ---------------------------------------------------------------------------
# Konkurrenzvergleich: 3–5 Wettbewerber derselben Branche
# ---------------------------------------------------------------------------
PEER_CACHE = {}


def industry_key(name):
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower().replace("&", "and")).strip("-")


def peer_metrics(sym, name_hint=None):
    """KGV, operative Marge, Umsatzwachstum und Börsenwert eines Wettbewerbers (Finnhub, sonst Yahoo)."""
    hit = PEER_CACHE.get(sym)
    if hit and time.time() - hit[0] < 6 * 3600:
        return hit[1]
    out = None
    if finnhub_key():
        met = (finnhub("stock/metric", symbol=sym, metric="all") or {}).get("metric") or {}
        if met:
            prof = finnhub("stock/profile2", symbol=sym) or {}
            pct = lambda k: (num(met.get(k)) / 100) if num(met.get(k)) is not None else None
            mc = num(prof.get("marketCapitalization"))
            out = {"symbol": sym, "name": prof.get("name") or name_hint or sym, "currency": prof.get("currency") or "",
                   "mcap": mc * 1e6 if mc else None,
                   "pe": num(met.get("peTTM")) or num(met.get("peBasicExclExtraTTM")),
                   "op_m": pct("operatingMarginTTM"), "growth": pct("revenueGrowthTTMYoy"), "source": "Finnhub"}
    if out is None:
        t = yf.Ticker(sym)
        info = fill_info(t, safe(lambda: t.info, {}) or {}, {"name": name_hint})
        if current_price(info):
            out = {"symbol": sym, "name": info.get("shortName") or info.get("longName") or name_hint or sym,
                   "currency": info.get("currency") or "", "mcap": num(info.get("marketCap")),
                   "pe": num(info.get("trailingPE")), "op_m": num(info.get("operatingMargins")),
                   "growth": num(info.get("revenueGrowth")), "source": "Yahoo"}
    if out and out["pe"] is not None and out["pe"] <= 0:
        out["pe"] = None  # Verlust -> kein sinnvolles KGV
    PEER_CACHE[sym] = (time.time(), out)
    return out


FX_CACHE = {}


def usd_rate(cur):
    """Umrechnungskurs Währung -> USD (für Größenvergleich der Börsenwerte), gecacht."""
    if not cur or cur == "USD":
        return 1.0
    scale = 0.01 if cur in ("GBp", "GBX", "ZAc", "ILA") else 1.0
    base = {"GBp": "GBP", "GBX": "GBP", "ZAc": "ZAR", "ILA": "ILS"}.get(cur, cur)
    hit = FX_CACHE.get(base)
    if not hit or time.time() - hit[0] > 12 * 3600:
        rate = num(safe(lambda: yf.Ticker(f"{base}USD=X").fast_info.last_price))
        hit = FX_CACHE[base] = (time.time(), rate)
    return hit[1] * scale if hit[1] else None


def competitors(symbol, info, alternatives):
    """Bis zu 5 Wettbewerber: Finnhub-Peers (auch über US-Notierung) + Yahoo-Branchenliste."""
    own_base = symbol.split(".")[0].upper()
    own_name = clean_company_name(info.get("longName") or info.get("shortName") or "").lower()
    alt_syms = {a["symbol"].upper() for a in alternatives}
    cands, names, source = [], {}, []
    if finnhub_key():
        for sym in [symbol] + [a["symbol"] for a in alternatives if "." not in a["symbol"]][:2]:
            ps = finnhub("stock/peers", symbol=sym)
            if isinstance(ps, list) and len(ps) > 1:
                cands += [x for x in ps if isinstance(x, str)]
                source.append("Finnhub")
                break
    def add_top(obj_fn, label):
        tc = safe(obj_fn)
        if tc is not None and len(tc):
            for sym_, row in tc.iterrows():
                cands.append(str(sym_))
                nm = row.get("name")
                if isinstance(nm, str) and nm.strip():
                    names[str(sym_).upper()] = nm
            source.append(label)
    key = info.get("industryKey") or industry_key(info.get("industry"))
    if key:
        add_top(lambda: yf.Industry(key).top_companies, "Yahoo-Branchenliste")
    picked, seen = [], set()
    for c in cands:
        cu = c.upper()
        if cu in seen or cu.split(".")[0] == own_base or cu in alt_syms:
            continue
        if names.get(cu) and clean_company_name(names[cu]).lower() == own_name:
            continue
        seen.add(cu)
        picked.append(cu)

    own_usd = None
    if num(info.get("marketCap")) and usd_rate(info.get("currency")):
        own_usd = num(info["marketCap"]) * usd_rate(info.get("currency"))

    def evaluate(cands_):
        good = []
        with ThreadPoolExecutor(max_workers=6) as ex:
            res = list(ex.map(lambda c: safe(lambda: peer_metrics(c, names.get(c))), cands_))
        for r in res:
            if not r or sum(r.get(k) is not None for k in ("pe", "op_m", "growth")) < 2:
                continue
            if own_name and clean_company_name(r["name"]).lower() == own_name:
                continue  # dasselbe Unternehmen unter anderem Kürzel
            rate = usd_rate(r.get("currency"))
            if own_usd and r.get("mcap") and rate and r["mcap"] * rate < own_usd * 0.03:
                continue  # Kleinstfirmen sind keine sinnvollen Vergleichswerte
            good.append(r)
        return good

    rows = evaluate(picked[:8])[:5]
    if len(rows) < 3:  # Branche zu klein besetzt -> größte Firmen desselben Sektors ergänzen
        skey = info.get("sectorKey") or industry_key(info.get("sector"))
        if skey:
            before = len(cands)
            add_top(lambda: yf.Sector(skey).top_companies, "Yahoo-Sektorliste")
            extra = []
            for c in cands[before:]:
                cu = c.upper()
                if cu not in seen and cu.split(".")[0] != own_base and cu not in alt_syms:
                    seen.add(cu)
                    extra.append(cu)
            have = {r["symbol"] for r in rows}
            rows += [r for r in evaluate(extra[:8]) if r["symbol"] not in have][: 5 - len(rows)]
    return {"peers": rows, "source": " + ".join(source), "industry": info.get("industry") or ""}


def peer_summary(own, peers):
    """Median der Wettbewerber und Rang der analysierten Aktie je Kennzahl."""
    def med(vals):
        vals = sorted(v for v in vals if v is not None)
        if not vals:
            return None
        k = len(vals) // 2
        return vals[k] if len(vals) % 2 else (vals[k - 1] + vals[k]) / 2
    out = {}
    for key, better_low in (("pe", True), ("op_m", False), ("growth", False)):
        vals = [p.get(key) for p in peers if p.get(key) is not None]
        mv, ov = med(vals), own.get(key)
        beats = None
        if ov is not None and vals:
            beats = sum(1 for v in vals if (ov < v if better_low else ov > v))
        out[key] = {"median": mv, "n": len(vals), "beats": beats}
    return out


# ---------------------------------------------------------------------------
# Termine: Quartalszahlen, Dividende, Hauptversammlung
# ---------------------------------------------------------------------------
GERMAN_SUFFIX = (".DE", ".F", ".MU", ".SG", ".HM", ".BE", ".DU", ".HA", ".VI")
EVENT_CACHE = {}


def _as_date(v):
    if v is None:
        return None
    if hasattr(v, "date") and callable(v.date):
        v = v.date()
    return v if hasattr(v, "year") else None


def company_events(symbol, alternatives=(), currency=""):
    """Nächste Termine (bis 13 Monate voraus). Geschätzte Termine sind als solche markiert."""
    hit = EVENT_CACHE.get(symbol)
    if hit and time.time() - hit[0] < 6 * 3600:
        return hit[1]
    from datetime import date
    today = date.today()
    horizon = today + timedelta(days=400)
    t = yf.Ticker(symbol)
    cal = safe(lambda: t.calendar) or {}
    if not isinstance(cal, dict):
        cal = {}
    ev = []

    # --- Quartalszahlen
    future, past, eps_est = [], [], None
    for d in cal.get("Earnings Date") or []:
        d = _as_date(d)
        if d and d >= today:
            future.append(d)
    eps_est = num(cal.get("Earnings Average"))
    ed = safe(lambda: t.get_earnings_dates(limit=12))
    if ed is not None and len(ed):
        for ts, r in ed.iterrows():
            d = _as_date(ts)
            if not d:
                continue
            if d >= today:
                future.append(d)
                eps_est = eps_est or num(r.get("EPS Estimate"))
            else:
                past.append(d)
    source = "Yahoo" if future else ""
    if not future and finnhub_key():
        for sym in [symbol] + [a["symbol"] for a in alternatives if "." not in a["symbol"]][:2]:
            fc = finnhub("calendar/earnings", symbol=sym, **{"from": str(today - timedelta(days=400)), "to": str(horizon)})
            rows = (fc or {}).get("earningsCalendar") or []
            for r0 in rows:
                d = safe(lambda: datetime.strptime(r0["date"], "%Y-%m-%d").date())
                if d:
                    (future if d >= today else past).append(d)
                    if d >= today and not eps_est:
                        eps_est = num(r0.get("epsEstimate"))
            if rows:
                source = "Finnhub" if future else ""
                break
    if future:
        d = min(future)
        ev.append({"type": "earnings", "date": str(d), "estimated": False, "source": source,
                   "label": "Quartalszahlen", "detail": f"Erwarteter Gewinn je Aktie: {fnum(eps_est, 2)}" if eps_est else ""})
    elif past:  # Schätzung: gleicher Termin wie vor einem Jahr
        cands = sorted(d + timedelta(days=364) for d in past if d + timedelta(days=364) >= today)
        if cands:
            ev.append({"type": "earnings", "date": str(cands[0]), "estimated": True, "source": "Vorjahrestermin",
                       "label": "Quartalszahlen", "detail": "geschätzt nach dem Vorjahrestermin"})

    # --- Dividende
    divs = safe(lambda: t.dividends)
    last_amt, freq_days = None, None
    if divs is not None and len(divs):
        dd = [(_as_date(i), float(v)) for i, v in divs.items() if v > 0]
        dd = [x for x in dd if x[0]]
        if dd:
            last_d, last_amt = dd[-1]
            recent = [x for x in dd if x[0] >= today - timedelta(days=400)]
            per_year = len([x for x in dd if x[0] >= today - timedelta(days=370)])
            # in ganzen Wochen, damit die Schätzung auf denselben Wochentag wie zuletzt fällt
            freq_days = {0: None, 1: 364, 2: 182, 3: 119, 4: 91}.get(per_year, 28 if per_year >= 10 else 91)
            if not recent:
                freq_days = None  # Dividende ausgesetzt
    ex_off = _as_date(cal.get("Ex-Dividend Date"))
    pay_off = _as_date(cal.get("Dividend Date"))
    cur = currency or ""
    amt_txt = f"zuletzt {fnum(last_amt, 2)} {cur} je Aktie".strip() if last_amt else ""
    ex_date, ex_est = None, False
    if ex_off and ex_off >= today:
        ex_date = ex_off
    elif freq_days and divs is not None and len(divs):
        nxt = last_d + timedelta(days=freq_days)
        while nxt < today:
            nxt += timedelta(days=freq_days)
        ex_date, ex_est = nxt, True
    if ex_date and ex_date <= horizon:
        ev.append({"type": "exdiv", "date": str(ex_date), "estimated": ex_est, "source": "Yahoo" if not ex_est else "Zahlungsrhythmus",
                   "label": "Ex-Dividende", "detail": amt_txt + (" · geschätzt nach dem Zahlungsrhythmus" if ex_est else "")})
    if pay_off and pay_off >= today:
        ev.append({"type": "pay", "date": str(pay_off), "estimated": False, "source": "Yahoo",
                   "label": "Dividendenzahlung", "detail": amt_txt})

    # --- Hauptversammlung (Deutschland/Österreich: Ex-Tag = Handelstag nach der HV)
    if ex_date and freq_days and freq_days >= 300 and symbol.upper().endswith(GERMAN_SUFFIX):
        agm = ex_date - timedelta(days=1)
        while agm.weekday() >= 5:
            agm -= timedelta(days=1)
        if agm >= today:
            ev.append({"type": "agm", "date": str(agm), "estimated": True, "source": "Ex-Tag",
                       "label": "Hauptversammlung", "detail": "geschätzt: Handelstag vor dem Ex-Dividenden-Tag"})

    ev.sort(key=lambda e: e["date"])
    for e in ev:
        e["days"] = (datetime.strptime(e["date"], "%Y-%m-%d").date() - today).days
    EVENT_CACHE[symbol] = (time.time(), ev)
    return ev


def ics_calendar(symbol, name, events):
    """iCalendar-Datei (ganztägige Termine) für Kalender-Apps."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Aktien-Check//DE", "CALSCALE:GREGORIAN"]
    for e in events:
        d = e["date"].replace("-", "")
        nxt = (datetime.strptime(e["date"], "%Y-%m-%d") + timedelta(days=1)).strftime("%Y%m%d")
        title = f"{name}: {e['label']}" + (" (voraussichtlich)" if e["estimated"] else "")
        desc = (e.get("detail") or "").replace(",", "\\,").replace(";", "\\;")
        lines += ["BEGIN:VEVENT", f"UID:{symbol}-{e['type']}-{d}@aktien-check", f"DTSTAMP:{stamp}",
                  f"DTSTART;VALUE=DATE:{d}", f"DTEND;VALUE=DATE:{nxt}",
                  "SUMMARY:" + title.replace(",", "\\,").replace(";", "\\;"), f"DESCRIPTION:{desc}",
                  "BEGIN:VALARM", "TRIGGER:-PT15H", "ACTION:DISPLAY", "DESCRIPTION:Erinnerung", "END:VALARM",
                  "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


# ---------------------------------------------------------------------------
# Kursverlauf für den Chart
# ---------------------------------------------------------------------------
CHART_RANGES = {  # Zeitraum -> (yfinance-Periode, Intervall, Cache-Sekunden)
    "1d": ("5d", "5m", 120), "5d": ("5d", "15m", 300), "1mo": ("1mo", "60m", 900), "1y": ("1y", "1d", 3600),
    "5y": ("5y", "1wk", 6 * 3600), "max": ("max", "1mo", 12 * 3600),
}
CHART_CACHE = {}


def chart_data(symbol, rng):
    symbol = symbol.strip().upper()
    if not re.fullmatch(r"[A-Z0-9.\-^=]{1,15}", symbol) or rng not in CHART_RANGES:
        raise ValueError("Ungültige Anfrage")
    period, interval, ttl = CHART_RANGES[rng]
    key = (symbol, rng)
    hit = CHART_CACHE.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    t = yf.Ticker(symbol)
    h = safe(lambda: t.history(period=period, interval=interval, auto_adjust=False))
    if h is None or h.empty:
        raise ValueError("Keine Kursdaten verfügbar")
    h = h[h["Close"].notna()]
    prev_close = None
    if rng == "1d":  # nur den letzten Handelstag zeigen, Vergleich mit dem Vortagesschluss
        last_day = max(ts.date() for ts in h.index)
        prev = h[[ts.date() < last_day for ts in h.index]]
        prev_close = float(prev["Close"].iloc[-1]) if len(prev) else None
        h = h[[ts.date() == last_day for ts in h.index]]
    pts = [[int(ts.timestamp() * 1000), round(float(c), 4)] for ts, c in zip(h.index, h["Close"])]
    ohlc = None
    if all(k in h for k in ("Open", "High", "Low")):
        ohlc = [[round(float(o), 4) if o == o else round(float(c), 4), round(float(hh), 4) if hh == hh else round(float(c), 4),
                 round(float(ll), 4) if ll == ll else round(float(c), 4), round(float(c), 4)]
                for o, hh, ll, c in zip(h["Open"], h["High"], h["Low"], h["Close"])]
    # Dividendenbereinigter Kurs (für die Gesamtrendite mit wieder angelegten Dividenden)
    adj = [round(float(a), 4) for a in h["Adj Close"]] if "Adj Close" in h and rng != "1d" else None
    if adj and all(abs(a_ - c_) <= 1e-4 * max(1.0, abs(c_)) for a_, c_ in zip(adj, h["Close"])):
        adj = None  # keine Ausschüttungen -> Gesamtrendite = Kurs
    if rng in ("1d", "5d", "1mo"):  # letzten Live-Kurs ergänzen
        last = num(safe(lambda: t.fast_info.last_price))
        if last and pts and abs(last / pts[-1][1] - 1) < 0.2:
            if adj:
                adj[-1] = round(adj[-1] * last / pts[-1][1], 4)
            pts[-1][1] = round(last, 4)
            if ohlc:  # Live-Kurs auch in die letzte Kerze übernehmen
                o_, hh_, ll_, _ = ohlc[-1]
                ohlc[-1] = [o_, round(max(hh_, last), 4), round(min(ll_, last), 4), round(last, 4)]
    divs = []
    if pts and rng != "1d":
        d = safe(lambda: t.dividends)
        if d is not None and len(d):
            lo, hi = pts[0][0], pts[-1][0] + 86400000 * 31
            divs = [[int(ts.timestamp() * 1000), round(float(v), 4)] for ts, v in d.items()
                    if lo <= ts.timestamp() * 1000 <= hi and v > 0]
    # Gleitende Durchschnitte (50/200 Handelstage) aus Tageskursen, auf die Chartpunkte übertragen
    sma50 = sma200 = None
    daily = safe(lambda: t.history(period={"1d": "2y", "5d": "2y", "1mo": "2y", "1y": "2y", "5y": "10y", "max": "max"}[rng],
                                   interval="1d", auto_adjust=False))
    if daily is not None and len(daily) >= 60 and pts:
        import pandas as pd
        dc = daily["Close"].copy()
        dc.index = pd.to_datetime([ts.timestamp() for ts in dc.index], unit="s")
        idx = pd.to_datetime([p[0] / 1000 for p in pts], unit="s")

        def on_points(series):
            vals = series.reindex(series.index.union(idx)).ffill().reindex(idx)
            return [None if v != v else round(float(v), 4) for v in vals]
        sma50 = on_points(dc.rolling(50).mean())
        sma200 = on_points(dc.rolling(200).mean()) if len(dc) >= 200 else None
    volume = [int(v) if v == v else 0 for v in h["Volume"]] if "Volume" in h else None
    base = prev_close if prev_close else (pts[0][1] if pts else None)
    out = {"symbol": symbol, "range": rng, "points": pts, "ohlc": ohlc if ohlc and len(ohlc) == len(pts) else None, "base": base, "intraday": rng in ("1d", "5d", "1mo"),
           "sma50": sma50, "sma200": sma200,
           "volume": volume if volume and any(volume) and len(volume) == len(pts) else None,
           "change": (pts[-1][1] / base - 1) if pts and base else None,
           "adj": adj if adj and len(adj) == len(pts) and all(a > 0 for a in adj) else None,
           "dividends": divs,
           "currency": safe(lambda: t.fast_info.currency) or ""}
    CHART_CACHE[key] = (time.time(), out)
    return out


INCOME_CACHE = {}
MONTHS_DE_SHORT = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]


def income_data(symbol, freq):
    """Erfolgsrechnung (Umsatz, Reinertrag, Nettomarge) je Geschäftsjahr oder Quartal, in Berichtswährung."""
    symbol = symbol.strip().upper()
    if not re.fullmatch(r"[A-Z0-9.\-^=]{1,15}", symbol) or freq not in ("annual", "quarterly"):
        raise ValueError("Ungültige Anfrage")
    key = (symbol, freq)
    hit = INCOME_CACHE.get(key)
    if hit and time.time() - hit[0] < 12 * 3600:
        return hit[1]
    t = yf.Ticker(symbol)
    df = safe(lambda: t.income_stmt if freq == "annual" else t.quarterly_income_stmt)
    if df is None or getattr(df, "empty", True):
        raise ValueError("Keine Geschäftszahlen verfügbar")

    def row(*names):
        for nm in names:
            if nm in df.index:
                return df.loc[nm]
        return None
    rev = row("Total Revenue", "Operating Revenue")
    ni = row("Net Income", "Net Income Common Stockholders", "Net Income From Continuing Operation Net Minority Interest")
    op = row("Operating Income", "Total Operating Income As Reported", "EBIT")
    if rev is None or ni is None:
        raise ValueError("Keine Geschäftszahlen verfügbar")
    periods = []
    for col in sorted(df.columns):
        r, n = num(rev.get(col)), num(ni.get(col))
        o = num(op.get(col)) if op is not None else None
        if r is None or n is None or r <= 0:
            continue  # Yahoo hängt oft eine leere Spalte an
        end = col.date() if hasattr(col, "date") else col
        # Quartale nach Monat des Periodenendes benennen (Geschäftsquartale weichen oft vom Kalender ab)
        label = str(end.year) if freq == "annual" else f"{MONTHS_DE_SHORT[end.month - 1]} {str(end.year)[2:]}"
        periods.append({"label": label, "end": end.isoformat(), "revenue": r, "net_income": n, "margin": n / r,
                        "op_income": o, "op_margin": o / r if o is not None else None})
    periods = periods[-5:] if freq == "annual" else periods[-6:]
    if not periods:
        raise ValueError("Keine Geschäftszahlen verfügbar")
    out = {"symbol": symbol, "freq": freq, "periods": periods,
           "currency": financial_currency(symbol) or safe(lambda: t.fast_info.currency) or ""}
    INCOME_CACHE[key] = (time.time(), out)
    return out


# ---------------------------------------------------------------------------
# Kryptowährungen
# ---------------------------------------------------------------------------
# Große Coins: Kürzel -> CoinGecko-ID (Namen werden zusätzlich über CoinGecko gesucht)
CRYPTO_IDS = {
    "BTC": "bitcoin", "ETH": "ethereum", "BNB": "binancecoin", "SOL": "solana", "XRP": "ripple",
    "DOGE": "dogecoin", "ADA": "cardano", "TRX": "tron", "AVAX": "avalanche-2", "LINK": "chainlink",
    "DOT": "polkadot", "TON": "the-open-network", "SHIB": "shiba-inu", "LTC": "litecoin", "BCH": "bitcoin-cash",
    "XLM": "stellar", "NEAR": "near", "UNI": "uniswap", "SUI": "sui", "APT": "aptos", "ICP": "internet-computer",
    "ETC": "ethereum-classic", "XMR": "monero", "ATOM": "cosmos", "HBAR": "hedera-hashgraph", "POL": "polygon-ecosystem-token",
    "ARB": "arbitrum", "OP": "optimism", "RENDER": "render-token", "PEPE": "pepe", "KAS": "kaspa", "FIL": "filecoin",
    "ALGO": "algorand", "AAVE": "aave", "INJ": "injective-protocol", "ZEC": "zcash", "HYPE": "hyperliquid",
    "USDT": "tether", "USDC": "usd-coin", "DAI": "dai",
}
CRYPTO_NAMES = {"bitcoin": "BTC", "ethereum": "ETH", "ether": "ETH", "solana": "SOL", "ripple": "XRP", "dogecoin": "DOGE",
                "cardano": "ADA", "tron": "TRX", "avalanche": "AVAX", "chainlink": "LINK", "polkadot": "DOT", "toncoin": "TON",
                "litecoin": "LTC", "stellar": "XLM", "monero": "XMR", "cosmos": "ATOM", "polygon": "POL", "binance coin": "BNB",
                "shiba inu": "SHIB", "bitcoin cash": "BCH", "tether": "USDT", "zcash": "ZEC"}
STABLE = {"USDT", "USDC", "DAI", "FDUSD", "TUSD", "USDE", "PYUSD", "USDS", "EURC"}
CRYPTO_WEIGHTS = {"valuation": .20, "quality": .20, "growth": .15, "risk": .15,
                  "dividend": 0.0, "chart": .15, "sentiment": .10, "macro": .05}
CG_CACHE = {}


def coingecko(path, ttl=600):
    """CoinGecko-API (kostenlos; optional COINGECKO_API_KEY als Demo-Schlüssel), gecacht."""
    hit = CG_CACHE.get(path)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    headers = dict(UA)
    if os.environ.get("COINGECKO_API_KEY"):
        headers["x-cg-demo-api-key"] = os.environ["COINGECKO_API_KEY"].strip()
    data = None
    for attempt in range(2):
        try:
            req = urllib.request.Request("https://api.coingecko.com/api/v3/" + path, headers=headers)
            with urllib.request.urlopen(req, timeout=12) as r:
                data = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt == 0:
                time.sleep(2.5)  # gedrosselt -> kurz warten, einmal erneut
                continue
            break
        except Exception:
            break
    if data is None:
        LOG.warning("[CoinGecko] keine Antwort für %s – %s", path.split("?")[0],
                    "nutze Zwischenspeicher" if hit else "ohne Daten")
        return hit[1] if hit else None  # bei Limit/Fehler: letzter bekannter Stand
    CG_CACHE[path] = (time.time(), data)
    return data


def cg_markets(vs="eur"):
    """Marktdaten der 250 größten Coins in einer Abfrage (Kurs, Rang, Angebot, Allzeithoch, Performance)."""
    return coingecko(f"coins/markets?vs_currency={vs}&order=market_cap_desc&per_page=250&page=1"
                     f"&price_change_percentage=30d,1y", ttl=600) or []


def fear_greed():
    d = safe(lambda: json.loads(http_get("https://api.alternative.me/fng/?limit=1"))["data"][0])
    return (int(d["value"]), d["value_classification"]) if d else (None, None)


FG_DE = {"Extreme Fear": "extreme Angst", "Fear": "Angst", "Neutral": "neutral", "Greed": "Gier", "Extreme Greed": "extreme Gier"}


CAT_PRIORITY = ["Stablecoins", "Meme", "Layer 2 (L2)", "Layer 1 (L1)", "Smart Contract Platform",
                "Decentralized Finance (DeFi)", "Oracle", "Privacy Coins", "Artificial Intelligence (AI)", "Payment Solutions"]


def crypto_categories(cats):
    """Aussagekräftige Kategorien zuerst; Portfolio-/Ökosystem-Einträge von CoinGecko ausblenden."""
    cats = [c for c in (cats or []) if c and not re.search(r"portfolio|ecosystem|holdings|binance|coinbase|launchpad|index|alleged", c, re.I)]
    prio = {c: i for i, c in enumerate(CAT_PRIORITY)}
    return sorted(cats, key=lambda c: prio.get(c, 99))


def resolve_crypto(query):
    """Erkennt Kryptowährungen: Kürzel (BTC, BTC-EUR), Namen (Bitcoin) oder Yahoo-Suchtreffer."""
    q = query.strip()
    qu = q.upper()
    m_ = re.fullmatch(r"([A-Z0-9]{2,12})-(EUR|USD|USDT)", qu)
    base = re.sub(r"\d+$", "", m_.group(1)) if m_ else None
    if not base and qu in CRYPTO_IDS:
        base = qu
    if not base and q.lower() in CRYPTO_NAMES:
        base = CRYPTO_NAMES[q.lower()]
    if not base:
        quotes = safe(lambda: yf.Search(q, max_results=6, news_count=0).quotes, []) or []
        first = quotes[0] if quotes else {}
        if first.get("quoteType") != "CRYPTOCURRENCY" or any(x.get("quoteType") == "EQUITY" and
                                                            q.lower() in (x.get("shortname") or "").lower() for x in quotes[:3]):
            return None
        base = re.sub(r"\d+$", "", first["symbol"].split("-")[0])
    cg_id = CRYPTO_IDS.get(base)
    if not cg_id:
        found = (coingecko(f"search?query={urllib.parse.quote(base)}") or {}).get("coins") or []
        exact = [c for c in found if c.get("symbol", "").upper() == base and c.get("market_cap_rank")]
        exact.sort(key=lambda c: c["market_cap_rank"])
        cg_id = exact[0]["id"] if exact else None
    return {"base": base, "id": cg_id, "quote": m_.group(2) if m_ else "EUR"}


def crypto_yahoo_symbol(base, name, cg_price_eur, cg_price_usd):
    """Yahoo-Kürzel für Kursverlauf; Preis wird mit CoinGecko abgeglichen (gleiches Kürzel ≠ gleicher Coin)."""
    def plausible(sym, ref):
        h = safe(lambda: yf.Ticker(sym).history(period="5d"))
        if h is None or h.empty:
            return False
        last = float(h["Close"].dropna().iloc[-1])
        return not ref or 0.8 < last / ref < 1.25
    for sym, ref in ((f"{base}-EUR", cg_price_eur), (f"{base}-USD", cg_price_usd)):
        if plausible(sym, ref):
            return sym
    for it in safe(lambda: yf.Search(name or base, max_results=8, news_count=0).quotes, []) or []:
        sym = it.get("symbol", "")
        if it.get("quoteType") == "CRYPTOCURRENCY" and sym.endswith(("-USD", "-EUR")) and \
                re.sub(r"\d+$", "", sym.split("-")[0]) == base:
            if plausible(sym, cg_price_eur if sym.endswith("-EUR") else cg_price_usd):
                return sym
    return None


def crypto_indicators(m, hist, btc_hist=None):
    """Charttechnik-Kennzahlen (24/7-Handel: 365 Tage/Jahr)."""
    c = hist["Close"].dropna()
    c = c[c > 0]
    last = float(c.iloc[-1])
    m["last"] = last
    m["sma50"] = float(c.rolling(50).mean().iloc[-1]) if len(c) >= 50 else None
    m["sma200"] = float(c.rolling(200).mean().iloc[-1]) if len(c) >= 200 else None
    m["sma200_3m"] = float(c.rolling(200).mean().iloc[-91]) if len(c) >= 291 else None
    m["price_3m_ago"] = float(c.iloc[-91]) if len(c) > 91 else None

    def perf(n):
        return last / float(c.iloc[-n - 1]) - 1 if len(c) > n else None
    m["perf_1m"], m["perf_3m"], m["perf_6m"], m["perf_1y"] = perf(30), perf(90), perf(180), perf(365)
    delta = c.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    m["rsi"] = float(100 - 100 / (1 + up.iloc[-1] / dn.iloc[-1])) if dn.iloc[-1] else 100.0
    y = c.iloc[-365:]
    m["vol"] = float(y.pct_change().dropna().std() * math.sqrt(365))
    m["hi52"], m["lo52"] = float(y.max()), float(y.min())
    m["max_dd"] = float((y / y.cummax() - 1).min())
    m["mayer"] = last / m["sma200"] if m["sma200"] else None
    m["corr_btc"] = m["beta_btc"] = None
    if btc_hist is not None and not btc_hist.empty:
        import pandas as pd
        a_ = y.pct_change()
        b_ = btc_hist["Close"].dropna().iloc[-365:].pct_change()
        a_.index, b_.index = a_.index.normalize(), b_.index.normalize()
        j = pd.concat([a_, b_], axis=1, join="inner").dropna()
        if len(j) > 60 and j.iloc[:, 1].var() > 0:
            m["corr_btc"] = float(j.iloc[:, 0].corr(j.iloc[:, 1]))
            m["beta_btc"] = float(j.iloc[:, 0].cov(j.iloc[:, 1]) / j.iloc[:, 1].var())


def c_valuation(m):
    parts, why = [], []
    if m.get("mayer"):
        parts.append((clamp((1.25 - m["mayer"]) / 0.75), 1.2))
        why.append(f"Mayer-Multiple (Kurs ÷ GD200) {fnum(m['mayer'], 2)} – unter 1 historisch günstig, über 2,4 überhitzt")
    d = m.get("ath_change")
    if d is not None:
        s = -0.5 if d > -0.1 else -0.1 if d > -0.3 else 0.3 if d > -0.6 else 0.6 if d > -0.85 else 0.1
        parts.append((s, 0.8))
        why.append(f"Abstand zum Allzeithoch {pct(d)} (Hoch {fnum(m['ath'], 2)} {m['currency']} am {m.get('ath_date') or '–'})")
    if m.get("mcap") and m.get("vol24"):
        ratio = m["mcap"] / m["vol24"]
        parts.append((clamp((40 - ratio) / 40) * 0.5, 0.4))
        why.append(f"Marktwert ÷ Tagesvolumen {fnum(ratio, 0)} (niedrig = viel Handelsaktivität relativ zum Wert)")
    v = wavg(parts)
    if v is None:
        return {"score": None, "adjective": "fair bewertet", "reasons": why + ["Zu wenige Daten"]}
    hot = (m.get("rsi") or 50) > 70 or (m.get("mayer") or 1) > 2.0
    if v >= 0.6:
        adj = "unterbewertet"
    elif v >= 0.15 and (m.get("fg") or 50) < 30:
        adj = "unterschätzt"
    elif v >= 0.45:
        adj = "günstig"
    elif v >= 0.3:
        adj = "preiswert"
    elif v >= 0.15:
        adj = "attraktiv bewertet"
    elif v >= 0.05:
        adj = "angemessen bewertet"
    elif v >= -0.05:
        adj = "fair bewertet"
    elif v >= -0.15:
        adj = "marktgerecht"
    elif v < -0.6 and hot:
        adj = "überhitzt"
    elif v < -0.3 and hot:
        adj = "heißgelaufen"
    elif v < -0.45:
        adj = "überbewertet"
    elif v < -0.3:
        adj = "teuer"
    else:
        adj = "ambitioniert bewertet"
    return {"score": v, "adjective": adj, "reasons": why}


def c_quality(m):
    parts, why = [], []
    rank, age = m.get("rank"), m.get("age_years")
    if rank:
        parts.append((1.0 if rank <= 2 else 0.6 if rank <= 10 else 0.3 if rank <= 25 else 0.0 if rank <= 50 else -0.5, 1.2))
        why.append(f"Rang {rank} nach Marktkapitalisierung")
    if age is not None:
        parts.append((0.8 if age >= 8 else 0.4 if age >= 4 else 0.0 if age >= 2 else -0.4, 0.8))
        why.append(f"Seit {fnum(age, 1)} Jahren am Markt" + (f" (Start {m['genesis']})" if m.get("genesis") else ""))
    if m.get("mcap") and m.get("vol24"):
        liq = m["vol24"] / m["mcap"]
        parts.append((clamp((liq - 0.01) / 0.03), 0.6))
        why.append(f"Liquidität: Tagesvolumen {pct(liq)} des Marktwerts")
    if m.get("max_supply"):
        parts.append((0.3, 0.4))
        why.append("Begrenzte Maximalmenge")
    q = wavg(parts)
    d = m.get("ath_change") or 0
    if rank == 1:
        adj = "dominant"
    elif rank and rank <= 3:
        adj = "marktführend"
    elif rank and rank <= 10 and (age or 0) >= 5:
        adj = "wettbewerbsstark (mit „Burggraben“)"
    elif d < -0.85 and (m.get("perf_1y") or 0) < -0.5:
        adj = "angeschlagen"
    elif rank and rank <= 20:
        adj = "robust"
    elif rank and rank <= 50:
        adj = "solide"
    else:
        adj = "schwach"
    return {"score": q, "adjective": adj, "reasons": why}


def c_growth(m):
    parts, why = [], []
    g = m.get("perf_1y")
    if g is not None:
        parts.append((clamp(g / 0.8), 1.0))
        why.append(f"Wertentwicklung 12 Monate {pct(g)} (Indikator für Nachfrage/Adoption)")
    circ, mx, tot = m.get("circ"), m.get("max_supply"), m.get("total_supply")
    if circ and mx:
        share = circ / mx
        parts.append((clamp((share - 0.6) / 0.35), 0.7))
        why.append(f"Umlauf {pct(share)} der Maximalmenge ({fnum(mx, 0)}) – {'kaum weitere Verwässerung' if share > 0.9 else 'weitere Neuausgabe ausstehend'}")
    elif circ:
        parts.append((-0.2, 0.5))
        why.append(f"Keine feste Maximalmenge – laufende Neuausgabe möglich (Umlauf {fnum(circ, 0)})")
    if m.get("fdv") and m.get("mcap"):
        why.append(f"Vollverwässerter Wert {money(m['fdv'], m['currency'])} ({fnum(m['fdv'] / m['mcap'], 2)}× Marktwert)")
    s_ = wavg(parts)
    age = m.get("age_years") or 99
    cats = " ".join(m.get("categories") or []).lower()
    g = g or 0
    if age < 4 and g > 0.5:
        adj = "aufstrebend"
    elif g > 1.0:
        adj = "wachstumsstark"
    elif g > 0.3:
        adj = "dynamisch"
    elif g > 0 and any(k in cats for k in ("smart contract", "artificial intelligence", "defi", "layer 2")):
        adj = "innovativ"
    elif age >= 10 and -0.3 <= g <= 0.3:
        adj = "reif"
    elif -0.1 <= g <= 0.1:
        adj = "stagnierend"
    elif g < -0.3:
        adj = "rückläufig"
    else:
        adj = "gesättigt"
    return {"score": s_, "adjective": adj, "reasons": why}


def c_risk(m):
    parts, why = [], []
    vol = m.get("vol")
    if vol is not None:
        parts.append((clamp((0.55 - vol) / 0.35), 1.0))
        why.append(f"Volatilität (1 J., annualisiert) {pct(vol)} – Aktienmarkt zum Vergleich ca. 15–20 %")
    if m.get("max_dd") is not None:
        parts.append((clamp((0.45 + m["max_dd"]) / 0.3), 0.7))
        why.append(f"Maximaler Rückgang im letzten Jahr {pct(m['max_dd'])}")
    rank = m.get("rank")
    if rank:
        parts.append((0.3 if rank <= 10 else 0.0 if rank <= 30 else -0.6, 0.6))
    if m.get("corr_btc") is not None:
        why.append(f"Korrelation zu Bitcoin {fnum(m['corr_btc'], 2)}, Beta {fnum(m['beta_btc'], 2)} – bewegt sich stark mit dem Gesamtmarkt"
                   if m["corr_btc"] > 0.6 else f"Korrelation zu Bitcoin {fnum(m['corr_btc'], 2)}")
    r = wavg(parts)
    if r is not None:
        r = min(r, 0.1)  # Kryptowährungen sind grundsätzlich riskante Anlagen
    vol = vol or 1
    if m.get("stable"):
        adj = "schwankungsarm"
    elif vol < 0.35:
        adj = "berechenbar"
    elif (rank or 999) > 50 or vol > 0.9:
        adj = "spekulativ"
    elif vol < 0.6:
        adj = "volatil"
    else:
        adj = "riskant"
    return {"score": r, "adjective": adj, "reasons": why}


def c_sentiment(m, news):
    why, parts = [], []
    fg, fgc = m.get("fg"), m.get("fg_class")
    if fg is not None:
        parts.append(((fg - 50) / 50, 1.0))
        why.append(f"Crypto Fear & Greed Index {fg} von 100 ({FG_DE.get(fgc, fgc)})")
    ns = news["sentiment"]
    if ns is not None and news["count"]:
        parts.append((clamp(ns * 2.5), 1.0))
        why.append(f"News-Tonalität (30 Tage, tier-gewichtet) {'+' if ns >= 0 else ''}{fnum(ns, 2)} aus {news['count']} Meldungen "
                   f"({news['pos']} positiv / {news['neg']} negativ)")
    s_ = wavg(parts) or 0.0
    cnt = news["count"]
    split = news["pos"] >= 3 and news["neg"] >= 3 and min(news["pos"], news["neg"]) / max(news["pos"], news["neg"]) > 0.6
    fg = fg if fg is not None else 50
    if fg >= 75 and cnt >= 15:
        adj = "gehypt"
    elif cnt < 8:
        adj = "vernachlässigt" if s_ <= 0 else "übersehen"
    elif split:
        adj = "umstritten"
    elif fg >= 60 or s_ >= 0.25:
        adj = "gefragt"
    elif s_ >= 0.08:
        adj = "beliebt"
    elif fg <= 30 or s_ <= -0.15:
        adj = "unbeliebt"
    else:
        adj = "umstritten"
    return {"score": s_, "adjective": adj, "reasons": why}


def c_macro(m, mac):
    why, parts = [], []
    if mac["rf"] is not None:
        why.append(f"US-10J-Rendite {fnum(mac['rf'], 2)} % ({'+' if (mac['rf_chg'] or 0) >= 0 else ''}{fnum(mac['rf_chg'], 2)} Pp. in 6 Monaten)")
        s_ = -0.4 if mac["rf"] >= 4 else 0.0 if mac["rf"] >= 3 else 0.3
        if mac["rf_chg"] is not None:
            s_ += -0.3 if mac["rf_chg"] > 0.3 else 0.3 if mac["rf_chg"] < -0.3 else 0
        parts.append((clamp(s_), 1.0))
        why.append("Kryptowährungen reagieren wie Wachstumswerte empfindlich auf steigende Zinsen und knappe Liquidität")
    if m["currency"] == "USD" and mac.get("fx_chg") is not None:
        parts.append((clamp(mac["fx_chg"] / 0.1) * 0.6, 0.6))
        why.append(f"Kurs in US-Dollar – Wechselkursrisiko für Euro-Anleger ({pct(mac['fx_chg'])} ggü. EUR in 12 Monaten)")
    elif m["currency"] == "EUR":
        why.append("Kurs in Euro – der Wert hängt aber global am US-Dollar-Markt")
    why.append("Regulierung (z. B. MiCA in der EU) und Bitcoin-ETF-Zuflüsse beeinflussen den gesamten Kryptomarkt")
    s_ = wavg(parts)
    return {"score": s_ if s_ is not None else 0.0, "adjective": None, "reasons": why}


def crypto_competitors(cg_id, currency):
    vs = "eur"  # Vergleich immer aus der Euro-Liste (Prozentwerte sind währungsunabhängig)
    mk = cg_markets(vs)[:25]

    def row(c):
        return {"symbol": f"{c['symbol'].upper()}-{vs.upper()}", "name": c.get("name"), "currency": vs.upper(),
                "mcap": num(c.get("market_cap")), "perf_30d": (num(c.get("price_change_percentage_30d_in_currency")) or 0) / 100,
                "perf_1y": (num(c.get("price_change_percentage_1y_in_currency")) / 100) if num(c.get("price_change_percentage_1y_in_currency")) is not None else None,
                "ath_change": (num(c.get("ath_change_percentage")) or 0) / 100, "rank": c.get("market_cap_rank")}
    own = next((row(c) for c in mk if c.get("id") == cg_id), None)
    peers = [row(c) for c in mk if c.get("id") != cg_id and c.get("symbol", "").upper() not in STABLE
             and (num(c.get("price_change_percentage_30d_in_currency")) is None or abs(num(c.get("price_change_percentage_30d_in_currency"))) > 0.5)][:5]
    return own, peers


def crypto_peer_summary(own, peers):
    def med(vals):
        vals = sorted(v for v in vals if v is not None)
        if not vals:
            return None
        k = len(vals) // 2
        return vals[k] if len(vals) % 2 else (vals[k - 1] + vals[k]) / 2
    out = {}
    for key in ("perf_1y", "perf_30d", "ath_change"):
        vals = [p.get(key) for p in peers if p.get(key) is not None]
        ov = (own or {}).get(key)
        out[key] = {"median": med(vals), "n": len(vals),
                    "beats": sum(1 for v in vals if ov is not None and ov > v) if ov is not None and vals else None}
    return out


def analyze_crypto(cr):
    # Details (Start, Kategorien, Beschreibung) ändern sich selten -> 24 h; Marktdaten aus der Top-250-Liste
    cg = coingecko(f"coins/{cr['id']}?localization=false&tickers=false&market_data=true&community_data=false"
                   f"&developer_data=false&sparkline=false", ttl=86400) if cr.get("id") else None
    mk_eur = next((c for c in cg_markets("eur") if c.get("id") == cr.get("id")), None) if cr.get("id") else None
    md = (cg or {}).get("market_data") or {}
    if mk_eur:  # aktuelle Marktdaten haben Vorrang vor den (bis 24 h alten) Detaildaten
        md = {**md,
              "current_price": {**(md.get("current_price") or {}), "eur": mk_eur.get("current_price")},
              "market_cap": {**(md.get("market_cap") or {}), "eur": mk_eur.get("market_cap")},
              "total_volume": {**(md.get("total_volume") or {}), "eur": mk_eur.get("total_volume")},
              "ath": {**(md.get("ath") or {}), "eur": mk_eur.get("ath")},
              "ath_change_percentage": {**(md.get("ath_change_percentage") or {}), "eur": mk_eur.get("ath_change_percentage")},
              "ath_date": {**(md.get("ath_date") or {}), "eur": mk_eur.get("ath_date")},
              "atl": {**(md.get("atl") or {}), "eur": mk_eur.get("atl")},
              "fully_diluted_valuation": {**(md.get("fully_diluted_valuation") or {}), "eur": mk_eur.get("fully_diluted_valuation")},
              "circulating_supply": mk_eur.get("circulating_supply"), "total_supply": mk_eur.get("total_supply"),
              "max_supply": mk_eur.get("max_supply")}
        if not (md.get("current_price") or {}).get("usd"):
            usd = next((c for c in cg_markets("usd") if c.get("id") == cr.get("id")), None)
            if usd:
                for k_ in ("current_price", "market_cap", "total_volume", "ath", "ath_change_percentage", "ath_date", "atl",
                           "fully_diluted_valuation"):
                    md[k_] = {**(md.get(k_) or {}), "usd": usd.get(k_)}
    name = (cg or {}).get("name") or (mk_eur or {}).get("name") or cr["base"]
    if not cg and mk_eur:
        cg = {"name": name, "market_cap_rank": mk_eur.get("market_cap_rank")}
    p_eur, p_usd = num((md.get("current_price") or {}).get("eur")), num((md.get("current_price") or {}).get("usd"))
    ysym = crypto_yahoo_symbol(cr["base"], name, p_eur, p_usd)
    if not ysym and not cg:
        raise ValueError(f"Keine Kursdaten zu „{cr['base']}“ gefunden.")
    cur = "USD" if (ysym or "").endswith("-USD") else "EUR"
    vs = cur.lower()
    pick = lambda d: num((d or {}).get(vs))
    m = {"symbol": ysym or f"{cr['base']}-{cur}", "name": name, "currency": cur, "base": cr["base"],
         "rank": (cg or {}).get("market_cap_rank"), "mcap": pick(md.get("market_cap")), "vol24": pick(md.get("total_volume")),
         "ath": pick(md.get("ath")),
         "ath_change": (pick(md.get("ath_change_percentage")) / 100) if pick(md.get("ath_change_percentage")) is not None else None,
         "ath_date": ((md.get("ath_date") or {}).get(vs) or "")[:10] or None,
         "atl": pick(md.get("atl")), "circ": num(md.get("circulating_supply")), "total_supply": num(md.get("total_supply")),
         "max_supply": num(md.get("max_supply")), "fdv": pick(md.get("fully_diluted_valuation")),
         "genesis": (cg or {}).get("genesis_date"), "categories": crypto_categories((cg or {}).get("categories")),
         "homepage": (((cg or {}).get("links") or {}).get("homepage") or [""])[0]}
    if m["ath_date"]:
        m["ath_date"] = datetime.strptime(m["ath_date"], "%Y-%m-%d").strftime("%d.%m.%Y")
    m["stable"] = cr["base"] in STABLE or any("stablecoin" in c.lower() for c in m["categories"])
    with ThreadPoolExecutor(max_workers=5) as ex:
        fh = ex.submit(lambda: yf.Ticker(ysym).history(period="2y", auto_adjust=False) if ysym else None)
        fbtc = ex.submit(lambda: yf.Ticker(f"BTC-{cur}").history(period="2y") if cr["base"] != "BTC" else None)
        fmac = ex.submit(gather_macro, cur)
        fnews = ex.submit(collect_news, m["symbol"], name, m["homepage"], (), ("crypto", "Kurs"))
        ffg = ex.submit(fear_greed)
        fpeers = ex.submit(crypto_competitors, cr.get("id"), cur)
        hist, btc, mac, news = safe(fh.result), safe(fbtc.result), fmac.result(), fnews.result()
        m["fg"], m["fg_class"] = safe(ffg.result, (None, None)) or (None, None)
        own_peer, peers = safe(fpeers.result, (None, [])) or (None, [])
    if hist is not None and not hist.empty:
        crypto_indicators(m, hist, btc)
        first = hist.index[0]
        m["data_since"] = first.strftime("%d.%m.%Y")
    else:
        for k in ("last", "sma50", "sma200", "sma200_3m", "price_3m_ago", "perf_1m", "perf_3m", "perf_6m", "perf_1y",
                  "rsi", "vol", "hi52", "lo52", "max_dd", "mayer", "corr_btc", "beta_btc"):
            m[k] = None
    m["price"] = (p_eur if cur == "EUR" else p_usd) or m.get("last")
    if m.get("perf_1y") is None and num(md.get("price_change_percentage_1y")) is not None:
        m["perf_1y"] = num(md["price_change_percentage_1y"]) / 100
    if m["genesis"]:
        m["age_years"] = (datetime.now() - datetime.strptime(m["genesis"], "%Y-%m-%d")).days / 365.25
    else:
        m["age_years"] = None

    cats = {"valuation": c_valuation(m), "quality": c_quality(m), "growth": c_growth(m), "risk": c_risk(m),
            "dividend": {"score": None, "adjective": "nicht anwendbar",
                         "reasons": ["Kryptowährungen zahlen keine Dividende. Staking-Erträge werden nicht bewertet."]},
            "chart": score_chart(m), "sentiment": c_sentiment(m, news), "macro": c_macro(m, mac)}
    total = (wavg([(cats[k]["score"], w) for k, w in CRYPTO_WEIGHTS.items() if w]) or 0.0) * 100
    notes = []
    if m["stable"]:
        total = 0.0
        notes.append("Stablecoin: an eine Währung gekoppelt – Kursgewinne sind nicht vorgesehen, eine Kauf-/Verkaufsempfehlung ist nicht sinnvoll.")
    elif (m.get("rank") or 999) > 50 and total > 8:
        total = 8
        notes.append("Deckel: Coin außerhalb der Top 50 nach Marktwert – hochspekulativ, daher höchstens „Halten“.")
    if not cg:
        notes.append("CoinGecko war nicht erreichbar – Rang, Angebot und Allzeithoch fehlen, die Einschätzung ist unvollständig.")
    label, group = map_rating(total)
    s_adj = summary_adj(total, cats)
    confidence = "hoch" if cg and hist is not None and news["count_trusted"] >= 5 else "mittel" if cg or hist is not None else "niedrig"

    titles = {"valuation": "Bewertung (Zyklus & Abstand zum Allzeithoch)", "quality": "Qualität des Netzwerks",
              "growth": "Wachstum (Adoption & Angebot)", "risk": "Risiko und Schwankung", "dividend": "Dividende und Ausschüttung",
              "chart": "Kursentwicklung und Charttechnik", "sentiment": "Stimmung und Wahrnehmung"}
    out_cats = [{"key": k, "title": t_, "adjective": cats[k]["adjective"], "options": ADJ[k],
                 "score": None if cats[k]["score"] is None else round(cats[k]["score"], 3),
                 "weight": CRYPTO_WEIGHTS[k], "reasons": cats[k]["reasons"]} for k, t_ in titles.items()]
    c = m["currency"]
    share = (m["circ"] / m["max_supply"]) if m.get("circ") and m.get("max_supply") else None
    fundamentals = [
        {"title": "Markt & Netzwerk", "rows": [
            ["Rang nach Marktwert", f"#{m['rank']}" if m.get("rank") else "–", ""],
            ["Marktkapitalisierung", money(m.get("mcap"), c), ""],
            ["Handelsvolumen 24 Std.", money(m.get("vol24"), c),
             f"{pct(m['vol24'] / m['mcap'])} des Marktwerts" if m.get("vol24") and m.get("mcap") else ""],
            ["Start / Alter", (datetime.strptime(m["genesis"], "%Y-%m-%d").strftime("%d.%m.%Y") if m.get("genesis") else "–"),
             f"{fnum(m['age_years'], 1)} Jahre" if m.get("age_years") else ""],
            ["Kategorien", ", ".join(m["categories"][:3]) or "–", ""]]},
        {"title": "Angebot & Inflation", "rows": [
            ["Umlaufmenge", fnum(m.get("circ"), 0), ""],
            ["Maximalmenge", fnum(m.get("max_supply"), 0) if m.get("max_supply") else "unbegrenzt",
             "feste Obergrenze" if m.get("max_supply") else "Neuausgabe ohne feste Grenze"],
            ["Anteil im Umlauf", pct(share), ""],
            ["Vollverwässerter Wert", money(m.get("fdv"), c), "bei Ausgabe aller Coins"]]},
        {"title": "Bewertung & Marktzyklus", "rows": [
            ["Allzeithoch", f"{fnum(m.get('ath'), 2)} {c}" if m.get("ath") else "–", m.get("ath_date") or ""],
            ["Abstand zum Allzeithoch", pct(m.get("ath_change")), ""],
            ["Mayer-Multiple (Kurs ÷ GD200)", fnum(m.get("mayer"), 2), "< 1 günstig · > 2,4 überhitzt"],
            ["52-Wochen-Spanne", f"{fnum(m.get('lo52'), 2)} – {fnum(m.get('hi52'), 2)}" if m.get("hi52") else "–", ""]]},
        {"title": "Risiko", "rows": [
            ["Volatilität 1 Jahr", pct(m.get("vol")), "Aktien zum Vergleich ca. 15–20 %"],
            ["Maximaler Rückgang 1 Jahr", pct(m.get("max_dd")), ""],
            ["Korrelation zu Bitcoin", fnum(m.get("corr_btc"), 2), "1 = bewegt sich genau wie Bitcoin"],
            ["Beta zu Bitcoin", fnum(m.get("beta_btc"), 2), "> 1 = stärkere Ausschläge als Bitcoin"]]},
        {"title": "Marktstimmung & Umfeld", "rows": [
            ["Crypto Fear & Greed Index", f"{m['fg']} / 100" if m.get("fg") is not None else "–", FG_DE.get(m.get("fg_class"), "")],
            ["US-10J-Rendite", "–" if mac["rf"] is None else fnum(mac["rf"], 2) + " %", "hohe Zinsen belasten Risikoanlagen"],
            ["Kurswährung", c, "Yahoo-Kürzel " + (ysym or "–")]]},
    ]
    desc = re.sub(r"<[^>]+>", "", (((cg or {}).get("description") or {}).get("de") or ((cg or {}).get("description") or {}).get("en") or "")).strip()
    if desc:
        desc = " ".join(re.split(r"(?<=[.!?])\s+", desc)[:3])
    comp = {"crypto": True, "own": own_peer or {"symbol": m["symbol"], "name": name, "currency": c, "mcap": m.get("mcap"),
                                               "perf_1y": m.get("perf_1y"), "perf_30d": m.get("perf_1m"), "ath_change": m.get("ath_change")},
            "peers": peers, "source": "CoinGecko (größte Kryptowährungen nach Marktwert, ohne Stablecoins)", "industry": "Kryptowährungen"}
    comp["own"]["own"] = True
    comp["summary"] = crypto_peer_summary(comp["own"], peers)
    alt_cur = "USD" if cur == "EUR" else "EUR"
    return {
        "asset": "crypto", "symbol": m["symbol"], "name": name, "exchange": "Krypto · 24/7", "currency": c, "price": m["price"],
        "sector": "Kryptowährung", "industry": (m["categories"][0] if m["categories"] else ""),
        "country": f"Rang #{m['rank']}" if m.get("rank") else "", "website": m["homepage"], "business": desc[:900],
        "alternatives": [{"symbol": f"{cr['base']}-{alt_cur}", "name": f"{name} in {alt_cur}", "exchange": "Krypto"}],
        "rating": {"label": label, "group": group, "score": round(total, 1),
                   "scale": [{"label": l_, "group": g_, "min": thr} for thr, l_, g_ in RATING_SCALE]},
        "summary": {"adjective": s_adj, "options": ADJ["summary"]},
        "categories": out_cats,
        "macro": {"score": round(cats["macro"]["score"], 3), "weight": CRYPTO_WEIGHTS["macro"], "reasons": cats["macro"]["reasons"]},
        "fundamentals": fundamentals,
        "facts": {k: m.get(k) for k in ("mcap", "rank", "vol24", "ath", "ath_change", "vol", "perf_1y", "perf_1m",
                                        "hi52", "lo52", "fg", "fg_class", "mayer")},
        "news": news, "notes": notes, "confidence": confidence, "events": [], "competitors": comp,
        "tech": safe(lambda: technicals(hist)),
        "generated": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "sources": ["Yahoo Finance", "CoinGecko", "alternative.me (Fear & Greed)", "Google News"],
    }


# ---------------------------------------------------------------------------
# ETFs: eigenes Schema (Kosten & Struktur, Bewertung der Bestände, Rendite, Risiko & Streuung)
# ---------------------------------------------------------------------------
ETF_WEIGHTS = {"valuation": .20, "quality": .25, "growth": .15, "risk": .15, "dividend": .05, "chart": .15,
               "sentiment": .05, "macro": 0.0}
SECTOR_DE = {"technology": "Technologie", "financial_services": "Finanzen", "healthcare": "Gesundheit",
             "industrials": "Industrie", "consumer_cyclical": "Zyklischer Konsum", "consumer_defensive": "Basiskonsum",
             "communication_services": "Kommunikation", "energy": "Energie", "basic_materials": "Grundstoffe",
             "utilities": "Versorger", "realestate": "Immobilien"}


def etf_short_name(name):
    """„iShares Core MSCI World UCITS ETF USD (Acc)“ -> „iShares Core MSCI World“ (für die News-Suche)."""
    n = re.split(r"\s+(?:UCITS|ETF)\b", name or "", maxsplit=1)[0]
    return n.strip(" -–") or name


def etf_price_metrics(m, hist):
    c = hist["Close"].dropna()
    c = c[c > 0]
    last = float(c.iloc[-1])
    m["last"] = last
    m["sma50"] = float(c.rolling(50).mean().iloc[-1]) if len(c) >= 50 else None
    m["sma200"] = float(c.rolling(200).mean().iloc[-1]) if len(c) >= 200 else None
    m["sma200_3m"] = float(c.rolling(200).mean().iloc[-64]) if len(c) >= 264 else None
    m["price_3m_ago"] = float(c.iloc[-64]) if len(c) > 64 else None

    def perf(n):
        return last / float(c.iloc[-n - 1]) - 1 if len(c) > n else None
    m["perf_1m"], m["perf_3m"], m["perf_6m"], m["perf_1y"] = perf(21), perf(63), perf(126), perf(252)
    years = (c.index[-1] - c.index[0]).days / 365.25
    m["data_years"] = years

    def cagr(y):
        n = int(round(252 * y))
        return (last / float(c.iloc[-n - 1])) ** (1 / y) - 1 if len(c) > n else None
    m["cagr3"], m["cagr5"], m["cagr10"] = cagr(3), cagr(5), cagr(10)
    m["cagr_all"] = (last / float(c.iloc[0])) ** (1 / years) - 1 if years >= 1 else None
    delta = c.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    m["rsi"] = float(100 - 100 / (1 + up.iloc[-1] / dn.iloc[-1])) if dn.iloc[-1] else 100.0
    y = c.iloc[-252:]
    m["vol"] = float(y.pct_change().dropna().std() * math.sqrt(252))
    m["hi52"], m["lo52"] = float(y.max()), float(y.min())
    m["max_dd"] = float((y / y.cummax() - 1).min())
    y5 = c.iloc[-252 * 5:]
    m["max_dd_5y"] = float((y5 / y5.cummax() - 1).min())


def etf_data(m, t, info):
    """Fondsdaten: Kosten, Volumen, Zusammensetzung, Bewertung der Bestände (Yahoo; auf Servern teils gesperrt)."""
    fd = safe(lambda: t.funds_data)
    ops = safe(lambda: fd.fund_operations) if fd is not None else None
    ter = num(info.get("netExpenseRatio"))
    m["ter"] = ter / 100 if ter is not None else None
    if m["ter"] is None and ops is not None and m["symbol"] in ops:
        m["ter"] = num(ops[m["symbol"]].get("Annual Report Expense Ratio"))
    m["aum"] = num(info.get("totalAssets"))
    m["family"] = info.get("fundFamily") or (safe(lambda: fd.fund_overview.get("family")) if fd is not None else None) or ""
    m["category"] = info.get("category") or (safe(lambda: fd.fund_overview.get("categoryName")) if fd is not None else None) or ""
    inc = num(info.get("fundInceptionDate"))
    m["inception"] = datetime.utcfromtimestamp(inc).strftime("%Y-%m-%d") if inc else None
    top = safe(lambda: fd.top_holdings) if fd is not None else None
    m["top"] = []
    if top is not None and not top.empty:
        for sym_, r in top.iterrows():
            w = num(r.get("Holding Percent"))
            if w is not None:
                m["top"].append({"symbol": str(sym_), "name": str(r.get("Name") or sym_), "weight": w})
    m["top10"] = sum(x["weight"] for x in m["top"][:10]) if m["top"] else None
    sw = safe(lambda: fd.sector_weightings) if fd is not None else None
    m["sectors"] = sorted(({"name": SECTOR_DE.get(k, k), "weight": num(v)} for k, v in (sw or {}).items()
                           if num(v)), key=lambda x: -x["weight"])
    m["max_sector"] = m["sectors"][0] if m["sectors"] else None
    ac = safe(lambda: fd.asset_classes) if fd is not None else None
    m["assets"] = {"Aktien": num((ac or {}).get("stockPosition")), "Anleihen": num((ac or {}).get("bondPosition")),
                   "Cash": num((ac or {}).get("cashPosition")), "Sonstiges": num((ac or {}).get("otherPosition"))}
    m["bond_etf"] = (m["assets"]["Anleihen"] or 0) > 0.5
    eq = safe(lambda: fd.equity_holdings) if fd is not None else None
    m["pe"] = m["pb"] = None
    if eq is not None and m["symbol"] in eq:
        ey, by = num(eq[m["symbol"]].get("Price/Earnings")), num(eq[m["symbol"]].get("Price/Book"))
        # Yahoo liefert hier den Kehrwert (Gewinnrendite): 0,045 -> KGV 22
        m["pe"] = 1 / ey if ey and 0 < ey < 1 else (ey if ey and ey >= 1 else None)
        m["pb"] = 1 / by if by and 0 < by < 1 else (by if by and by >= 1 else None)
    name = (m["name"] or "").lower()
    if re.search(r"\bacc\b|accumulat|thesaur|\(c\)", name):
        m["dist"] = "thesaurierend"
    elif re.search(r"\bdist\b|distribut|aussch|\(d\)", name):
        m["dist"] = "ausschüttend"
    else:
        m["dist"] = None


def e_valuation(m):
    if m["bond_etf"]:
        return {"score": None, "adjective": "fair bewertet",
                "reasons": ["Anleihen-ETF: Bewertung über KGV/KBV nicht sinnvoll – zählt nicht"]}
    parts, why = [], []
    if m["pe"]:
        parts.append((clamp((1 - m["pe"] / 20) * 1.5), 1.0))
        why.append(f"KGV der enthaltenen Aktien {fnum(m['pe'])} (Weltmarkt langfristig ~16–20)")
    if m["pb"]:
        parts.append((clamp(1 - m["pb"] / 3.0), 0.5))
        why.append(f"Kurs-Buchwert der Bestände {fnum(m['pb'], 2)}")
    if m.get("sma200") and m.get("last"):
        d200 = m["last"] / m["sma200"] - 1
        parts.append((clamp(-d200 / 0.15) * 0.5, 0.4))
        why.append(f"Abstand zur 200-Tage-Linie {pct(d200)} (stark darüber = kurzfristig heißgelaufen)")
    v = wavg(parts)
    if v is None:
        return {"score": None, "adjective": "fair bewertet", "reasons": why + ["Keine Bewertungsdaten der Bestände verfügbar"]}
    adj = ("günstig" if v >= 0.45 else "preiswert" if v >= 0.3 else "attraktiv bewertet" if v >= 0.15 else
           "angemessen bewertet" if v >= 0.05 else "fair bewertet" if v >= -0.05 else "marktgerecht" if v >= -0.15 else
           "ambitioniert bewertet" if v >= -0.3 else "teuer" if v >= -0.45 else "überbewertet")
    return {"score": v, "adjective": adj, "reasons": why}


def e_quality(m):
    parts, why = [], []
    if m["ter"] is not None:
        parts.append((clamp((0.0035 - m["ter"]) / 0.0025), 1.2))
        why.append(f"Laufende Kosten (TER) {pct(m['ter'], 2)} p. a. (unter 0,2 % günstig, über 0,5 % teuer)")
    else:
        why.append("TER nicht verfügbar – bitte beim Anbieter prüfen")
    if m["aum"]:
        a_ = m["aum"]
        parts.append((-0.8 if a_ < 1e8 else -0.2 if a_ < 5e8 else 0.2 if a_ < 1e9 else 0.6 if a_ < 1e10 else 0.9, 0.8))
        why.append(f"Fondsvolumen {money(a_, 'USD')}" + (" – unter 100 Mio.: erhöhtes Schließungsrisiko" if a_ < 1e8 else ""))
    age = None
    if m.get("inception"):
        age = (datetime.now() - datetime.strptime(m["inception"], "%Y-%m-%d")).days / 365.25
    elif m.get("data_years"):
        age = m["data_years"]
    if age is not None:
        parts.append((-0.3 if age < 3 else 0.0 if age < 5 else 0.3, 0.4))
        why.append(f"Alter {fnum(age, 1)} Jahre" + (" (kurze Historie)" if age < 3 else ""))
    if m["family"]:
        why.append(f"Anbieter: {m['family']}")
    q = wavg(parts)
    if q is None:
        return {"score": None, "adjective": "solide", "reasons": why}
    return {"score": q, "adjective": "robust" if q >= 0.5 else "solide" if q >= 0.2 else "stabil" if q >= -0.1 else "schwach",
            "reasons": why}


def e_growth(m):
    g = next((x for x in (m.get("cagr5"), m.get("cagr3"), m.get("cagr_all"), m.get("perf_1y")) if x is not None), None)
    why = [f"Rendite p. a. (inkl. Ausschüttungen): 3 J. {pct(m.get('cagr3'))} · 5 J. {pct(m.get('cagr5'))} · "
           f"10 J. {pct(m.get('cagr10'))}", f"Letzte 12 Monate {pct(m.get('perf_1y'))}"]
    if g is None:
        return {"score": None, "adjective": "reif", "reasons": why + ["Zu kurze Kurshistorie"]}
    adj = ("wachstumsstark" if g >= 0.12 else "dynamisch" if g >= 0.08 else "reif" if g >= 0.04 else
           "stagnierend" if g >= 0 else "rückläufig")
    return {"score": clamp((g - 0.07) / 0.07), "adjective": adj, "reasons": why}  # ~7 % p. a. = langfristiger Aktienschnitt


def e_risk(m):
    parts, why = [], []
    if m.get("vol") is not None:
        parts.append((clamp((0.22 - m["vol"]) / 0.10), 1.0))
        why.append(f"Volatilität 1 J. {pct(m['vol'])} (breiter Weltmarkt ~15 %)")
    if m.get("max_dd_5y") is not None:
        parts.append((clamp((0.35 + m["max_dd_5y"]) / 0.20), 0.6))
        why.append(f"Größter Rückgang in 5 J. {pct(m['max_dd_5y'])}")
    if m.get("top10") is not None:
        parts.append((clamp((0.45 - m["top10"]) / 0.25), 0.8))
        why.append(f"Top-10-Positionen = {pct(m['top10'])} des Fonds (unter 25 % breit gestreut, über 50 % konzentriert)")
    if m.get("max_sector"):
        ms = m["max_sector"]
        parts.append((clamp((0.45 - ms["weight"]) / 0.20), 0.5))
        why.append(f"Größte Branche: {ms['name']} {pct(ms['weight'])}")
    r = wavg(parts)
    if r is None:
        return {"score": None, "adjective": "berechenbar", "reasons": why}
    vol = m.get("vol") or 0.2
    adj = ("defensiv" if r >= 0.5 and vol < 0.12 else "schwankungsarm" if r >= 0.3 and vol < 0.16 else
           "berechenbar" if r >= 0.0 else "volatil" if r >= -0.4 else "riskant")
    return {"score": r, "adjective": adj, "reasons": why}


def e_dividend(m):
    y = m.get("div_yield") or 0
    if m["dist"] == "thesaurierend" or (m["dist"] is None and not y):
        return {"score": None, "adjective": "nicht anwendbar (thesaurierend)",
                "reasons": ["Thesaurierender ETF: Erträge werden automatisch wieder angelegt (in der Rendite enthalten)"]}
    why = [f"Ausschüttungsrendite (12 Monate) {pct(y, 2)}"]
    if y >= 0.03:
        return {"score": 0.5, "adjective": "ausschüttungsfreudig", "reasons": why}
    if y >= 0.015:
        return {"score": 0.3, "adjective": "verlässlich", "reasons": why}
    return {"score": 0.0, "adjective": "dividendenschwach", "reasons": why}


def analyze_etf(symbol, t, info, alternatives):
    name = info.get("longName") or info.get("shortName") or symbol
    m = {"symbol": symbol, "name": name, "currency": info.get("currency") or "", "price": current_price(info),
         "rec_mean": None, "n_analysts": 0, "rec_dist": None, "short_float": None, "mcap": None}
    short = etf_short_name(name)
    with ThreadPoolExecutor(max_workers=4) as ex:
        fh = ex.submit(lambda: t.history(period="max", auto_adjust=True))
        fd = ex.submit(etf_data, m, t, info)
        fnews = ex.submit(collect_news, symbol, short, "", (), ("ETF",))
        fmac = ex.submit(gather_macro, m["currency"])
        hist, news, mac = safe(fh.result), fnews.result(), fmac.result()
        safe(fd.result)
    if hist is not None and not hist.empty and len(hist) > 30:
        hist = hist[hist["Close"].notna() & (hist["Close"] > 0)]
        etf_price_metrics(m, hist)
        m["tech"] = safe(lambda: technicals(hist.iloc[-1300:]))
        m["data_since"] = hist.index[0].strftime("%d.%m.%Y")
        divs = safe(lambda: t.dividends)
        if divs is not None and len(divs):
            d_ = divs.copy()
            d_.index = d_.index.tz_localize(None) if d_.index.tz is not None else d_.index
            ttm_ = float(d_[d_.index >= datetime.now() - timedelta(days=365)].sum())
            raw_last = safe(lambda: float(t.history(period="5d", auto_adjust=False)["Close"].dropna().iloc[-1]))
            m["div_yield"] = ttm_ / raw_last if raw_last and ttm_ > 0 else 0.0
            if m["dist"] is None:
                m["dist"] = "ausschüttend" if ttm_ > 0 else "thesaurierend"
    else:
        for k in ("last", "sma50", "sma200", "sma200_3m", "price_3m_ago", "perf_1m", "perf_3m", "perf_6m", "perf_1y",
                  "rsi", "vol", "hi52", "lo52", "max_dd", "max_dd_5y", "cagr3", "cagr5", "cagr10", "cagr_all", "data_years"):
            m[k] = None
    m["price"] = m["price"] or m.get("last")
    for k in ("ter", "aum", "family", "category", "inception", "top", "top10", "sectors", "max_sector", "assets", "bond_etf",
              "pe", "pb", "dist"):
        m.setdefault(k, None if k not in ("top", "sectors") else [])
    m["assets"] = m["assets"] or {}

    cats = {"valuation": e_valuation(m), "quality": e_quality(m), "growth": e_growth(m), "risk": e_risk(m),
            "dividend": e_dividend(m), "chart": score_chart(m), "sentiment": score_sentiment(m, news, None)}
    total = (wavg([(cats[k]["score"], w) for k, w in ETF_WEIGHTS.items() if w and k in cats]) or 0.0) * 100
    notes = ["ETF-Modell: Bewertet werden Kosten und Struktur, die Bewertung der enthaltenen Aktien, die bisherige Rendite, "
             "Risiko und Streuung sowie der Kurstrend. Eine Kaufempfehlung bezieht sich auf den Zeitpunkt, "
             "nicht auf die Eignung als langfristiger Sparplan-Baustein."]
    if m["ter"] is None and not m["top"]:
        notes.append("Fondsdaten (TER, Zusammensetzung) waren nicht abrufbar – die Einschätzung stützt sich vor allem auf den Kursverlauf.")
    label, group = map_rating(total)
    s_adj = summary_adj(total, cats)
    have = sum(1 for x in (m["ter"], m["aum"], m["pe"], m["top10"], m.get("cagr5"), m.get("vol")) if x is not None)
    confidence = "hoch" if have >= 5 else "mittel" if have >= 3 else "niedrig"
    titles = {"valuation": "Bewertung der enthaltenen Aktien", "quality": "Kosten & Struktur",
              "growth": "Rendite (Wertentwicklung)", "risk": "Risiko und Streuung", "dividend": "Ausschüttung",
              "chart": "Kursentwicklung und Charttechnik", "sentiment": "Stimmung und Wahrnehmung"}
    out_cats = [{"key": k, "title": t_, "adjective": cats[k]["adjective"], "options": ADJ[k],
                 "score": None if cats[k]["score"] is None else round(cats[k]["score"], 3),
                 "weight": ETF_WEIGHTS[k] if not (k == "dividend" and cats[k]["score"] is None) else 0.0,
                 "reasons": cats[k]["reasons"]} for k, t_ in titles.items()]
    c = m["currency"]
    fundamentals = [
        {"title": "Kosten & Struktur", "rows": [
            ["Laufende Kosten (TER)", pct(m["ter"], 2) if m["ter"] is not None else "–", "pro Jahr, im Kurs enthalten"],
            ["Fondsvolumen", money(m["aum"], "USD"), "unter 100 Mio. = Schließungsrisiko"],
            ["Anbieter", m["family"] or "–", ""],
            ["Auflage", datetime.strptime(m["inception"], "%Y-%m-%d").strftime("%d.%m.%Y") if m["inception"] else "–",
             f"Kursdaten ab {m.get('data_since', '–')}"],
            ["Ertragsverwendung", (m["dist"] or "–").capitalize(), ""]]},
        {"title": "Rendite (inkl. wieder angelegter Ausschüttungen)", "rows": [
            ["12 Monate", pct(m.get("perf_1y")), ""], ["3 Jahre p. a.", pct(m.get("cagr3")), ""],
            ["5 Jahre p. a.", pct(m.get("cagr5")), ""], ["10 Jahre p. a.", pct(m.get("cagr10")), ""]]},
        {"title": "Risiko & Streuung", "rows": [
            ["Volatilität 1 Jahr", pct(m.get("vol")), "breiter Weltmarkt ca. 15 %"],
            ["Größter Rückgang 5 Jahre", pct(m.get("max_dd_5y")), ""],
            ["Anteil Top-10-Positionen", pct(m.get("top10")), "unter 25 % = breit gestreut"],
            ["Größte Branche", f"{m['max_sector']['name']} {pct(m['max_sector']['weight'])}" if m.get("max_sector") else "–", ""]]},
        {"title": "Bewertung der enthaltenen Aktien", "rows": [
            ["KGV", fnum(m["pe"]), "Weltmarkt langfristig ~16–20"], ["Kurs-Buchwert", fnum(m["pb"], 2), ""],
            ["Anlageklassen", " · ".join(f"{k} {pct(v, 0)}" for k, v in m["assets"].items() if v) or "–", ""]]},
        {"title": "Umfeld", "rows": [
            ["Handelswährung", c or "–", f"{mac['fx_pair']}: 12M {pct(mac['fx_chg'])} ggü. EUR" if mac.get("fx_pair") else "Euro"],
            ["US-10J-Rendite", "–" if mac["rf"] is None else fnum(mac["rf"], 2) + " %", ""]]},
    ]
    return {
        "asset": "etf", "symbol": symbol, "name": name, "exchange": info.get("fullExchangeName") or info.get("exchange") or "",
        "currency": c, "price": m["price"], "sector": "ETF", "industry": m["category"] or (m["family"] or ""),
        "country": "", "website": "", "business": "", "alternatives": alternatives,
        "rating": {"label": label, "group": group, "score": round(total, 1),
                   "scale": [{"label": l_, "group": g_, "min": thr} for thr, l_, g_ in RATING_SCALE]},
        "summary": {"adjective": s_adj, "options": ADJ["summary"]},
        "categories": out_cats,
        "macro": {"score": 0.0, "weight": 0.0, "reasons": ["Makro fließt bei ETFs über Rendite und Risiko ein"]},
        "fundamentals": fundamentals,
        "facts": {k: m.get(k) for k in ("ter", "aum", "pe", "perf_1y", "cagr5", "vol", "dist", "top10", "hi52", "lo52")},
        "etf": {"top": m["top"][:10], "sectors": m["sectors"], "assets": m["assets"], "family": m["family"]},
        "news": news, "notes": notes, "confidence": confidence, "events": [], "tech": m.get("tech"),
        "competitors": {"peers": [], "source": "", "industry": ""}, "profile": None,
        "model": {"key": "etf", "label": "ETF-Modell", "text": notes[0]},
        "generated": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "sources": ["Yahoo Finance (Kurse, Fondsdaten)", "Google News"],
    }


# ---------------------------------------------------------------------------
# Unternehmensprofil („Über“): Yahoo + Wikidata (ISIN, Gründung, CEO, Sitz) + OpenFIGI + Finnhub (Börsengang)
# ---------------------------------------------------------------------------
PROFILE_CACHE = {}
# Yahoo-Börsenkürzel -> Länderkennung der ISIN und Bloomberg-Börsencode (Composite) für OpenFIGI
SUFFIX_MARKET = {"": ("US", "US"), "DE": ("DE", "GR"), "F": ("DE", "GR"), "BE": ("DE", "GR"), "MU": ("DE", "GR"),
                 "SG": ("DE", "GR"), "HM": ("DE", "GR"), "DU": ("DE", "GR"), "HA": ("DE", "GR"), "L": ("GB", "LN"),
                 "PA": ("FR", "FP"), "AS": ("NL", "NA"), "MI": ("IT", "IM"), "SW": ("CH", "SW"), "CO": ("DK", "DC"),
                 "ST": ("SE", "SS"), "HE": ("FI", "FH"), "OL": ("NO", "NO"), "MC": ("ES", "SM"), "VI": ("AT", "AV"),
                 "BR": ("BE", "BB"), "LS": ("PT", "PL"), "IR": ("IE", "ID"), "TO": ("CA", "CN"), "V": ("CA", "CN"),
                 "T": ("JP", "JP"), "HK": ("HK", "HK"), "AX": ("AU", "AU")}


COUNTRY_DE = {"United States": "USA", "Germany": "Deutschland", "United Kingdom": "Großbritannien",
              "France": "Frankreich", "Netherlands": "Niederlande", "Switzerland": "Schweiz", "Denmark": "Dänemark",
              "Sweden": "Schweden", "Finland": "Finnland", "Norway": "Norwegen", "Spain": "Spanien", "Italy": "Italien",
              "Austria": "Österreich", "Belgium": "Belgien", "Ireland": "Irland", "Japan": "Japan", "China": "China",
              "Taiwan": "Taiwan", "South Korea": "Südkorea", "Canada": "Kanada", "Australia": "Australien",
              "Hong Kong": "Hongkong", "Luxembourg": "Luxemburg", "Portugal": "Portugal", "Israel": "Israel",
              "India": "Indien", "Brazil": "Brasilien"}


def _plain_name(s):
    return re.sub(r"[^a-z0-9 ]", " ", (s or "").lower().replace("&", " and ")).split()


def wikidata_company(ticker, company, isin_cc):
    """Stammdaten über das Börsenkürzel aus Wikidata; nur wenn der Firmenname passt."""
    variants = {ticker, ticker.replace("-", " "), ticker.replace("-", "."), ticker.replace("-", "")}
    vals = " ".join('"%s"' % v.replace('"', "") for v in variants)
    q = '''SELECT ?c ?cLabel ?isin ?inc ?ceoLabel ?hqLabel ?web WHERE {
      VALUES ?t { %s } ?c p:P414 ?st. ?st pq:P249 ?t.
      OPTIONAL { ?c wdt:P946 ?isin }
      OPTIONAL { ?c wdt:P571 ?inc }
      OPTIONAL { ?c p:P169 ?cs. ?cs ps:P169 ?ceo. FILTER NOT EXISTS { ?cs pq:P582 ?end } }
      OPTIONAL { ?c wdt:P159 ?hq }
      OPTIONAL { ?c wdt:P856 ?web }
      SERVICE wikibase:label { bd:serviceParam wikibase:language "de,en". } } LIMIT 80''' % vals
    url = "https://query.wikidata.org/sparql?format=json&query=" + urllib.parse.quote(q)
    req = urllib.request.Request(url, headers={"User-Agent": "Aktien-Check/1.0 (private Analyse-App)"})
    with urllib.request.urlopen(req, timeout=12) as r:
        rows = json.loads(r.read())["results"]["bindings"]
    want = _plain_name(company)
    if not want:
        return None
    best = {}
    for b in rows:
        v = {k: x["value"] for k, x in b.items()}
        got = _plain_name(v.get("cLabel"))
        # Erster Namensbestandteil muss übereinstimmen (verhindert z. B. SAP -> Sappi, ALV -> Autoliv/Allianz)
        if not got or got[0] != want[0]:
            continue
        e = best.setdefault(v["c"], {"isins": set(), "inc": None, "ceo": None, "hq": None, "web": None})
        e["web"] = e["web"] or v.get("web")
        if v.get("isin"):
            e["isins"].add(v["isin"])
        e["inc"] = e["inc"] or v.get("inc")
        if v.get("ceoLabel") and not re.fullmatch(r"Q\d+", v["ceoLabel"]):
            e["ceo"] = e["ceo"] or v["ceoLabel"]
        if v.get("hqLabel") and not re.fullmatch(r"Q\d+", v["hqLabel"]):
            e["hq"] = e["hq"] or v["hqLabel"]
    if len(best) != 1:
        return None  # nicht eindeutig -> lieber nichts anzeigen
    e = next(iter(best.values()))
    isins = sorted(e["isins"], key=lambda i: (not i.startswith(isin_cc), i))
    return {"isins": isins, "founded": e["inc"][:4] if e["inc"] and e["inc"][:1] != "-" else None,
            "ceo": e["ceo"], "hq": e["hq"], "website": e["web"]}


def openfigi_map(id_type, value, exch):
    body = json.dumps([{"idType": id_type, "idValue": value, "exchCode": exch, "marketSecDes": "Equity"}]).encode()
    req = urllib.request.Request("https://api.openfigi.com/v3/mapping", data=body,
                                 headers={**UA, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return (json.loads(r.read()) or [{}])[0].get("data") or []


def verified_isin(isins, ticker, exch):
    """Wikidata kennt oft mehrere ISINs (z. B. A- und B-Aktie) -> per OpenFIGI die zum Kürzel passende wählen."""
    want = ticker.replace("-", "/").upper()
    for isin in isins[:3]:
        data = safe(lambda: openfigi_map("ID_ISIN", isin, exch)) if exch else None
        if data and any((d.get("ticker") or "").upper() == want for d in data):
            return isin, True
    return (isins[0], False) if len(isins) == 1 else (None, False)


def openfigi(ticker, exch):
    """Composite-FIGI des Börsenplatzes (frei nutzbare OpenFIGI-Schnittstelle)."""
    body = json.dumps([{"idType": "TICKER", "idValue": ticker.replace("-", "/"), "exchCode": exch,
                        "marketSecDes": "Equity"}]).encode()
    req = urllib.request.Request("https://api.openfigi.com/v3/mapping", data=body,
                                 headers={**UA, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        data = (json.loads(r.read()) or [{}])[0].get("data") or []
    return data[0].get("compositeFIGI") or data[0].get("figi") if data else None


def company_profile(symbol, info, company):
    hit = PROFILE_CACHE.get(symbol)
    if hit and time.time() - hit[0] < 7 * 86400:
        return hit[1]
    base, _, suf = symbol.partition(".")
    isin_cc, exch = SUFFIX_MARKET.get(suf, (None, None))
    wd = safe(lambda: wikidata_company(base, company, isin_cc or "")) or {}
    figi = safe(lambda: openfigi(base, exch)) if exch else None
    fh = (safe(lambda: finnhub("stock/profile2", symbol=symbol)) or {}) if not suf else {}
    # CEO: Yahoo ist aktueller als Wikidata
    ceo = None
    for o in info.get("companyOfficers") or []:
        title = o.get("title") or ""
        if re.search(r"\bCEO\b|Chief Executive", title) and not re.search(r"\b(Former|Ex-)\b", title):
            nm = re.sub(r"^(Mr|Ms|Mrs|Dr|Prof)\.?\s+", "", re.sub(r"\s+", " ", o.get("name") or ""))
            # Abschlüsse/Titel am Ende entfernen (z. B. „B.A.“, „Ph.D.“, „CPA“)
            nm = re.sub(r"(,?\s+(?:[A-Z][a-zA-Z]{0,3}\.){1,4}|,?\s+(?:CPA|CFA|MBA|BSc|MSc))+$", "", nm).strip(" ,")
            ceo = nm or None
            break
    ceo = ceo or wd.get("ceo")
    hq = wd.get("hq") or info.get("city")
    country = COUNTRY_DE.get(info.get("country") or "", info.get("country") or "")
    isin, isin_ok = verified_isin(wd.get("isins") or [], base, exch)
    ipo, ipo_label = None, "Börsengang"
    if fh.get("ipo"):
        ipo = fh["ipo"]
    else:
        ms = num(info.get("firstTradeDateMilliseconds"))
        if ms:
            ipo, ipo_label = datetime.utcfromtimestamp(ms / 1000).strftime("%Y-%m-%d"), "Erster Handelstag"
    out = {
        "sector": info.get("sector") or "", "industry": info.get("industry") or fh.get("finnhubIndustry") or "",
        "ceo": ceo, "website": info.get("website") or fh.get("weburl") or wd.get("website") or "",
        "hq": ", ".join(x for x in (hq, country) if x) or None,
        "founded": wd.get("founded"), "ipo": ipo, "ipo_label": ipo_label,
        "employees": num(info.get("fullTimeEmployees")),
        "isin": isin,
        # ISIN einer anderen Börse (z. B. US-Hinterlegungsschein auf eine deutsche Aktie)
        "isin_home": bool(isin and not isin_ok and isin_cc and not isin.startswith(isin_cc)),
        "cusip": isin[2:11] if isin and isin[:2] in ("US", "CA") else None,
        "figi": figi,
        "sources": [s for s, ok in (("Yahoo Finance", True), ("Wikidata", bool(wd)), ("OpenFIGI", bool(figi)),
                                    ("Finnhub", bool(fh))) if ok],
    }
    PROFILE_CACHE[symbol] = (time.time(), out)
    return out


CACHE = {}


def analyze(query):
    key = query.strip().lower()
    if key in CACHE and time.time() - CACHE[key][0] < 900:
        return CACHE[key][1]
    cr = resolve_crypto(query)
    if cr:
        result = analyze_crypto(cr)
        CACHE[key] = (time.time(), result)
        return result
    symbol, t, info, alternatives = resolve(query)
    if info.get("quoteType") == "ETF":
        result = analyze_etf(symbol, t, info, alternatives)
        CACHE[key] = (time.time(), result)
        return result
    with ThreadPoolExecutor(max_workers=4) as ex:
        fm = ex.submit(gather, symbol, t, info)
        fmac = ex.submit(gather_macro, info.get("currency") or "")
        company = clean_company_name(info.get("longName") or info.get("shortName") or symbol)
        siblings = sibling_names(company, symbol)
        fnews = ex.submit(collect_news, symbol, company, info.get("website") or "", siblings)
        ftgt = ex.submit(news_targets, company, info.get("currency") or "", current_price(info), siblings)
        fev = ex.submit(company_events, symbol, alternatives, info.get("currency") or "")
        fpeer = ex.submit(competitors, symbol, info, alternatives)
        fprof = ex.submit(company_profile, symbol, info, company)
        m, mac, news, tgt = fm.result(), fmac.result(), fnews.result(), ftgt.result()
        events = safe(lambda: fev.result(timeout=30), []) or []
        comp = safe(lambda: fpeer.result(timeout=45), {}) or {"peers": [], "source": "", "industry": ""}
        profile = safe(lambda: fprof.result(timeout=30))
    finnhub_enrich(m, symbol, alternatives)
    own_row = {"symbol": symbol, "name": m["name"], "currency": m["currency"], "mcap": m["mcap"],
               "pe": m["pe"] if (m["pe"] or 0) > 0 else None, "op_m": m["op_m"],
               "growth": m["rev_g"] if m["rev_g"] is not None else m["rev_cagr"], "own": True}
    comp["own"] = own_row
    comp["summary"] = peer_summary(own_row, comp["peers"])
    if comp["summary"]["pe"]["n"] >= 3:
        m["peer_pe_med"], m["peer_n"] = comp["summary"]["pe"]["median"], comp["summary"]["pe"]["n"]
    m["target_n"], m["target_src"], m["target_items"] = 0, "", tgt["items"]
    if m["upside"] is None and tgt["n"] >= 2:
        m["target"] = tgt["median"]
        m["upside"] = tgt["median"] / m["price"] - 1
        m["target_n"] = tgt["n"]
        m["target_src"] = f"Median aus {tgt['n']} Analysten-Kurszielen in Nachrichten, 90 Tage"

    cats = {}
    cats["valuation"] = score_valuation(m, mac)
    cats["quality"] = score_quality(m)
    cats["growth"] = score_growth(m)
    cats["risk"] = score_risk(m)
    cats["dividend"] = score_dividend(m)
    cats["chart"] = score_chart(m)
    cats["sentiment"] = score_sentiment(m, news, cats["valuation"]["score"])
    cats["macro"] = score_macro(m, mac)

    total = wavg([(cats[k]["score"], w) for k, w in WEIGHTS.items()]) or 0.0
    total *= 100
    notes = []
    vs, qs = cats["valuation"]["score"], cats["quality"]["score"]
    if vs is not None and vs <= -0.45 and total > 14:
        total = 14
        notes.append("Deckel: Bewertung sehr hoch – auch ein Spitzenunternehmen ist zu diesem Preis kein Kauf.")
    if qs is not None and qs <= -0.5 and total > 14:
        total = 14
        notes.append("Deckel: Unternehmensqualität zu schwach für eine Kaufempfehlung.")
    biz = m["biz"]
    if biz == "pre_revenue" and total > 9:
        total = 9
        notes.append("Deckel: Vorumsatz-Unternehmen – ohne nennenswerte Umsätze höchstens „Market Perform“.")
    if biz != "standard":
        notes.insert(0, f"{BIZ_MODELS[biz][0]}: {BIZ_MODELS[biz][1]}")
    label, group = map_rating(total)
    s_adj = summary_adj(total, cats)

    available = sum(1 for k in ("pe", "ev_ebitda", "fcf", "op_m", "roe", "rev_cagr", "nd_ebitda", "vol",
                                "rec_mean", "pe_hist_med") if m.get(k) is not None)
    confidence = "hoch" if available >= 8 and news["count_trusted"] >= 5 else "mittel" if available >= 5 else "niedrig"

    titles = {"valuation": "Bewertung (Preis im Verhältnis zum Wert)", "quality": "Qualität des Unternehmens",
              "growth": "Wachstum", "risk": "Risiko und Schwankung", "dividend": "Dividende und Ausschüttung",
              "chart": "Kursentwicklung und Charttechnik", "sentiment": "Stimmung und Wahrnehmung"}
    out_cats = []
    for k, title in titles.items():
        c = cats[k]
        out_cats.append({"key": k, "title": title, "adjective": c["adjective"], "options": ADJ[k],
                         "score": None if c["score"] is None else round(c["score"], 3),
                         "weight": WEIGHTS[k], "reasons": c["reasons"]})
    result = {
        "symbol": symbol, "name": m["name"], "exchange": m["exchange"], "currency": m["currency"],
        "price": m["price"], "sector": m["sector"], "industry": m["industry"], "country": m["country"],
        "website": m["website"], "business": m["summary_text"][:900], "alternatives": alternatives,
        "rating": {"label": label, "group": group, "score": round(total, 1),
                   "scale": [{"label": l, "group": g, "min": thr} for thr, l, g in RATING_SCALE]},
        "summary": {"adjective": s_adj, "options": ADJ["summary"]},
        "categories": out_cats,
        "macro": {"score": round(cats["macro"]["score"], 3), "weight": WEIGHTS["macro"], "reasons": cats["macro"]["reasons"]},
        "fundamentals": build_fundamentals(m, mac),
        "facts": {k: m.get(k) for k in ("mcap", "pe", "fpe", "fcf_yield", "div_yield", "perf_1y", "perf_1m",
                                        "upside", "target", "beta", "hi52", "lo52", "n_analysts", "rec_mean",
                                        "ev_ebitda", "vol")} | ({"ev_ebitda": None} if m["is_financial"] else {}),
        "news": news, "notes": notes, "confidence": confidence, "events": events, "competitors": comp,
        "tech": m.get("tech"),
        "profile": profile,
        "model": {"key": m["biz"], "label": BIZ_MODELS[m["biz"]][0], "text": BIZ_MODELS[m["biz"]][1]},
        "fair": m.get("fair"),
        "checklist": safe(lambda: checklist(m, cats), []) or [],
        "valchart": m.get("valchart"), "balance": m.get("balance"), "divhist": m.get("divhist"),
        "holders": m.get("holders"), "eps_quarters": m.get("eps_quarters"),
        "targets": {"low": m.get("target_low"), "high": m.get("target_high"), "mean": m.get("target"),
                    "median": m.get("target_median"), "n": m.get("n_analysts"), "hist": m.get("rec_hist"),
                    "items": m.get("target_items") or [], "src": m.get("target_src") or ""},
        "forecast": {"rev": m.get("est_rev") or {}, "eps": m.get("est_eps") or {}, "n": est_analysts(m),
                     "fpe": m.get("fpe"), "currency": m["currency"]},
        "generated": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "sources": ["Yahoo Finance"] + (["Finnhub"] if m["finnhub"] else [])
                   + (["Analysten-Schlagzeilen"] if m.get("target_n") else []) + ["Google News", "Pressedienste"],
    }
    CACHE[key] = (time.time(), result)
    if len(CACHE) > 40:
        safe(prune_caches)
    return result


# ---------------------------------------------------------------------------
# Webserver
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Preisalarme mit Push über ntfy (https://ntfy.sh)
# ---------------------------------------------------------------------------
ALERT_FILE = Path(__file__).with_name("alerts.json")
GIST_DESCRIPTION = "aktien-check-alerts (automatisch verwaltet)"   # alter, unverschlüsselter Speicher
GIST_DESCRIPTION_ENC = "aktien-check-data (verschlüsselt, automatisch verwaltet)"
ENC_MARK = "fernet-v1"
CHECK_INTERVAL = 600          # Sekunden zwischen Kursprüfungen
RATING_INTERVAL = 12 * 3600   # Empfehlungswechsel höchstens alle 12 Std. prüfen (volle Analyse)


def github_token():
    return (os.environ.get("GITHUB_TOKEN") or "").strip()


def gh_api(method, path, body=None):
    req = urllib.request.Request(
        "https://api.github.com" + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {github_token()}", "Accept": "application/vnd.github+json",
                 "User-Agent": "aktien-check", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read() or b"null")


def store_key():
    """Schlüssel aus STORE_KEY (mind. 16 Zeichen). Ohne Schlüssel wird unverschlüsselt gespeichert."""
    raw = (os.environ.get("STORE_KEY") or "").strip()
    if len(raw) < 16:
        return None
    import base64
    return base64.urlsafe_b64encode(hashlib.sha256(("aktien-check-store|" + raw).encode("utf-8")).digest())


def encrypt_text(text, key):
    from cryptography.fernet import Fernet
    return json.dumps({"enc": ENC_MARK, "data": Fernet(key).encrypt(text.encode("utf-8")).decode("ascii")})


def decrypt_text(text, key):
    """Gibt (Klartext, war_verschlüsselt) zurück. Wirft ValueError bei fehlendem/falschem Schlüssel."""
    try:
        obj = json.loads(text or "{}")
    except ValueError:
        obj = None
    if not (isinstance(obj, dict) and obj.get("enc") == ENC_MARK):
        return text or "{}", False
    if not key:
        raise ValueError("Speicher ist verschlüsselt, aber STORE_KEY fehlt")
    from cryptography.fernet import Fernet, InvalidToken
    try:
        return Fernet(key).decrypt(obj["data"].encode("ascii")).decode("utf-8"), True
    except InvalidToken:
        raise ValueError("STORE_KEY passt nicht zum gespeicherten Datenbestand")


class AlertStore:
    """Dauerhafter Speicher: privates GitHub-Gist (wenn GITHUB_TOKEN gesetzt) oder lokale Datei.

    Mit STORE_KEY wird der Inhalt verschlüsselt (Fernet/AES). Beim ersten Start mit Schlüssel wird ein neues,
    verschlüsseltes Gist angelegt und erst nach erfolgreicher Kontrolle das alte Klartext-Gist samt Versionsverlauf
    gelöscht. Konnte der Speicher nicht gelesen werden, ist Schreiben gesperrt (kein Überschreiben mit leeren Daten).
    """

    def __init__(self):
        self.lock = threading.RLock()
        self.data = None
        self.gist_id = None
        self.plain_gist_id = None   # altes, unverschlüsseltes Gist (wird nach Migration gelöscht)
        self.error = ""
        self.dirty = False          # ungespeicherte Änderungen (Verlauf wird gebündelt geschrieben)
        self.locked = False         # Schreiben gesperrt, weil Lesen fehlgeschlagen ist
        self.loaded_at = 0
        self.encrypted = False      # aktueller Bestand liegt verschlüsselt vor

    @property
    def backend(self):
        return "gist" if github_token() else "file"

    @property
    def persistent(self):
        # Auf Render ist das Dateisystem flüchtig -> nur das Gist ist dauerhaft
        return self.backend == "gist" or "RENDER" not in os.environ

    def _find_gists(self):
        found = {}
        for page in range(1, 4):
            batch = gh_api("GET", f"/gists?per_page=100&page={page}") or []
            for g in batch:
                if g.get("description") in (GIST_DESCRIPTION, GIST_DESCRIPTION_ENC):
                    found.setdefault(g["description"], g["id"])
            if len(batch) < 100:
                break
        return found.get(GIST_DESCRIPTION_ENC), found.get(GIST_DESCRIPTION)

    def _read_gist(self, gid):
        g = gh_api("GET", f"/gists/{gid}")
        f = g["files"]["alerts.json"]
        if f.get("truncated"):  # große Dateien liefert die API nur gekürzt -> Rohdaten nachladen
            req = urllib.request.Request(f["raw_url"], headers={"Authorization": f"Bearer {github_token()}",
                                                                "User-Agent": "aktien-check"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.read().decode("utf-8")
        return f["content"]

    def load(self):
        with self.lock:
            if self.data is not None and not (self.locked and time.time() - self.loaded_at > 60):
                return self.data
            data, key = {}, store_key()
            self.loaded_at = time.time()
            try:
                raw = None
                if self.backend == "gist":
                    enc_id, plain_id = self._find_gists()
                    if enc_id:
                        self.gist_id, raw = enc_id, self._read_gist(enc_id)
                        self.plain_gist_id = plain_id  # Rest einer abgebrochenen Migration
                    elif plain_id:
                        self.gist_id, raw = plain_id, self._read_gist(plain_id)
                        self.plain_gist_id = plain_id
                elif ALERT_FILE.exists():
                    raw = ALERT_FILE.read_text(encoding="utf-8")
                text, self.encrypted = decrypt_text(raw, key) if raw is not None else ("{}", False)
                data = json.loads(text or "{}")
                self.locked, self.error = False, ""
            except Exception as e:
                self.locked = True
                self.error = (str(e) if isinstance(e, ValueError) else f"Speicher nicht lesbar: {type(e).__name__}") \
                    + " – Änderungen werden nicht gespeichert."
                data = self.data or {}
            data.setdefault("users", {})
            data.setdefault("u", {})
            data.setdefault("last_check", None)
            if any(k in data for k in ("alerts", "topic", "history")):  # altes Einzelbenutzer-Format -> Konto "admin"
                sp = data["u"].setdefault("admin", {})
                sp.setdefault("alerts", data.pop("alerts", {}))
                if "topic" in data:
                    sp.setdefault("topic", data.pop("topic"))
                sp.setdefault("history", data.pop("history", {}))
            self.data = data
            # Mit Schlüssel, aber noch Klartext gespeichert -> sofort verschlüsselt umziehen
            migrate = not self.locked and key and (not self.encrypted or self.plain_gist_id)
            if migrate:
                self.save()
            # Protokoll ohne Inhalte – nur der Zustand des Speichers
            state = "GESPERRT" if self.locked else ("verschlüsselt" if self.encrypted else "unverschlüsselt")
            (LOG.error if self.error else LOG.info)(f"[Speicher] {self.backend} · {state}"
                  f" · Schlüssel {'gesetzt' if key else 'fehlt'} · Benutzer: {len(data['users'])}"
                  f" · altes Klartext-Gist: {'vorhanden' if self.plain_gist_id else 'keins'}"
                  f"{' · Umzug durchgeführt' if migrate and not self.error else ''}"
                  f"{' · FEHLER: ' + self.error if self.error else ''}")
            return data

    def save(self):
        with self.lock:
            if self.data is None or self.locked:
                return
            self.dirty = False
            key = store_key()
            content = json.dumps(self.data, ensure_ascii=False, separators=(",", ":"))
            stored = encrypt_text(content, key) if key else content
            try:
                if self.backend == "gist":
                    files = {"alerts.json": {"content": stored}}
                    if key and (not self.gist_id or self.gist_id == self.plain_gist_id):
                        # neues verschlüsseltes Gist anlegen und kontrollieren, dann Klartext-Gist löschen
                        g = gh_api("POST", "/gists", {"description": GIST_DESCRIPTION_ENC, "public": False, "files": files})
                        check, _ = decrypt_text(self._read_gist(g["id"]), key)
                        if json.loads(check) != json.loads(content):
                            raise RuntimeError("Kontrolle des verschlüsselten Speichers fehlgeschlagen")
                        old, self.gist_id = self.plain_gist_id, g["id"]
                        if old:
                            gh_api("DELETE", f"/gists/{old}")
                            self.plain_gist_id = None
                    elif key and self.plain_gist_id:
                        gh_api("PATCH", f"/gists/{self.gist_id}", {"files": files})
                        gh_api("DELETE", f"/gists/{self.plain_gist_id}")
                        self.plain_gist_id = None
                    elif self.gist_id:
                        gh_api("PATCH", f"/gists/{self.gist_id}", {"files": files})
                    else:
                        g = gh_api("POST", "/gists", {"description": GIST_DESCRIPTION, "public": False, "files": files})
                        self.gist_id = g["id"]
                        self.plain_gist_id = g["id"]
                else:
                    ALERT_FILE.write_text(stored, encoding="utf-8")
                self.encrypted = bool(key)
                self.error = ""
            except Exception as e:
                self.dirty = True
                self.error = f"Speichern fehlgeschlagen: {type(e).__name__}"
                LOG.error("[Speicher] Speichern fehlgeschlagen (%s): %s", self.backend, e)


STORE = AlertStore()
CHECK_LOCK = threading.Lock()
HISTORY_MAX_POINTS = 250    # Tage je Aktie
HISTORY_MAX_SYMBOLS = 60


USER_RE = re.compile(r"[a-z0-9_-]{2,32}")


def new_topic():
    return "aktien-check-" + secrets.token_urlsafe(12).replace("_", "-").lower()


def user_space(user):
    """Datenbereich eines Benutzers: Alarme, ntfy-Thema, Verlauf, Watchlist."""
    data = STORE.load()
    with STORE.lock:
        sp = data["u"].setdefault(user, {})
        sp.setdefault("alerts", {})
        sp.setdefault("history", {})
        sp.setdefault("watchlist", [])
        if not sp.get("topic"):
            sp["topic"] = new_topic()
        return sp


def hash_pw(pw, salt=None, iterations=200_000):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), bytes.fromhex(salt), iterations).hex()
    return f"pbkdf2${iterations}${salt}${h}"


def check_pw(pw, stored):
    try:
        _, it, salt, h = stored.split("$")
        return hmac.compare_digest(hash_pw(pw, salt, int(it)).split("$")[3], h)
    except Exception:
        return False


def users():
    data = STORE.load()
    with STORE.lock:
        u = data["users"]
        if "admin" not in u:  # Admin-Konto: meldet sich (auch) mit APP_PASSWORD an
            u["admin"] = {"pw": None, "admin": True, "created": time.time(), "ver": 0}
        return u


def authenticate(username, password):
    acc = users().get(username)
    if not acc or not password:
        return False
    if username == "admin" and app_password() and hmac.compare_digest(password.encode("utf-8"), app_password().encode("utf-8")):
        return True  # APP_PASSWORD bleibt als Notfallzugang für den Admin gültig
    return bool(acc.get("pw")) and check_pw(password, acc["pw"])


def save_async():
    threading.Thread(target=lambda: safe(STORE.save), daemon=True).start()


def record_history(res, user):
    """Speichert Score/Empfehlung/Kurs der Analyse (ein Punkt pro Tag) für den Benutzer und liefert den Verlauf."""
    sp = user_space(user)
    sym, today = res["symbol"], datetime.now().strftime("%Y-%m-%d")
    entry = [today, round(res["rating"]["score"], 1), res["rating"]["label"],
             round(res["price"], 4) if res.get("price") else None]
    with STORE.lock:
        hist = sp["history"]
        pts = hist.setdefault(sym, [])
        if pts and pts[-1][0] == today:
            pts[-1] = entry
        else:
            pts.append(entry)
        del pts[:-HISTORY_MAX_POINTS]
        sig = signals_of(sp)
        last = next((x for x in reversed(sig) if x[0] == sym), None)
        group = res["rating"].get("group") or label_group(entry[2])
        if entry[3] and (last is None or last[3] != group):
            sig.append([sym, today, entry[2], group, entry[3]])  # neues Signal: erste Analyse oder Gruppenwechsel
            del sig[:-SIGNALS_MAX]
        if len(hist) > HISTORY_MAX_SYMBOLS:  # am längsten nicht analysierte Aktien zuerst verwerfen
            for old in sorted(hist, key=lambda k: hist[k][-1][0] if hist[k] else "")[: len(hist) - HISTORY_MAX_SYMBOLS]:
                if old != sym:
                    hist.pop(old, None)
        STORE.dirty = True
        return [list(x) for x in pts]


# ---------------------------------------------------------------------------
# Trefferquote: Wie haben sich die Empfehlungen seitdem entwickelt (vs. Heimatindex)?
# ---------------------------------------------------------------------------
SIGNALS_MAX = 600
TRACK_CACHE = {}
BENCH_BY_SUFFIX = {"": ("^GSPC", "S&P 500"), "DE": ("^GDAXI", "DAX"), "F": ("^GDAXI", "DAX"), "BE": ("^GDAXI", "DAX"),
                   "MU": ("^GDAXI", "DAX"), "SG": ("^GDAXI", "DAX"), "HM": ("^GDAXI", "DAX"), "DU": ("^GDAXI", "DAX"),
                   "HA": ("^GDAXI", "DAX"), "L": ("^FTSE", "FTSE 100"), "PA": ("^FCHI", "CAC 40"),
                   "SW": ("^SSMI", "SMI"), "AS": ("^AEX", "AEX"), "MI": ("FTSEMIB.MI", "FTSE MIB"),
                   "T": ("^N225", "Nikkei 225"), "HK": ("^HSI", "Hang Seng"), "TO": ("^GSPTSE", "TSX"),
                   "AX": ("^AXJO", "ASX 200")}
TRACK_HORIZONS = (("1M", 30), ("3M", 91), ("6M", 182), ("12M", 365))


def label_group(label):
    return next((g for _, l_, g in RATING_SCALE if l_ == label), "")


def is_crypto_symbol(sym):
    return bool(re.fullmatch(r"[A-Z0-9]+-(USD|EUR)", sym))


def benchmark_for(sym):
    if is_crypto_symbol(sym):
        return None, ""
    suf = sym.partition(".")[2]
    return BENCH_BY_SUFFIX.get(suf, ("^STOXX", "STOXX Europe 600"))


def signals_of(sp):
    """Signal-Liste [Symbol, Datum, Stufe, Gruppe, Kurs]; beim ersten Mal aus dem bisherigen Verlauf aufgebaut."""
    if "signals" not in sp:
        sig = []
        for sym, pts in (sp.get("history") or {}).items():
            last = None
            for d, _score, label, price in pts:
                g = label_group(label)
                if price and g and g != last:
                    sig.append([sym, d, label, g, price])
                    last = g
        sp["signals"] = sorted(sig, key=lambda x: x[1])[-SIGNALS_MAX:]
    return sp["signals"]


def price_table(symbols, start):
    """Tagesschlusskurse ab start für mehrere Werte: {Symbol: pandas.Series}."""
    out = {}
    for sym in symbols:
        h = safe(lambda: yf.Ticker(sym).history(start=start, interval="1d", auto_adjust=False))
        if h is not None and not h.empty:
            c = h["Close"].dropna()
            c.index = [ts.tz_localize(None) if ts.tzinfo else ts for ts in c.index]
            out[sym] = c
    return out


def asof(series, day):
    import pandas as pd
    if series is None or series.empty:
        return None
    sub = series[series.index <= pd.Timestamp(day) + pd.Timedelta(hours=23)]
    return float(sub.iloc[-1]) if len(sub) else None


def track_record(signals):
    """Wertet Signale aus: Rendite seit Signal, je Horizont, und Überrendite gegenüber dem Heimatindex."""
    if not signals:
        return {"signals": [], "groups": {}, "horizons": {}, "since": None}
    start = (datetime.strptime(min(x[1] for x in signals), "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
    syms = sorted({x[0] for x in signals})
    benches = sorted({benchmark_for(x)[0] for x in syms if benchmark_for(x)[0]})
    px = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        for part in ex.map(lambda sym: price_table([sym], start), syms + benches):
            px.update(part)
    today = datetime.now().strftime("%Y-%m-%d")
    rows = []
    by_sym = {}
    for x in sorted(signals, key=lambda x: x[1]):
        by_sym.setdefault(x[0], []).append(x)
    for sym, sigs in by_sym.items():
        b_sym, b_name = benchmark_for(sym)
        ser, bser = px.get(sym), px.get(b_sym) if b_sym else None
        for i, (_, d, label, group, p0) in enumerate(sigs):
            end = sigs[i + 1][1] if i + 1 < len(sigs) else today
            p_end = asof(ser, end)
            b0, b_end = asof(bser, d), asof(bser, end)
            ret = p_end / p0 - 1 if p_end and p0 else None
            bret = b_end / b0 - 1 if b_end and b0 else None
            hz = {}
            age = (datetime.now() - datetime.strptime(d, "%Y-%m-%d")).days
            for key, days in TRACK_HORIZONS:
                if age >= days:
                    t_ = (datetime.strptime(d, "%Y-%m-%d") + timedelta(days=days)).strftime("%Y-%m-%d")
                    pr, br = asof(ser, t_), asof(bser, t_)
                    r_ = pr / p0 - 1 if pr and p0 else None
                    b_ = br / b0 - 1 if br and b0 else None
                    hz[key] = {"ret": r_, "excess": (r_ - b_) if r_ is not None and b_ is not None else None}
            rows.append({"symbol": sym, "date": d, "label": label, "group": group, "price": p0, "end": end,
                         "active": i + 1 == len(sigs), "days": (datetime.strptime(end, "%Y-%m-%d")
                                                                 - datetime.strptime(d, "%Y-%m-%d")).days,
                         "ret": ret, "bench": b_name, "bench_ret": bret,
                         "excess": (ret - bret) if ret is not None and bret is not None else None, "h": hz})

    def stats(items, key=None):
        ex_ = [r["excess"] if key is None else r["h"][key]["excess"] for r in items
               if (r["excess"] if key is None else r["h"].get(key, {}).get("excess")) is not None]
        rt = [r["ret"] if key is None else r["h"][key]["ret"] for r in items
              if (r["ret"] if key is None else r["h"].get(key, {}).get("ret")) is not None]
        return {"n": len(rt), "ret": sum(rt) / len(rt) if rt else None,
                "excess": sum(ex_) / len(ex_) if ex_ else None, "n_ex": len(ex_),
                "beat": sum(1 for e in ex_ if e > 0) / len(ex_) if ex_ else None}
    groups = {g: stats([r for r in rows if r["group"] == g]) for g in ("Kaufen", "Halten", "Verkaufen")}
    horizons = {k: {g: stats([r for r in rows if r["group"] == g and k in r["h"]], k) for g in ("Kaufen", "Halten", "Verkaufen")}
                for k, _ in TRACK_HORIZONS}
    rows.sort(key=lambda r: r["date"], reverse=True)
    return {"signals": rows, "groups": groups, "horizons": horizons, "since": min(x[1] for x in signals)}


def track_payload(user, everyone=False):
    key = "*" if everyone else user
    hit = TRACK_CACHE.get(key)
    if hit and time.time() - hit[0] < 3600:
        return hit[1]
    data = STORE.load()
    with STORE.lock:
        if everyone:
            spaces = list(data["u"].values())
        else:
            spaces = [user_space(user)]
        sig = []
        for sp in spaces:
            sig += [list(x) for x in signals_of(sp)]
    if everyone:  # gleiche Aktie am selben Tag von mehreren Benutzern nur einmal zählen
        sig = list({(x[0], x[1]): x for x in sig}.values())
    out = track_record(sig)
    out["scope"] = "all" if everyone else "me"
    TRACK_CACHE[key] = (time.time(), out)
    return out


# ---------------------------------------------------------------------------
# Admin-Dashboard: Nutzungsstatistik, Systemzustand, Datenquellen
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Abo (2 € pro Monat, manuelle Zahlung): Benutzer fragt an, Admin schaltet nach Zahlungseingang frei
# ---------------------------------------------------------------------------
SUB_PRICE_EUR = 2
DEFAULT_PAYMENT_INFO = ("Bitte überweise 2 € pro Monat (oder 24 € für ein Jahr) und gib deinen Benutzernamen als "
                        "Verwendungszweck an. Der Administrator schaltet dein Abo nach Zahlungseingang frei.")


def sub_status(sp):
    sub = sp.get("sub") or {}
    now = time.time()
    until = sub.get("paid_until") or 0
    if until > now:
        state = "gekündigt" if sub.get("cancel_requested") else "aktiv"   # gekündigt: läuft bis zum Ende weiter
    elif sub.get("requested"):
        state = "angefragt"
    else:
        state = "abgelaufen" if until else "inaktiv"
    return {"state": state, "active": until > now, "paid_until": until or None, "requested": sub.get("requested"),
            "cancel_requested": sub.get("cancel_requested"), "price": SUB_PRICE_EUR,
            "history": (sub.get("history") or [])[-12:]}


def payment_info():
    return (STORE.load().get("settings") or {}).get("payment_info") or DEFAULT_PAYMENT_INFO


def sub_user_action(user, action):
    sp = user_space(user)
    with STORE.lock:
        sub = sp.setdefault("sub", {})
        if action == "request":
            sub["requested"] = int(time.time())
            sub.pop("cancel_requested", None)
        elif action == "cancel":
            sub["cancel_requested"] = int(time.time())
            sub.pop("requested", None)
        else:
            raise ValueError("unbekannte Aktion")
        STORE.dirty = True
    save_async()
    LOG.info("[Abo] %s: %s", user, "angefragt" if action == "request" else "Kündigung")
    admin_topics = {user_space(u_)["topic"] for u_, acc in users().items() if acc.get("admin")}
    for tp in admin_topics:  # Admin per Push informieren
        safe(lambda: ntfy_send("💶 Abo " + ("angefragt" if action == "request" else "gekündigt"),
                               f"{user} hat das Abo ({SUB_PRICE_EUR} €/Monat) " + ("angefragt – bitte Zahlungseingang prüfen und im Admin-Dashboard freischalten."
                                                                                  if action == "request" else "gekündigt."),
                               tags=["moneybag"], priority=3, topic=tp))
    return sub_status(sp)


def sub_admin_action(admin, name, action, months=1):
    if name not in users():
        raise ValueError("Diesen Benutzer gibt es nicht.")
    sp = user_space(name)
    with STORE.lock:
        sub = sp.setdefault("sub", {})
        now = time.time()
        if action == "extend":
            months = int(months) if str(months).isdigit() and int(months) in (1, 3, 6, 12) else 1
            base = max(now, sub.get("paid_until") or 0)
            sub["paid_until"] = int(base + months * 30.44 * 86400)
            sub.pop("requested", None)
            sub.pop("cancel_requested", None)
            sub.setdefault("history", []).append({"t": int(now), "action": f"+{months} Monat(e)", "by": admin,
                                                  "amount": months * SUB_PRICE_EUR})
        elif action == "end":
            sub["paid_until"] = int(now) - 1 if (sub.get("paid_until") or 0) > now else sub.get("paid_until")
            sub.pop("requested", None)
            sub.setdefault("history", []).append({"t": int(now), "action": "beendet", "by": admin})
        else:
            raise ValueError("unbekannte Aktion")
        STORE.dirty = True
    save_async()
    LOG.info("[Abo] %s: %s für %s", admin, action, name)
    return sub_status(sp)


def record_usage(user, symbol):
    """Zählt Analysen je Tag, Benutzer und Wert (für das Admin-Dashboard; 90 Tage)."""
    data = STORE.load()
    day = datetime.now().strftime("%Y-%m-%d")
    with STORE.lock:
        st = data.setdefault("stats", {"days": {}, "symbols": {}})
        d = st["days"].setdefault(day, {"analyses": 0, "users": {}})
        d["analyses"] += 1
        d["users"][user] = d["users"].get(user, 0) + 1
        st["symbols"][symbol] = st["symbols"].get(symbol, 0) + 1
        for old in sorted(st["days"])[:-90]:
            st["days"].pop(old, None)
        if len(st["symbols"]) > 500:  # seltene Werte verwerfen
            for k in sorted(st["symbols"], key=st["symbols"].get)[:100]:
                st["symbols"].pop(k, None)
        STORE.dirty = True


def data_source_checks(sym="SAP.DE"):
    """Erreichbarkeit und Antwortzeit der Datenquellen."""
    checks = {
        "Yahoo · Kursdaten": lambda: f"{len(yf.Ticker(sym).history(period='5d'))} Tage",
        "Yahoo · Unternehmensdaten": lambda: "Kurs " + str(current_price(yf.Ticker(sym).info)),
        "Yahoo · Bilanzen": lambda: f"{len(yf.Ticker(sym).quarterly_income_stmt.columns)} Quartale",
        "Yahoo · Analystenschätzungen": lambda: f"{len(yf.Ticker(sym).earnings_estimate)} Zeilen",
        "Yahoo · Suche": lambda: f"{len(search_symbols(sym))} Treffer",
        "Google News": lambda: f"{len(google_news(sym, 'en'))} Meldungen",
        "Finnhub": lambda: (f"{len(finnhub('stock/recommendation', symbol=sym.split('.')[0]) or [])} Perioden"
                            if finnhub_key() else "kein Schlüssel"),
        "CoinGecko": lambda: f"{len(cg_markets('eur') or [])} Coins",
        "Wikidata": lambda: "ok" if wikidata_company("SAP", "SAP", "DE") else "keine Antwort",
        "ntfy.sh": lambda: str(urllib.request.urlopen(urllib.request.Request("https://ntfy.sh/v1/health", headers=UA), timeout=8).status),
    }
    out = []
    for name, fn in checks.items():
        t0 = time.time()
        try:
            val = fn()
            ok = not any(x in str(val) for x in ("None", "kein", "keine", " 0 "))
            out.append({"name": name, "ok": ok, "detail": str(val)[:120], "ms": int((time.time() - t0) * 1000)})
        except Exception as e:
            out.append({"name": name, "ok": False, "detail": f"{type(e).__name__}: {e}"[:160], "ms": int((time.time() - t0) * 1000)})
    return out


def admin_dashboard():
    data = STORE.load()
    now = time.time()
    st = data.get("stats") or {"days": {}, "symbols": {}}
    today = datetime.now().strftime("%Y-%m-%d")
    days = [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(29, -1, -1)]
    per_day = [{"day": d, "n": (st["days"].get(d) or {}).get("analyses", 0)} for d in days]
    week = sum(x["n"] for x in per_day[-7:])
    accs = users()
    ulist = []
    with STORE.lock:
        for name, acc in sorted(accs.items()):
            sp = data["u"].get(name, {})
            used = sum((st["days"].get(d) or {}).get("users", {}).get(name, 0) for d in days)
            ulist.append({"name": name, "admin": bool(acc.get("admin")), "created": acc.get("created"),
                          "last_login": acc.get("last_login"), "last_seen": sp.get("last_seen"),
                          "watchlist": len(sp.get("watchlist", [])), "alerts": len(sp.get("alerts", {})),
                          "signals": len(sp.get("signals", [])), "analyses_30d": used,
                          "report": (sp.get("report") or {}).get("enabled", True),
                          "report_last": (sp.get("report") or {}).get("last"),
                          "sub": None if acc.get("admin") else sub_status(sp)})
        alerts_total = sum(len(sp.get("alerts", {})) for sp in data["u"].values())
        top = sorted((st.get("symbols") or {}).items(), key=lambda kv: -kv[1])[:12]
    scr = screener_payload()
    sst = SCREENER_STATE
    caches = [{"name": n, "entries": len(c), "max": mx} for n, c, _t, mx in cache_rules()]
    logs = list(LOG_BUFFER)
    warn = [x for x in logs if x["level"] in ("WARNING", "ERROR", "CRITICAL")][-40:][::-1]
    recent = logs[-30:][::-1]
    mem = mem_mb()
    subs_active = sum(1 for u_ in ulist if u_.get("sub") and u_["sub"]["active"])
    subs_open = sum(1 for u_ in ulist if u_.get("sub") and u_["sub"]["state"] == "angefragt")
    return {
        "subs": {"active": subs_active, "requested": subs_open, "revenue_month": subs_active * SUB_PRICE_EUR,
                 "price": SUB_PRICE_EUR, "payment_info": payment_info()},
        "kpi": {"users": len(accs), "analyses_today": (st["days"].get(today) or {}).get("analyses", 0),
                "analyses_7d": week, "alerts": alerts_total, "memory_mb": round(mem) if mem else None,
                "uptime_s": int(now - START_TIME), "warnings": len(warn)},
        "per_day": per_day, "top_symbols": [{"symbol": k, "n": v} for k, v in top], "users": ulist,
        "screener": {"running": sst["running"], "done": sst["done"], "target": sst["target"], "by": sst["by"],
                     "unis": sst.get("unis") or [], "finished": sst["finished"], "mem_stop": sst.get("mem_stop", False),
                     "rated": len(scr["rows"]), "total": scr["total"], "fresh": scr["fresh"],
                     "universes": scr["universes"],
                     "failed": sorted(k for k, v in screener_store().items() if v.get("failed") and not v.get("label"))[:30]},
        "caches": caches, "warnings": warn, "recent": recent,
        "system": {"python": sys.version.split()[0], "yfinance": getattr(yf, "__version__", "?"),
                   "commit": (os.environ.get("RENDER_GIT_COMMIT") or "")[:7] or "lokal",
                   "hosted": "RENDER" in os.environ, "storage": STORE.backend, "encrypted": STORE.encrypted,
                   "persistent": STORE.persistent, "store_error": STORE.error, "finnhub": bool(finnhub_key()),
                   "last_check": data.get("last_check"), "started": int(START_TIME),
                   "memory_soft": MEM_SOFT_MB, "memory_hard": MEM_HARD_MB,
                   "store_kb": round(len(json.dumps(data, default=str)) / 1024)},
    }


def clean_watchlist(items):
    out, seen = [], set()
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        sym = str(it.get("symbol") or "").upper()
        if not re.fullmatch(r"[A-Z0-9.\-^=]{1,15}", sym) or sym in seen:
            continue
        seen.add(sym)
        keep = {k: it[k] for k in ("name", "exchange", "currency", "price", "label", "group", "score", "summary",
                                   "perf_1m", "upside", "updated", "next_event") if k in it}
        out.append({"symbol": sym, **keep})
    return out[:150]


# ---------------------------------------------------------------------------
# Screener: Indizes im Hintergrund bewerten (langsam, ein Wert nach dem anderen), Rangliste mit Filtern
# ---------------------------------------------------------------------------
# Zusammensetzung Stand 21.10.2026: S&P 500 (datasets/s-and-p-500-companies), Nasdaq-100 (Nasdaq), MDAX/TecDAX
# (Wikipedia, Kürzel per Yahoo-Suche), DAX/Euro Stoxx 50/Dow nach bestem Wissen (Hochtief für Porsche SE ab 22.06.2026,
# Sartorius in den MDAX).
# Indexänderungen bei Bedarf hier nachtragen – die App bewertet einfach die hier gelisteten Kürzel.
SCREENER_UNIVERSES = {
    "dax": ("DAX", ["ADS.DE", "AIR.DE", "ALV.DE", "BAS.DE", "BAYN.DE", "BEI.DE", "BMW.DE", "BNR.DE", "CBK.DE",
                       "CON.DE", "DTG.DE", "DBK.DE", "DB1.DE", "DHL.DE", "DTE.DE", "EOAN.DE", "FRE.DE", "FME.DE",
                       "G24.DE", "G1A.DE", "HNR1.DE", "HEI.DE", "HEN3.DE", "IFX.DE", "MBG.DE",
                       "MRK.DE", "MTX.DE", "MUV2.DE", "HOT.DE", "QIA.DE", "RHM.DE", "RWE.DE", "SAP.DE",
                       "SIE.DE", "ENR.DE", "SHL.DE", "SY1.DE", "VOW3.DE", "VNA.DE", "ZAL.DE"]),
    "mdax": ("MDAX", [
        "8TRA.DE", "AG1.DE", "AIXA.DE", "AMV0.DE", "AT1.DE", "BC8.DE", "BOSS.DE", "DEZ.DE", "DHER.DE", "DWS.DE",
        "ELG.DE", "EVD.DE", "EVK.DE", "FNTN.DE", "FPE3.DE", "FRA.DE", "FTK.DE", "GBF.DE", "HAG.DE", "HLE.DE",
        "IOS.DE", "JEN.DE", "KBX.DE", "KGX.DE", "KRN.DE", "LEG.DE", "LHA.DE", "LXS.DE", "NDA.DE", "NDX1.DE",
        "NEM.DE", "P911.DE", "PAH3.DE", "PUM.DE", "R3NK.DE", "RAA.DE", "RRTL.DE", "SDF.DE", "SHA0.DE",
        "SMHN.DE", "SRT3.DE", "SZG.DE", "TEG.DE", "TKA.DE", "TKMS.DE", "TLX.DE", "TUI1.DE", "UTDI.DE", "WAF.DE",
        "WCH.DE"]),
    "tecdax": ("TecDAX", [
        "AFX.DE", "AIXA.DE", "AOF.DE", "BC8.DE", "DRW3.DE", "DTE.DE", "ELG.DE", "EUZ.DE", "EVT.DE", "FNTN.DE",
        "HAG.DE", "IFX.DE", "IOS.DE", "JEN.DE", "KTN.DE", "NDX1.DE", "NEM.DE", "OBCK.DE", "OHB.DE", "QIA.DE",
        "S92.DE", "SAP.DE", "SHL.DE", "SMHN.DE", "SRT3.DE", "TMV.DE", "TPE.DE", "UTDI.DE", "VBK.DE", "WAF.DE"]),
    "es50": ("Euro Stoxx 50", ["ADS.DE", "ADYEN.AS", "AD.AS", "AI.PA", "AIR.DE", "ALV.DE", "ABI.BR", "ARGX.BR",
                               "ASML.AS", "CS.PA", "BAS.DE", "BAYN.DE", "BBVA.MC", "SAN.MC", "BMW.DE", "BNP.PA",
                               "BN.PA", "DB1.DE", "DHL.DE", "DTE.DE", "ENEL.MI", "ENI.MI", "EL.PA", "RACE.MI",
                               "IBE.MC", "ITX.MC", "IFX.DE", "INGA.AS", "ISP.MI", "OR.PA", "MC.PA", "MBG.DE",
                               "MUV2.DE", "NOKIA.HE", "NDA-FI.HE", "PRX.AS", "RMS.PA", "SAF.PA", "SAN.PA", "SAP.DE",
                               "SU.PA", "SIE.DE", "STLAM.MI", "TTE.PA", "UCG.MI", "DG.PA", "VOW3.DE", "WKL.AS",
                               "RHM.DE", "ENR.DE"]),
    "dow": ("Dow Jones 30", ["AAPL", "AMGN", "AMZN", "AXP", "BA", "CAT", "CRM", "CSCO", "CVX", "DIS", "GS", "HD",
                             "HON", "IBM", "JNJ", "JPM", "KO", "MCD", "MMM", "MRK", "MSFT", "NKE", "NVDA", "PG",
                             "SHW", "TRV", "UNH", "V", "VZ", "WMT"]),
    "ndx": ("Nasdaq-100", [
        "AAPL", "ABNB", "ADBE", "ADI", "ADP", "ADSK", "AEP", "ALAB", "ALNY", "AMAT", "AMD", "AMGN", "AMZN",
        "APP", "ARM", "ASML", "AVGO", "AXON", "BKNG", "BKR", "CCEP", "CDNS", "CEG", "CMCSA", "COST", "CPRT",
        "CRWD", "CRWV", "CSCO", "CSX", "CTAS", "DASH", "DDOG", "DXCM", "EXC", "FANG", "FAST", "FER", "FTNT",
        "GEHC", "GILD", "GOOG", "GOOGL", "HON", "HONA", "IDXX", "INTC", "INTU", "ISRG", "KDP", "KLAC", "LIN",
        "LITE", "LRCX", "MAR", "MCHP", "MDLZ", "MELI", "META", "MNST", "MPWR", "MRNA", "MRVL", "MSFT", "MSTR",
        "MU", "NBIS", "NFLX", "NVDA", "NXPI", "ODFL", "ORLY", "PANW", "PAYX", "PCAR", "PDD", "PEP", "PLTR",
        "PYPL", "QCOM", "REGN", "RKLB", "ROP", "ROST", "SBUX", "SHOP", "SNDK", "SNPS", "SPCX", "STX", "TER",
        "TMUS", "TRI", "TSLA", "TTWO", "TXN", "VRTX", "WDAY", "WDC", "WMT", "XEL"]),
    "sp500": ("S&P 500", [
        "A", "AAPL", "ABBV", "ABNB", "ABT", "ACGL", "ACN", "ADBE", "ADI", "ADM", "ADP", "ADSK", "AEE", "AEP",
        "AES", "AFL", "AIG", "AIZ", "AJG", "AKAM", "ALB", "ALGN", "ALL", "ALLE", "AMAT", "AMCR", "AMD", "AME",
        "AMGN", "AMP", "AMT", "AMZN", "ANET", "AON", "AOS", "APA", "APD", "APH", "APO", "APP", "APTV", "ARE",
        "ARES", "ATO", "AVGO", "AVY", "AWK", "AXON", "AXP", "AZO", "BA", "BAC", "BALL", "BAX", "BBY", "BDX",
        "BE", "BEN", "BF-B", "BG", "BIIB", "BKNG", "BKR", "BLK", "BMY", "BNY", "BR", "BRK-B", "BRO", "BSX",
        "BX", "BXP", "C", "CAH", "CARR", "CASY", "CAT", "CB", "CBOE", "CBRE", "CCI", "CCL", "CDNS", "CDW",
        "CEG", "CF", "CFG", "CHD", "CHRW", "CHTR", "CI", "CIEN", "CINF", "CL", "CLX", "CMCSA", "CME", "CMG",
        "CMI", "CMS", "CNC", "CNP", "COF", "COHR", "COIN", "COO", "COP", "COR", "COST", "CPAY", "CPRT", "CPT",
        "CRH", "CRL", "CRM", "CRWD", "CSCO", "CSGP", "CSX", "CTAS", "CTSH", "CVNA", "CVS", "CVX", "D", "DAL",
        "DASH", "DD", "DDOG", "DE", "DECK", "DELL", "DG", "DGX", "DHI", "DHR", "DIS", "DLR", "DLTR", "DOC",
        "DOV", "DOW", "DPZ", "DRI", "DTE", "DUK", "DVA", "DVN", "DXCM", "EBAY", "ECHO", "ECL", "ED", "EFX",
        "EG", "EIX", "EL", "ELV", "EME", "EMR", "EOG", "EQIX", "EQT", "ERIE", "ES", "ESS", "ETN", "ETR", "EVRG",
        "EW", "EXC", "EXE", "EXPD", "EXPE", "EXR", "F", "FANG", "FAST", "FCX", "FDS", "FDX", "FDXF", "FE",
        "FERG", "FFIV", "FICO", "FIS", "FISV", "FITB", "FIX", "FLEX", "FOX", "FOXA", "FRT", "FSLR", "FTNT",
        "FTV", "GD", "GDDY", "GE", "GEHC", "GEN", "GEV", "GILD", "GIS", "GL", "GLW", "GM", "GNRC", "GOOG",
        "GOOGL", "GPC", "GPN", "GRMN", "GS", "GWW", "HAL", "HAS", "HBAN", "HCA", "HD", "HIG", "HII", "HLT",
        "HON", "HONA", "HOOD", "HPE", "HPQ", "HRL", "HSIC", "HST", "HSY", "HUBB", "HUM", "HWM", "IBKR", "IBM",
        "ICE", "IDXX", "IEX", "IFF", "ILMN", "INCY", "INTC", "INTU", "INVH", "IP", "IQV", "IR", "IRM", "ISRG",
        "IT", "ITW", "IVZ", "J", "JBHT", "JBL", "JCI", "JKHY", "JNJ", "JPM", "KDP", "KEY", "KEYS", "KHC", "KIM",
        "KKR", "KLAC", "KMB", "KMI", "KO", "KR", "KVUE", "L", "LDOS", "LEN", "LH", "LHX", "LII", "LIN", "LITE",
        "LLY", "LMT", "LNT", "LOW", "LRCX", "LULU", "LUV", "LVS", "LYB", "LYV", "MA", "MAA", "MAR", "MAS",
        "MCD", "MCHP", "MCK", "MCO", "MDLZ", "MDT", "MET", "META", "MGM", "MKC", "MLM", "MMM", "MNST", "MO",
        "MOS", "MPC", "MPWR", "MRK", "MRNA", "MRSH", "MRVL", "MS", "MSCI", "MSFT", "MSI", "MTB", "MTD", "MU",
        "NCLH", "NDAQ", "NDSN", "NEE", "NEM", "NFLX", "NI", "NKE", "NOC", "NOW", "NRG", "NSC", "NTAP", "NTRS",
        "NUE", "NVDA", "NVR", "NWS", "NWSA", "NXPI", "O", "ODFL", "OKE", "OMC", "ON", "ORCL", "ORLY", "OTIS",
        "OXY", "P", "PANW", "PAYX", "PCAR", "PCG", "PEG", "PEP", "PFE", "PFG", "PG", "PGR", "PH", "PHM", "PKG",
        "PLD", "PLTR", "PM", "PNC", "PNR", "PNW", "PODD", "PPG", "PPL", "PRU", "PSA", "PSX", "PTC", "PWR",
        "PYPL", "Q", "QCOM", "RCL", "RDDT", "REG", "REGN", "RF", "RJF", "RL", "RMD", "ROK", "ROL", "ROP",
        "ROST", "RSG", "RTX", "RVTY", "SBAC", "SBUX", "SCHW", "SHW", "SJM", "SKYD", "SLB", "SMCI", "SNA",
        "SNDK", "SNPS", "SO", "SOLV", "SPG", "SPGI", "SRE", "STE", "STLD", "STT", "STX", "STZ", "SW", "SWK",
        "SWKS", "SYF", "SYK", "SYY", "T", "TDG", "TDY", "TECH", "TEL", "TER", "TFC", "TGT", "TJX", "TKO", "TMO",
        "TMUS", "TPL", "TPR", "TRGP", "TRMB", "TROW", "TRV", "TSCO", "TSLA", "TSN", "TT", "TTWO", "TWLO", "TXN",
        "TXT", "TYL", "UAL", "UBER", "UDR", "UHS", "ULTA", "UNH", "UNP", "UPS", "URI", "USB", "V", "VEEV",
        "VICI", "VLO", "VLTO", "VMC", "VMRK", "VRSK", "VRSN", "VRT", "VRTX", "VST", "VTR", "VTRS", "VYLR", "VZ",
        "WAB", "WAT", "WDAY", "WDC", "WEC", "WELL", "WFC", "WM", "WMB", "WMT", "WRB", "WSM", "WST", "WTW", "WY",
        "WYNN", "XEL", "XOM", "XYL", "XYZ", "YUM", "ZBH", "ZBRA", "ZTS"]),
}
SCREENER_MAX_AGE = 20 * 3600     # einen Wert höchstens einmal in 20 Stunden neu bewerten
SCREENER_PAUSE = 10              # Sekunden Pause nach jeder Bewertung (Prozessor schonen)
SCREENER_STATE = {"running": False, "current": None, "started": None, "by": None, "mode": "due", "stop": False,
                  "done": 0, "target": 0, "finished": None, "seen": set(), "unis": []}
SCREENER_LOCK = threading.Lock()


def screener_symbols():
    out = {}
    for key, (_name, syms) in SCREENER_UNIVERSES.items():
        for sym in syms:
            out.setdefault(sym, []).append(key)
    return out


def screener_row(res, universes):
    cats = {c["key"]: c.get("score") for c in res.get("categories") or []}
    f = res.get("facts") or {}
    fair = res.get("fair") or {}
    return {"symbol": res["symbol"], "name": res["name"], "u": universes, "price": res.get("price"),
            "currency": res.get("currency", ""), "label": res["rating"]["label"], "group": res["rating"]["group"],
            "score": res["rating"]["score"], "summary": (res.get("summary") or {}).get("adjective"),
            "sector": res.get("sector") or "", "model": (res.get("model") or {}).get("label", ""),
            "fair": fair.get("base"), "fair_up": fair.get("upside"), "pe": f.get("pe"), "fpe": f.get("fpe"),
            "div": f.get("div_yield"), "perf_1y": f.get("perf_1y"), "mcap": f.get("mcap"), "upside": f.get("upside"),
            "c": {k: (round(v, 2) if v is not None else None) for k, v in cats.items()},
            "updated": int(time.time())}


def screener_store():
    data = STORE.load()
    with STORE.lock:
        return data.setdefault("screener", {})


def screener_due(mode="due", since=None, unis=None):
    """Fällige Werte der gewählten Indizes, älteste zuerst.
    mode="all": alles, was im laufenden Durchgang noch nicht bewertet wurde."""
    store = screener_store()
    now = time.time()
    out = []
    for sym, member in screener_symbols().items():
        if unis and not set(member) & set(unis):
            continue
        e = store.get(sym, {})
        last = max(e.get("updated", 0), e.get("failed", 0))
        if mode == "all":
            if last < (since or now) and sym not in SCREENER_STATE["seen"]:
                out.append((e.get("updated", 0), sym))
        elif now - e.get("updated", 0) > SCREENER_MAX_AGE and now - e.get("failed", 0) > 6 * 3600:
            out.append((e.get("updated", 0), sym))
    return [s_ for _, s_ in sorted(out)]


def screener_next():
    """Nächster fälliger Wert im laufenden Durchgang – oder None."""
    due = screener_due(SCREENER_STATE["mode"], SCREENER_STATE["started"], SCREENER_STATE["unis"])
    return due[0] if due else None


def screener_step():
    """Bewertet genau einen fälligen Wert. True, wenn etwas zu tun war."""
    sym = screener_next()
    if not sym:
        return False
    SCREENER_STATE["current"] = sym
    SCREENER_STATE["seen"].add(sym)  # im laufenden Durchgang nicht noch einmal
    unis = screener_symbols()[sym]
    store = screener_store()
    try:
        res = analyze(sym)
        row = screener_row(res, unis)
        with STORE.lock:
            store[sym] = row
            STORE.dirty = True
    except Exception as e:
        with STORE.lock:
            store.setdefault(sym, {"symbol": sym, "u": unis})["failed"] = int(time.time())
            STORE.dirty = True
        LOG.warning("[Screener] %s nicht bewertbar: %s", sym, str(e)[:120])
    finally:
        SCREENER_STATE["current"] = None
    return True


def screener_run():
    """Ein Durchgang: bewertet alle fälligen Werte nacheinander und endet dann (oder bei „Stopp“)."""
    st = SCREENER_STATE
    LOG.info("[Screener] Start durch %s · %s · %d Werte (%s)", st["by"],
             ", ".join(SCREENER_UNIVERSES[k][0] for k in st["unis"]), st["target"], "alle" if st["mode"] == "all" else "veraltete")
    try:
        while not st["stop"]:
            if REPORT_LOCK.locked():       # Wochenbericht hat Vorrang
                time.sleep(30)
                continue
            if not screener_step():
                break
            st["done"] += 1
            mb = release_memory() if MEM_GUARD else None
            if st["done"] % 10 == 0:
                LOG.info("[Screener] %d von %d · Speicher %s MB", st["done"], st["target"], f"{mb:.0f}" if mb else "?")
            if mb and mb > MEM_SOFT_MB:
                safe(prune_caches)
                CACHE.clear()
                CHART_CACHE.clear()
                time.sleep(20)
                mb = release_memory()
                LOG.warning("[Screener] Speicher knapp – aufgeräumt, jetzt %.0f MB", mb or 0)
                if mb and mb > MEM_HARD_MB:
                    st["stop"] = True
                    st["mem_stop"] = True
                    LOG.warning("[Screener] Abgebrochen: Speicher bleibt über %d MB – mit „Start“ geht es später weiter",
                                MEM_HARD_MB)
                    break
            for _ in range(SCREENER_PAUSE):
                if st["stop"]:
                    break
                time.sleep(1)
    except Exception:
        LOG.exception("[Screener] Fehler")
    finally:
        LOG.info("[Screener] %s nach %d Werten", "Gestoppt" if st["stop"] else "Fertig", st["done"])
        st.update(running=False, current=None, finished=int(time.time()))
        safe(STORE.save)
        safe(prune_caches)


def screener_start(user, mode="due", unis=None):
    """Startet einen Durchgang für genau einen Index, falls keiner läuft. Gibt (gestartet, Meldung) zurück."""
    unis = [k for k in (unis or []) if k in SCREENER_UNIVERSES][:1]  # immer nur ein Index je Durchgang
    if not unis:
        return False, "Bitte einen Index auswählen."
    with SCREENER_LOCK:
        st = SCREENER_STATE
        if st["running"]:
            return False, "Der Screener läuft bereits."
        now = time.time()
        st["seen"] = set()
        due = screener_due(mode, now, unis)
        names = ", ".join(SCREENER_UNIVERSES[k][0] for k in unis)
        if not due:
            return False, f"{names}: alle Werte sind aktuell (jünger als 20 Stunden) – „Alle neu bewerten“ erzwingt einen Durchgang."
        st.update(running=True, stop=False, started=now, by=user, mode=mode, done=0, target=len(due), finished=None, unis=unis,
                  mem_stop=False)
        threading.Thread(target=screener_run, daemon=True).start()
        return True, f"Gestartet: {names} – {len(due)} Werte werden bewertet."


def screener_payload():
    store = screener_store()
    syms = screener_symbols()
    with STORE.lock:
        rows = [dict(r) for sym, r in store.items() if sym in syms and r.get("label")]
    for r in rows:
        r["u"] = syms[r["symbol"]]  # aktuelle Indexzuordnung
    unis = {k: {"name": n, "total": len(lst), "done": sum(1 for x in lst if (store.get(x) or {}).get("label"))}
            for k, (n, lst) in SCREENER_UNIVERSES.items()}
    fresh = sum(1 for sym in syms if time.time() - (store.get(sym) or {}).get("updated", 0) <= SCREENER_MAX_AGE)
    st = SCREENER_STATE
    return {"rows": rows, "universes": unis, "total": len(syms), "fresh": fresh,
            "current": st["current"], "pause": SCREENER_PAUSE, "running": st["running"], "by": st["by"],
            "done": st["done"], "target": st["target"], "mode": st["mode"], "stopping": st["running"] and st["stop"],
            "finished": st["finished"], "due": len(screener_due("due")), "run_unis": st["unis"],
            "mem_stop": st.get("mem_stop", False),
            "due_by": {k: len(screener_due("due", None, [k])) for k in SCREENER_UNIVERSES}}


# ---------------------------------------------------------------------------
# Zwischenspeicher begrenzen: abgelaufene Einträge löschen, Höchstzahl je Speicher (älteste zuerst raus)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Arbeitsspeicher unter Linux (Render): glibc legt pro Thread eigene Speicherbereiche („Arenen“) an und gibt
# freien Speicher kaum zurück – bei vielen Analysen wächst der Prozess so über 512 MB. Gegenmittel:
# Arenen begrenzen, nach Arbeit aktiv zurückgeben (malloc_trim) und den Screener bei Knappheit bremsen.
# ---------------------------------------------------------------------------
MEM_SOFT_MB = 400        # ab hier räumt der Screener auf und pausiert
MEM_HARD_MB = 450        # bleibt es darüber, stoppt der Screener geordnet (Limit des kostenlosen Servers: 512 MB)
MEM_GUARD = os.name != "nt"  # Speicherbremse nur auf dem Linux-Server (lokal unter Windows gibt es kein 512-MB-Limit)
_LIBC = None


def libc():
    global _LIBC
    if _LIBC is None:
        try:
            import ctypes
            _LIBC = ctypes.CDLL("libc.so.6")
        except Exception:
            _LIBC = False  # Windows/macOS: nicht nötig
    return _LIBC


def limit_malloc_arenas(n=2):
    lc = libc()
    if lc:
        safe(lambda: lc.mallopt(-8, n))  # M_ARENA_MAX


def mem_mb():
    """Belegter Arbeitsspeicher des Prozesses in MB (nur Linux, sonst None)."""
    try:
        with open("/proc/self/statm") as f:
            return int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") / 1e6
    except Exception:
        pass
    if os.name == "nt":  # lokal unter Windows (nur für die Anzeige im Admin-Dashboard)
        try:
            import ctypes
            import ctypes.wintypes as wt

            class PMC(ctypes.Structure):
                _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD), ("Peak", ctypes.c_size_t),
                            ("WorkingSetSize", ctypes.c_size_t)] + [(f"x{i}", ctypes.c_size_t) for i in range(6)]
            k32, psapi = ctypes.windll.kernel32, ctypes.windll.psapi
            k32.GetCurrentProcess.restype = wt.HANDLE
            psapi.GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(PMC), wt.DWORD]
            pmc = PMC()
            pmc.cb = ctypes.sizeof(PMC)
            if psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
                return pmc.WorkingSetSize / 1e6
        except Exception:
            return None
    return None


def release_memory():
    import gc
    gc.collect()
    lc = libc()
    if lc:
        safe(lambda: lc.malloc_trim(0))
    return mem_mb()


def cache_rules():
    """(Name, Speicher, Lebensdauer in Sekunden, Höchstzahl Einträge) – Einträge sind (Zeitstempel, Daten)."""
    return [("Analysen", CACHE, 900, 40), ("Charts", CHART_CACHE, 12 * 3600, 120),
            ("Erfolgsrechnung", INCOME_CACHE, 12 * 3600, 60), ("Profile", PROFILE_CACHE, 7 * 86400, 150),
            ("Wettbewerber", PEER_CACHE, 6 * 3600, 200), ("Termine", EVENT_CACHE, 6 * 3600, 100),
            ("Finnhub", FINNHUB_CACHE, 3600, 400), ("CoinGecko", CG_CACHE, 86400, 60),
            ("Trefferquote", TRACK_CACHE, 3600, 10), ("Wechselkurse", FX_CACHE, 86400, 50)]


def prune_caches():
    """Räumt alle Zwischenspeicher auf; gibt die Zahl gelöschter Einträge zurück."""
    removed, now = 0, time.time()
    for _name, cache, ttl, maxn in cache_rules():
        items = list(cache.items())
        for k, v in items:
            ts = v[0] if isinstance(v, tuple) and v and isinstance(v[0], (int, float)) else now
            if now - ts > ttl:
                cache.pop(k, None)
                removed += 1
        if len(cache) > maxn:
            for k, _v in sorted(cache.items(), key=lambda kv: kv[1][0] if isinstance(kv[1], tuple) else 0)[:len(cache) - maxn]:
                cache.pop(k, None)
                removed += 1
    if len(FIN_CUR_CACHE) > 500:  # nur kurze Texte (Bilanzwährung) – bei Bedarf komplett leeren
        removed += len(FIN_CUR_CACHE)
        FIN_CUR_CACHE.clear()
    if removed:
        release_memory()
    return removed


def history_flush_loop():
    while True:
        time.sleep(60)
        if STORE.dirty:
            safe(STORE.save)
        n = safe(prune_caches) or 0
        if n:
            LOG.info("[Speicher] Zwischenspeicher aufgeräumt: %d Einträge entfernt", n)


def app_base_url():
    return (os.environ.get("RENDER_EXTERNAL_URL") or f"http://localhost:{os.environ.get('PORT', PORT)}").rstrip("/")


def cron_key():
    return hashlib.sha256(("aktien-check-cron|" + app_password()).encode("utf-8")).hexdigest()[:24]


def ntfy_send(title, message, symbol=None, tags=None, priority=4, topic=None):
    topic = topic or user_space("admin")["topic"]
    body = {"topic": topic, "title": title, "message": message, "tags": tags or [], "priority": priority}
    if symbol:
        body["click"] = f"{app_base_url()}/?q={urllib.parse.quote(symbol)}"
    req = urllib.request.Request("https://ntfy.sh/", data=json.dumps(body).encode("utf-8"),
                                 headers={**UA, "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status == 200


def fmt_price(v, cur):
    return f"{fnum(v, 2)} {cur}".strip()


def live_quote(symbol):
    fi = yf.Ticker(symbol).fast_info
    last, prev = num(safe(lambda: fi.last_price)), num(safe(lambda: fi.previous_close))
    return last, prev


def run_alert_checks(force_rating=False):
    """Prüft alle Alarme einmal. Gibt die Liste der ausgelösten Meldungen zurück."""
    if not CHECK_LOCK.acquire(blocking=False):
        return []
    fired = []
    try:
        data = STORE.load()
        now = time.time()
        today = datetime.now().strftime("%Y-%m-%d")
        changed = False
        work = [(user, sp, sym, a) for user, sp in list(data["u"].items()) if user in users()
                for sym, a in list(sp.get("alerts", {}).items())]
        for user, sp, sym, a in work:
            st = a.setdefault("state", {})
            name, cur = a.get("name") or sym, a.get("currency") or ""
            msgs = []
            if a.get("below") or a.get("above") or a.get("move"):
                last, prev = safe(lambda: live_quote(sym), (None, None))
                if last:
                    st["last_price"] = last
                    if a.get("below") and not st.get("below_fired") and last <= a["below"]:
                        st["below_fired"] = now
                        msgs.append((f"📉 {name} unter {fmt_price(a['below'], cur)}",
                                     f"Aktueller Kurs: {fmt_price(last, cur)}", ["chart_with_downwards_trend"]))
                    if a.get("above") and not st.get("above_fired") and last >= a["above"]:
                        st["above_fired"] = now
                        msgs.append((f"📈 {name} über {fmt_price(a['above'], cur)}",
                                     f"Aktueller Kurs: {fmt_price(last, cur)}", ["chart_with_upwards_trend"]))
                    if a.get("move") and prev:
                        chg = last / prev - 1
                        st["day_change"] = chg
                        if abs(chg) * 100 >= a["move"] and st.get("move_day") != today:
                            st["move_day"] = today
                            sign = "+" if chg > 0 else ""
                            msgs.append((f"⚡ {name} {sign}{fnum(chg * 100, 1)} % heute",
                                         f"Kurs {fmt_price(last, cur)} (Vortag {fmt_price(prev, cur)}) – "
                                         f"Schwelle ±{fnum(a['move'], 1)} %", ["zap"]))
            if a.get("events"):  # Erinnerung am Vortag eines Termins
                evs = safe(lambda: company_events(sym, (), cur), []) or []
                sent_ev = st.setdefault("events_sent", [])
                for e in evs:
                    key = f"{e['type']}:{e['date']}"
                    if e["days"] == 1 and key not in sent_ev and datetime.now().hour >= 8:
                        sent_ev.append(key)
                        msgs.append((f"📅 Morgen: {name} – {e['label']}" + (" (voraussichtlich)" if e["estimated"] else ""),
                                     e.get("detail") or datetime.strptime(e["date"], "%Y-%m-%d").strftime("%d.%m.%Y"),
                                     ["calendar"]))
                st["events_sent"] = sent_ev[-20:]
            if a.get("rating") and (force_rating or now - (st.get("rating_checked") or 0) > RATING_INTERVAL):
                res = safe(lambda: analyze(sym))
                if res:
                    safe(lambda: record_history(res, user))
                    label, old = res["rating"]["label"], st.get("last_label")
                    st["rating_checked"] = now
                    if old and label != old:
                        msgs.append((f"🔔 {name}: Empfehlung {old} → {label}",
                                     f"Score {fnum(res['rating']['score'], 1)} · Urteil: {res['summary']['adjective']}",
                                     ["bell"]))
                    st["last_label"] = label
            for title, msg, tags in msgs:
                ok = safe(lambda: ntfy_send(title, msg, sym, tags, topic=sp.get("topic")), False)
                fired.append({"user": user, "symbol": sym, "title": title, "sent": bool(ok)})
                (LOG.info if ok else LOG.warning)("[Alarm] %s · %s · %s%s", user, sym, title, "" if ok else " – Push NICHT zugestellt")
                st.setdefault("log", []).insert(0, {"t": now, "title": title})
                st["log"] = st["log"][:10]
            changed = True
        data["last_check"] = now
        LOG.info("[Alarm] Prüfung: %d Alarm(e), %d ausgelöst, %.1f s", len(work), len(fired), time.time() - now)
        if changed or fired:
            STORE.save()
        return fired
    finally:
        CHECK_LOCK.release()


def alert_loop():
    time.sleep(30)
    while True:
        try:
            run_alert_checks()
        except Exception:
            LOG.exception("[Alarm] Prüfung abgebrochen")
        safe(send_due_reports)
        time.sleep(CHECK_INTERVAL)


# ---------------------------------------------------------------------------
# Wochenbericht: jeden Sonntag ab 18 Uhr (deutsche Zeit) eine Zusammenfassung der Watchlist per Push
# ---------------------------------------------------------------------------
REPORT_WEEKDAY, REPORT_HOUR = 6, 18
REPORT_MAX = 30          # höchstens so viele Watchlist-Werte neu bewerten
REPORT_LOCK = threading.Lock()
REPORT_PAUSE = 1.5       # Sekunden zwischen zwei Werten (Prozessor des kostenlosen Servers schonen)
REPORT_USER_PAUSE = 20   # Sekunden zwischen zwei Konten
WEEKDAY_DE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def berlin_now():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Europe/Berlin")).replace(tzinfo=None)
    except Exception:
        return datetime.utcnow() + timedelta(hours=1)


def report_settings(sp):
    return sp.setdefault("report", {"enabled": True, "last": None})


def week_change(symbol):
    h = safe(lambda: yf.Ticker(symbol).history(period="8d", interval="1d", auto_adjust=False))
    if h is None or h.empty:
        return None
    c = h["Close"].dropna()
    c = c[c.index.tz_localize(None) >= (datetime.now() - timedelta(days=7.5))] if c.index.tz is not None else c.iloc[-6:]
    return float(c.iloc[-1] / c.iloc[0] - 1) if len(c) >= 2 else None


def build_weekly_report(user):
    """Bewertet die Watchlist neu und baut die Push-Nachricht (Titel, Text)."""
    sp = user_space(user)
    items = list(sp.get("watchlist") or [])[:REPORT_MAX]
    if not items:
        return None
    rows = []
    for it in items:
        sym = it["symbol"]
        with STORE.lock:
            pts = list((sp.get("history") or {}).get(sym) or [])
        today = datetime.now().strftime("%Y-%m-%d")
        prev = next((p_[2] for p_ in reversed(pts) if p_[0] != today), None) or it.get("label")
        res = safe(lambda: analyze(sym))
        time.sleep(REPORT_PAUSE)
        if not res:
            rows.append({"symbol": sym, "name": it.get("name") or sym, "error": True})
            continue
        safe(lambda: record_history(res, user))
        nm_ = etf_short_name(res["name"]) if res.get("asset") == "etf" else clean_company_name(res["name"])
        rows.append({"symbol": sym, "name": nm_ or sym, "label": res["rating"]["label"],
                     "group": res["rating"]["group"], "score": res["rating"]["score"], "prev": prev,
                     "chg": week_change(res["symbol"]), "price": res.get("price"), "currency": res.get("currency", ""),
                     "events": [e for e in res.get("events") or [] if 0 <= (e.get("days") if e.get("days") is not None else 99) <= 7]})
        with STORE.lock:  # Watchlist-Eintrag aktualisieren, damit die App den neuen Stand zeigt
            for w in sp.get("watchlist") or []:
                if w["symbol"] == sym:
                    w.update({"label": res["rating"]["label"], "group": res["rating"]["group"],
                              "score": res["rating"]["score"], "price": res.get("price"),
                              "summary": res["summary"]["adjective"], "updated": datetime.now().isoformat(timespec="seconds")})
            STORE.dirty = True
    ok = [r for r in rows if not r.get("error")]
    chg = [r for r in ok if r["chg"] is not None]
    lines = []
    avg = sum(r["chg"] for r in chg) / len(chg) if chg else None
    lines.append(f"{len(ok)} Werte" + (f" · Ø diese Woche {'+' if avg >= 0 else ''}{fnum(avg * 100, 1)} %" if avg is not None else ""))
    groups = {g: sum(1 for r in ok if r["group"] == g) for g in ("Kaufen", "Halten", "Verkaufen")}
    lines.append(f"Kaufen {groups['Kaufen']} · Halten {groups['Halten']} · Verkaufen {groups['Verkaufen']}")
    changed = [r for r in ok if r["prev"] and r["prev"] != r["label"]]
    if changed:
        lines += ["", "Empfehlung geändert:"] + [f"• {r['name']}: {r['prev']} → {r['label']}" for r in changed[:8]]
    if chg:
        srt = sorted(chg, key=lambda r: r["chg"], reverse=True)
        fmt = lambda r: f"{r['name']} {'+' if r['chg'] >= 0 else ''}{fnum(r['chg'] * 100, 1)} %"
        winners = [r for r in srt if r["chg"] > 0][:3]
        lines.append("")
        if winners:
            lines.append("Beste der Woche: " + " · ".join(fmt(r) for r in winners))
        losers = [r for r in srt[::-1] if r["chg"] < 0][:3]
        if losers:
            lines.append("Schwächste: " + " · ".join(fmt(r) for r in losers))
    ev = sorted(((e["date"], r["name"], e["label"], e.get("estimated")) for r in ok for e in r["events"]), key=lambda x: x[0])
    if ev:
        lines += ["", "Termine nächste Woche:"]
        for d, nm, lab, est in ev[:8]:
            dt = datetime.strptime(d, "%Y-%m-%d")
            lines.append(f"• {WEEKDAY_DE[dt.weekday()]} {dt.strftime('%d.%m.')} {nm}: {lab}{' (geschätzt)' if est else ''}")
    bad = [r for r in rows if r.get("error")]
    if bad:
        lines += ["", f"Nicht bewertbar: {', '.join(r['name'] for r in bad[:5])}"]
    if len(sp.get("watchlist") or []) > REPORT_MAX:
        lines.append(f"(Nur die ersten {REPORT_MAX} Werte der Watchlist)")
    msg = "\n".join(lines)
    return f"📊 Wochenbericht {datetime.now().strftime('%d.%m.%Y')}", msg[:3900]


def send_weekly_report(user, manual=False):
    if not REPORT_LOCK.acquire(blocking=manual):
        return False
    try:
        rep_ = build_weekly_report(user)
        sp = user_space(user)
        if not rep_:
            if manual:
                ntfy_send("📊 Wochenbericht", "Deine Watchlist ist leer – füge Aktien hinzu, dann erhältst du sonntags eine Zusammenfassung.",
                          topic=sp["topic"])
            return False
        ntfy_send(rep_[0], rep_[1], tags=["bar_chart"], priority=3, topic=sp["topic"])
        LOG.info("[Bericht] Wochenbericht an %s gesendet (%s)", user, "manuell" if manual else "planmäßig")
        return True
    finally:
        REPORT_LOCK.release()


def send_due_reports():
    now = berlin_now()
    if now.weekday() != REPORT_WEEKDAY or now.hour < REPORT_HOUR:
        return
    today = now.strftime("%Y-%m-%d")
    data = STORE.load()
    with STORE.lock:
        due = [u_ for u_, sp in (data.get("u") or {}).items()
               if report_settings(sp).get("enabled", True) and report_settings(sp).get("last") != today
               and sp.get("watchlist")]
        for u_ in due:  # vorab markieren -> kein Doppelversand bei parallelen Prüfungen
            data["u"][u_]["report"]["last"] = today
        if due:
            STORE.dirty = True
    for i_, u_ in enumerate(due):  # Konten nacheinander, mit Pause und Aufräumen dazwischen
        if i_:
            time.sleep(REPORT_USER_PAUSE)
        try:
            send_weekly_report(u_)
        except Exception:
            LOG.exception("[Bericht] Versand an %s fehlgeschlagen", u_)
        safe(prune_caches)
    if due:
        safe(STORE.save)


def alerts_payload(user, host_url=""):
    data = STORE.load()
    sp = user_space(user)
    base = host_url or app_base_url()
    return {"alerts": sp["alerts"], "topic": sp["topic"], "last_check": data.get("last_check"), "user": user,
            "storage": STORE.backend, "persistent": STORE.persistent, "error": STORE.error,
            "encrypted": STORE.encrypted,
            "hosted": "RENDER" in os.environ,
            "cron_url": f"{base}/api/cron?key={cron_key()}" if app_password() else "",
            "report": dict(report_settings(sp))}


def save_alert(body, user):
    sym = str(body.get("symbol") or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9.\-^=]{1,15}", sym):
        raise ValueError("Ungültiges Symbol")

    def pos(key):
        v = num(body.get(key))
        return v if v and v > 0 else None
    cfg = {"name": str(body.get("name") or sym)[:80], "currency": str(body.get("currency") or "")[:6],
           "below": pos("below"), "above": pos("above"), "move": pos("move"), "rating": bool(body.get("rating")),
           "events": bool(body.get("events"))}
    alerts = user_space(user)["alerts"]
    with STORE.lock:
        if not (cfg["below"] or cfg["above"] or cfg["move"] or cfg["rating"] or cfg["events"]):
            alerts.pop(sym, None)
        else:
            old = alerts.get(sym, {}).get("state", {})
            # Neu gespeichert = scharf geschaltet; Verlauf und letzte Empfehlung bleiben erhalten
            cfg["state"] = {"log": old.get("log", []), "events_sent": old.get("events_sent", []),
                            "last_label": str(body.get("label") or "") or old.get("last_label"),
                            "rating_checked": time.time() if body.get("label") else old.get("rating_checked"),
                            "created": old.get("created") or time.time()}
            alerts[sym] = cfg
        STORE.save()


HTML_PATH = Path(__file__).with_name("index.html")
STATIC_DIR = Path(__file__).with_name("static")
WEB_MANIFEST = {
    "name": "Aktien-Check", "short_name": "Aktien-Check", "lang": "de",
    "description": "Kaufen, Halten oder Verkaufen – automatisierte Aktienanalyse",
    "start_url": "/", "scope": "/", "display": "standalone",
    "background_color": "#0c111d", "theme_color": "#1f4fd8",
    "icons": [{"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
              {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"},
              {"src": "/static/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}],
}

# --- Login mit dauerhafter Sitzung (nur aktiv, wenn APP_PASSWORD gesetzt ist) ---
SESSION_COOKIE = "ac_session"
SESSION_DAYS = 365
FAILED_LOGINS = {}  # IP -> Zeitstempel fehlgeschlagener Versuche
FAILED_LOCK = threading.Lock()


def app_password():
    return os.environ.get("APP_PASSWORD") or ""


def session_secret():
    # Aus dem Passwort abgeleitet: Passwortwechsel meldet alle Geräte ab.
    return hashlib.sha256(("aktien-check-session|" + app_password()).encode("utf-8")).digest()


def make_session_token(user):
    """Token "benutzer.ablauf.version.signatur"; Version steigt bei Passwortwechsel -> alte Sitzungen ungültig."""
    ver = int(users().get(user, {}).get("ver", 0))
    payload = f"{user}.{int(time.time()) + SESSION_DAYS * 86400}.{ver}"
    sig = hmac.new(session_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def session_user(token):
    try:
        user, exp, ver, sig = token.split(".")
        good = hmac.new(session_secret(), f"{user}.{exp}.{ver}".encode(), hashlib.sha256).hexdigest()
        if int(exp) < time.time() or not hmac.compare_digest(sig, good):
            return None
        acc = users().get(user)
        return user if acc and int(acc.get("ver", 0)) == int(ver) else None
    except Exception:
        return None


def too_many_failures(ip):
    now = time.time()
    with FAILED_LOCK:
        recent = [t for t in FAILED_LOGINS.get(ip, []) if now - t < 900]
        FAILED_LOGINS[ip] = recent
        return len(recent) >= 8


def note_failure(ip):
    with FAILED_LOCK:
        FAILED_LOGINS.setdefault(ip, []).append(time.time())


LOGIN_PAGE = """<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Aktien-Check">
<link rel="apple-touch-icon" href="/static/apple-touch-icon.png">
<link rel="icon" type="image/png" sizes="192x192" href="/static/icon-192.png">
<link rel="manifest" href="/manifest.webmanifest">
<meta name="theme-color" content="#1f4fd8">
<title>Anmelden · Aktien-Check</title>
<style>
:root{--bg:#f5f6f8;--surface:#fff;--border:#d0d5dd;--text:#101828;--text-2:#475467;--accent:#1f4fd8;--accent-soft:#eef3ff;--neg:#b42318;--neg-soft:#fef3f2}
@media (prefers-color-scheme:dark){:root{--bg:#0c111d;--surface:#131a2a;--border:#334056;--text:#f2f4f7;--text-2:#b4bccb;--accent:#7c9cff;--accent-soft:#1a2547;--neg:#f97066;--neg-soft:#2f1414}}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--text);
  font:15px/1.5 Inter,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;padding:16px}
.box{width:100%;max-width:380px;background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:28px}
.logo{width:40px;height:40px;border-radius:10px;background:var(--accent);display:grid;place-items:center;margin-bottom:16px}
h1{font-size:21px;margin:0 0 4px;letter-spacing:-.01em}
p{margin:0 0 20px;color:var(--text-2);font-size:14px}
label{display:block;font-size:13px;font-weight:600;margin-bottom:6px}
input{width:100%;height:46px;padding:0 14px;border:1px solid var(--border);border-radius:10px;background:var(--surface);
  color:var(--text);font:inherit;font-size:16px}
input:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
button{width:100%;height:46px;margin-top:14px;border:0;border-radius:10px;background:var(--accent);color:#fff;
  font:inherit;font-weight:600;font-size:15px;cursor:pointer}
.err{background:var(--neg-soft);color:var(--neg);font-size:13.5px;padding:10px 12px;border-radius:8px;margin-bottom:14px}
small{display:block;margin-top:16px;color:var(--text-2);font-size:12.5px;text-align:center}
</style></head><body>
<form class="box" method="post" action="/login">
  <div class="logo"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.4"
    stroke-linecap="round" stroke-linejoin="round"><path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/></svg></div>
  <h1>Aktien-Check</h1>
  <p>Bitte einmal anmelden – dieses Gerät bleibt danach angemeldet.</p>
  {error}
  <input type="hidden" name="next" value="{next}">
  <label for="un">Benutzername</label>
  <input id="un" name="username" autocomplete="username" autocapitalize="none" autocorrect="off" spellcheck="false"
    value="{user}" required {ufocus}>
  <label for="pw" style="margin-top:12px">Passwort</label>
  <input id="pw" name="password" type="password" autocomplete="current-password" required {pfocus}>
  <button type="submit">Anmelden</button>
  <small>Angemeldet für {days} Tage oder bis das Passwort geändert wird. Zugang erhältst du vom Administrator.</small>
</form></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def send(self, code, body, ctype, cookie=None):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def client_ip(self):
        fwd = self.headers.get("X-Forwarded-For", "")
        return fwd.split(",")[0].strip() if fwd else self.client_address[0]

    def current_user(self):
        if not app_password():
            return "admin"  # lokal ohne Passwort: ein Benutzer
        if hasattr(self, "_user"):
            return self._user
        jar = http.cookies.SimpleCookie()
        try:
            jar.load(self.headers.get("Cookie", ""))
        except http.cookies.CookieError:
            jar = {}
        c = jar.get(SESSION_COOKIE)
        self._user = session_user(c.value) if c else None
        return self._user

    def logged_in(self):
        return self.current_user() is not None

    def is_admin(self):
        u = self.current_user()
        return bool(u and users().get(u, {}).get("admin"))

    def send_json(self, obj, code=200, cookie=None):
        return self.send(code, json.dumps(json_safe(obj), ensure_ascii=False), "application/json; charset=utf-8", cookie)

    def redirect(self, location, cookie=None):
        self.send_response(303)
        self.send_header("Location", location)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def cookie(self, value, max_age):
        secure = "; Secure" if self.headers.get("X-Forwarded-Proto", "") == "https" else ""
        return f"{SESSION_COOKIE}={value}; Max-Age={max_age}; Path=/; HttpOnly; SameSite=Lax{secure}"

    def login_page(self, error="", nxt="/", code=200, user=""):
        err = f'<div class="err">{error}</div>' if error else ""
        clean = lambda v: v.replace('"', "").replace("<", "").replace(">", "")
        page = (LOGIN_PAGE.replace("{error}", err).replace("{next}", clean(nxt)).replace("{days}", str(SESSION_DAYS))
                .replace("{user}", clean(user)).replace("{ufocus}", "" if user else "autofocus")
                .replace("{pfocus}", "autofocus" if user else ""))
        return self.send(code, page, "text/html; charset=utf-8")

    def require_login(self, u):
        if self.logged_in():
            return True
        # Abrufe aus der Seite (fetch) bekommen 401; direkt im Browser geöffnete Links die Login-Seite
        if u.path.startswith("/api/") and "text/html" not in self.headers.get("Accept", ""):
            self.send(401, json.dumps({"error": "login"}), "application/json")
        else:
            target = u.path + (("?" + u.query) if u.query else "")
            self.redirect("/login?" + urllib.parse.urlencode({"next": target}))
        return False

    def host_url(self):
        host = self.headers.get("Host", "")
        proto = self.headers.get("X-Forwarded-Proto", "http")
        return f"{proto}://{host}" if host else ""

    def json_body(self):
        length = min(int(self.headers.get("Content-Length") or 0), 16384)
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return {}

    def _guard(self, fn):
        try:
            fn()
        except (BrokenPipeError, ConnectionResetError):
            pass  # Browser hat die Verbindung geschlossen
        except Exception:
            LOG.exception("[Server] Fehler bei %s %s", self.command, urllib.parse.urlparse(self.path).path)
            try:
                self.send(500, json.dumps({"error": "Interner Fehler"}), "application/json")
            except Exception:
                pass

    def do_POST(self):
        self._guard(self._do_POST)

    def _do_POST(self):
        u = urllib.parse.urlparse(self.path)
        if u.path.startswith("/api/"):
            if not self.require_login(u):
                return
            if "application/json" not in self.headers.get("Content-Type", ""):
                return self.send(415, json.dumps({"error": "JSON erwartet"}), "application/json")
            body = self.json_body()
            user = self.current_user()
            try:
                if u.path == "/api/watchlist":
                    with STORE.lock:
                        user_space(user)["watchlist"] = clean_watchlist(body.get("items"))
                    save_async()
                    return self.send_json({"items": user_space(user)["watchlist"]})
                if u.path == "/api/account/password":
                    if not app_password():
                        raise ValueError("Lokal ohne Anmeldung nicht nötig")
                    if not authenticate(user, str(body.get("old") or "")):
                        raise ValueError("Das aktuelle Passwort stimmt nicht.")
                    new = str(body.get("new") or "")
                    if len(new) < 8:
                        raise ValueError("Das neue Passwort muss mindestens 8 Zeichen haben.")
                    with STORE.lock:
                        acc = users()[user]
                        acc["pw"], acc["ver"] = hash_pw(new), int(acc.get("ver", 0)) + 1  # andere Geräte abmelden
                    STORE.save()
                    return self.send_json({"ok": True}, cookie=self.cookie(make_session_token(user), SESSION_DAYS * 86400))
                if u.path == "/api/subscription":
                    return self.send_json({**sub_user_action(user, body.get("action")), "payment_info": payment_info()})
                if u.path == "/api/admin/subscription":
                    if not self.is_admin():
                        return self.send_json({"error": "Nur für Administratoren"}, 403)
                    if body.get("payment_info") is not None:
                        txt = str(body.get("payment_info") or "").strip()[:1500]
                        data_ = STORE.load()
                        with STORE.lock:
                            data_.setdefault("settings", {})["payment_info"] = txt
                            STORE.dirty = True
                        save_async()
                        return self.send_json({"ok": True, "message": "Zahlungsanleitung gespeichert"})
                    st_ = sub_admin_action(user, str(body.get("username") or "").strip().lower(), body.get("action"),
                                           body.get("months", 1))
                    return self.send_json({"ok": True, "sub": st_})
                if u.path == "/api/admin/system":
                    if not self.is_admin():
                        return self.send_json({"error": "Nur für Administratoren"}, 403)
                    act = body.get("action")
                    LOG.info("[Admin] %s: System-Aktion %s", user, act)
                    if act == "diag":
                        return self.send(200, json.dumps({"checks": data_source_checks(str(body.get("symbol") or "SAP.DE")[:15])},
                                                         ensure_ascii=False), "application/json; charset=utf-8")
                    if act == "clear_cache":
                        for _n, c, _t, _m in cache_rules():
                            c.clear()
                        mb = release_memory()
                        return self.send_json({"ok": True, "message": "Zwischenspeicher geleert" + (f" – Speicher jetzt {mb:.0f} MB" if mb else "")})
                    if act == "reset_all":
                        if SCREENER_STATE["running"]:
                            SCREENER_STATE["stop"] = True          # laufenden Durchgang beenden
                            for _ in range(60):
                                if not SCREENER_STATE["running"]:
                                    break
                                time.sleep(0.5)
                        removed = sum(len(c) for _n, c, _t, _m in cache_rules()) + len(FIN_CUR_CACHE)
                        for _n, c, _t, _m in cache_rules():
                            c.clear()
                        FIN_CUR_CACHE.clear()
                        data_ = STORE.load()
                        with STORE.lock:
                            n_scr = len(data_.get("screener") or {})
                            data_["screener"] = {}
                            STORE.dirty = True
                        SCREENER_STATE.update(done=0, target=0, finished=None, mem_stop=False, seen=set())
                        STORE.save()
                        mb = release_memory()
                        LOG.warning("[Admin] %s: alles geleert – %d Zwischenspeicher-Einträge, %d Screener-Werte", user, removed, n_scr)
                        return self.send_json({"ok": True, "message": f"Geleert: {removed} Zwischenspeicher-Einträge und {n_scr} Screener-Werte"
                                               + (f" – Speicher jetzt {mb:.0f} MB" if mb else "")})
                    if act == "save":
                        STORE.save()
                        return self.send_json({"ok": True, "message": "Speicher gesichert"})
                    if act == "check_alerts":
                        n = len(run_alert_checks() or [])
                        return self.send_json({"ok": True, "message": f"Alarme geprüft – {n} ausgelöst"})
                    return self.send_json({"error": "unbekannte Aktion"}, 400)
                if u.path == "/api/admin/users":
                    if not self.is_admin():
                        return self.send_json({"error": "Nur für Administratoren"}, 403)
                    self.admin_action(body, user)
                    return self.send_json(self.admin_list())
                if u.path == "/api/screener/start":
                    unis_ = body.get("unis") if isinstance(body.get("unis"), list) else None
                    ok, msg = screener_start(user, "all" if body.get("mode") == "all" else "due", unis_)
                    return self.send(200, json.dumps(json_safe({**screener_payload(), "message": msg, "started": ok}),
                                                     ensure_ascii=False), "application/json; charset=utf-8")
                if u.path == "/api/screener/stop":
                    if SCREENER_STATE["running"]:
                        SCREENER_STATE["stop"] = True
                        LOG.info("[Screener] Stopp angefordert von %s", user)
                    return self.send(200, json.dumps(json_safe(screener_payload()), ensure_ascii=False),
                                     "application/json; charset=utf-8")
                if u.path == "/api/report":
                    with STORE.lock:
                        report_settings(user_space(user))["enabled"] = bool(body.get("enabled"))
                        STORE.dirty = True
                    save_async()
                    return self.send_json(alerts_payload(user, self.host_url()))
                if u.path == "/api/report/send":
                    threading.Thread(target=lambda: safe(lambda: send_weekly_report(user, manual=True)), daemon=True).start()
                    return self.send_json({"ok": True})
                if not u.path.startswith("/api/alerts"):
                    return self.send(404, json.dumps({"error": "unbekannt"}), "application/json")
                if u.path == "/api/alerts":
                    save_alert(body, user)
                elif u.path == "/api/alerts/test":
                    ntfy_send("✅ Aktien-Check: Test", f"Push-Benachrichtigungen für „{user}“ funktionieren.",
                              tags=["white_check_mark"], topic=user_space(user)["topic"])
                elif u.path == "/api/alerts/check":
                    fired = [f for f in run_alert_checks(force_rating=bool(body.get("rating"))) if f.get("user") == user]
                    return self.send(200, json.dumps({**alerts_payload(user, self.host_url()), "fired": fired},
                                                     ensure_ascii=False), "application/json; charset=utf-8")
                else:
                    return self.send(404, json.dumps({"error": "unbekannt"}), "application/json")
            except ValueError as e:
                return self.send(400, json.dumps({"error": str(e)}, ensure_ascii=False), "application/json")
            except Exception as e:
                return self.send(502, json.dumps({"error": f"{type(e).__name__}: {e}"[:200]}, ensure_ascii=False),
                                 "application/json")
            return self.send(200, json.dumps(alerts_payload(user, self.host_url()), ensure_ascii=False),
                             "application/json; charset=utf-8")
        if u.path != "/login":
            return self.send(404, "Not found", "text/plain")
        length = min(int(self.headers.get("Content-Length") or 0), 4096)
        form = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8", "replace"))
        nxt = (form.get("next") or ["/"])[0]
        if not nxt.startswith("/") or nxt.startswith("//"):
            nxt = "/"
        ip = self.client_ip()
        if too_many_failures(ip):
            LOG.warning("[Login] gesperrt wegen Fehlversuchen: IP %s", ip)
            return self.login_page("Zu viele Fehlversuche. Bitte in 15 Minuten erneut versuchen.", nxt, 429)
        given = (form.get("password") or [""])[0]
        username = (form.get("username") or [""])[0].strip().lower()
        if app_password() and USER_RE.fullmatch(username) and authenticate(username, given):
            with STORE.lock:
                users()[username]["last_login"] = time.time()
            STORE.dirty = True
            LOG.info("[Login] angemeldet: %s", username)
            return self.redirect(nxt, self.cookie(make_session_token(username), SESSION_DAYS * 86400))
        LOG.warning("[Login] fehlgeschlagen: Benutzer %r, IP %s", username[:40], ip)
        note_failure(ip)
        time.sleep(1)  # bremst Durchprobieren
        return self.login_page("Benutzername oder Passwort falsch.", nxt, 401, username)

    def admin_list(self):
        out = []
        for name, acc in sorted(users().items()):
            sp = STORE.load()["u"].get(name, {})
            out.append({"name": name, "admin": bool(acc.get("admin")), "created": acc.get("created"),
                        "last_login": acc.get("last_login"), "alerts": len(sp.get("alerts", {})),
                        "watchlist": len(sp.get("watchlist", []))})
        return {"users": out, "me": self.current_user()}

    def admin_action(self, body, me):
        action = body.get("action")
        if not action:
            return
        LOG.info("[Admin] %s: %s %s", me, action, str(body.get("username") or "")[:40])
        name = str(body.get("username") or "").strip().lower()
        if not USER_RE.fullmatch(name):
            raise ValueError("Benutzername: 2–32 Zeichen, nur a–z, 0–9, - und _")
        accs = users()
        with STORE.lock:
            if action == "create":
                if name in accs:
                    raise ValueError("Diesen Benutzer gibt es bereits.")
                pw = str(body.get("password") or "")
                if len(pw) < 8:
                    raise ValueError("Das Startpasswort muss mindestens 8 Zeichen haben.")
                accs[name] = {"pw": hash_pw(pw), "admin": bool(body.get("admin")), "created": time.time(), "ver": 0}
                user_space(name)
            elif name not in accs:
                raise ValueError("Unbekannter Benutzer")
            elif action == "reset":
                pw = str(body.get("password") or "")
                if len(pw) < 8:
                    raise ValueError("Das neue Passwort muss mindestens 8 Zeichen haben.")
                accs[name]["pw"], accs[name]["ver"] = hash_pw(pw), int(accs[name].get("ver", 0)) + 1
            elif action == "delete":
                if name == me or name == "admin":
                    raise ValueError("Dieses Konto kann nicht gelöscht werden.")
                accs.pop(name)
                STORE.load()["u"].pop(name, None)
            elif action == "admin":
                if name == me or name == "admin":
                    raise ValueError("Die eigenen Admin-Rechte können nicht geändert werden.")
                accs[name]["admin"] = not accs[name].get("admin")
            else:
                raise ValueError("Unbekannte Aktion")
        STORE.save()

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        self._guard(self._do_GET)

    def _do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == "/healthz":
            return self.send(200, "ok", "text/plain")
        if u.path == "/manifest.webmanifest":
            return self.send(200, json.dumps(WEB_MANIFEST, ensure_ascii=False), "application/manifest+json; charset=utf-8")
        if u.path.startswith("/static/"):
            f = STATIC_DIR / Path(u.path).name  # nur Dateien direkt im Ordner, kein Pfad-Ausbruch
            if f.suffix == ".png" and f.is_file():
                data = f.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "public, max-age=604800")
                self.end_headers()
                self.wfile.write(data)
                return
            return self.send(404, "Not found", "text/plain")
        qs = urllib.parse.parse_qs(u.query)
        if u.path == "/login":
            nxt = (qs.get("next") or ["/"])[0]
            if not nxt.startswith("/") or nxt.startswith("//"):
                nxt = "/"
            return self.redirect(nxt) if self.logged_in() else self.login_page(nxt=nxt)
        if u.path == "/logout":
            return self.redirect("/login", self.cookie("", 0))
        if u.path == "/api/cron":  # Weckruf von cron-job.org: prüft Alarme im Hintergrund
            if not app_password() or not hmac.compare_digest((qs.get("key") or [""])[0], cron_key()):
                return self.send(403, "forbidden", "text/plain")
            threading.Thread(target=lambda: (safe(run_alert_checks), safe(send_due_reports)), daemon=True).start()
            return self.send(200, "ok", "text/plain")
        if not self.require_login(u):
            return
        q = (qs.get("q") or [""])[0].strip()
        if u.path in ("/", "/index.html"):
            return self.send(200, HTML_PATH.read_bytes(), "text/html; charset=utf-8")
        if u.path == "/api/diag":  # Erreichbarkeit der Datenquellen prüfen
            sym = q or "SAP.DE"
            checks = {
                "info": lambda: str(current_price(yf.Ticker(sym).info)),
                "history": lambda: str(len(yf.Ticker(sym).history(period="5d"))),
                "search": lambda: str(len(search_symbols(sym))),
                "statements": lambda: str(len(yf.Ticker(sym).quarterly_income_stmt.columns)),
                "fast_info": lambda: str(yf.Ticker(sym).fast_info.market_cap),
                "calendar": lambda: str(yf.Ticker(sym).calendar.get("Earnings Date")),
                "earnings_dates": lambda: str(len(yf.Ticker(sym).get_earnings_dates(limit=8))),
                "google_news": lambda: str(len(google_news(sym, "en"))),
                "finnhub_key": lambda: "gesetzt" if finnhub_key() else "FEHLT",
                "finnhub": lambda: str(len(finnhub("stock/recommendation", symbol=sym.split(".")[0]) or [])) + " Perioden",
            }
            out = {}
            for name, fn in checks.items():
                try:
                    out[name] = "ok: " + fn()
                except Exception as e:
                    out[name] = f"{type(e).__name__}: {e}"[:300]
            return self.send(200, json.dumps(out, ensure_ascii=False), "application/json; charset=utf-8")
        user = self.current_user()
        if u.path == "/api/me":
            sp_ = user_space(user)
            if time.time() - (sp_.get("last_seen") or 0) > 300:
                sp_["last_seen"] = int(time.time())
                STORE.dirty = True
            return self.send_json({"user": user, "admin": self.is_admin(), "multi": bool(app_password())})
        if u.path == "/api/subscription":
            acc_ = users().get(user) or {}
            return self.send_json({**sub_status(user_space(user)), "admin": bool(acc_.get("admin")) or not app_password(),
                                   "payment_info": payment_info()})
        if u.path == "/api/admin/dashboard":
            if not self.is_admin():
                return self.send_json({"error": "Nur für Administratoren"}, 403)
            return self.send(200, json.dumps(json_safe(admin_dashboard()), ensure_ascii=False), "application/json; charset=utf-8")
        if u.path == "/api/watchlist":
            return self.send_json({"items": user_space(user)["watchlist"]})
        if u.path == "/api/screener":
            return self.send(200, json.dumps(json_safe(screener_payload()), ensure_ascii=False),
                             "application/json; charset=utf-8")
        if u.path == "/api/track":
            everyone = (qs.get("scope") or [""])[0] == "all" and self.is_admin()
            t0 = time.time()
            res = track_payload(user, everyone)
            LOG.info("[Trefferquote] %s · %d Signale · %.1f s", "alle" if everyone else user, len(res["signals"]),
                     time.time() - t0)
            return self.send(200, json.dumps(json_safe(res), ensure_ascii=False), "application/json; charset=utf-8")
        if u.path == "/api/admin/users":
            return self.send_json(self.admin_list()) if self.is_admin() else self.send_json({"error": "Nur für Administratoren"}, 403)
        if u.path == "/api/alerts":
            return self.send(200, json.dumps(alerts_payload(user, self.host_url()), ensure_ascii=False),
                             "application/json; charset=utf-8")
        if u.path == "/api/ics":
            sym = q.upper()
            if not re.fullmatch(r"[A-Z0-9.\-^=]{1,15}", sym):
                return self.send(400, "Ungültiges Symbol", "text/plain")
            name = (qs.get("name") or [sym])[0][:80]
            body = ics_calendar(sym, name, company_events(sym))
            data = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/calendar; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="{re.sub(r"[^A-Za-z0-9]", "_", sym)}-termine.ics"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if u.path == "/api/chart":
            try:
                return self.send(200, json.dumps(json_safe(chart_data(q, (qs.get("range") or ["1y"])[0]))),
                                 "application/json; charset=utf-8")
            except ValueError as e:
                return self.send(400, json.dumps({"error": str(e)}, ensure_ascii=False), "application/json")
        if u.path == "/api/income":
            try:
                return self.send(200, json.dumps(json_safe(income_data(q, (qs.get("freq") or ["annual"])[0]))),
                                 "application/json; charset=utf-8")
            except ValueError as e:
                return self.send(400, json.dumps({"error": str(e)}, ensure_ascii=False), "application/json")
        if u.path == "/api/search":
            return self.send(200, json.dumps(search_symbols(q, include_crypto=True) if len(q) >= 2 else []), "application/json")
        if u.path == "/api/analyze":
            if not q:
                return self.send(400, json.dumps({"error": "Bitte Aktie eingeben."}), "application/json")
            t0 = time.time()
            try:
                res = analyze(q)
                res = {**res, "history": safe(lambda: record_history(res, user), []) or []}
                safe(lambda: record_usage(user, res["symbol"]))
                LOG.info("[Analyse] %s -> %s · %s (%+.1f) · %.1f s · %s", q, res["symbol"], res["rating"]["label"],
                         res["rating"]["score"], time.time() - t0, user)
                return self.send(200, json.dumps(json_safe(res), ensure_ascii=False), "application/json; charset=utf-8")
            except ValueError as e:
                LOG.warning("[Analyse] %s nicht möglich: %s", q, e)
                return self.send(404, json.dumps({"error": str(e)}, ensure_ascii=False), "application/json")
            except Exception as e:
                LOG.exception("[Analyse] %s abgebrochen nach %.1f s", q, time.time() - t0)
                return self.send(500, json.dumps({"error": f"Fehler bei der Analyse: {e}"}, ensure_ascii=False),
                                 "application/json")
        self.send(404, "Not found", "text/plain")


def lan_ips():
    """IPv4-Adressen dieses PCs im lokalen Netz."""
    import socket
    ips = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))  # sendet nichts, ermittelt nur die ausgehende Schnittstelle
            ips.add(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    return sorted(ip for ip in ips if not ip.startswith("127."))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args:
        res = analyze(" ".join(args))
        print(f"{res['name']} ({res['symbol']}): {res['rating']['label']} [{res['rating']['group']}], "
              f"Score {res['rating']['score']}, Urteil: {res['summary']['adjective']}")
        for c in res["categories"]:
            print(f"  {c['title']}: {c['adjective']}")
        return
    hosted = "PORT" in os.environ  # z. B. bei einem Cloud-Hoster
    port = int(os.environ.get("PORT", PORT))
    network = "--netz" in sys.argv or hosted
    srv = ThreadingHTTPServer(("0.0.0.0" if network else "127.0.0.1", port), Handler)
    LOG.info("[Start] Python %s · yfinance %s · Port %s · Login %s · Finnhub %s · Speicher %s%s",
             sys.version.split()[0], getattr(yf, "__version__", "?"), port, "an" if app_password() else "aus",
             "an" if finnhub_key() else "aus", STORE.backend, " (verschlüsselt)" if store_key() else "")
    url = f"http://localhost:{port}"
    print(f"Aktien-Check läuft auf {url}  (Beenden mit Strg+C)")
    if network and not hosted:
        print("\nVon anderen Geräten im selben WLAN/Netzwerk erreichbar unter:")
        for ip in lan_ips():
            print(f"   http://{ip}:{port}")
        print("(Falls Windows nach der Firewall fragt: Zugriff für 'Private Netzwerke' erlauben.)\n")
    if "--no-browser" not in sys.argv and not hosted:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        limit_malloc_arenas()
        threading.Thread(target=alert_loop, daemon=True).start()
        threading.Thread(target=history_flush_loop, daemon=True).start()
        srv.serve_forever()
    except KeyboardInterrupt:
        print("Beendet.")


if __name__ == "__main__":
    main()
