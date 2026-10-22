"""Schnelltests ohne Internet: python -m unittest discover -s tests -v

Geprüft werden Rechenlogik, Empfehlungsstufen, Text-Auswertung, Währungsumrechnung, Krypto-Bewertung,
Speicher (inkl. Verschlüsselung und Schutz vor Überschreiben), Login/Sitzungen, Alarme und die Webschnittstelle.
"""
import base64
import http.cookiejar
import json
import math
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pandas as pd  # noqa: E402

import aktien_check as a  # noqa: E402

a.LOG.setLevel("WARNING")  # Info-Protokoll in Tests ausblenden
ENV_KEYS = ("APP_PASSWORD", "GITHUB_TOKEN", "STORE_KEY", "FINNHUB_API_KEY", "FORCE_FALLBACK", "RENDER")


class Isolated(unittest.TestCase):
    """Eigener temporärer Speicher und saubere Umgebungsvariablen je Test."""

    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ENV_KEYS}
        for k in ENV_KEYS:
            os.environ.pop(k, None)
        self._tmp = Path(tempfile.mkdtemp())
        self._file = a.ALERT_FILE
        a.ALERT_FILE = self._tmp / "alerts.json"
        a.STORE.__init__()

    def tearDown(self):
        a.ALERT_FILE = self._file
        a.STORE.__init__()
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self._tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
class TestHelpers(unittest.TestCase):
    def test_json_safe_replaces_nan(self):
        d = a.json_safe({"a": float("nan"), "b": [1.0, float("inf")], "c": {"d": -float("inf")}, "e": "NaN"})
        self.assertEqual(d, {"a": None, "b": [1.0, None], "c": {"d": None}, "e": "NaN"})
        json.dumps(d, allow_nan=False)  # darf keine Ausnahme werfen

    def test_num_clamp_wavg(self):
        self.assertIsNone(a.num(float("nan")))
        self.assertIsNone(a.num("abc"))
        self.assertEqual(a.num("2.5"), 2.5)
        self.assertEqual(a.clamp(5), 1.0)
        self.assertEqual(a.clamp(-5), -1.0)
        self.assertAlmostEqual(a.wavg([(1, 1), (None, 5), (0, 1)]), 0.5)
        self.assertIsNone(a.wavg([(None, 1)]))

    def test_rating_scale_covers_all_14_levels(self):
        labels = [a.map_rating(t)[0] for t in range(-100, 101)]
        self.assertEqual(len(set(labels)), 14)
        self.assertEqual(a.map_rating(60), ("Strong Buy", "Kaufen"))
        self.assertEqual(a.map_rating(15), ("Accumulate", "Kaufen"))
        self.assertEqual(a.map_rating(0)[1], "Halten")
        self.assertEqual(a.map_rating(-30)[1], "Verkaufen")
        self.assertEqual(a.map_rating(-99), ("Strong Sell", "Verkaufen"))

    def test_parse_target_headlines(self):
        cases = [
            ("SAP Aktie: Jefferies hebt Kursziel auf 220 Euro", "de", ("Jefferies", 220.0, "EUR")),
            ("Barclays senkt Ziel für SAP von 300 auf 280 Euro - 'Overweight'", "de", ("Barclays", 280.0, "EUR")),
            ("UBS belässt SAP auf 'Buy' - Ziel 290 Euro", "de", ("UBS", 290.0, "EUR")),
            ("Morgan Stanley Adjusts Price Target on Apple to $355 From $360, Keeps Overweight Rating", "en",
             ("Morgan Stanley", 355.0, "USD")),
            ("Apple Price Target Raised to $365 by Citi, Goldman Sachs Upgrades Palantir", "en", ("Citi", 365.0, "USD")),
        ]
        for title, lang, expected in cases:
            self.assertEqual(a.parse_target(title, lang), expected, title)
        self.assertIsNone(a.parse_target("Why Our Target Sits Above Wall Street's", "en"))
        # Firmenname darf keine Zahl/kein "Kursziel" enthalten
        firm, value, _ = a.parse_target("Allianz Aktie: Kursziel auf 440 Euro erhöht", "de")
        self.assertIsNone(firm)
        self.assertEqual(value, 440.0)

    def test_headline_sentiment(self):
        self.assertGreater(a.headline_sentiment("Aktie steigt auf Rekordhoch"), 0)
        self.assertLess(a.headline_sentiment("Stock plunges after earnings miss"), 0)
        self.assertEqual(a.headline_sentiment("This Biotech Could Be a Winner in the Weight Loss Market"), 0)
        for s in (a.headline_sentiment(t) for t in ("Aktie fällt trotz Rekordgewinn", "Company reports no growth")):
            self.assertLess(s, 0)  # Gegensatz und Verneinung
        self.assertGreater(a.headline_sentiment("Weak quarter, but outlook raised"), 0)

    def test_headline_sentiment_accuracy(self):
        """Mindestens 90 % der von Hand bewerteten Schlagzeilen müssen richtig eingeordnet werden."""
        sys.path.insert(0, str(Path(__file__).parent))
        from sentiment_cases import CASES
        lab = lambda v: 1 if v > 0.15 else -1 if v < -0.15 else 0
        wrong = [(t, w, round(a.headline_sentiment(t), 2)) for t, w in CASES if lab(a.headline_sentiment(t)) != w]
        self.assertGreaterEqual(1 - len(wrong) / len(CASES), 0.9, wrong)

    def test_reverse_dcf_is_monotonic(self):
        g1 = a.reverse_dcf(100, 2_000, 0.09)
        g2 = a.reverse_dcf(100, 4_000, 0.09)
        self.assertIsNotNone(g1)
        self.assertGreater(g2, g1)
        self.assertIsNone(a.reverse_dcf(-5, 2_000, 0.09))

    def test_clean_company_name_and_siblings(self):
        self.assertEqual(a.clean_company_name("Siemens Aktiengesellschaft"), "Siemens")
        self.assertEqual(a.clean_company_name("Apple Inc."), "Apple")
        self.assertTrue(a.mentions_sibling("Siemens Energy-Aktie: Kursziel 200 Euro", ["siemens energy"]))
        self.assertFalse(a.mentions_sibling("Siemens hebt Prognose", ["siemens energy"]))

    def test_convert_df_scales_money_not_shares(self):
        df = pd.DataFrame({"2025": [100.0, 10.0, 0.21]}, index=["Total Revenue", "Diluted Average Shares", "Tax Rate For Calcs"])
        out = a.convert_df(df, 0.5)
        self.assertEqual(out.loc["Total Revenue", "2025"], 50.0)
        self.assertEqual(out.loc["Diluted Average Shares", "2025"], 10.0)
        self.assertEqual(out.loc["Tax Rate For Calcs", "2025"], 0.21)
        self.assertIs(a.convert_df(df, 1.0), df)

    def test_fx_rate(self):
        orig = a.usd_rate
        a.usd_rate = lambda cur: {"USD": 1.0, "EUR": 1.10, "DKK": 0.15, "GBp": 0.0127}.get(cur)
        try:
            self.assertEqual(a.fx_rate("USD", "USD"), 1.0)
            self.assertAlmostEqual(a.fx_rate("DKK", "USD"), 0.15)
            self.assertAlmostEqual(a.fx_rate("EUR", "DKK"), 1.10 / 0.15)
            self.assertEqual(a.fx_rate(None, "USD"), 1.0)
            self.assertEqual(a.fx_rate("XYZ", "USD"), 1.0)  # unbekannt -> keine Umrechnung
        finally:
            a.usd_rate = orig

    def test_clean_watchlist(self):
        items = [{"symbol": "sap.de", "name": "SAP"}, {"symbol": "SAP.DE"}, {"symbol": "bad sym!"}, "kein dict",
                 {"symbol": "BTC-EUR", "label": "Buy", "evil": "<script>"}]
        out = a.clean_watchlist(items)
        self.assertEqual([x["symbol"] for x in out], ["SAP.DE", "BTC-EUR"])
        self.assertNotIn("evil", out[1])
        self.assertEqual(len(a.clean_watchlist([{"symbol": f"A{i}"} for i in range(300)])), 150)


