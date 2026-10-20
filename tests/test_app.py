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


if __name__ == "__main__":
    unittest.main(verbosity=2)
