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
        "welt.de", "capital.de", "investors.com", "zacks.com", "benzinga.com", "thestreet.com"],
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

POS_WORDS = ["beat", "beats", "surge", "surges", "soar", "soars", "jump", "jumps", "rally", "rallies",
             "upgrade", "upgraded", "upgrades", "record", "raises", "raised", "strong", "outperform",
             "bullish", "gain", "gains", "rise", "rises", "tops", "exceeds", "expands", "wins", "approval",
             "approved", "partnership", "boost", "boosts", "buy rating", "growth", "higher", "climbs",
             "steigt", "steigen", "rekord", "hebt", "erhöht", "übertrifft", "stark", "starke", "kaufempfehlung",
             "plus", "legt zu", "zulegen", "hoch", "gewinnt", "kursziel erhöht", "hochgestuft", "wachstum",
             "optimistisch", "rally", "aufwärts"]
NEG_WORDS = ["miss", "misses", "plunge", "plunges", "fall", "falls", "drop", "drops", "slump", "slumps",
             "downgrade", "downgraded", "downgrades", "cut", "cuts", "weak", "loss", "losses", "lawsuit",
             "probe", "investigation", "recall", "warning", "warns", "bearish", "decline", "declines",
             "layoffs", "fraud", "fine", "fined", "bankruptcy", "tumble", "tumbles", "sinks", "lower",
             "slides", "sell-off", "selloff", "concern", "concerns", "fällt", "fallen", "sinkt", "verlust",
             "warnung", "warnt", "senkt", "gesenkt", "herabstufung", "abgestuft", "bricht ein", "schwach",
             "schwache", "klage", "minus", "einbruch", "kursrutsch", "ermittlung", "rückruf", "stellenabbau",
             "pleite", "insolvenz", "abwärts"]


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------
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
def search_symbols(q):
    out = []
    res = safe(lambda: yf.Search(q, max_results=10, news_count=0).quotes, [])
    if not res:
        url = "https://query2.finance.yahoo.com/v1/finance/search?" + urllib.parse.urlencode(
            {"q": q, "quotesCount": 10, "newsCount": 0})
        res = safe(lambda: json.loads(http_get(url)).get("quotes", []), [])
    for it in res or []:
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
    put("quoteType", "EQUITY")

    inc, qinc = safe(lambda: t.income_stmt), safe(lambda: t.quarterly_income_stmt)
    cf, qcf = safe(lambda: t.cashflow), safe(lambda: t.quarterly_cashflow)
    bs, qbs = safe(lambda: t.balance_sheet), safe(lambda: t.quarterly_balance_sheet)
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
    if re.fullmatch(r"[A-Za-z0-9.\-^=]{1,15}", q):
        sym = q.upper()
        t = yf.Ticker(sym)
        info = safe(lambda: t.info, {}) or {}
        found = search_symbols(info.get("longName") or q)
        hint = next((a for a in found if a["symbol"] == sym), None)
        if current_price(info) or hint:
            info = fill_info(t, info, hint)
        if current_price(info) and info.get("quoteType", "EQUITY") == "EQUITY":
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


def headline_sentiment(title):
    t = " " + title.lower() + " "
    for phrase in ("weight loss", "weight-loss", "stop-loss", "stop loss", "abnehm"):  # keine Wertung
        t = t.replace(phrase, " ")
    pos = sum(1 for w in POS_WORDS if re.search(r"(?<![a-zäöüß])" + re.escape(w) + r"(?![a-zäöüß])", t))
    neg = sum(1 for w in NEG_WORDS if re.search(r"(?<![a-zäöüß])" + re.escape(w) + r"(?![a-zäöüß])", t))
    if pos == neg:
        return 0.0
    return clamp((pos - neg) / max(1, pos + neg))


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