# ---------------------------------------------------------------------------
class TestCrypto(unittest.TestCase):
    def test_resolve_known_coins_without_network(self):
        self.assertEqual(a.resolve_crypto("BTC")["id"], "bitcoin")
        self.assertEqual(a.resolve_crypto("bitcoin")["base"], "BTC")
        r = a.resolve_crypto("eth-usd")
        self.assertEqual((r["base"], r["quote"], r["id"]), ("ETH", "USD", "ethereum"))

    def _m(self, **kw):
        m = {"currency": "EUR", "rank": 5, "age_years": 9, "mcap": 1e11, "vol24": 3e9, "max_supply": 21e6, "circ": 20e6,
             "total_supply": 20e6, "ath": 100, "ath_change": -0.4, "ath_date": "01.01.2025", "mayer": 1.0, "rsi": 50,
             "perf_1y": 0.2, "vol": 0.5, "max_dd": -0.3, "categories": ["Layer 1 (L1)"], "fg": 50, "stable": False}
        m.update(kw)
        return m

    def test_valuation_overheated(self):
        r = a.c_valuation(self._m(mayer=2.6, rsi=80, ath_change=-0.02))
        self.assertLess(r["score"], -0.3)
        self.assertIn(r["adjective"], ("überhitzt", "heißgelaufen"))
        self.assertIn(r["adjective"], a.ADJ["valuation"])

    def test_quality_and_risk(self):
        self.assertEqual(a.c_quality(self._m(rank=1))["adjective"], "dominant")
        self.assertEqual(a.c_quality(self._m(rank=80, age_years=1))["adjective"], "schwach")
        calm = a.c_risk(self._m(vol=0.1, max_dd=-0.05, rank=1))
        self.assertLessEqual(calm["score"], 0.1)  # Krypto-Risiko ist nie "positiv"
        self.assertEqual(a.c_risk(self._m(rank=120, vol=1.2))["adjective"], "spekulativ")
        self.assertEqual(a.c_risk(self._m(stable=True))["adjective"], "schwankungsarm")

    def test_all_crypto_adjectives_come_from_the_lists(self):
        m = self._m()
        news = {"sentiment": 0.1, "count": 20, "pos": 8, "neg": 2, "count_trusted": 10}
        for key, fn in (("valuation", a.c_valuation), ("quality", a.c_quality), ("growth", a.c_growth), ("risk", a.c_risk)):
            self.assertIn(fn(m)["adjective"], a.ADJ[key], key)
        self.assertIn(a.c_sentiment(m, news)["adjective"], a.ADJ["sentiment"])


# ---------------------------------------------------------------------------
class TestStore(Isolated):
    def test_plain_file_roundtrip_and_old_format_migration(self):
        a.ALERT_FILE.write_text(json.dumps({"alerts": {"SAP.DE": {"below": 1}}, "topic": "t-alt", "history": {}}), encoding="utf-8")
        d = a.STORE.load()
        self.assertEqual(d["u"]["admin"]["topic"], "t-alt")
        self.assertIn("SAP.DE", d["u"]["admin"]["alerts"])
        self.assertNotIn("alerts", d)

    def test_encryption_roundtrip(self):
        os.environ["STORE_KEY"] = "test-schluessel-mit-genug-zeichen"
        a.STORE.load()["u"]["anna"] = {"alerts": {"X": 1}}
        a.STORE.save()
        raw = a.ALERT_FILE.read_text(encoding="utf-8")
        self.assertEqual(json.loads(raw)["enc"], a.ENC_MARK)
        self.assertNotIn("anna", raw)
        a.STORE.__init__()
        self.assertIn("anna", a.STORE.load()["u"])

    def test_wrong_or_missing_key_locks_and_never_overwrites(self):
        os.environ["STORE_KEY"] = "richtiger-schluessel-1234567890"
        a.STORE.load()["u"]["anna"] = {}
        a.STORE.save()
        before = a.ALERT_FILE.read_text(encoding="utf-8")
        for key in ("falscher-schluessel-0987654321", None):
            if key:
                os.environ["STORE_KEY"] = key
            else:
                os.environ.pop("STORE_KEY")
            a.STORE.__init__()
            a.STORE.load()
            self.assertTrue(a.STORE.locked)
            a.STORE.data["u"] = {}
            a.STORE.save()
            self.assertEqual(a.ALERT_FILE.read_text(encoding="utf-8"), before)

    def test_gist_migration_deletes_plain_gist_only_after_check(self):
        gists, calls = {"old": {"description": a.GIST_DESCRIPTION, "content": json.dumps({"u": {"admin": {"topic": "t1"}}})}}, []

        def fake(method, path, body=None):
            calls.append(method)
            if method == "GET" and path.startswith("/gists?"):
                return [{"id": k, "description": v["description"]} for k, v in gists.items()]
            gid = path.split("/")[2] if path.count("/") >= 2 else None
            if method == "GET":
                return {"files": {"alerts.json": {"content": gists[gid]["content"], "truncated": False}}}
            if method == "POST":
                gists["new"] = {"description": body["description"], "content": body["files"]["alerts.json"]["content"]}
                return {"id": "new"}
            if method == "PATCH":
                gists[gid]["content"] = body["files"]["alerts.json"]["content"]
                return {}
            if method == "DELETE":
                gists.pop(gid)
        orig = a.gh_api
        a.gh_api = fake
        try:
            os.environ["GITHUB_TOKEN"] = "x"
            os.environ["STORE_KEY"] = "gist-schluessel-1234567890"
            a.STORE.__init__()
            self.assertEqual(a.STORE.load()["u"]["admin"]["topic"], "t1")
            self.assertEqual(list(gists), ["new"])
            self.assertEqual(gists["new"]["description"], a.GIST_DESCRIPTION_ENC)
            self.assertNotIn("t1", gists["new"]["content"])
            self.assertLess(calls.index("POST"), calls.index("DELETE"))
        finally:
            a.gh_api = orig


# ---------------------------------------------------------------------------
class TestAuth(Isolated):
    def test_password_hashing(self):
        h = a.hash_pw("geheim-123")
        self.assertTrue(h.startswith("pbkdf2$"))
        self.assertTrue(a.check_pw("geheim-123", h))
        self.assertFalse(a.check_pw("falsch", h))
        self.assertNotEqual(a.hash_pw("geheim-123"), h)  # zufälliges Salz

    def test_sessions(self):
        os.environ["APP_PASSWORD"] = "admin-pass"
        a.users()["anna"] = {"pw": a.hash_pw("anna-pass-1"), "admin": False, "ver": 0}
        tok = a.make_session_token("anna")
        self.assertEqual(a.session_user(tok), "anna")
        self.assertIsNone(a.session_user(tok[:-1] + ("0" if tok[-1] != "0" else "1")))  # manipuliert
        a.users()["anna"]["ver"] = 1  # Passwortwechsel -> alte Sitzungen ungültig
        self.assertIsNone(a.session_user(tok))
        os.environ["APP_PASSWORD"] = "anderes"  # neues APP_PASSWORD -> alle Sitzungen ungültig
        self.assertIsNone(a.session_user(a.make_session_token("anna").replace("x", "x")) and None)

    def test_authenticate(self):
        os.environ["APP_PASSWORD"] = "admin-pass"
        self.assertTrue(a.authenticate("admin", "admin-pass"))  # Notfallzugang
        a.users()["anna"] = {"pw": a.hash_pw("anna-pass-1"), "admin": False, "ver": 0}
        self.assertTrue(a.authenticate("anna", "anna-pass-1"))
        self.assertFalse(a.authenticate("anna", "admin-pass"))
        self.assertFalse(a.authenticate("niemand", "x"))


# ---------------------------------------------------------------------------
class TestAlerts(Isolated):
    def setUp(self):
        super().setUp()
        self.sent = []
        self._orig = (a.ntfy_send, a.live_quote, a.analyze, a.company_events)
        a.ntfy_send = lambda title, msg, symbol=None, tags=None, priority=4, topic=None: self.sent.append((title, topic)) or True
        self.quote = {"SAP.DE": (178.0, 185.0)}
        a.live_quote = lambda sym: self.quote[sym]
        self.label = "Buy"
        a.analyze = lambda sym: {"symbol": sym, "price": 178.0, "rating": {"label": self.label, "score": 40.0},
                                 "summary": {"adjective": "kaufenswert"}}
        a.company_events = lambda sym, alts=(), cur="": [{"type": "earnings", "date": "2099-01-02", "days": 1,
                                                         "estimated": False, "label": "Quartalszahlen", "detail": ""}]

    def tearDown(self):
        a.ntfy_send, a.live_quote, a.analyze, a.company_events = self._orig
        super().tearDown()

    def test_alerts_fire_once_per_user_and_rearm(self):
        a.users()["anna"] = {"pw": None, "admin": False, "ver": 0}
        a.save_alert({"symbol": "SAP.DE", "name": "SAP", "currency": "EUR", "below": "180", "move": "3",
                      "rating": True, "events": True, "label": "Hold"}, "admin")
        a.save_alert({"symbol": "SAP.DE", "name": "SAP", "currency": "EUR", "above": "999"}, "anna")
        fired = a.run_alert_checks(force_rating=True)
        titles = [f["title"] for f in fired if f["user"] == "admin"]
        # unter Grenze, Tagesbewegung, Empfehlung Hold->Buy (+ Termin morgen, wird erst ab 8 Uhr verschickt)
        from datetime import datetime
        self.assertEqual(len(titles), 3 + (1 if datetime.now().hour >= 8 else 0), titles)
        self.assertFalse([f for f in fired if f["user"] == "anna"])
        topics = {t for _, t in self.sent}
        self.assertEqual(topics, {a.user_space("admin")["topic"]})
        self.assertEqual(a.run_alert_checks(force_rating=True), [])  # keine Wiederholung
        a.save_alert({"symbol": "SAP.DE", "name": "SAP", "currency": "EUR", "below": "180"}, "admin")  # scharf schalten
        self.assertEqual(len(a.run_alert_checks()), 1)

    def test_invalid_symbol_rejected(self):
        with self.assertRaises(ValueError):
            a.save_alert({"symbol": "../etc"}, "admin")