def collect_news(symbol, company, website, siblings=()):
    company_domain = domain_of(website) if website else ""
    base_sym = symbol.split(".")[0]
    jobs = {
        "en": lambda: google_news(f'"{company}" stock', "en"),
        "de": lambda: google_news(f'"{company}" Aktie', "de"),
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
    m["is_financial"] = m["sector"] == "Financial Services" or "Bank" in m["industry"] or "Insurance" in m["industry"]

    inc = safe(lambda: t.income_stmt)
    cf = safe(lambda: t.cashflow)
    bs = safe(lambda: t.balance_sheet)
    hist = safe(lambda: t.history(period="5y", auto_adjust=True))
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
    m["fcf"] = num(g("freeCashflow")) or first(fcf_hist)
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
    revs = row(inc, "Total Revenue")
    ops = row(inc, "Operating Income")
    nis = row(inc, "Net Income")
    m["revenues"], m["net_incomes"] = revs, nis
    om_hist = [o / r for o, r in zip(ops, revs) if o is not None and r]
    m["op_m_trend"] = (om_hist[0] - om_hist[-1]) if len(om_hist) >= 2 else None
    m["loss_years"] = sum(1 for n in nis if n is not None and n < 0)
    rd = first(row(inc, "Research And Development"))
    m["rd_ratio"] = rd / m["revenue"] if rd and m["revenue"] else None

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

    # --- Dividende
    m["div_yield"] = num(g("trailingAnnualDividendYield"))
    m["payout"] = num(g("payoutRatio"))
    m["div_cut"], m["div_streak"], m["div_years"] = False, 0, 0
    if divs is not None and len(divs):
        d = divs.copy()
        d.index = d.index.tz_localize(None) if d.index.tz is not None else d.index
        last_year = datetime.now() - timedelta(days=365)
        ttm = float(d[d.index >= last_year].sum())
        if m["price"] and ttm > 0:
            m["div_yield"] = ttm / m["price"]
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
def score_valuation(m, mac):
    ref_pe, ref_ev = SECTOR_REF.get(m["sector"], (20, 13))
    parts, why = [], []
    pe = m["pe"]
    if pe and pe > 0:
        s = clamp((1 - pe / ref_pe) * 1.5)
        parts.append((s, 1.0))
        why.append(f"KGV {fnum(pe)} vs. Branchen-Referenz ~{ref_pe} ({m['sector'] or 'Markt'})")
    elif m["net_m"] is not None and m["net_m"] < 0:
        parts.append((-0.4, 1.0))
        why.append("Kein positives KGV – Unternehmen schreibt Verluste")
    if pe and pe > 0 and m["pe_hist_med"]:
        s = clamp((1 - pe / m["pe_hist_med"]) * 1.5)
        parts.append((s, 1.0))
        why.append(f"KGV vs. eigener Historie (Median {fnum(m['pe_hist_med'])}, {len(m['pe_hist'])} Jahre)")
    if m["fpe"] and m["fpe"] > 0 and pe and pe > 0:
        why.append(f"Forward-KGV {fnum(m['fpe'])} ({'Gewinnanstieg erwartet' if m['fpe'] < pe else 'Gewinnrückgang erwartet'})")
    if m["ev_ebitda"] and m["ev_ebitda"] > 0 and not m["is_financial"]:
        parts.append((clamp((1 - m["ev_ebitda"] / ref_ev) * 1.5), 1.0))
        why.append(f"EV/EBITDA {fnum(m['ev_ebitda'])} vs. Branche ~{ref_ev}")
    if m["fcf_yield"] is not None and not m["is_financial"]:
        parts.append((clamp((m["fcf_yield"] - 0.04) / 0.04), 1.0))
        why.append(f"Free-Cashflow-Rendite {pct(m['fcf_yield'])} (4 % ≈ neutral)")
    if m["peg"] and m["peg"] > 0:
        parts.append((clamp((1.5 - m["peg"]) / 1.0), 0.7))
        why.append(f"PEG-Ratio {fnum(m['peg'], 2)} (unter 1 = günstig relativ zum Wachstum)")
    if m["upside"] is not None and (m["n_analysts"] >= 3 or m.get("target_n", 0) >= 2):
        w = 0.6 if not m.get("target_n") else 0.6 * min(1.0, m["target_n"] / 6)  # wenige Meldungen -> weniger Gewicht
        parts.append((clamp(m["upside"] / 0.3), w))
        src = f" ({m['target_src']})" if m.get("target_src") else ""
        why.append(f"Analysten-Kursziel {fnum(m['target'], 2)} {m['currency']} → {pct(m['upside'])} Potenzial{src}")
        if m.get("target_n"):
            why.append("Einzelziele: " + " · ".join(f"{t['firm']} {fnum(t['value'], 0)}" for t in m["target_items"][:8]))

    # Eingepreiste Erwartungen (Reverse-DCF)
    r = clamp((mac["rf"] or 4.0) / 100 + (m["beta"] or 1.0) * 0.05, 0.07, 0.13)
    ev = m["ev"] or ((m["mcap"] or 0) + (m["net_debt"] or 0))
    implied = None if m["is_financial"] else reverse_dcf(m["fcf"], ev, r)
    def med(xs):
        xs = sorted(x for x in xs if x is not None)
        return (xs[(len(xs) - 1) // 2] + xs[len(xs) // 2]) / 2 if xs else None
    rev_e, eps_e = med([m["rev_cagr"], m["rev_g"]]), med([m["eps_g"], m["fwd_eps_g"]])
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


def score_quality(m):
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
        parts.append((clamp((m["fcf_m"] - 0.03) / 0.12), 1.0))
        why.append(f"Free-Cashflow-Marge {pct(m['fcf_m'])}")
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
    q = wavg(parts)
    if q is None:
        return {"score": None, "adjective": "solide", "reasons": why + ["Zu wenige Qualitätsdaten"]}
    rev_down = m["rev_cagr"] is not None and m["rev_cagr"] < -0.02
    margin_down = m["op_m_trend"] is not None and m["op_m_trend"] < -0.03
    mcap, om, roe = m["mcap"] or 0, m["op_m"] or 0, m["roe"] or 0
    if q >= 0.25:
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
    return {"score": q, "adjective": adj, "reasons": why}


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
    if m["fwd_eps_g"] is not None:
        vals.append((clamp(m["fwd_eps_g"], -0.5, 0.6), 0.8))
        why.append(f"Erwartetes EPS-Wachstum (Forward vs. Trailing) {pct(m['fwd_eps_g'])}")
    if m["rd_ratio"] is not None:
        why.append(f"F&E-Quote {pct(m['rd_ratio'])} vom Umsatz")
    gr = wavg(vals)
    if gr is None:
        return {"score": None, "adjective": "reif", "reasons": why + ["Keine Wachstumsdaten"]}
    s = clamp((gr - 0.04) / 0.12)
    # Adjektiv orientiert sich primär am Umsatz (Gewinnsprünge sind oft Basiseffekte)
    rev_vals = [x for x in (m["rev_cagr"], m["rev_g"]) if x is not None]
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
    if m["nd_ebitda"] is not None and not m["is_financial"]:
        parts.append((clamp((2.5 - m["nd_ebitda"]) / 2.5), 0.8))
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
    why = [f"Dividendenrendite (12 Monate) {pct(y, 2)}", f"Ausschüttungsquote {pct(p)}"]
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
    return [
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
        {"title": "Bewertung – historisch & im Branchenvergleich", "rows": rows_(
            ["KGV (trailing / forward)", f"{fnum(m['pe'])} / {fnum(m['fpe'])}",
             f"Branche ~{SECTOR_REF.get(m['sector'], (20, 13))[0]}"],
            ["KGV historisch (Median)", fnum(m["pe_hist_med"]),
             ", ".join(fnum(x) for x in m["pe_hist"]) if m["pe_hist"] else ""],
            ["EV/EBITDA", fnum(m["ev_ebitda"]), f"Branche ~{SECTOR_REF.get(m['sector'], (20, 13))[1]}"],
            ["FCF-Rendite", pct(m["fcf_yield"]), ""],
            ["KBV / KUV / PEG", f"{fnum(m['pb'], 2)} / {fnum(m['ps'], 2)} / {fnum(m['peg'], 2)}", ""],
        )},
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
    # Dividendenbereinigter Kurs (für die Gesamtrendite mit wieder angelegten Dividenden)
    adj = [round(float(a), 4) for a in h["Adj Close"]] if "Adj Close" in h and rng != "1d" else None
    if rng in ("1d", "5d", "1mo"):  # letzten Live-Kurs ergänzen
        last = num(safe(lambda: t.fast_info.last_price))
        if last and pts and abs(last / pts[-1][1] - 1) < 0.2:
            if adj:
                adj[-1] = round(adj[-1] * last / pts[-1][1], 4)
            pts[-1][1] = round(last, 4)
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
    out = {"symbol": symbol, "range": rng, "points": pts, "base": base, "intraday": rng in ("1d", "5d", "1mo"),
           "sma50": sma50, "sma200": sma200,
           "volume": volume if volume and any(volume) and len(volume) == len(pts) else None,
           "change": (pts[-1][1] / base - 1) if pts and base else None,
           "adj": adj if adj and len(adj) == len(pts) and all(a > 0 for a in adj) else None,
           "dividends": divs,
           "currency": safe(lambda: t.fast_info.currency) or ""}
    CHART_CACHE[key] = (time.time(), out)
    return out


CACHE = {}


def analyze(query):
    key = query.strip().lower()
    if key in CACHE and time.time() - CACHE[key][0] < 900:
        return CACHE[key][1]
    symbol, t, info, alternatives = resolve(query)
    with ThreadPoolExecutor(max_workers=3) as ex:
        fm = ex.submit(gather, symbol, t, info)
        fmac = ex.submit(gather_macro, info.get("currency") or "")
        company = clean_company_name(info.get("longName") or info.get("shortName") or symbol)
        siblings = sibling_names(company, symbol)
        fnews = ex.submit(collect_news, symbol, company, info.get("website") or "", siblings)
        ftgt = ex.submit(news_targets, company, info.get("currency") or "", current_price(info), siblings)
        fev = ex.submit(company_events, symbol, alternatives, info.get("currency") or "")
        m, mac, news, tgt = fm.result(), fmac.result(), fnews.result(), ftgt.result()
        events = safe(lambda: fev.result(timeout=30), []) or []
    finnhub_enrich(m, symbol, alternatives)
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
        "news": news, "notes": notes, "confidence": confidence, "events": events,
        "generated": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "sources": ["Yahoo Finance"] + (["Finnhub"] if m["finnhub"] else [])
                   + (["Analysten-Schlagzeilen"] if m.get("target_n") else []) + ["Google News", "Pressedienste"],
    }
    CACHE[key] = (time.time(), result)
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
            print(f"[Speicher] {self.backend} · {'verschlüsselt' if self.encrypted else 'unverschlüsselt'}"
                  f" · Schlüssel {'gesetzt' if key else 'fehlt'} · Benutzer: {len(data['users'])}"
                  f" · altes Klartext-Gist: {'vorhanden' if self.plain_gist_id else 'keins'}"
                  f"{' · Umzug durchgeführt' if migrate and not self.error else ''}"
                  f"{' · FEHLER: ' + self.error if self.error else ''}", flush=True)
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
        if len(hist) > HISTORY_MAX_SYMBOLS:  # am längsten nicht analysierte Aktien zuerst verwerfen
            for old in sorted(hist, key=lambda k: hist[k][-1][0] if hist[k] else "")[: len(hist) - HISTORY_MAX_SYMBOLS]:
                if old != sym:
                    hist.pop(old, None)
        STORE.dirty = True
        return [list(x) for x in pts]


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


def history_flush_loop():
    while True:
        time.sleep(60)
        if STORE.dirty:
            safe(STORE.save)


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
                st.setdefault("log", []).insert(0, {"t": now, "title": title})
                st["log"] = st["log"][:10]
            changed = True
        data["last_check"] = now
        if changed or fired:
            STORE.save()
        return fired
    finally:
        CHECK_LOCK.release()


def alert_loop():
    time.sleep(30)
    while True:
        safe(run_alert_checks)
        time.sleep(CHECK_INTERVAL)


def alerts_payload(user, host_url=""):
    data = STORE.load()
    sp = user_space(user)
    base = host_url or app_base_url()
    return {"alerts": sp["alerts"], "topic": sp["topic"], "last_check": data.get("last_check"), "user": user,
            "storage": STORE.backend, "persistent": STORE.persistent, "error": STORE.error,
            "encrypted": STORE.encrypted,
            "hosted": "RENDER" in os.environ,
            "cron_url": f"{base}/api/cron?key={cron_key()}" if app_password() else ""}


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
        return self.send(code, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8", cookie)

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

    def do_POST(self):
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
                if u.path == "/api/admin/users":
                    if not self.is_admin():
                        return self.send_json({"error": "Nur für Administratoren"}, 403)
                    self.admin_action(body, user)
                    return self.send_json(self.admin_list())
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
            return self.login_page("Zu viele Fehlversuche. Bitte in 15 Minuten erneut versuchen.", nxt, 429)
        given = (form.get("password") or [""])[0]
        username = (form.get("username") or [""])[0].strip().lower()
        if app_password() and USER_RE.fullmatch(username) and authenticate(username, given):
            with STORE.lock:
                users()[username]["last_login"] = time.time()
            STORE.dirty = True
            return self.redirect(nxt, self.cookie(make_session_token(username), SESSION_DAYS * 86400))
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
        u = urllib.parse.urlparse(self.path)
        if u.path == "/healthz":
            return self.send(200, "ok", "text/plain")
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
            threading.Thread(target=lambda: safe(run_alert_checks), daemon=True).start()
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
            return self.send_json({"user": user, "admin": self.is_admin(), "multi": bool(app_password())})
        if u.path == "/api/watchlist":
            return self.send_json({"items": user_space(user)["watchlist"]})
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
                return self.send(200, json.dumps(chart_data(q, (qs.get("range") or ["1y"])[0])),
                                 "application/json; charset=utf-8")
            except ValueError as e:
                return self.send(400, json.dumps({"error": str(e)}, ensure_ascii=False), "application/json")
        if u.path == "/api/search":
            return self.send(200, json.dumps(search_symbols(q) if len(q) >= 2 else []), "application/json")
        if u.path == "/api/analyze":
            if not q:
                return self.send(400, json.dumps({"error": "Bitte Aktie eingeben."}), "application/json")
            try:
                print(f"Analysiere: {q} …")
                res = analyze(q)
                res = {**res, "history": safe(lambda: record_history(res, user), []) or []}
                print(f"  -> {res['symbol']}: {res['rating']['label']} ({res['rating']['score']})")
                return self.send(200, json.dumps(res, ensure_ascii=False), "application/json; charset=utf-8")
            except ValueError as e:
                return self.send(404, json.dumps({"error": str(e)}, ensure_ascii=False), "application/json")
            except Exception as e:
                import traceback
                traceback.print_exc()
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
        threading.Thread(target=alert_loop, daemon=True).start()
        threading.Thread(target=history_flush_loop, daemon=True).start()
        srv.serve_forever()
    except KeyboardInterrupt:
        print("Beendet.")


if __name__ == "__main__":
    main()