# ---------------------------------------------------------------------------
class TestHTTP(Isolated):
    def setUp(self):
        super().setUp()
        os.environ["APP_PASSWORD"] = "test-admin-pass"
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), a.Handler)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        super().tearDown()

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kw):
            return None

    def client(self):
        jar = http.cookiejar.CookieJar()
        return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), self._NoRedirect())

    def call(self, op, path, body=None, form=None, ctype="application/json", accept="*/*"):
        data, headers = None, {"Accept": accept}
        if form is not None:
            data, headers["Content-Type"] = urllib.parse.urlencode(form).encode(), "application/x-www-form-urlencoded"
        elif body is not None:
            data, headers["Content-Type"] = (json.dumps(body).encode() if ctype == "application/json" else body.encode()), ctype
        try:
            r = op.open(urllib.request.Request(self.base + path, data=data, headers=headers), timeout=10)
            return r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    def login(self, op, user, pw):
        return self.call(op, "/login", form={"username": user, "password": pw, "next": "/"})[0]

    def test_public_routes(self):
        op = self.client()
        self.assertEqual(self.call(op, "/healthz")[0], 200)
        self.assertEqual(self.call(op, "/manifest.webmanifest")[0], 200)
        self.assertEqual(self.call(op, "/static/apple-touch-icon.png")[0], 200)
        for bad in ("/static/../aktien_check.py", "/static/..%2Faktien_check.py", "/static/alerts.json"):
            self.assertEqual(self.call(op, bad)[0], 404, bad)

    def test_login_required_and_flow(self):
        op = self.client()
        st, hd, _ = self.call(op, "/?q=SAP.DE", accept="text/html")
        self.assertEqual(st, 303)
        self.assertIn("/login", hd["Location"])
        self.assertEqual(self.call(op, "/api/me")[0], 401)
        self.assertEqual(self.call(op, "/api/cron?key=falsch")[0], 403)
        self.assertEqual(self.login(op, "admin", "falsch"), 401)
        self.assertEqual(self.login(op, "admin", "test-admin-pass"), 303)
        st, _, b = self.call(op, "/api/me")
        self.assertEqual(json.loads(b), {"user": "admin", "admin": True, "multi": True})

    def test_users_watchlist_and_permissions(self):
        adm, anna = self.client(), self.client()
        self.login(adm, "admin", "test-admin-pass")
        st, _, b = self.call(adm, "/api/admin/users", {"action": "create", "username": "anna", "password": "anna-start-1"})
        self.assertEqual(st, 200)
        self.assertEqual(self.login(anna, "anna", "anna-start-1"), 303)
        self.assertEqual(self.call(anna, "/api/admin/users")[0], 403)
        self.assertEqual(self.call(anna, "/api/watchlist", "x=1", ctype="text/plain")[0], 415)
        self.call(anna, "/api/watchlist", {"items": [{"symbol": "ALV.DE"}]})
        self.assertEqual([x["symbol"] for x in json.loads(self.call(anna, "/api/watchlist")[2])["items"]], ["ALV.DE"])
        self.assertEqual(json.loads(self.call(adm, "/api/watchlist")[2])["items"], [])
        self.call(anna, "/api/account/password", {"old": "anna-start-1", "new": "neues-pass-99"})
        self.assertEqual(self.call(anna, "/api/me")[0], 200)  # dieses Gerät bleibt angemeldet
        self.call(adm, "/api/admin/users", {"action": "delete", "username": "anna"})
        self.assertEqual(self.call(anna, "/api/me")[0], 401)


class TestBusinessModels(unittest.TestCase):
    """Branchenspezifische Bewertung (Banken, Versicherer, Immobilien, Verlust-/Vorumsatzfirmen, Zykliker)."""
    MAC = {"rf": 4.0, "rf_chg": 0, "fx_chg": None, "fx_pair": None}

    def m(self, **kw):
        from collections import defaultdict
        base = {"sector": "", "industry": "", "currency": "USD", "pe_hist": [], "revenues": [1, 1], "net_incomes": [],
                "op_m_hist": [], "loss_years": 0, "n_analysts": 0, "div_streak": 0, "div_years": 0, "div_cut": False,
                "peer_n": 0, "is_financial": False, "beta": 1.0, "mcap": 50e9}
        d = defaultdict(lambda: None, {**base, **kw})
        d["biz"] = kw.get("biz") or a.classify_business(d)
        d["is_financial"] = d["biz"] in ("bank", "insurance")
        return d

    def test_classification(self):
        self.assertEqual(self.m(sector="Financial Services", industry="Banks - Regional")["biz"], "bank")
        self.assertEqual(self.m(sector="Financial Services", industry="Insurance - Diversified")["biz"], "insurance")
        self.assertEqual(self.m(sector="Financial Services", industry="Credit Services")["biz"], "standard")  # Visa
        self.assertEqual(self.m(sector="Real Estate", industry="REIT - Retail")["biz"], "real_estate")
        self.assertEqual(self.m(sector="Basic Materials", industry="Copper")["biz"], "cyclical")
        self.assertEqual(self.m(net_m=-0.2, revenue=2e9, rev_cagr=0.4, rev_g=0.25)["biz"], "loss_growth")
        self.assertEqual(self.m(net_m=-5.0, revenue=1e7, rev_cagr=0.1)["biz"], "pre_revenue")
        # winziger Anfangsumsatz bläht die CAGR auf – entscheidend ist der kleinere Wert
        self.assertEqual(self.m(net_m=-0.3, revenue=5e9, rev_cagr=1.5, rev_g=0.05)["biz"], "standard")

    def test_bank_pb_vs_roe(self):
        cheap = a.score_valuation(self.m(biz="bank", pb=0.6, roe=0.10), self.MAC)["score"]
        dear = a.score_valuation(self.m(biz="bank", pb=2.5, roe=0.10), self.MAC)["score"]
        self.assertGreater(cheap, 0.3)
        self.assertLess(dear, -0.3)
        reasons = " ".join(a.score_valuation(self.m(biz="bank", pb=1, roe=0.1, ev_ebitda=3, fcf_yield=-0.5), self.MAC)["reasons"])
        self.assertNotIn("EV/EBITDA", reasons)      # bei Banken nicht aussagekräftig
        self.assertNotIn("Free-Cashflow", reasons)

    def test_real_estate_ignores_pe(self):
        v = a.score_valuation(self.m(biz="real_estate", pe=3.5, p_ffo=25, pb=1.4), self.MAC)
        self.assertLess(v["score"], 0)  # KGV 3,5 durch Neubewertung darf nicht „billig“ machen
        self.assertTrue(any("verzerrt" in r for r in v["reasons"]))
        q = a.score_quality(self.m(biz="real_estate", op_m=0.5, ocf=3, revenue=5, ltv=0.7))
        self.assertTrue(any("Beleihungsquote" in r for r in q["reasons"]))

    def test_loss_makers_not_market_leaders(self):
        q = a.score_quality(self.m(biz="loss_growth", net_m=-0.1, gross_m=0.8, rev_cagr=0.4, rev_g=0.35, fcf_m=0.2,
                                   fcf=1e9, op_m_trend=0.1, mcap=500e9))
        self.assertNotIn(q["adjective"], ("marktführend", "dominant"))
        pre = a.score_quality(self.m(biz="pre_revenue", runway=8, cash=5e9, fcf=-6e8))
        self.assertEqual(pre["adjective"], "defizitär")  # viel Kasse ist noch keine Profitabilität

    def test_cyclical_peak_margin(self):
        peak = a.score_valuation(self.m(biz="cyclical", pe=6, op_m=0.40, op_m_hist=[0.40, 0.15, 0.12, 0.10]), self.MAC)
        self.assertTrue(any("Zyklushoch" in r for r in peak["reasons"]))


class TestQualityAndTrack(unittest.TestCase):
    """Bilanzqualität (Piotroski, Altman, Zinsdeckung, Aktienvergütung), Erwartungen und Trefferquote."""

    @staticmethod
    def frame(rows):
        cols = [pd.Timestamp("2025-12-31"), pd.Timestamp("2024-12-31")]
        return pd.DataFrame({c: {k: v[i] for k, v in rows.items()} for i, c in enumerate(cols)})

    def test_balance_quality(self):
        inc = self.frame({"Net Income": [120, 100], "Total Revenue": [1000, 900], "Gross Profit": [500, 430],
                          "EBIT": [200, 170], "Interest Expense": [10, 10]})
        bs = self.frame({"Total Assets": [2000, 1900], "Current Assets": [800, 700], "Current Liabilities": [400, 400],
                         "Long Term Debt": [300, 320], "Retained Earnings": [900, 800],
                         "Total Liabilities Net Minority Interest": [1000, 1000], "Ordinary Shares Number": [100, 101]})
        cf = self.frame({"Operating Cash Flow": [160, 130], "Stock Based Compensation": [50, 40]})
        m = {"mcap": 3000, "fcf": 150, "revenue": 1000}
        a.balance_quality(m, inc, bs, cf)
        self.assertEqual(m["piotroski"], 9)               # alle neun Prüfungen erfüllt
        self.assertGreater(m["altman_z"], 3)
        self.assertAlmostEqual(m["int_cov"], 20)
        self.assertLess(m["accruals"], 0)                 # Cashflow über Gewinn
        self.assertEqual(m["fcf_adj"], 100)               # Free Cashflow minus Aktienvergütung
        self.assertAlmostEqual(m["sbc_ratio"], 0.05)

    def test_revisions_and_insider_move_sentiment(self):
        news = {"sentiment": 0, "count": 10, "pos": 3, "neg": 3, "count_trusted": 5}
        base = {"rec_mean": None, "n_analysts": 0, "rec_dist": None, "short_float": None, "mcap": 1e10, "currency": "USD"}
        neutral = a.score_sentiment(dict(base), news, 0)["score"]
        good = a.score_sentiment({**base, "eps_rev": 0.08, "rev_breadth": (6, 0), "surprises": [0.05, 0.04, 0.06, 0.03],
                                  "insider": {"buys": 3e6, "sells": 0, "buyers": 3, "cur": "USD"}}, news, 0)
        bad = a.score_sentiment({**base, "eps_rev": -0.08, "rev_breadth": (0, 6), "surprises": [-0.05, -0.04, 0.01, -0.06]},
                                news, 0)["score"]
        self.assertGreater(good["score"], neutral + 0.3)
        self.assertLess(bad, neutral - 0.3)
        self.assertTrue(any("Insiderkäufe" in r for r in good["reasons"]))

    def test_signals_backfill_and_group_change(self):
        sp = {"history": {"SAP.DE": [["2026-01-02", 30, "Outperform", 200], ["2026-01-05", 33, "Outperform", 205],
                                     ["2026-02-01", 5, "Equal-weight", 190]]}}
        sig = a.signals_of(sp)
        self.assertEqual([x[3] for x in sig], ["Kaufen", "Halten"])  # nur Gruppenwechsel zählt als neues Signal

    def test_track_record_vs_index(self):
        days = pd.date_range("2026-01-01", "2027-01-10", freq="D")
        stock = pd.Series([100 * (1 + 0.002 * i) for i in range(len(days))], index=days)  # steigt stärker
        index = pd.Series([100 * (1 + 0.001 * i) for i in range(len(days))], index=days)
        orig, orig_now = a.price_table, a.datetime

        class FixedNow(a.datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2027, 1, 5)
        a.price_table = lambda syms, start: {s_: (index if s_.startswith("^") else stock) for s_ in syms}
        a.datetime = FixedNow
        try:
            res = a.track_record([["SAP.DE", "2026-01-01", "Buy", "Kaufen", 100.0]])
        finally:
            a.price_table, a.datetime = orig, orig_now
        row_ = res["signals"][0]
        self.assertEqual(row_["bench"], "DAX")
        self.assertGreater(row_["excess"], 0.3)
        self.assertEqual(res["groups"]["Kaufen"]["beat"], 1.0)
        self.assertIn("12M", row_["h"])


class TestEtfAndReport(Isolated):
    """ETF-Bewertung und Wochenbericht (ohne Internet)."""

    def etf(self, **kw):
        base = {"ter": 0.002, "aum": 5e10, "inception": "2010-01-01", "family": "Test", "data_years": 15, "pe": 20, "pb": 3,
                "bond_etf": False, "sma200": 100, "last": 100, "cagr5": 0.09, "cagr3": 0.08, "cagr10": 0.1, "perf_1y": 0.1,
                "vol": 0.14, "max_dd_5y": -0.2, "top10": 0.22, "max_sector": {"name": "Technologie", "weight": 0.3},
                "dist": "thesaurierend", "div_yield": 0}
        return {**base, **kw}

    def test_cheap_beats_expensive_etf(self):
        cheap = a.e_quality(self.etf(ter=0.0007))["score"]
        dear = a.e_quality(self.etf(ter=0.0075, aum=5e7))["score"]
        self.assertGreater(cheap, 0.5)
        self.assertLess(dear, -0.3)

    def test_concentration_raises_risk(self):
        broad = a.e_risk(self.etf())["score"]
        narrow = a.e_risk(self.etf(top10=0.65, max_sector={"name": "Technologie", "weight": 0.6}, vol=0.24))["score"]
        self.assertGreater(broad, narrow + 0.5)

    def test_accumulating_etf_has_no_dividend_score(self):
        self.assertIsNone(a.e_dividend(self.etf())["score"])
        self.assertIsNotNone(a.e_dividend(self.etf(dist="ausschüttend", div_yield=0.035))["score"])

    def test_isin_detection_and_etf_name(self):
        self.assertEqual(a.etf_short_name("iShares Core MSCI World UCITS ETF USD (Acc)"), "iShares Core MSCI World")

    def test_weekly_report_text(self):
        sp = a.user_space("anna")
        sp["watchlist"] = [{"symbol": "SAP.DE", "label": "Outperform"}, {"symbol": "BAYN.DE", "label": "Hold"}]
        fake = {
            "SAP.DE": {"symbol": "SAP.DE", "name": "SAP SE", "price": 200, "currency": "EUR", "summary": {"adjective": "x"},
                       "rating": {"label": "Buy", "group": "Kaufen", "score": 45},
                       "events": [{"date": "2026-10-28", "label": "Quartalszahlen", "days": 3}]},
            "BAYN.DE": {"symbol": "BAYN.DE", "name": "Bayer AG", "price": 25, "currency": "EUR", "summary": {"adjective": "x"},
                        "rating": {"label": "Hold", "group": "Halten", "score": -10}, "events": []}}
        orig = (a.analyze, a.week_change, a.REPORT_PAUSE)
        a.analyze = lambda q: fake[q]
        a.REPORT_PAUSE = 0
        a.week_change = lambda s_: {"SAP.DE": 0.03, "BAYN.DE": -0.02}[s_]
        try:
            title, msg = a.build_weekly_report("anna")
        finally:
            a.analyze, a.week_change, a.REPORT_PAUSE = orig
        self.assertIn("Wochenbericht", title)
        self.assertIn("SAP: Outperform → Buy", msg)
        self.assertNotIn("Bayer: Hold →", msg)            # unverändert
        self.assertIn("Beste der Woche: SAP +3,0 %", msg)
        self.assertIn("Schwächste: Bayer -2,0 %", msg)
        self.assertIn("SAP: Quartalszahlen", msg)
        self.assertEqual(sp["watchlist"][0]["label"], "Buy")  # Watchlist wurde aktualisiert

    def test_report_schedule(self):
        sent = []
        sp = a.user_space("anna")
        sp["watchlist"] = [{"symbol": "SAP.DE"}]
        orig = (a.berlin_now, a.send_weekly_report)
        a.send_weekly_report = lambda u, manual=False: sent.append(u)
        try:
            a.berlin_now = lambda: a.datetime(2026, 10, 24, 19)   # Samstag -> nichts
            a.send_due_reports()
            a.berlin_now = lambda: a.datetime(2026, 10, 25, 17)   # Sonntag vor 18 Uhr -> nichts
            a.send_due_reports()
            a.berlin_now = lambda: a.datetime(2026, 10, 25, 18, 5)
            a.send_due_reports()
            a.send_due_reports()                                  # zweiter Lauf am selben Sonntag -> kein Doppelversand
        finally:
            a.berlin_now, a.send_weekly_report = orig
        self.assertEqual(sent, ["anna"])


class TestCachePruning(unittest.TestCase):
    def test_prune_expired_and_cap(self):
        saved = (dict(a.CACHE), dict(a.PEER_CACHE))
        try:
            a.CACHE.clear()
            a.CACHE.update({f"x{i}": (time.time() - i, {}) for i in range(60)})
            a.PEER_CACHE["alt"] = (time.time() - 7 * 3600, None)
            a.prune_caches()
            self.assertEqual(len(a.CACHE), 40)          # Höchstzahl
            self.assertIn("x0", a.CACHE)                # neueste bleiben
            self.assertNotIn("x59", a.CACHE)            # älteste zuerst raus
            self.assertNotIn("alt", a.PEER_CACHE)       # abgelaufen
        finally:
            a.CACHE.clear(); a.CACHE.update(saved[0]); a.PEER_CACHE.clear(); a.PEER_CACHE.update(saved[1])


class TestScreenerStart(Isolated):
    """Screener läuft nur nach „Start“, bewertet fällige Werte und lässt sich stoppen."""

    def test_start_runs_only_due_and_stops(self):
        calls = []
        orig = (a.analyze, a.SCREENER_UNIVERSES, a.SCREENER_PAUSE)
        a.SCREENER_UNIVERSES = {"t": ("Test", ["AAA", "BBB", "CCC"])}
        a.SCREENER_PAUSE = 0
        a.analyze = lambda s_: (calls.append(s_), {"symbol": s_, "name": s_, "price": 1, "rating": {"label": "Buy", "group": "Kaufen", "score": 40},
                                                 "summary": {"adjective": "x"}, "categories": [], "facts": {}})[1]
        try:
            a.screener_store()["AAA"] = {"symbol": "AAA", "label": "Buy", "updated": int(time.time())}  # aktuell
            self.assertFalse(a.screener_start("anna")[0])            # ohne Index kein Start
            ok, _ = a.screener_start("anna", "due", ["t"])
            self.assertTrue(ok)
            for _ in range(50):
                if not a.SCREENER_STATE["running"]:
                    break
                time.sleep(0.05)
            self.assertEqual(sorted(calls), ["BBB", "CCC"])        # nur veraltete
            self.assertFalse(a.screener_start("anna", "due", ["t"])[0])  # alles aktuell -> kein neuer Durchgang
            calls.clear()
            self.assertTrue(a.screener_start("anna", "all", ["t"])[0])  # „Alle neu bewerten“
            for _ in range(50):
                if not a.SCREENER_STATE["running"]:
                    break
                time.sleep(0.05)
            self.assertEqual(sorted(calls), ["AAA", "BBB", "CCC"])
            # nur ein gewählter Index
            a.SCREENER_UNIVERSES = {"t": ("Test", ["AAA"]), "u": ("Zwei", ["DDD", "EEE"])}
            calls.clear()
            self.assertTrue(a.screener_start("anna", "all", ["u", "t"])[0])  # mehrere übergeben -> nur der erste
            for _ in range(50):
                if not a.SCREENER_STATE["running"]:
                    break
                time.sleep(0.05)
            self.assertEqual(sorted(calls), ["DDD", "EEE"])
            self.assertEqual(a.SCREENER_STATE["unis"], ["u"])
        finally:
            a.analyze, a.SCREENER_UNIVERSES, a.SCREENER_PAUSE = orig
            a.SCREENER_STATE.update(running=False, stop=False)


class TestScreenerMemoryGuard(Isolated):
    def test_stops_when_memory_stays_high(self):
        orig = (a.analyze, a.SCREENER_UNIVERSES, a.SCREENER_PAUSE, a.release_memory, a.time.sleep)
        a.SCREENER_UNIVERSES = {"t": ("Test", ["AAA", "BBB", "CCC"])}
        a.SCREENER_PAUSE = 0
        a.release_memory = lambda: 480.0            # Speicher bleibt über der harten Grenze
        a.time.sleep = lambda s_: None
        calls = []
        a.analyze = lambda s_: (calls.append(s_), {"symbol": s_, "name": s_, "price": 1, "summary": {"adjective": "x"},
                                                 "rating": {"label": "Buy", "group": "Kaufen", "score": 40}, "categories": [], "facts": {}})[1]
        try:
            self.assertTrue(a.screener_start("anna", "due", ["t"])[0])
            for _ in range(100):
                if not a.SCREENER_STATE["running"]:
                    break
                orig[4](0.02)
            self.assertEqual(len(calls), 1)                         # nach dem ersten Wert geordnet gestoppt
            self.assertTrue(a.screener_payload()["mem_stop"])
        finally:
            a.analyze, a.SCREENER_UNIVERSES, a.SCREENER_PAUSE, a.release_memory, a.time.sleep = orig
            a.SCREENER_STATE.update(running=False, stop=False, mem_stop=False)


class TestTechnicals(unittest.TestCase):
    @staticmethod
    def ohlc(closes):
        idx = pd.date_range("2024-01-01", periods=len(closes), freq="B")
        c = pd.Series(closes, index=idx, dtype=float)
        return pd.DataFrame({"Open": c.shift(1).fillna(c.iloc[0]), "High": c * 1.01, "Low": c * 0.99, "Close": c})

    def test_trend_signals(self):
        up = a.technicals(self.ohlc([100 * 1.004 ** i for i in range(400)]))
        down = a.technicals(self.ohlc([100 * 0.996 ** i for i in range(400)]))
        self.assertIn(up["frames"]["Tag"]["ma_sum"]["label"], ("Kaufen", "Starker Kauf"))
        self.assertIn(down["frames"]["Tag"]["ma_sum"]["label"], ("Verkaufen", "Starker Verkauf"))
        self.assertIn("Woche", up["frames"])

    def test_double_bottom_detected(self):
        import math
        seg = lambda a_, b_, n: [a_ + (b_ - a_) * i / n for i in range(n)]
        closes = seg(150, 120, 60) + seg(120, 100, 30) + seg(100, 115, 25) + seg(115, 100, 25) + seg(100, 108, 15)
        closes = [c + math.sin(i) * 0.2 for i, c in enumerate(closes)]
        names = [p_["name"] for p_ in a.chart_patterns(self.ohlc(closes))]
        self.assertIn("Doppelboden", names)

    def test_sideways_breakout(self):
        import math
        closes = [100 + 2 * math.sin(i / 3) for i in range(120)] + [104, 106, 108]
        names = [p_["name"] for p_ in a.chart_patterns(self.ohlc(closes))]
        self.assertIn("Ausbruch nach oben", names)


class TestForecastAndFairValue(unittest.TestCase):
    """Analystenprognosen, Forward-KGV und fairer Wert in drei Szenarien."""
    MAC = {"rf": 4.0}

    def m(self, **kw):
        from collections import defaultdict
        base = {"symbol": "TEST", "price": 100.0, "mcap": 100e9, "beta": 1.0, "currency": "USD", "biz": "standard", "net_debt": 0,
                "fcf": 5e9, "fcf_hist": [5e9, 4.5e9, 4e9], "sbc": None, "owner_earnings": None, "rev_cagr": 0.06,
                "est_rev": {"0y": {"growth": 0.08, "avg": 100, "low": 95, "high": 105, "n": 20, "ago": 92},
                            "+1y": {"growth": 0.10, "avg": 110, "low": 100, "high": 120, "n": 18, "ago": 100}},
                "est_eps": {}}
        return defaultdict(lambda: None, {**base, **kw})

    def test_dcf_monotonic(self):
        lo = a.dcf_value(1e9, 0.02, 0.10, 0.025, 0, 1e8)
        hi = a.dcf_value(1e9, 0.10, 0.10, 0.025, 0, 1e8)
        self.assertGreater(hi, lo)                                           # mehr Wachstum -> höherer Wert
        self.assertGreater(a.dcf_value(1e9, 0.05, 0.08, 0.025, 0, 1e8), a.dcf_value(1e9, 0.05, 0.11, 0.025, 0, 1e8))
        self.assertIsNone(a.dcf_value(1e9, 0.0, 0.10, 0.02, 1e12, 1e8))     # Schulden > Unternehmenswert

    def test_scenarios_ordered(self):
        f = a.fair_value(self.m(), self.MAC)
        self.assertEqual(f["method"], "Discounted-Cashflow (10 Jahre)")
        self.assertLess(f["bear"], f["base"])
        self.assertLess(f["base"], f["bull"])
        self.assertAlmostEqual(f["upside"], f["base"] / 100 - 1)

    def test_owner_earnings_for_heavy_investors(self):
        plain = a.fair_value(self.m(), self.MAC)["base"]
        invest = a.fair_value(self.m(owner_earnings=9e9), self.MAC)
        self.assertGreater(invest["base"], plain)
        self.assertTrue(invest["assumptions"][0].startswith("Owner Earnings"))

    def test_models_without_dcf(self):
        self.assertIn("na", a.fair_value(self.m(fcf=-2e9), self.MAC))           # negativer Free Cashflow
        self.assertIn("na", a.fair_value(self.m(biz="pre_revenue"), self.MAC))
        bank = a.fair_value(self.m(biz="bank", pb=1.0, roe=0.12), self.MAC)
        self.assertEqual(bank["method"], "Kurs-Buchwert aus Eigenkapitalrendite")
        reit = a.fair_value(self.m(biz="real_estate", ocf=7e9), self.MAC)
        self.assertAlmostEqual(reit["base"], 7e9 / 1e9 * 15)                    # FFO je Aktie × 15

    def test_lease_and_minority_adjustment(self):
        us = a.fair_value(self.m(lease_obl=12e9), self.MAC)["base"]                      # US-GAAP: Leasing schon im Cashflow
        ifrs = a.fair_value(self.m(symbol="TEST.DE", currency="EUR", lease_obl=12e9, net_debt=12e9), self.MAC)
        self.assertLess(ifrs["base"], a.fair_value(self.m(symbol="TEST.DE", currency="EUR", net_debt=12e9), self.MAC)["base"] + 0.01)
        self.assertTrue(any("Leasing" in x for x in ifrs["assumptions"]))
        self.assertLess(a.fair_value(self.m(minority=20e9), self.MAC)["base"], us)          # Minderheitsanteile abgezogen

    def test_forecast_growth(self):
        self.assertAlmostEqual(a.est_growth(self.m(), "est_rev"), 0.09)
        loss_base = {"0y": {"growth": 3.0, "ago": -0.5}, "+1y": {"growth": 0.2, "ago": 1.0}}
        self.assertAlmostEqual(a.est_growth(self.m(est_eps=loss_base), "est_eps"), 0.2)  # Wachstum aus Verlust ignoriert
        self.assertEqual(a.est_analysts(self.m()), 20)


if __name__ == "__main__":
    unittest.main(verbosity=2)
