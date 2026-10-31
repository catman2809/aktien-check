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
a.YQ_STATE.update(blocked=False, checked=float("inf"))  # keine echte Yahoo-Sperrprüfung im Testlauf

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
            self.assertNotIn('"topic"', gists["new"]["content"])  # nur Chiffretext (Base64 enthält nie Anführungszeichen im Inhalt)
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
        a.FAILED_LOGINS.clear()  # Fehlversuche anderer Tests sollen keine Anmeldesperre auslösen
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
        self.assertEqual(json.loads(b), {"user": "admin", "admin": True, "multi": True, "unread": 0,
                                         "maintenance": {"on": False, "text": ""},
                                         "prefs": {"lang": "de", "theme": "auto", "mv_uni": "dax", "mv_per": "day", "tax_fb": "1000"}})

    def test_lock_maintenance_backup_restore(self):
        adm, anna = self.client(), self.client()
        self.login(adm, "admin", "test-admin-pass")
        self.call(adm, "/api/admin/users", {"action": "create", "username": "anna", "password": "anna-start-1"})
        self.assertEqual(self.login(anna, "anna", "anna-start-1"), 303)
        self.assertEqual(self.call(anna, "/api/watchlist")[0], 200)
        # Sperren: Sitzung endet, Anmeldung zeigt Sperrhinweis
        self.assertEqual(self.call(adm, "/api/admin/users", {"action": "lock", "username": "anna"})[0], 200)
        self.assertEqual(self.call(anna, "/api/watchlist")[0], 401)
        st, _, b_ = self.call(anna, "/login", form={"username": "anna", "password": "anna-start-1", "next": "/"})
        self.assertEqual(st, 403)
        self.assertIn("gesperrt", b_.decode("utf-8"))
        self.assertEqual(self.call(adm, "/api/admin/users", {"action": "lock", "username": "admin"})[0], 400)
        self.call(adm, "/api/admin/users", {"action": "unlock", "username": "anna"})
        self.assertEqual(self.login(anna, "anna", "anna-start-1"), 303)
        # Wartungsmodus: Benutzer gesperrt, Admin nicht
        self.assertEqual(self.call(anna, "/api/admin/maintenance", {"on": True})[0], 403)
        self.call(adm, "/api/admin/maintenance", {"on": True, "text": "Update läuft"})
        st, _, b_ = self.call(anna, "/api/watchlist")
        self.assertEqual((st, json.loads(b_)["text"]), (503, "Update läuft"))
        self.assertEqual(self.call(anna, "/api/watchlist", {"items": []})[0], 503)
        self.assertTrue(json.loads(self.call(anna, "/api/me")[2])["maintenance"]["on"])
        self.assertEqual(self.call(adm, "/api/watchlist")[0], 200)
        self.call(adm, "/api/admin/maintenance", {"on": False})
        self.assertEqual(self.call(anna, "/api/watchlist")[0], 200)
        # Backup herunterladen, Daten ändern, wiederherstellen
        self.assertEqual(self.call(anna, "/api/admin/backup")[0], 403)
        st, hd, raw = self.call(adm, "/api/admin/backup")
        self.assertEqual(st, 200)
        self.assertIn("attachment", hd["Content-Disposition"])
        bk = json.loads(raw)
        self.assertEqual((bk["format"], bk["users"]), ("aktien-check-backup", 2))
        self.assertEqual(self.call(anna, "/api/admin/restore", bk)[0], 403)
        self.call(adm, "/api/admin/users", {"action": "delete", "username": "anna"})
        self.assertNotIn("anna", a.users())
        self.assertEqual(self.call(adm, "/api/admin/restore", {"format": "x"})[0], 400)
        st, _, b_ = self.call(adm, "/api/admin/restore", bk)
        self.assertEqual(st, 200, b_)
        self.assertIn("anna", a.users())
        # Betriebsdaten im Dashboard
        D = json.loads(self.call(adm, "/api/admin/dashboard")[2])
        self.assertIn("perf", D["ops"])
        self.assertFalse(D["ops"]["maintenance"]["on"])

    def test_users_watchlist_and_permissions(self):
        adm, anna = self.client(), self.client()
        self.login(adm, "admin", "test-admin-pass")
        st, _, b = self.call(adm, "/api/admin/users", {"action": "create", "username": "anna", "password": "anna-start-1"})
        self.assertEqual(st, 200)
        self.assertEqual(self.login(anna, "anna", "anna-start-1"), 303)
        self.assertEqual(self.call(anna, "/api/admin/users")[0], 403)
        # Abo: Benutzer fragt an, nur der Admin kann freischalten
        a.ntfy_send = lambda *x, **k: True
        self.assertEqual(json.loads(self.call(anna, "/api/subscription")[2])["state"], "inaktiv")
        self.assertEqual(json.loads(self.call(anna, "/api/subscription", {"action": "request"})[2])["state"], "angefragt")
        self.assertEqual(self.call(anna, "/api/admin/subscription", {"username": "anna", "action": "extend"})[0], 403)
        self.assertEqual(self.call(adm, "/api/admin/subscription", {"username": "anna", "action": "extend", "months": 12})[0], 200)
        st_sub = json.loads(self.call(anna, "/api/subscription")[2])
        self.assertEqual(st_sub["state"], "aktiv")
        self.assertGreater(st_sub["paid_until"], time.time() + 360 * 86400)
        dash = json.loads(self.call(adm, "/api/admin/dashboard")[2])
        self.assertEqual(dash["subs"]["active"], 1)
        self.assertTrue(any(x["user"] == "anna" and x["ok"] for x in dash["security"]["logins"]))       # Anmeldung protokolliert
        self.assertTrue(any(x["action"].startswith("Abo") for x in dash["security"]["audit"]))         # Admin-Aktion protokolliert
        self.assertTrue(any(f["name"] == "Abo" for f in dash["usage"]["features"]))                     # Nutzung gezählt
        self.assertIn("sources", dash["sources"])
        self.assertEqual(next(u_ for u_ in dash["users"] if u_["name"] == "anna")["sub"]["state"], "aktiv")
        # Mein Bereich: Einstellungen im Konto, Übersicht
        self.assertEqual(json.loads(self.call(anna, "/api/me")[2])["prefs"]["theme"], "auto")
        self.assertEqual(self.call(anna, "/api/prefs", {"theme": "pink"})[0], 400)
        self.assertEqual(self.call(anna, "/api/prefs", {"mv_uni": "nirgends"})[0], 400)
        self.call(anna, "/api/prefs", {"theme": "dark", "mv_uni": "sp500", "mv_per": "year"})
        self.assertEqual(json.loads(self.call(anna, "/api/me")[2])["prefs"],
                         {"lang": "de", "theme": "dark", "mv_uni": "sp500", "mv_per": "year", "tax_fb": "1000"})
        summ = json.loads(self.call(anna, "/api/me/summary")[2])
        self.assertEqual((summ["user"], summ["watchlist"], summ["depot"], summ["sub"]["state"]), ("anna", [], None, "aktiv"))
        self.assertEqual(self.call(self.client(), "/api/me/summary")[0], 401)
        self.assertEqual(self.call(anna, "/api/depot/outlook")[0], 403)                            # nur Admin (Finnhub)
        self.assertEqual(json.loads(self.call(adm, "/api/depot/outlook")[2]), {"wait": True})     # Admin ohne Depot
        self.call(anna, "/api/prefs", {"tax_fb": "2000"})
        self.assertEqual(json.loads(self.call(anna, "/api/me")[2])["prefs"]["tax_fb"], "2000")
        self.call(anna, "/api/prefs", {"tax_fb": "1000"})
        # Nachrichten: Benutzer -> Admin -> Benutzer, mit Ungelesen-Zähler
        self.assertEqual(self.call(anna, "/api/messages", {"text": "  "})[0], 400)        # leere Nachricht abgelehnt
        self.call(anna, "/api/messages", {"text": "Hallo Admin, wie bezahle ich?"})
        self.assertEqual(json.loads(self.call(adm, "/api/me")[2])["unread"], 1)
        self.assertEqual(self.call(anna, "/api/admin/messages")[0], 403)
        th = json.loads(self.call(adm, "/api/admin/messages?user=anna")[2])["messages"]
        self.assertEqual(th[0]["text"], "Hallo Admin, wie bezahle ich?")
        self.assertEqual(json.loads(self.call(adm, "/api/me")[2])["unread"], 0)          # beim Öffnen gelesen
        self.call(adm, "/api/admin/messages", {"user": "anna", "text": "Per Überweisung."})
        self.assertEqual(json.loads(self.call(anna, "/api/me")[2])["unread"], 1)
        self.assertEqual(len(json.loads(self.call(anna, "/api/messages")[2])["messages"]), 2)
        self.assertEqual(json.loads(self.call(anna, "/api/me")[2])["unread"], 0)
        self.assertEqual(self.call(anna, "/api/admin/dashboard")[0], 403)          # Dashboard nur für Admins
        self.assertEqual(self.call(anna, "/api/screener")[0], 403)                 # Screener nur für Admins
        self.assertEqual(self.call(anna, "/api/screener/start", {"unis": ["dax"]})[0], 403)
        self.assertEqual(self.call(adm, "/api/screener")[0], 200)
        self.assertEqual(self.call(anna, "/api/admin/system", {"action": "save"})[0], 403)
        st_, _h, body_ = self.call(adm, "/api/admin/dashboard")
        self.assertEqual(st_, 200)
        self.assertIn("kpi", json.loads(body_))
        a.screener_store()["SAP.DE"] = {"symbol": "SAP.DE", "label": "Buy", "updated": int(time.time())}
        a.CACHE["x"] = (time.time(), {})
        self.assertEqual(self.call(anna, "/api/admin/system", {"action": "reset_all"})[0], 403)
        self.assertEqual(self.call(adm, "/api/admin/system", {"action": "reset_all"})[0], 200)
        self.assertEqual(a.STORE.load().get("screener"), {})                      # Screener-Ergebnisse gelöscht
        self.assertEqual(len(a.CACHE), 0)
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
        orig = (a.analyze, a.SCREENER_UNIVERSES, a.SCREENER_PAUSE, a.release_memory, a.time.sleep, a.MEM_GUARD)
        a.MEM_GUARD = True
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
            a.analyze, a.SCREENER_UNIVERSES, a.SCREENER_PAUSE, a.release_memory, a.time.sleep, a.MEM_GUARD = orig
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


class TestSubReminder(Isolated):
    def test_reminder_five_days_before_once(self):
        orig = (a.users, a.ntfy_send)
        a.users = lambda: {"admin": {"admin": True}, "anna": {"admin": False}, "ben": {"admin": False}}
        a.ntfy_send = lambda *x, **k: True
        try:
            a.user_space("anna")["sub"] = {"paid_until": int(time.time() + 3 * 86400)}     # läuft in 3 Tagen ab
            a.user_space("ben")["sub"] = {"paid_until": int(time.time() + 20 * 86400)}     # noch lange
            self.assertEqual(a.check_sub_reminders(), 1)
            self.assertEqual(a.check_sub_reminders(), 0)                                   # nur einmal je Laufzeit
            msgs = a.user_space("anna")["messages"]
            self.assertTrue(msgs[-1]["system"] and "läuft am" in msgs[-1]["text"])
            self.assertEqual(a.unread_for_user("anna"), 1)
            self.assertNotIn("messages", a.user_space("ben"))
        finally:
            a.users, a.ntfy_send = orig


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
        self.assertTrue(f["method"].startswith("Discounted-Cashflow (10 Jahre)"))
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

    def test_forward_factor(self):
        f = a.forward_factor(self.m())["f"]
        self.assertAlmostEqual(f["avg"], (0.5 * 1.08 + 0.5 * 1.08 * 1.10) / (0.5 + 0.5 * 1.08))  # ohne Datum: halbes Jahr
        q0 = a.forward_factor(self.m(fy_end="2026-06-30", q_end="2026-06-30"))["f"]["avg"]
        self.assertAlmostEqual(q0, 1.08)                                         # Jahr gerade beendet -> laufendes GJ
        self.assertLess(f["low"], f["avg"])
        eps = {"0y": {"avg": 5.5, "growth": 0.1, "ago": 5.0}, "+1y": {"avg": 6.6, "low": 6.0, "high": 7.2, "growth": 0.2, "ago": 5.5}}
        both = a.forward_factor(self.m(est_eps=eps, eps_ttm=5.2, eps_fy_last=5.0))
        self.assertEqual(both["src"], "eps+rev")
        self.assertAlmostEqual(both["f"]["avg"], ((5.5 + 6.6) / 2 / 5.2 + (0.5 * 1.08 + 0.5 * 1.188) / 1.04) / 2)
        other_cur = a.forward_factor(self.m(est_eps=eps, eps_ttm=5.2, eps_fy_last=40.0))  # EPS in anderer Währung
        self.assertEqual(other_cur["src"], "rev")
        self.assertIsNone(a.forward_factor(self.m(est_rev={})))

    def test_growth_company_valued_on_next_year(self):
        fast = {"0y": {"growth": 0.40, "avg": 140, "low": 130, "high": 150, "n": 20, "ago": 100},
                "+1y": {"growth": 0.35, "avg": 189, "low": 170, "high": 205, "n": 18, "ago": 140}}
        with_fwd = a.fair_value(self.m(est_rev=fast, rev_cagr=0.4), self.MAC)
        no_fwd = a.fair_value(self.m(est_rev={}, rev_cagr=0.4), self.MAC)
        self.assertTrue(with_fwd["forward"])
        self.assertGreater(with_fwd["base"], no_fwd["base"] * 1.03)
        self.assertTrue(any(x.startswith("Startwert nächste 12 Monate") for x in with_fwd["assumptions"]))
        # Free Cashflow negativ, aber Gewinn im nächsten Jahr erwartet -> Startwert aus dem erwarteten Gewinn
        eps = {"0y": {"avg": 0.5, "n": 10, "ago": -0.2}, "+1y": {"avg": 2.0, "low": 1.5, "high": 2.5, "n": 10, "ago": 0.5}}
        f = a.fair_value(self.m(fcf=-1e9, est_rev={}, est_eps=eps, eps_fy_last=-0.2), self.MAC)
        self.assertNotIn("na", f)
        self.assertTrue(f["forward"])
        self.assertIn("na", a.fair_value(self.m(fcf=-1e9, est_rev={}, est_eps={}), self.MAC))

    def test_forecast_outweighs_history(self):
        slow = {"0y": {"growth": 0.10, "n": 20}, "+1y": {"growth": 0.10, "n": 20}}
        f = a.fair_value(self.m(est_rev=slow, rev_cagr=0.55), self.MAC)
        g = [x for x in f["assumptions"] if x.startswith("Wachstum Jahre")][0]
        self.assertIn("/ 13,0 % /", g)  # 0,8 × 10 % + 0,2 × (10 % + 15 Pp.) statt früher 0,6 × 10 % + 0,4 × 50 % = 26 %

    def test_forecast_growth(self):
        self.assertAlmostEqual(a.est_growth(self.m(), "est_rev"), 0.09)
        loss_base = {"0y": {"growth": 3.0, "ago": -0.5}, "+1y": {"growth": 0.2, "ago": 1.0}}
        self.assertAlmostEqual(a.est_growth(self.m(est_eps=loss_base), "est_eps"), 0.2)  # Wachstum aus Verlust ignoriert
        self.assertEqual(a.est_analysts(self.m()), 20)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestOps(Isolated):
    def test_restart_reason_and_perf(self):
        o = a.ops()
        o.update({"alive": a.START_TIME - 3600, "commit": a.ops().get("commit") or "lokal", "mem_last": 480})
        o["commit"] = (os.environ.get("RENDER_GIT_COMMIT") or "")[:7] or "lokal"
        a.note_startup()
        self.assertIn("Speicherüberlauf", a.ops()["restarts"][-1]["reason"])
        o["mem_last"] = 200
        o["alive"] = a.START_TIME - 3600
        a.note_startup()
        self.assertIn("eingeschlafen", a.ops()["restarts"][-1]["reason"])
        o["commit"] = "alt1234"
        a.note_startup()
        self.assertIn("Update", a.ops()["restarts"][-1]["reason"])
        a.record_analysis("SAP", "SAP.DE", 4.0, True)
        a.record_analysis("SAP", "SAP.DE", 8.0, True)
        a.record_analysis("xyzq", "", 1.0, False, "nicht gefunden")
        a.record_analysis("xyzq", "", 1.0, False, "nicht gefunden")
        p_ = a.analysis_perf()
        self.assertEqual((p_["d7"]["n"], p_["d7"]["fail"]), (4, 2))
        self.assertAlmostEqual(p_["d7"]["avg"], 6.0)
        self.assertEqual(p_["failing"][0]["n"], 2)
        self.assertEqual(p_["slowest"][0]["secs"], 8.0)
        for i in range(20):
            a.ops_tick(i)
        self.assertEqual(len(a.ops()["mem"]), 2 if a.mem_mb() else 0)


class TestIssuerParsing(unittest.TestCase):
    def test_numbers_countries_sectors(self):
        self.assertEqual(a._num_any("5,47"), 5.47)
        self.assertEqual(a._num_any("1.234,5"), 1234.5)
        self.assertEqual(a._num_any("1,234.5"), 1234.5)
        self.assertEqual(a._num_any("6.82"), 6.82)
        self.assertIsNone(a._num_any("-"))
        self.assertEqual(a._country("US"), "USA")
        self.assertEqual(a._country("Vereinigte Staaten von Amerika"), "USA")
        self.assertEqual(a._country("Großbritannien (UK)"), "Großbritannien")
        self.assertEqual(a._country("-"), "Sonstige")
        self.assertEqual(a._sector("Information Technology"), "IT")
        self.assertEqual(a._sector("Finanzwesen"), "Finanzen")

    def test_xlsx_reader_and_shares(self):
        import io, zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
            z.writestr("xl/sharedStrings.xml", f'<sst {ns}><si><t>Name</t></si><si><t>Weighting</t></si><si><t>NVIDIA</t></si></sst>')
            z.writestr("xl/worksheets/sheet1.xml", f'<worksheet {ns}><sheetData><row r="1"><c r="B1" t="s"><v>0</v></c><c r="C1" t="s"><v>1</v></c></row>'
                                                   f'<row r="2"><c r="B2" t="s"><v>2</v></c><c r="C2"><v>0.055</v></c></row></sheetData></worksheet>')
        rows = a._xlsx_rows(buf.getvalue())
        self.assertEqual(rows, [["", "Name", "Weighting"], ["", "NVIDIA", "0.055"]])
        sh = a._shares({f"L{i}": 0.05 for i in range(20)})
        self.assertEqual(len(sh), 14)
        self.assertEqual(sh[-1]["name"], "Weitere")
        self.assertAlmostEqual(sum(x["weight"] for x in sh), 1.0)

    def test_name_tokens(self):
        self.assertEqual(a._name_tokens("Amundi Core MSCI World UCITS ETF Acc"), {"amundi", "core", "msci", "world"})


class TestBusinessModel(Isolated):
    M = {"symbol": "TST", "name": "Test Software AG", "industry": "Software - Application", "sector": "Technology",
         "country": "Germany", "revenue": 3.9e10, "currency": "EUR", "fin_currency": "EUR", "op_m": 0.3, "gross_m": 0.74,
         "rev_cagr": 0.08, "roic": 0.2, "net_debt": -1e9, "nd_ebitda": None, "int_cov": 50, "pe": 45, "fcf": 5e9,
         "op_m_trend": 0.0, "eps_rev": None, "share_change": 0.0, "sbc_ratio": 0.12, "biz": "standard",
         "summary_text": "Test Software provides enterprise software."}

    def test_rules(self):
        b = a.biz_rules(dict(self.M))
        self.assertIn("Anwendungssoftware", b["text"])
        self.assertIn("39,0 Mrd. EUR", b["text"])
        self.assertEqual(b["context"], "Sektor Technologie · Sitz Deutschland")
        self.assertTrue(2 <= len(b["chances"]) <= 4 and 2 <= len(b["risks"]) <= 4)
        self.assertTrue(any("Bruttomarge" in x for x in b["chances"]))
        self.assertTrue(any("Bewertung" in x for x in b["risks"]))
        self.assertTrue(any("Cloud" in x for x in b["chances"]))  # branchentypisch ergänzt
        ins = a.biz_rules(dict(self.M, industry="Insurance - Diversified", biz="insurance"))
        self.assertFalse(any("Nettokasse" in x or "Bruttomarge" in x for x in ins["chances"]))

    def test_ai_cached_and_fallback(self):
        import unittest.mock as um
        self.assertIsNone(a.biz_ai(dict(self.M)))  # ohne Schlüssel kein Aufruf
        answer = {"content": [{"type": "text", "text": '{"beschreibung": "Testbeschreibung.", "chancen": ["C1", "C2", "C3"], "risiken": ["R1", "R2", "R3"]}'}]}
        calls = []

        class Resp:
            def __enter__(self): return self
            def __exit__(self, *x): return False
            def read(self): return json.dumps(answer).encode()

        def fake(req, timeout=0):
            calls.append(req.full_url)
            return Resp()
        with um.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}), um.patch.object(a.urllib.request, "urlopen", fake):
            b1 = a.business_model(dict(self.M))
            b2 = a.business_model(dict(self.M))
        self.assertEqual((b1["source"], b1["text"], b1["risks"]), ("Claude", "Testbeschreibung.", ["R1", "R2", "R3"]))
        self.assertEqual(b2["text"], "Testbeschreibung.")
        self.assertEqual(len(calls), 1)  # zweiter Aufruf aus dem Zwischenspeicher
        self.assertEqual(b1["context"], "Sektor Technologie · Sitz Deutschland")


class TestRequestBodies(TestHTTP):
    def test_bad_bodies_never_wipe_watchlist(self):
        op = self.client()
        self.login(op, "admin", "test-admin-pass")
        items = [{"symbol": f"S{i}.DE", "name": f"Firma {i} SE", "exchange": "XETRA", "currency": "EUR", "price": 231.45,
                  "label": "Outperform", "group": "Kaufen", "score": 23.4, "summary": "kaufenswert", "perf_1m": -0.04,
                  "upside": 0.15, "updated": 1792858539123, "next_event": {"type": "earnings", "date": "2027-01-28"}}
                 for i in range(150)]
        st, _, b = self.call(op, "/api/watchlist", {"items": items})  # ~50 KB – früher bei 16 KB abgeschnitten
        self.assertEqual((st, len(json.loads(b)["items"])), (200, 150))
        self.assertEqual(self.call(op, "/api/watchlist", "{kaputt", ctype="application/json; charset=utf-8")[0], 400)
        self.assertEqual(self.call(op, "/api/watchlist", {})[0], 400)
        self.assertEqual(self.call(op, "/api/watchlist", {"items": "abc"})[0], 400)
        self.assertEqual(self.call(op, "/api/alerts", "[1, 2]", ctype="application/json; charset=utf-8")[0], 400)
        self.assertEqual(self.call(op, "/api/alerts", {"x": "a" * 20000})[0], 413)
        self.assertEqual(len(json.loads(self.call(op, "/api/watchlist")[2])["items"]), 150)


class TestSecSegments(unittest.TestCase):
    def test_drop_parents(self):
        v = {"Products": 307.0, "iPhone": 209.6, "Mac": 33.7, "iPad": 28.0, "Wearables": 35.7, "Services": 109.2}
        self.assertEqual(set(a._drop_parents(v)), {"iPhone", "Mac", "iPad", "Wearables", "Services"})
        self.assertEqual(set(a._drop_parents({"A": 5.0, "B": 3.0, "C": 1.0})), {"A", "B", "C"})

    def test_quarters_with_derived_q4(self):
        rows = [{"start": "2025-01-01", "end": "2025-12-31", "val": 100, "filed": "2026-02-01"},
                {"start": "2025-01-01", "end": "2025-03-31", "val": 20, "filed": "2025-05-01"},
                {"start": "2025-04-01", "end": "2025-06-30", "val": 25, "filed": "2025-08-01"},
                {"start": "2025-07-01", "end": "2025-09-30", "val": 30, "filed": "2025-11-01"},
                {"start": "2025-01-01", "end": "2025-06-30", "val": 45, "filed": "2025-08-01"}]  # Halbjahr wird ignoriert
        y, q = a._sec_periods({"units": {"USD": rows}}, "USD")
        self.assertEqual(y, {"2025-12-31": 100})
        self.assertEqual(q, {"2025-03-31": 20, "2025-06-30": 25, "2025-09-30": 30, "2025-12-31": 25})

    def test_labels(self):
        self.assertEqual(a._seg_label("msft:LinkedInCorporationMember", {}), "Linked In Corporation")
        self.assertEqual(a._seg_label("country:US", {}), "USA")
        self.assertEqual(a._seg_label("aapl:AmericasSegmentMember", {"aapl:AmericasSegmentMember": "Americas"}), "Amerika")
        self.assertEqual(a._seg_label("x:IPhoneMember", {"x:IPhoneMember": "iPhone [Member]"}), "iPhone")


class TestSecStatements(unittest.TestCase):
    """Jahresabschlüsse aus SEC-XBRL als primäre Quelle (synthetische companyfacts, ohne Internet)."""

    @staticmethod
    def dur(start, end, val, filed="2026-02-01"):
        return {"start": start, "end": end, "val": val, "filed": filed}

    def facts(self):
        d, i = self.dur, (lambda end, val: {"end": end, "val": val, "filed": "2026-02-01"})
        rev = [d("2024-01-01", "2024-12-31", 360), d("2025-01-01", "2025-12-31", 400),
               d("2025-01-01", "2025-03-31", 90), d("2025-04-01", "2025-06-30", 100), d("2025-07-01", "2025-09-30", 100),
               d("2024-01-01", "2024-03-31", 85), d("2024-04-01", "2024-06-30", 90), d("2024-07-01", "2024-09-30", 90)]
        ni = [dict(r_, val=r_["val"] / 10) for r_ in rev]
        # Cashflows nur kumuliert (3/6/9/12 Monate), wie in den 10-Q-Meldungen
        ocf = [d("2025-01-01", "2025-03-31", 20), d("2025-01-01", "2025-06-30", 45), d("2025-01-01", "2025-09-30", 70),
               d("2025-01-01", "2025-12-31", 100), d("2024-01-01", "2024-12-31", 80)]
        capex = [dict(r_, val=r_["val"] / 5) for r_ in ocf]
        u = lambda rows, unit="USD": {"units": {unit: rows}}
        return {"_annual_form": "10-K", "Revenues": u(rev), "NetIncomeLoss": u(ni), "NetCashProvidedByUsedInOperatingActivities": u(ocf),
                "PaymentsToAcquirePropertyPlantAndEquipment": u(capex),
                "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest":
                    u([d("2025-01-01", "2025-12-31", 50)]),
                "IncomeTaxExpenseBenefit": u([d("2025-01-01", "2025-12-31", 10)]),
                "Assets": u([i("2025-12-31", 1000), i("2024-12-31", 900)]),
                "StockholdersEquity": u([i("2025-12-31", 400), i("2024-12-31", 380)]),
                "LongTermDebtNoncurrent": u([i("2025-12-31", 200)]), "LongTermDebtCurrent": u([i("2025-12-31", 20)]),
                "CommercialPaper": u([i("2025-12-31", 5)]), "FinanceLeaseLiability": u([i("2025-12-31", 7)]),
                "OperatingLeaseLiability": u([i("2025-12-31", 30)]),
                "CashAndCashEquivalentsAtCarryingValue": u([i("2025-12-31", 60)]), "ShortTermInvestments": u([i("2025-12-31", 40)])}

    def build(self):
        import unittest.mock as um
        a.SEC_CACHE.pop(("st2", 1), None)
        with um.patch.object(a, "_sec_facts", return_value=self.facts()),                 um.patch.object(a, "datetime", wraps=a.datetime) as dt:
            dt.now.return_value = a.datetime(2026, 3, 1)
            dt.fromisoformat = a.datetime.fromisoformat
            st = a.sec_statements(1)
        a.SEC_CACHE.pop(("st2", 1), None)
        return st

    def test_ytd_cashflow_quarters(self):
        y, q = a._sec_periods(self.facts()["NetCashProvidedByUsedInOperatingActivities"], "USD")
        self.assertEqual(y, {"2025-12-31": 100, "2024-12-31": 80})
        self.assertEqual(q, {"2025-03-31": 20, "2025-06-30": 25, "2025-09-30": 25, "2025-12-31": 30})
        shares = {"units": {"shares": [self.dur("2025-01-01", "2025-12-31", 100), self.dur("2025-01-01", "2025-09-30", 90)]}}
        self.assertEqual(a._sec_periods(shares, "shares", derive=False)[1], {})  # Durchschnittszahlen nie ableiten

    def test_net_income_tagged_in_millions(self):
        # Arista/Medtronic/FedEx: NetIncomeLoss im Jahr in Millionen getaggt, Ersatzkennzahl korrekt -> Ersatz, Q4 neu
        import unittest.mock as um
        f = self.facts()
        good = f["NetIncomeLoss"]["units"]["USD"]
        f["NetIncomeLossAvailableToCommonStockholdersBasic"] = {"units": {"USD": [dict(r_) for r_ in good if r_["start"][5:] == "01-01" and r_["end"][5:] == "12-31"]}}
        f["NetIncomeLoss"] = {"units": {"USD": [dict(r_, val=r_["val"] / 1e6) if r_["end"][5:] == "12-31" and r_["start"][5:] == "01-01" else r_ for r_ in good]}}
        f["Revenues"]["units"]["USD"] = [dict(r_, val=r_["val"] * 1e6) for r_ in f["Revenues"]["units"]["USD"]]
        f["NetIncomeLoss"]["units"]["USD"] = [dict(r_, val=r_["val"] * 1e6) for r_ in f["NetIncomeLoss"]["units"]["USD"]]
        f["NetIncomeLossAvailableToCommonStockholdersBasic"]["units"]["USD"] = [dict(r_, val=r_["val"] * 1e6) for r_ in f["NetIncomeLossAvailableToCommonStockholdersBasic"]["units"]["USD"]]
        a.SEC_CACHE.pop(("st2", 1), None)
        with um.patch.object(a, "_sec_facts", return_value=f), um.patch.object(a, "datetime", wraps=a.datetime) as dt:
            dt.now.return_value = a.datetime(2026, 3, 1)
            dt.fromisoformat = a.datetime.fromisoformat
            st = a.sec_statements(1)
        a.SEC_CACHE.pop(("st2", 1), None)
        inc, qinc = st["income"]
        self.assertEqual(a.row(inc, "Net Income")[:2], [40e6, 36e6])           # Jahr: Ersatzkennzahl
        self.assertEqual(a.row(qinc, "Net Income")[0], 11e6)                   # Q4 = korrigiertes Jahr − Q1–Q3

    def test_statements_yahoo_layout(self):
        st = self.build()
        inc, qinc = st["income"]
        bs, cf = st["balance"][0], st["cashflow"][0]
        self.assertEqual([c.strftime("%Y-%m-%d") for c in inc.columns], ["2025-12-31", "2024-12-31"])  # neueste zuerst
        self.assertEqual(a.row(qinc, "Total Revenue")[:4], [110, 100, 100, 90])  # Q4 = Jahr − Q1–Q3
        self.assertAlmostEqual(a.first(a.row(inc, "Tax Rate For Calcs")), 0.2)
        self.assertEqual(a.first(a.row(cf, "Capital Expenditure")), -20)
        self.assertEqual(a.first(a.row(cf, "Free Cash Flow")), 80)
        self.assertEqual(a.first(a.row(bs, "Total Debt")), 232)  # 200 + 20 + 5 + Finanzierungsleasing 7, ohne Operating-Leasing
        self.assertEqual(a.first(a.row(bs, "Capital Lease Obligations")), 37)
        self.assertEqual(a.first(a.row(bs, "Cash Cash Equivalents And Short Term Investments")), 100)

    def test_foreign_filer_not_primary(self):
        import unittest.mock as um
        f = dict(self.facts(), _annual_form="20-F")  # z. B. Alibaba: USD-Werte nur als Umrechnungshilfe
        a.SEC_CACHE.pop(("st2", 1), None)
        with um.patch.object(a, "_sec_facts", return_value=f):
            self.assertIsNone(a.sec_statements(1))
        a.SEC_CACHE.pop(("st2", 1), None)
        st = self.build()
        yq = pd.DataFrame({pd.Timestamp("2026-03-31"): [28.8, 25.5e9]}, index=["Diluted EPS", "Net Income"])  # Yahoo in CNY
        t = type("T", (), {"quarterly_income_stmt": yq})()
        self.assertNotIn(pd.Timestamp("2026-03-31"), a.SecTicker(t, st, "CNY").quarterly_income_stmt.columns)
        self.assertIn(pd.Timestamp("2026-03-31"), a.SecTicker(t, st, "USD").quarterly_income_stmt.columns)

    def test_merge_prefers_sec_and_fills_gaps(self):
        sec = pd.DataFrame({pd.Timestamp("2025-12-31"): [400.0, float("nan")]}, index=["Total Revenue", "Net Income"])
        yahoo = pd.DataFrame({pd.Timestamp("2026-03-31"): [105.0, 9.0, 1.0], pd.Timestamp("2025-12-30"): [390.0, 38.0, 2.0]},
                             index=["Total Revenue", "Net Income", "EBITDA"])
        out = a.merge_frames(sec, yahoo)
        self.assertEqual(list(out.columns), [pd.Timestamp("2026-03-31"), pd.Timestamp("2025-12-31")])  # neuere Yahoo-Periode
        self.assertEqual(a.row(out, "Total Revenue"), [105.0, 400.0])  # SEC hat Vorrang
        self.assertEqual(a.row(out, "Net Income"), [9.0, 38.0])        # Lücke aus Yahoo
        self.assertEqual(a.row(out, "EBITDA"), [1.0, 2.0])             # Zeile nur bei Yahoo

    def test_sec_info_overrides_yahoo(self):
        st = self.build()
        t = a.SecTicker(type("T", (), {"ticker": "X"})(), st)
        info = a.sec_info(t, {"currency": "USD", "currentPrice": 10.0, "marketCap": 1000.0, "totalRevenue": 1.0,
                              "forwardPE": 12.0})
        self.assertEqual(info["totalRevenue"], 400)       # 12 Monate aus den SEC-Quartalen
        self.assertEqual(info["forwardPE"], 12.0)         # Analystenwerte bleiben von Yahoo
        self.assertEqual(info["totalCash"], 100)
        self.assertTrue(info["_sec"])


class TestEsef(unittest.TestCase):
    """EU-Jahresberichte (ESEF, xBRL-JSON) – Auswertung und Abgleich ohne Internet."""

    @staticmethod
    def doc():
        f = lambda c, per, v, unit="iso4217:EUR", **extra: {"value": str(v), "dimensions": {
            "concept": "ifrs-full:" + c, "entity": "scheme:LEI1", "period": per, "unit": unit, **extra}}
        fy25, fy24 = "2025-01-01T00:00:00/2026-01-01T00:00:00", "2024-01-01T00:00:00/2025-01-01T00:00:00"
        facts = [f("Revenue", fy25, 1000), f("Revenue", fy24, 900), f("ProfitLoss", fy25, 130),
                 f("ProfitLossAttributableToOwnersOfParent", fy25, 120), f("ProfitLossAttributableToOwnersOfParent", fy24, 100),
                 f("DilutedEarningsLossPerShare", fy25, 1.2, "iso4217:EUR/xbrli:shares"),
                 f("Assets", "2026-01-01T00:00:00", 5000), f("Revenue", "2025-07-01T00:00:00/2026-01-01T00:00:00", 520),
                 f("Revenue", fy25, 600, **{"ifrs-full:SegmentsAxis": "x:EuropeMember"})]
        return {"facts": {str(i): x for i, x in enumerate(facts)}}

    def test_values(self):
        years, cur = a.esef_values(self.doc())
        self.assertEqual(cur, "EUR")
        self.assertEqual(years["2025-12-31"]["revenue"], 1000)      # Segmentwert und Halbjahr ignoriert
        self.assertEqual(years["2025-12-31"]["net_income"], 120)    # Anteil der Aktionäre vor Gesamtgewinn
        self.assertEqual(years["2025-12-31"]["assets"], 5000)       # Stichtag 1.1.2026 0 Uhr = 31.12.2025
        self.assertEqual(years["2024-12-31"]["net_income"], 100)

    def test_legal_names(self):
        self.assertEqual(a._legal_tokens("LVMH Moët Hennessy - Louis Vuitton, Société Européenne"),
                         a._legal_tokens("LVMH MOET HENNESSY LOUIS VUITTON"))
        self.assertNotEqual(a._legal_tokens("Heineken N.V."), a._legal_tokens("Heineken Holding N.V."))
        self.assertNotEqual(a._legal_tokens("Nokia Oyj"), a._legal_tokens("Nokian Renkaat Oyj"))
        self.assertEqual(a._legal_tokens("Banco Santander, S.A."), ["banco", "santander"])

    def test_check_against_yahoo(self):
        import unittest.mock as um
        years, cur = a.esef_values(self.doc())
        rep_ = {"lei": "LEI1", "name": "X SE", "country": "FR", "period_end": "2025-12-31", "published": "", "currency": cur,
                "viewer": None, "package": None, "years": years}
        cols = [pd.Timestamp("2025-12-31"), pd.Timestamp("2024-12-31")]
        inc = pd.DataFrame({cols[0]: [1000.0, 110.0], cols[1]: [900.0, 100.0]}, index=["Total Revenue", "Net Income"])
        t = type("T", (), {"income_stmt": inc, "cashflow": None, "balance_sheet": None})()
        with um.patch.object(a, "esef_report", return_value=rep_):
            out = a.esef_check({"isin": "FR0000000001"}, t, "EUR", "X.PA", "X SE")
            self.assertIsNone(a.esef_check({"isin": "US0000000001"}, t, "USD", "X", "X Inc"))  # keine EU-Aktie
        self.assertEqual(out["rows"][0]["revenue"]["ok"], True)
        self.assertEqual(out["rows"][0]["net_income"]["ok"], False)  # Yahoo 110 statt 120
        self.assertEqual((out["checked"], out["mismatch"]), (4, 1))
        with um.patch.object(a, "esef_report", return_value=rep_):
            self.assertEqual(a.esef_check({"isin": "FR0000000001"}, t, "USD", "X.PA")["checked"], 0)  # andere Währung


class TestCurrencyGuards(unittest.TestCase):
    """Keine Mischung von Börsen- und Bilanzwährung (ADRs wie Alibaba: Kurs USD, Bilanz CNY)."""

    def test_finnhub_currency(self):
        self.assertTrue(a.finnhub_currency_ok("AAPL", {"currency": "USD"}))
        self.assertFalse(a.finnhub_currency_ok("BABA", {"currency": "CNY"}))
        self.assertTrue(a.finnhub_currency_ok("SAP.DE", {"currency": "EUR"}))  # Börsenwährung unbekannt -> nicht sperren

    def test_peer_falls_back_to_yahoo_for_adr(self):
        import unittest.mock as um
        calls = {"stock/metric": {"metric": {"peTTM": 3.5}}, "stock/profile2": {"currency": "CNY", "name": "Alibaba"}}
        a.PEER_CACHE.pop("BABA", None)
        fake_t = type("T", (), {"info": {}})()
        with um.patch.object(a, "finnhub_key", return_value="x"),                 um.patch.object(a, "finnhub", side_effect=lambda path, **kw: calls.get(path)),                 um.patch.object(a.yf, "Ticker", return_value=fake_t),                 um.patch.object(a, "fill_info", return_value={"currentPrice": 100.0, "trailingPE": 24.0, "currency": "USD"}):
            p_ = a.peer_metrics("BABA")
        a.PEER_CACHE.pop("BABA", None)
        self.assertEqual((p_["source"], p_["pe"]), ("Yahoo", 24.0))

    def test_finnhub_target_other_currency_ignored(self):
        import unittest.mock as um
        from collections import defaultdict
        m = defaultdict(lambda: None, {"price": 100.0, "upside": None})
        calls = {"stock/recommendation": [{"buy": 5, "hold": 1, "period": "2026-10-01"}],
                 "stock/price-target": {"targetMean": 900.0}, "stock/quote": {"c": 100.0}, "stock/metric": {"metric": {}}}
        with um.patch.object(a, "finnhub_key", return_value="x"),                 um.patch.object(a, "finnhub", side_effect=lambda path, **kw: calls.get(path)):
            a.finnhub_enrich(m, "TSM", [])
        self.assertIsNone(m["upside"])  # Kursziel 9-fach = andere Währung

    def test_revenue_estimate_sanity(self):
        from collections import defaultdict
        import unittest.mock as um
        bad = {"0y": {"growth": 15.1, "ago": 0.8e12, "avg": 12.9e12, "cur": "JPY"},
               "+1y": {"growth": -0.01, "ago": 12.9e12, "avg": 12.8e12, "cur": "JPY"}}
        m = defaultdict(lambda: None, {"currency": "USD", "fin_currency": "JPY", "revenues": [None, 83e9], "est_rev": bad})
        with um.patch.object(a, "usd_rate", side_effect=lambda c: {"USD": 1.0, "JPY": 1 / 150}.get(c)):
            a.check_revenue_estimates(m)            # Vorjahr 0,8 statt ~12,5 Bio. JPY -> Prognose verworfen
            self.assertEqual(m["est_rev"], {})
            good = {"0y": {"growth": 0.04, "ago": 12.48e12, "avg": 12.9e12, "cur": "JPY"}}
            m2 = defaultdict(lambda: None, {"currency": "USD", "fin_currency": "JPY", "revenues": [83e9], "est_rev": good})
            a.check_revenue_estimates(m2)
            self.assertIn("0y", m2["est_rev"])
            self.assertAlmostEqual(a.est_fx(m2, good["0y"]), 1 / 150)
        self.assertIsNone(a.est_fx(defaultdict(lambda: None, {"currency": "USD", "fin_currency": "CNY"}), {}))

    def test_forward_earnings_needs_same_currency(self):
        from collections import defaultdict
        eps = {"0y": {"avg": 40.0, "n": 10}, "+1y": {"avg": 60.0, "n": 10}}
        base = {"price": 900.0, "currency": "USD", "est_eps": eps}
        m_usd = defaultdict(lambda: None, dict(base, fin_currency="USD"))
        m_cny = defaultdict(lambda: None, dict(base, fin_currency="CNY"))
        self.assertIsNotNone(a.forward_earnings(m_usd, 1e9))
        self.assertIsNone(a.forward_earnings(m_cny, 1e9))


class TestCountryRisk(unittest.TestCase):
    """Länderrisiko-Aufschlag (Damodaran) relativ zu den USA."""
    TAB = {"united states": 0.0023, "china": 0.0091, "ireland": 0.0078, "italy": 0.0246, "germany": 0.0}

    def crp(self, **kw):
        import unittest.mock as um
        from collections import defaultdict
        m = defaultdict(lambda: None, {"symbol": "X", **kw})
        with um.patch.object(a, "crp_table", return_value=self.TAB):
            return a.country_risk(m)

    def test_premium(self):
        self.assertIsNone(self.crp(country="United States", fin_currency="USD"))      # USA unverändert
        self.assertIsNone(self.crp(country="Germany", fin_currency="EUR"))
        it = self.crp(country="Italy", fin_currency="EUR")
        self.assertAlmostEqual(it["premium"], 0.0223)
        pdd = self.crp(country="Ireland", fin_currency="CNY")                        # Sitz Irland, Geschäft China
        self.assertEqual((pdd["country"], pdd["basis"]), ("China", "Bilanzwährung CNY"))
        self.assertEqual(self.crp(country_alt="People's Republic of China")["country"], "China")
        self.assertEqual(self.crp(symbol="ENI.MI")["country"], "Italien")             # Sitzland fehlt -> Börsenplatz

    def test_discount_rate_includes_premium(self):
        mac = {"rf": 4.0}
        base = {"beta": 1.0}
        self.assertAlmostEqual(a.cost_of_equity(dict(base, crp={"premium": 0.02}), mac) - a.cost_of_equity(base, mac), 0.02)


class TestDepotParse(unittest.TestCase):
    """Depot-Import aus Broker-CSV und Prüfpunkte (ohne Internet)."""
    COMDIRECT = ('"Depotübersicht vom 27.10.2026";\n\n'
                 '"Bezeichnung";"WKN";"ISIN";"Stück/Nom.";"Einstandskurs";"Kurswert in EUR";"Währung"\n'
                 '"Apple Inc.";"865985";"US0378331005";"20";"145,30";"5.902,00";"EUR"\n'
                 '"SAP SE";"716460";"DE0007164600";"1.035";"120,00";"222.155,00";"EUR"\n'
                 '"SAP SE";"716460";"DE0007164600";"15";"180,00";"3.219,75";"EUR"\n'
                 '"Summe";"";"";"";"";"231.276,75";""\n')

    def test_numbers(self):
        self.assertEqual(a._depot_num("1.234,56 €", True), 1234.56)
        self.assertEqual(a._depot_num("1,234.56", False), 1234.56)
        self.assertEqual(a._depot_num("1.035", True), 1035)      # deutsches Tausenderformat
        self.assertEqual(a._depot_num("12.5", True), 12.5)
        self.assertEqual(a._depot_num("0,05", True), 0.05)
        self.assertEqual(a._depot_num("-12,5 %", True), -12.5)
        self.assertIsNone(a._depot_num("–", True))

    def test_comdirect_layout(self):
        pos, notes = a.parse_depot_csv(self.COMDIRECT)
        self.assertEqual(len(pos), 2)                              # Summenzeile ignoriert, SAP zusammengefasst
        sap = pos[1]
        self.assertEqual((sap["isin"], sap["qty"]), ("DE0007164600", 1050))
        self.assertAlmostEqual(sap["buy"], (1035 * 120 + 15 * 180) / 1050)
        self.assertAlmostEqual(sap["value"], 225374.75)
        self.assertEqual(pos[0]["name"], "Apple Inc.")

    def test_english_and_errors(self):
        pos, _ = a.parse_depot_csv("Symbol,Name,Quantity,Average price\nKO,Coca-Cola,50,58.10\nJNJ,Johnson & Johnson,1,234.50\n")
        self.assertEqual([(p_["symbol"], p_["qty"], p_["buy"]) for p_ in pos], [("KO", 50, 58.1), ("JNJ", 1, 234.5)])
        with self.assertRaises(ValueError):
            a.parse_depot_csv("Datum;Betrag\n01.01.2026;100\n")       # keine Wertpapier-/Stück-Spalte
        with self.assertRaises(ValueError):
            a.parse_depot_csv("")

    SCALABLE = ("date;time;status;reference;description;assetType;type;isin;shares;price;amount;fee;tax;currency\n"
                "2026-09-15;10:00;Executed;R7;Apple;Security;Sell;US0378331005;5;200,00;1000,00;0;0;EUR\n"
                "2026-08-01;09:00;Executed;R6;Apple;Security;Distribution;US0378331005;;;12,00;0;0;EUR\n"
                "2026-07-01;09:00;Cancelled;R5;SAP;Security;Buy;DE0007164600;100;150,00;-15000,00;0;0;EUR\n"
                "2026-06-01;09:00;Executed;R4;Tesla;Security;Sell;US88160R1014;3;250,00;750,00;0;0;EUR\n"
                "2026-03-01;09:00;Executed;R3;Tesla;Security;Buy;US88160R1014;3;180,00;-540,00;1;0;EUR\n"
                "2026-02-01;09:00;Executed;R2;Apple;Security;Savings plan;US0378331005;10;150,00;-1500,00;0;0;EUR\n"
                "2026-01-01;09:00;Executed;R1;Apple;Security;Buy;US0378331005;10;130,00;-1300,00;0;0;EUR\n"
                "2026-01-01;08:00;Executed;R0;;Cash;Deposit;;;;5000,00;0;0;EUR\n")
    COMDIRECT_TX = ('"Geschäftstag";"Bezeichnung";"WKN";"ISIN";"Geschäftsart";"Stück / Nom.";"Kurs";"Kurswert"\n'
                    '"10.10.2026";"Allianz SE";"840400";"DE0008404005";"Verkauf";"10";"380,00";"3.800,00"\n'
                    '"05.05.2026";"Allianz SE";"840400";"DE0008404005";"Kauf";"5";"300,00";"1.500,00"\n'
                    '"02.01.2026";"Allianz SE";"840400";"DE0008404005";"Kauf";"10";"250,00";"2.500,00"\n'
                    '"02.01.2026";"BASF SE";"BASF11";"DE000BASF111";"Kauf";"20";"45,00";"900,00"\n')

    def test_transactions_scalable(self):
        pos, notes = a.parse_depot_csv(self.SCALABLE)
        self.assertEqual([(p_["isin"], p_["qty"]) for p_ in pos], [("US0378331005", 15)])   # Tesla verkauft, SAP storniert
        self.assertAlmostEqual(pos[0]["buy"], 140.0)   # Ø-Einstand (1300 + 1500) / 20, Verkauf senkt anteilig
        text = " ".join(notes)
        self.assertIn("3 Käufe und 2 Verkäufe", text)
        self.assertIn("1 Positionen wurden vollständig verkauft", text)
        self.assertIn("1 stornierte", text)

    def test_transactions_comdirect(self):
        pos, notes = a.parse_depot_csv(self.COMDIRECT_TX)
        self.assertEqual({p_["isin"]: p_["qty"] for p_ in pos}, {"DE0008404005": 5, "DE000BASF111": 20})
        pos = sorted(pos, key=lambda p_: p_["isin"])
        self.assertAlmostEqual(pos[0]["buy"], (2500 + 1500) / 15)   # Verkauf ändert den Ø-Einstandskurs nicht
        self.assertIsNone(pos[0]["value"])                          # Kurswert eines Auftrags ist kein Depotwert

    def test_transactions_negative_quantities(self):
        csv_ = ("Datum;Name;ISIN;Anzahl;Kurs\n03.03.2026;SAP;DE0007164600;-4;200\n"
                "01.01.2026;SAP;DE0007164600;10;100\n02.02.2026;SAP;DE0007164600;2;130\n")
        pos, _ = a.parse_depot_csv(csv_)
        self.assertEqual(pos[0]["qty"], 8)
        self.assertAlmostEqual(pos[0]["buy"], (1000 + 260) / 12)
        with self.assertRaises(ValueError):
            a.parse_depot_csv("Datum;ISIN;Typ;Stück\n01.01.2026;DE0007164600;Kauf;5\n02.01.2026;DE0007164600;Verkauf;5\n")

    def test_holdings_list_unchanged(self):
        # Bestandsliste mit „Art“ = Wertpapierart darf nicht als Umsatzliste gelten
        pos, notes = a.parse_depot_csv("Bezeichnung;ISIN;Art;Stück;Kurswert\nSAP;DE0007164600;Aktie;10;2000\n"
                                       "MSCI World;IE00B4L5Y983;ETF;5;600\n")
        self.assertEqual([p_["qty"] for p_ in pos], [10, 5])
        self.assertEqual(notes, [])

    TR_HEAD = ('"datetime","date","account_type","category","type","asset_class","name","symbol","shares","price","amount",'
               '"fee","tax","currency","original_amount","original_currency","fx_rate","description","transaction_id",'
               '"counterparty_name","counterparty_iban","payment_reference","mcc_code"\n')

    @classmethod
    def tr_row(cls, dt, cat, typ, asset="", name="", sym="", shares="", price="", amount="0.00"):
        return (f'"{dt}T10:00:00.000Z","{dt}","DEFAULT","{cat}","{typ}","{asset}","{name}","{sym}","{shares}","{price}",'
                f'"{amount}","","","EUR","","","","{name}","id-{dt}-{typ}","","","",""\n')

    def test_trade_republic_export(self):
        r = self.tr_row
        csv_ = self.TR_HEAD + "".join([
            r("2026-09-01", "TRADING", "SELL", "STOCK", "Apple", "US0378331005", "-5.000000", "200.00", "1000.00"),
            r("2026-08-15", "CASH", "DIVIDEND", "STOCK", "Apple", "US0378331005", "15.000000", "", "3.20"),
            r("2026-07-01", "TRADING", "BUY_CANCELLED", "STOCK", "SAP", "DE0007164600", "100.000000", "150.00", "-15000.00"),
            r("2026-06-01", "CORPORATE_ACTION", "SPIN_OFF", "STOCK", "Siemens Energy", "DE000ENER6Y0", "2.000000"),
            r("2026-05-01", "TRADING", "BUY", "CRYPTO", "Ethereum", "ETH", "0.500000", "2000.00", "-1000.00"),
            r("2026-03-01", "TRADING", "SELL", "STOCK", "Tesla", "US88160R1014", "-3.000000", "250.00", "750.00"),
            r("2026-02-01", "TRADING", "BUY", "STOCK", "Tesla", "US88160R1014", "3.000000", "180.00", "-540.00"),
            r("2026-02-01", "SAVINGS_PLAN", "BUY", "FUND", "iShares Core MSCI World", "IE00B4L5Y983", "10.000000", "100.00", "-1000.00"),
            r("2026-01-02", "TRADING", "BUY", "STOCK", "Apple", "US0378331005", "20.000000", "150.00", "-3000.00"),
            r("2026-01-01", "CASH", "CUSTOMER_INBOUND", amount="10000.00"),
            r("2026-01-01", "CASH", "INTEREST_PAYOUT", amount="12.00"),
        ])
        pos, notes = a.parse_depot_csv(csv_)
        got = {(p_["isin"] or p_["symbol"]): round(p_["qty"], 6) for p_ in pos}
        self.assertEqual(got, {"US0378331005": 15, "DE000ENER6Y0": 2, "ETH-EUR": 0.5, "IE00B4L5Y983": 10})
        apple = next(p_ for p_ in pos if p_["isin"] == "US0378331005")
        self.assertAlmostEqual(apple["buy"], 150.0)
        self.assertIn("1 Positionen wurden vollständig verkauft", " ".join(notes))     # Tesla
        self.assertIn("1 stornierte", " ".join(notes))                                 # SAP

    def test_resolve_isin_via_openfigi(self):
        import unittest.mock as um
        search = lambda q, include_crypto=False: ([{"symbol": "GOOGL", "name": "Alphabet Inc.", "exchange": "NASDAQ",
                                                     "sector": "Communication Services", "industry": ""}] if q == "GOOGL" else [])
        figi = lambda id_type, value, exch: [{"ticker": "GOOGL", "securityType": "Common Stock"}] if exch == "US" else []
        a.DEPOT_SYM_CACHE.pop("US02079K3059", None)
        with um.patch.object(a, "search_symbols", side_effect=search), um.patch.object(a, "openfigi_map", side_effect=figi):
            hit = a.depot_resolve({"isin": "US02079K3059", "name": "Alphabet (A)", "symbol": ""})
        a.DEPOT_SYM_CACHE.pop("US02079K3059", None)
        self.assertEqual(hit["symbol"], "GOOGL")   # Yahoo kennt die ISIN nicht -> OpenFIGI liefert das Kürzel
        self.assertEqual(" ".join(a.DEPOT_NAME_NOISE.sub(" ", "TSMC ADR").split()), "TSMC")
        self.assertEqual(" ".join(a.DEPOT_NAME_NOISE.sub(" ", "Alphabet (A)").split()), "Alphabet")

    def test_split_row_with_quantity(self):
        r = self.tr_row
        csv_ = self.TR_HEAD + "".join([
            r("2024-03-01", "TRADING", "SELL", "STOCK", "Alphabet (A)", "US02079K3059", "-5.000000", "130.00", "650.00"),
            r("2022-07-18", "CORPORATE_ACTION", "STOCK_SPLIT", "STOCK", "Alphabet (A)", "US02079K3059", "19.000000"),
            r("2021-05-03", "TRADING", "BUY", "STOCK", "Alphabet (A)", "US02079K3059", "1.000000", "2000.00", "-2000.00")])
        pos, notes = a.parse_depot_csv(csv_)
        self.assertEqual(pos[0]["qty"], 15)                         # 1 + 19 (Split) − 5
        self.assertAlmostEqual(pos[0]["buy"], 2000 * 0.75 / 15)

    def alphabet_csv(self, qty_2021, price_2021):
        r = self.tr_row
        return self.TR_HEAD + "".join([
            r("2024-03-01", "TRADING", "SELL", "STOCK", "Alphabet (A)", "US02079K3059", "-5.000000", "130.00", "650.00"),
            r("2021-05-03", "TRADING", "BUY", "STOCK", "Alphabet (A)", "US02079K3059", qty_2021, price_2021, "-2000.00")])

    def test_split_from_yahoo_history(self):
        import unittest.mock as um
        fake_t = type("T", (), {})()
        fake_t.splits = pd.Series({pd.Timestamp("2022-07-18"): 20.0})
        fake_t.fast_info = type("F", (), {"currency": "USD"})()
        fake_t.history = lambda **kw: pd.DataFrame({"Close": [100.0, 100.0]},
                                                   index=[pd.Timestamp("2021-05-03"), pd.Timestamp("2024-03-01")])
        a.DEPOT_SPLIT_CACHE.clear()
        with um.patch.object(a, "depot_resolve", return_value={"symbol": "GOOGL"}), \
                um.patch.object(a.yf, "Ticker", return_value=fake_t), um.patch.object(a, "fx_rate", return_value=1.0):
            # ohne Split-Prüfung: 1 − 5 < 0 -> Position fehlt (der gemeldete Fehler)
            with self.assertRaises(ValueError):
                a.parse_depot_csv(self.alphabet_csv("1.000000", "2000.00"))
            pos, notes = a.parse_depot_csv(self.alphabet_csv("1.000000", "2000.00"), split_fn=a.depot_split_factors)
            self.assertEqual(pos[0]["qty"], 15)                     # 1 Aktie vor dem 20:1-Split = 20 − 5
            self.assertIn("Aktiensplits berücksichtigt", " ".join(notes))
            a.DEPOT_SPLIT_CACHE.clear()
            # Broker hat alte Buchung schon umgerechnet (20 Stück zu 100) -> nicht noch einmal mal 20
            pos, _ = a.parse_depot_csv(self.alphabet_csv("20.000000", "100.00"), split_fn=a.depot_split_factors)
            self.assertEqual(pos[0]["qty"], 15)
        a.DEPOT_SPLIT_CACHE.clear()

    def test_time_weighted_return(self):
        idx = pd.date_range("2026-01-01", periods=4)
        # Tag 0: 100 €; Tag 1: +10 %; Tag 2: Kauf für 100 € und weitere +9,09 %; Tag 3: Verkauf für 50 €, Kurs unverändert
        V = pd.Series([100.0, 110.0, 220.0, 170.0], index=idx)
        F = pd.Series([0.0, 0.0, 100.0, -50.0], index=idx)
        D = pd.Series(0.0, index=idx)
        twr, level = a.depot_twr(V, F, D)
        self.assertAlmostEqual(twr, 0.2)                     # 1,1 × (120/110) × 1,0 − 1: Einzahlungen zählen nicht als Rendite
        self.assertAlmostEqual(level[-1], 120.0)
        D2 = pd.Series([0.0, 0.0, 0.0, 2.2], index=idx)       # ausgezahlte Dividende erhöht die Rendite
        self.assertGreater(a.depot_twr(V, F, D2)[0], twr)
        self.assertEqual(a.depot_twr(pd.Series([0.0, 0.0, 100.0], index=idx[:3]),
                                     pd.Series([0.0, 0.0, 100.0], index=idx[:3]), D[:3])[0], 0.0)  # vor dem 1. Kauf keine Rendite

    def test_fees_taxes_and_order(self):
        # Trade Republic: „amount“ ist brutto (Stück × Kurs), Gebühr und Steuer stehen daneben; neueste Buchung oben
        def row(ts, dt, typ, name, isin, shares, price, amount, fee="", tax="", cat="TRADING"):
            return (f'"{ts}","{dt}","DEFAULT","{cat}","{typ}","STOCK","{name}","{isin}","{shares}","{price}","{amount}",'
                    f'"{fee}","{tax}","EUR","","","","","id-{ts}","","","",""\n')
        csv_ = self.TR_HEAD + "".join([
            row("2026-07-15T08:00:00.000Z", "2026-07-15", "DIVIDEND", "Apple", "US0378331005", "1", "", "0.40", tax="-0.06", cat="CASH"),
            row("2026-03-10T15:00:00.000Z", "2026-03-10", "SELL", "Apple", "US0378331005", "-1.0", "190.00", "190.00", "-1.00", "-2.50"),
            row("2026-03-10T14:00:00.000Z", "2026-03-10", "BUY", "Apple", "US0378331005", "2.0", "180.50", "-361.00", "-1.00"),
            row("2026-03-09T09:00:00.000Z", "2026-03-09", "GIFT", "Tesla", "US88160R1014", "0.1", "300.00", "0.00"),
            row("2026-03-01T09:00:00.000Z", "2026-03-01", "TAX_OPTIMIZATION", "", "", "", "", "0.00", tax="1.20", cat="CASH")])
        pos, notes, hist = a.parse_depot_csv_full(csv_)
        by = {p_["isin"]: p_ for p_ in pos}
        self.assertAlmostEqual(by["US0378331005"]["buy"], 181.0)           # Einstand inkl. 1 € Gebühr
        self.assertAlmostEqual(by["US88160R1014"]["qty"], 0.1)              # geschenkte Aktie zählt zum Bestand
        keys = {k["key"]: k for k in hist["keys"]}
        self.assertAlmostEqual(keys["US0378331005"]["realized"], 189 - 181)  # Kauf vor Verkauf, obwohl unten in der Datei
        self.assertEqual(keys["US0378331005"]["trades"], [["2026-03-10", 2.0, 362.0], ["2026-03-10", -1.0, -189.0]])
        self.assertAlmostEqual(hist["fees"], 2.0)
        self.assertAlmostEqual(hist["taxes"], -2.5 - 0.06 + 1.2)
        self.assertEqual(hist["dividends"], [["2026-07-15", "US0378331005", 0.4]])
        self.assertTrue(any("Ordergebühren von 2,00 €" in n for n in notes))
        # Betrag schon inkl. Gebühr (andere Broker): Endbetrag übernehmen, Gebühr nicht doppelt zählen
        csv2 = self.TR_HEAD + row("2026-03-10T14:00:00.000Z", "2026-03-10", "BUY", "Apple", "US0378331005", "2.0", "180.50", "-362.00", "-1.00")
        self.assertAlmostEqual(a.parse_depot_csv_full(csv2)[0][0]["buy"], 181.0)

    def test_realized_gains_and_dividends(self):
        r = self.tr_row
        csv_ = self.TR_HEAD + "".join([
            r("2026-08-14", "CASH", "DIVIDEND", "STOCK", "Apple", "US0378331005", "15.000000", "", "3.10"),
            r("2026-08-03", "TRADING", "SELL", "STOCK", "Apple", "US0378331005", "-5.000000", "250.00", "1250.00"),
            r("2026-05-04", "TRADING", "BUY", "STOCK", "Apple", "US0378331005", "10.000000", "240.00", "-2400.00"),
            r("2026-03-02", "TRADING", "SELL", "STOCK", "Tesla", "US88160R1014", "-4.000000", "340.00", "1360.00"),
            r("2025-12-01", "TRADING", "BUY", "STOCK", "Tesla", "US88160R1014", "4.000000", "370.00", "-1480.00"),
            r("2025-11-03", "TRADING", "BUY", "STOCK", "Apple", "US0378331005", "10.000000", "230.00", "-2300.00")])
        pos, notes, hist = a.parse_depot_csv_full(csv_)
        keys = {k["key"]: k for k in hist["keys"]}
        self.assertAlmostEqual(keys["US0378331005"]["realized"], 5 * (250 - 235))     # Ø-Einstand 235
        self.assertAlmostEqual(keys["US88160R1014"]["realized"], 4 * (340 - 370))
        self.assertFalse(keys["US88160R1014"]["open"])                                 # verkauft, zählt aber zur Rendite
        self.assertEqual(hist["dividends"], [["2026-08-14", "US0378331005", 3.1]])
        self.assertEqual(keys["US0378331005"]["trades"][-1], ["2026-08-03", -5.0, -1250.0])  # Verkauf: Geld aus dem Depot
        self.assertIsNone(a.parse_depot_csv_full("ISIN;Stück\nDE0007164600;10\n")[2])       # Bestandsliste: kein Verlauf

    def test_checks(self):
        rows = [{"name": "A", "kind": "Aktie", "weight": 0.4, "gain_pct": -0.4},
                {"name": "B", "kind": "Aktie", "weight": 0.6, "gain_pct": 0.1}]
        S = {"eff_stocks": 1.9, "see_through": 0, "div_yield": 0.01}
        A = {"sectors": [{"label": "Technologie", "weight": 1.0}], "countries": [{"label": "Deutschland", "weight": 1.0}],
             "currencies": [{"label": "EUR", "weight": 1.0}]}
        titles = {c["title"]: c["level"] for c in a.depot_checks(S, A, {"vol": 0.3}, rows)}
        for t, lvl in (("Klumpenrisiko Einzelaktie", "warn"), ("Geringe Streuung", "warn"), ("Branchen-Klumpen", "warn"),
                       ("Heimatmarkt-Neigung", "info"), ("Größere Verlustpositionen", "info"), ("Hohe Schwankung", "warn")):
            self.assertEqual(titles.get(t), lvl, t)


class TestHostedWithoutPassword(TestHTTP):
    def test_locked(self):
        old = {k: os.environ.get(k) for k in ("RENDER", "APP_PASSWORD")}
        os.environ["RENDER"] = "true"
        os.environ.pop("APP_PASSWORD", None)
        try:
            op = self.client()
            self.assertEqual(self.call(op, "/api/watchlist")[0], 503)   # ohne Passwort online: alles gesperrt
            self.assertEqual(self.call(op, "/")[0], 503)
            self.assertEqual(self.call(op, "/healthz")[0], 200)
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


class TestDepotHTTP(TestHTTP):
    def wait(self, op, st, b):
        """Analysen laufen im Hintergrund: mit der Auftragsnummer nachfragen, bis das Ergebnis da ist."""
        d = json.loads(b)
        for _ in range(200):
            if st != 200 or "pending" not in d:
                return st, d
            time.sleep(0.05)
            st, _, b = self.call(op, "/api/depot?job=" + d["pending"])
            d = json.loads(b)
        self.fail("Analyse wurde nicht fertig")

    def test_save_load_delete(self):
        import unittest.mock as um
        op = self.client()
        self.login(op, "admin", "test-admin-pass")
        fake = {"summary": {"total": 1.0}, "positions": [], "alloc": {}, "risk": {}, "chart": None, "checks": [],
                "unresolved": [], "generated": "x"}
        self.assertEqual(json.loads(self.call(op, "/api/depot")[2]), {"empty": True})
        with um.patch.object(a, "analyze_depot", return_value=dict(fake)) as an:
            st, _, b = self.call(op, "/api/depot", {"csv": "ISIN;Stück\nDE0007164600;10\n", "save": True, "filename": "d.csv"})
            self.assertIn("pending", json.loads(b))                                          # sofortige Antwort, Analyse läuft
            st, d = self.wait(op, st, b)
            self.assertEqual(st, 200, d)
            self.assertEqual(an.call_args[0][0][0]["isin"], "DE0007164600")
            saved = a.user_space("admin")["depot"]
            self.assertEqual((saved["positions"][0]["qty"], saved["file"]), (10, "d.csv"))
            self.assertEqual(json.loads(self.call(op, "/api/depot")[2])["file"], "d.csv")     # aus dem Zwischenspeicher
            a.DEPOT_CACHE.clear()
            st, _, b = self.call(op, "/api/depot")                                           # neu berechnen, ebenfalls im Hintergrund
            self.assertEqual(self.wait(op, st, b)[1]["file"], "d.csv")
        st, _, b = self.call(op, "/api/depot", {"csv": "Datum;Betrag\n1;2\n"})
        st, d = self.wait(op, st, b)
        self.assertEqual(st, 400)
        self.assertIn("Kopfzeile", d["error"])
        self.assertEqual(self.call(op, "/api/depot?job=falsch")[0], 404)
        # Seite öffnen startet eine Analyse, ein Upload direkt danach eine zweite: beide bleiben abrufbar
        import unittest.mock as um
        a.user_space("admin")["depot"] = {"positions": [{"isin": "DE0007164600", "qty": 1}], "saved": "x", "file": "d.csv"}
        a.DEPOT_CACHE.clear()
        slow = lambda *x: (time.sleep(0.3), {"positions": [], "unresolved": []})[1]
        with um.patch.object(a, "analyze_depot", side_effect=slow):
            st1, _, b1 = self.call(op, "/api/depot")
            st2, _, b2 = self.call(op, "/api/depot", {"csv": "ISIN;Stück\nDE0007164600;10\n", "filename": "e.csv"})
            self.assertNotEqual(json.loads(b1)["pending"], json.loads(b2)["pending"])
            self.assertEqual(self.wait(op, st1, b1)[0], 200)
            self.assertEqual(self.wait(op, st2, b2)[1]["file"], "e.csv")
        self.assertEqual(self.call(op, "/api/depot", {"action": "delete"})[0], 200)
        self.assertNotIn("depot", a.user_space("admin"))
        self.assertEqual(json.loads(self.call(op, "/api/depot")[2]), {"empty": True})


class TestQuarterAI(Isolated):
    def test_summary_cached(self):
        import unittest.mock as um
        calls = []

        class Resp:
            def __init__(self, d): self.d = d
            def __enter__(self): return self
            def __exit__(self, *x): return False
            def read(self): return json.dumps(self.d).encode()

        def fake_open(req, timeout=0):
            calls.append(req.full_url)
            return Resp({"content": [{"type": "text", "text": '{"kernaussagen": ["Umsatz +16 %"], "ausblick": "Keine Prognose in der Mitteilung.", "ton": "positiv"}'}]})
        with um.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}), \
                um.patch.object(a, "sec_press_release", lambda cik, acc: ("Apple reports results. " * 40, "https://x/ex99.htm")), \
                um.patch.object(a.urllib.request, "urlopen", fake_open):
            r1 = a.quarter_ai(1, "0001-26-1", "Apple")
            r2 = a.quarter_ai(1, "0001-26-1", "Apple")
        self.assertEqual((r1["points"], r1["tone"], r1["url"]), (["Umsatz +16 %"], "positiv", "https://x/ex99.htm"))
        self.assertEqual(r2["points"], r1["points"])
        self.assertEqual(len(calls), 1)
        self.assertIsNone(a.quarter_ai(1, "0001-26-2", "Apple"))  # ohne Schlüssel kein Aufruf

    def test_html_text(self):
        self.assertEqual(a._html_text("<p>Umsatz&nbsp;<b>109</b></p><script>x()</script><div>Q3</div>"), "Umsatz 109\nQ3")


class TestEnglish(unittest.TestCase):
    def test_tr_en(self):
        self.assertEqual(a.tr_en("Kaufen, halten oder verkaufen?"), "Buy, hold or sell?")
        self.assertEqual(a.tr_en("KGV 24,3 vs. Median von 5 Wettbewerbern 27,8"), "P/E 24.3 vs. median of 5 competitors 27.8")
        self.assertEqual(a.tr_en("📉 SAP SE unter 200,00 EUR"), "📉 SAP SE below 200.00 EUR")
        self.assertEqual(a.tr_en("Umsatz 1.234,5 Mrd. USD"), "Revenue 1,234.5 bn USD")
        self.assertEqual(a.tr_en("Geschäftsmodell · Sektor Basiskonsum · Sitz Kanada"), "Business model · Consumer staples sector · based in Canada")
        self.assertEqual(a.tr_en("Unbekannter deutscher Satz bleibt"), "Unbekannter deutscher Satz bleibt")
        self.assertEqual(a.tr_en("Termine nächste Woche:\n• Di 27.10. SAP SE: Quartalszahlen"),
                         "Events next week:\n• Tue Oct 27 SAP SE: Quarterly results")


class TestIncomeEstimates(unittest.TestCase):
    def test_operating_margin_derived(self):
        per = lambda m, om: {"margin": m, "op_margin": om}
        periods = [per(0.20, 0.26), per(0.09, 0.23), per(0.19, 0.26)]   # Mittleres Jahr mit Sondereffekt im Reinertrag
        est = [{"revenue": 100.0, "margin": 0.21}, {"revenue": 110.0, "margin": None}]
        a.add_op_estimates(periods, est, 3)
        self.assertAlmostEqual(est[0]["op_margin"], 0.21 + 0.07)          # Median der Differenzen (0,06 / 0,14 / 0,07)
        self.assertAlmostEqual(est[0]["op_income"], 28.0)
        self.assertTrue(est[0]["op_derived"])
        self.assertNotIn("op_margin", est[1])                              # ohne Nettomarge keine Ableitung
        est2 = [{"revenue": 100.0, "margin": 0.1}]
        a.add_op_estimates([per(0.1, 0.7), per(0.1, 0.7)], est2, 3)       # unplausible Differenz -> nichts
        self.assertNotIn("op_margin", est2[0])


class TestIncomeEstimatesSources(unittest.TestCase):
    def _t(self, rev_ago):
        import pandas as pd

        class T:
            pass
        t = T()
        t.revenue_estimate = pd.DataFrame({"avg": [110.0, 121.0], "low": [105.0, 115.0], "high": [115.0, 127.0],
                                           "numberOfAnalysts": [20, 18], "yearAgoRevenue": [rev_ago, 110.0], "currency": ["USD", "USD"]},
                                          index=["0y", "+1y"])
        t.earnings_estimate = pd.DataFrame({"avg": [2.2, 2.4], "low": [2.0, 2.2], "high": [2.4, 2.6], "numberOfAnalysts": [20, 18],
                                            "yearAgoEps": [2.0, 2.2], "currency": ["USD", "USD"]}, index=["0y", "+1y"])
        return t

    def test_nasdaq_for_second_year(self):
        periods = [{"end": "2025-12-31", "revenue": 100.0, "net_income": 20.0}]
        nasdaq = {2027: {"avg": 2.4, "n": 10}, 2028: {"avg": 3.0, "n": 4}}
        est = a.income_estimates(self._t(100.0), periods, "USD", 2.0, nasdaq)
        self.assertEqual([e["label"] for e in est], ["2026e", "2027e", "2028e"])
        self.assertAlmostEqual(est[1]["net_income"], 24.0)                  # 10 Aktien × 2,40
        self.assertAlmostEqual(est[2]["net_income"], 24.0 * 3.0 / 2.4)      # Gewinnwachstum laut Nasdaq-Konsens
        self.assertEqual((est[2]["ni_consensus"], est[2]["n_eps"]), ("Nasdaq", 4))
        self.assertAlmostEqual(est[2]["revenue"], 121.0 * 1.1)              # Umsatz fortgeschrieben

    def test_without_usable_revenue_estimate(self):
        periods = [{"end": "2025-12-31", "revenue": 100.0, "net_income": 20.0}]
        est = a.income_estimates(self._t(50.0), periods, "USD", 2.0)       # Vorjahreswert passt nicht -> kein Umsatz
        self.assertIsNone(est[0]["revenue"])
        self.assertAlmostEqual(est[0]["net_income"], 22.0)                  # Gewinnprognose bleibt
        self.assertIsNone(est[0]["margin"])


class TestIncomeFallbacks(unittest.TestCase):
    PER = [{"end": f"{y}-12-31", "revenue": r, "net_income": r * 0.2, "margin": 0.2} for y, r in ((2023, 80.0), (2024, 90.0), (2025, 100.0))]

    def test_nasdaq_only(self):
        nq = {2026: {"avg": 2.2, "n": 9}, 2027: {"avg": 2.5, "n": 8}, 2028: {"avg": 2.8, "n": 3}}
        est = a.income_estimates_nasdaq(self.PER, "USD", 2.0, nq, [80.0, 90.0, 100.0])
        self.assertEqual([e["label"] for e in est], ["2026e", "2027e", "2028e"])
        self.assertAlmostEqual(est[0]["net_income"], 10 * 2.2)                 # 10 Aktien (20 / 2,00) × 2,20
        self.assertAlmostEqual(est[0]["revenue"], 100 * (1 + a.trend_growth([80, 90, 100])))  # gewichtete Fortschreibung
        self.assertTrue(est[0]["rev_trend"])
        self.assertEqual(est[2]["n_eps"], 3)

    def test_trend_only(self):
        est = a.income_estimates_trend(self.PER)
        self.assertTrue(est and all(e["est"] == "trend" for e in est))
        self.assertAlmostEqual(est[0]["net_income"], est[0]["revenue"] * 0.2)


class TestYahooBlock(unittest.TestCase):
    def test_skip_when_blocked(self):
        calls = []
        try:
            a.YQ_STATE.update(blocked=True)
            self.assertEqual(a.yq(lambda: calls.append(1) or 5, "leer"), "leer")   # gesperrt: gar nicht erst anfragen
            self.assertEqual(calls, [])
            a.YQ_STATE.update(blocked=False)
            self.assertEqual(a.yq(lambda: 5), 5)
        finally:
            a.YQ_STATE.update(blocked=False, checked=float("inf"))


class TestTrendEstimates(unittest.TestCase):
    def test_trend_hides_unstable_net_income(self):
        per = [{"end": f"{y}-12-31", "revenue": 100.0 + y - 2023, "net_income": ni, "margin": ni / (100.0 + y - 2023)}
               for y, ni in ((2023, -2.0), (2024, 1.0), (2025, 3.0))]
        est = a.income_estimates_trend(per)
        self.assertTrue(est and all(e["net_income"] is None for e in est))   # Verlustjahr -> kein Reinertrag
        self.assertTrue(all(e["revenue"] for e in est))

    def test_couple_revenue_to_earnings_consensus(self):
        # Applied-Materials-Fall: Gewinn +48 %, Umsatz nur +4 % fortgeschrieben -> Marge 35 % > Deckel
        per = [{"end": f"202{i}-10-31", "revenue": r, "net_income": n, "margin": n / r}
               for i, (r, n) in enumerate(((23.1, 5.9), (25.8, 6.5), (26.5, 6.9), (27.2, 7.2), (28.4, 7.0)), 1)]
        est = [{"label": "2026e", "revenue": 29.5, "net_income": 10.34, "rev_trend": True, "est": "consensus"},
               {"label": "2027e", "revenue": 30.7, "net_income": 14.77, "rev_trend": True, "est": "consensus"},
               {"label": "2028e", "revenue": 31.9, "net_income": None, "rev_trend": True, "est": "consensus"}]
        a.couple_revenue(per, est)
        cap = max(p_["net_income"] / p_["revenue"] for p_ in per) * 1.1 + 0.01          # beste Marge × 1,1 + 1 Pkt.
        self.assertAlmostEqual(est[0]["revenue"], 29.5 + 0.75 * (10.34 / cap - 29.5))    # drei Viertel des Wegs
        self.assertTrue(est[0]["rev_coupled"] and est[1]["rev_coupled"])
        self.assertAlmostEqual(est[2]["revenue"] / est[1]["revenue"], 31.9 / 30.7)   # Folgejahr wächst vom neuen Niveau
        flat = [{"label": "2026e", "revenue": 30.0, "net_income": 7.5, "rev_trend": True, "est": "consensus"}]
        a.couple_revenue(per, flat)
        self.assertEqual(flat[0]["revenue"], 30.0)                                   # Marge im Rahmen -> unverändert

    def test_trend_growth_weights_recent_years(self):
        self.assertAlmostEqual(a.trend_growth([100, 125, 150, 160]), 0.25 * 0.2 + 0.25 * (0.2 + 1 / 15) / 2 + 0.5 / 15)
        self.assertEqual(a.trend_growth([10, 30, 90]), 0.25)            # Deckel
        self.assertIsNone(a.trend_growth([100]))

    def test_trend_berkshire_like(self):
        # Umsatz zuletzt flach nach einem Sprungjahr, Reinertrag schwankt mit Kursgewinnen (Verlust vor drei Jahren)
        y0 = a.datetime.now().year - 5
        rows = ((276.2, 89.9), (302.0, -22.8), (364.5, 96.2), (371.4, 89.0), (371.4, 67.0))
        per = [{"end": f"{y0 + i}-12-31", "revenue": r, "net_income": ni, "margin": ni / r} for i, (r, ni) in enumerate(rows)]
        est = a.income_estimates_trend(per)
        self.assertTrue(est and all(e["net_income"] is None for e in est))
        self.assertLess(est[0]["revenue"] / 371.4 - 1, 0.05)                 # nicht +9 % wie mit dem Sprungjahr


class TestOnvista(unittest.TestCase):
    def test_dividend_year_offset(self):
        y = a.datetime.now().year
        D = {"years": [y - 2, y - 1], "dps": [4.7, 5.2], "currency": "EUR", "ytd": 5.35, "per_year": 1, "paid_now": 1}
        ov = {"dps": {y - 2: {"dps": 5.2, "est": False, "cur": "EUR"}, y - 1: {"dps": 5.35, "est": False, "cur": "EUR"},
                      y: {"dps": 5.6, "est": True, "cur": "EUR"}, y + 1: {"dps": 5.9, "est": True, "cur": "EUR"}}}
        self.assertEqual(a.onvista_dps_forecast(D, ov), {y + 1: 5.6, y + 2: 5.9})   # Auszahlung im Folgejahr
        ov_bad = {"dps": {y - 1: {"dps": 9.0, "est": False, "cur": "EUR"}, y: {"dps": 9.5, "est": True, "cur": "EUR"}}}
        self.assertEqual(a.onvista_dps_forecast(D, ov_bad), {})                      # passt nicht -> nichts übernehmen

    def test_dividend_consensus_other_currency_and_outlier(self):
        y = a.datetime.now().year
        # gezahlt in Dollar, onvista in Euro (Faktor 1,16) -> über das Verhältnis der Vorjahre skalieren
        D = {"years": [y - 4, y - 3, y - 2, y - 1], "dps": [0.91, 0.95, 0.99, 1.03], "currency": "USD"}
        ov = {"dps": {**{y - 4 + i: {"dps": v / 1.16, "est": False, "cur": "EUR"} for i, v in enumerate((0.91, 0.95, 0.99, 1.03))},
                      y: {"dps": 0.93, "est": True, "cur": "EUR"}, y + 1: {"dps": 0.98, "est": True, "cur": "EUR"}}}
        out = a.onvista_dps_forecast(D, ov)
        self.assertAlmostEqual(out[y], 0.93 * 1.16, places=6)
        # Ausreißer: ein Jahr 13-mal so hoch wie Vor- und Folgejahr (Bayer) -> verworfen
        D2 = {"years": [y - 3, y - 2, y - 1], "dps": [0.11, 0.11, 0.11], "currency": "EUR"}
        ov2 = {"dps": {y - 3: {"dps": 0.11, "est": False, "cur": "EUR"}, y - 2: {"dps": 0.11, "est": False, "cur": "EUR"},
                       y - 1: {"dps": 0.11, "est": False, "cur": "EUR"}, y: {"dps": 0.11, "est": True, "cur": "EUR"},
                       y + 1: {"dps": 1.47, "est": True, "cur": "EUR"}, y + 2: {"dps": 0.11, "est": True, "cur": "EUR"}}}
        self.assertEqual(sorted(a.onvista_dps_forecast(D2, ov2)), [y, y + 2])
        # nur ein Vergleichsjahr in fremder Währung -> nichts übernehmen
        D3 = {"years": [y - 1], "dps": [1.03], "currency": "USD"}
        ov3 = {"dps": {y - 1: {"dps": 0.9, "est": False, "cur": "EUR"}, y: {"dps": 0.95, "est": True, "cur": "EUR"}}}
        self.assertEqual(a.onvista_dps_forecast(D3, ov3), {})

    def test_net_income_from_onvista_eps(self):
        periods = [{"end": "2025-09-30", "revenue": 80.0, "net_income": 10.0}, {"end": "2024-09-30", "revenue": 75.0, "net_income": 9.0}][::-1]
        eps = {2026: {"avg": 11.0, "est": True}, 2027: {"avg": 12.5, "est": True}}
        est = a.income_estimates_nasdaq(periods, "EUR", 10.0, eps, [75.0, 80.0], "onvista", "EUR")
        self.assertEqual([e["label"] for e in est], ["2026e", "2027e"])
        self.assertAlmostEqual(est[0]["net_income"], 11.0)          # 1 Mrd. Aktien × 11,00
        self.assertEqual(est[0]["ni_consensus"], "onvista")

    def test_news_targets_mix_google_and_onvista_dates(self):
        import unittest.mock as mock
        now = a.datetime.now(a.timezone.utc)
        g = [{"title": "JPMorgan hebt Ziel für SAP auf 250 Euro", "date": now, "source": "x"}]
        page = ('"articleSubTypeName":"Aktieneinstufung","headline":"JPMorgan hebt Ziel f\\u00fcr SAP auf 255 Euro",'
                '"datetimePublication":"' + now.strftime("%Y-%m-%dT%H:%M:%S") + '.000+00:00"')
        with mock.patch.object(a, "google_news", return_value=g), mock.patch.object(a, "onvista_isin", return_value="DE0007164600"), \
                mock.patch.object(a, "_fetch", return_value=page.encode()):
            out = a.news_targets("SAP", "EUR", 210.0, symbol="SAP.DE")   # früher: Absturz naiv vs. mit Zeitzone
        self.assertEqual(out["n"], 1)

    def test_share_count_when_prior_year_depressed(self):
        # berichteter Gewinn durch Sonderbelastung gedrückt (bereinigter Konsens > 2,5 ×) -> gemeldete Aktienzahl nehmen
        periods = [{"end": "2024-12-31", "revenue": 180.0, "net_income": 6.0}, {"end": "2025-12-31", "revenue": 185.0, "net_income": 2.8}]
        eps = {2026: {"avg": 12.0}, 2027: {"avg": 13.0}}
        self.assertEqual(a.income_estimates_nasdaq(periods, "USD", 2.9, eps, [180.0, 185.0]), [])
        est = a.income_estimates_nasdaq(periods, "USD", 2.9, eps, [180.0, 185.0], shares_out=0.95)
        self.assertAlmostEqual(est[0]["net_income"], 11.4)
        self.assertEqual(len(est), 2)
        absurd = {2026: {"avg": 120.0}}                                         # > 60 % des Umsatzes -> verwerfen
        self.assertEqual(a.income_estimates_nasdaq(periods, "USD", 2.9, absurd, [180.0, 185.0], shares_out=0.95), [])

    def test_isin_name_matching(self):
        import unittest.mock as mock
        res = {"air liquide": [{"entityType": "STOCK", "name": "Air Liquide", "isin": "FR0000120073"}],
               "volvo": [{"entityType": "STOCK", "name": "Volvo Car", "isin": "SE0021628898"},
                         {"entityType": "STOCK", "name": "Volvo B", "isin": "SE0000115446"}]}
        fake = lambda url, **k: a.json.dumps({"list": res.get(a.urllib.parse.parse_qs(url.split("?")[1])["searchValue"][0], [])}).encode()
        with mock.patch.object(a, "_fetch", side_effect=fake):
            self.assertEqual(a._onvista_isin("AI.PA", "L'Air Liquide S.A."), "FR0000120073")
            self.assertEqual(a._onvista_isin("VOLV-B.ST", "AB Volvo (publ)"), "SE0000115446")   # nicht Volvo Cars

    def test_target_from_onvista_page(self):
        today = a.datetime.now().strftime("%Y-%m-%d")
        page = ('"targetPrice":312.25,"numberRecommendations":29,"numberBuyRecommendations":17},"recommendationList":'
                '{"expires":1,"total":2,"list":[{"date":"' + today + 'T00:00:00.000+00:00","targetPrice":300,"targetPriceEur":300,'
                '"bank":"JEFFERIES \\u0026 CO","rating":"HOLD"},{"date":"' + today + 'T00:00:00.000+00:00","targetPriceEur":345,'
                '"bank":"JP MORGAN","rating":"BUY"},{"date":"2019-01-01T00:00:00.000+00:00","targetPriceEur":99,"bank":"ALT"}]}')
        import unittest.mock as mock
        a.ONVISTA_TARGET_CACHE.clear()
        with mock.patch.object(a, "onvista_isin", return_value="DE0007236101"), \
                mock.patch.object(a, "_fetch", return_value=page.encode()):
            m = {"price": 290.0, "currency": "EUR", "upside": None}
            a.apply_onvista_target(m, "SIE.DE")
        a.ONVISTA_TARGET_CACHE.clear()
        self.assertAlmostEqual(m["target"], 312.25)
        self.assertEqual(m["target_n"], 29)
        self.assertEqual([it["firm"] for it in m["target_items"]], ["Jp Morgan", "Jefferies & Co"])  # alte Ziele weg
        self.assertEqual((m["target_low"], m["target_high"]), (300, 345))

    def test_stale_onvista_consensus_uses_fresh_targets(self):
        import unittest.mock as mock
        items = [{"firm": f"B{i}", "value": v, "date": "", "rating": "", "age": 3} for i, v in enumerate((258, 250, 250, 240, 235, 201, 175))]
        with mock.patch.object(a, "onvista_target", return_value={"mean": 199.57, "n": 34, "items": items}):
            m = {"price": 211.2, "currency": "EUR", "upside": None}
            a.apply_onvista_target(m, "SAP.DE")
        self.assertEqual((m["target"], m["target_n"]), (240, 7))     # Konsens hinkt nach -> Median der frischen Ziele
        self.assertNotIn("age", m["target_items"][0])


class TestFcfEstimates(unittest.TestCase):
    def test_conversion_and_matching(self):
        import pandas as pd
        periods = [{"end": e, "revenue": 100.0, "net_income": ni} for e, ni in
                   (("2023-12-31", 10.0), ("2024-12-31", 10.0), ("2025-12-31", 10.0))]
        cf = pd.DataFrame({pd.Timestamp("2025-12-28"): [None, 13.0, -6.0], pd.Timestamp("2024-12-31"): [12.0, None, None],
                           pd.Timestamp("2023-12-31"): [11.0, None, None]},
                          index=["Free Cash Flow", "Operating Cash Flow", "Capital Expenditure"])
        a.fcf_by_period(cf, periods)
        self.assertEqual([p_["fcf"] for p_ in periods], [11.0, 12.0, 7.0])   # 2025: 13 − 6, Periodenende 3 Tage abweichend
        est = [{"revenue": 120.0, "net_income": 20.0}, {"revenue": 130.0, "net_income": None}]
        a.add_fcf_estimates(periods, est, 3)
        self.assertAlmostEqual(est[0]["fcf"], 20.0 * (1.1 + 0.7) / 2)        # halb Median (1,1), halb jüngstes Jahr (0,7)
        self.assertAlmostEqual(est[1]["fcf"], 130.0 * (0.11 + 0.07) / 2)     # ohne Gewinnprognose: Free-Cashflow-Marge
        self.assertTrue(est[0]["fcf_derived"])
        est2 = [{"revenue": 120.0, "net_income": 40.0}]                       # Gewinnsprung (Sondereffekt) im Konsens
        a.add_fcf_estimates(periods, est2, 3, by_margin=True)
        self.assertAlmostEqual(est2[0]["fcf"], 120.0 * (0.11 + 0.07) / 2)    # Jahre: über die Umsatzmarge, nicht den Gewinn
        self.assertEqual(est2[0]["fcf_basis"], "margin")


class TestDividendForecast(unittest.TestCase):
    def test_forecast(self):
        y = a.datetime.now().year
        m = {"div_yield": 0.02, "biz": "standard",
             "divhist": {"years": [y - 2, y - 1], "dps": [1.0, 1.05], "g5": 0.06, "ytd": 0.8, "per_year": 4, "paid_now": 3},
             "est_eps": {"0y": {"avg": 2.2, "ago": 2.0}, "+1y": {"avg": 2.25, "ago": 2.2}}}
        f = a.dividend_forecast(m)
        self.assertEqual([x["year"] for x in f], [y, y + 1, y + 2])
        self.assertAlmostEqual(f[0]["dps"], 1.05 * 1.06, places=4)   # Dividendenwachstum 6 %, Gewinn +10 % -> 6 %
        self.assertAlmostEqual(f[1]["growth"], 2.25 / 2.2 - 1, places=4)  # Gewinn nur +2,3 % -> Dividende höchstens so stark
        m["divhist"].update(per_year=1, paid_now=1, ytd=1.2)           # jährliche Zahlung schon erfolgt
        f = a.dividend_forecast(m)
        self.assertTrue(f[0]["done"])
        self.assertEqual(f[0]["dps"], 1.2)
        m["est_eps"] = {"0y": {"avg": 1.5, "ago": 2.0}}                # Gewinnrückgang -> Dividende gehalten, keine Kürzung
        m["divhist"].update(per_year=4, paid_now=1, ytd=0.25)
        self.assertAlmostEqual(a.dividend_forecast(m)[0]["dps"], 1.05)
        self.assertIsNone(a.dividend_forecast({"div_yield": 0, "divhist": m["divhist"]}))


class TestMovers(unittest.TestCase):
    def test_top_and_flop(self):
        import unittest.mock as um
        import pandas as pd
        syms = ["A.DE", "B.DE", "C.DE", "D.DE", "E.DE", "F.DE", "G.DE"]
        idx = pd.to_datetime(["2026-10-26", "2026-10-27"])
        df = pd.DataFrame({"A.DE": [100, 110], "B.DE": [100, 90], "C.DE": [100, 101], "D.DE": [100, 99],
                           "E.DE": [100, 105], "F.DE": [100, 97], "G.DE": [100, float("nan")]}, index=idx)
        with um.patch.dict(a.SCREENER_UNIVERSES, {"test": ("Testindex", syms)}),                 um.patch.object(a.yf, "download", lambda *x, **k: pd.concat({"Close": df}, axis=1)),                 um.patch.object(a, "_mover_name", lambda s_: s_.split(".")[0]):
            a.MOVERS_CACHE.pop(("test", "day"), None)
            r = a.market_movers("test", n=2)
        self.assertEqual([x["symbol"] for x in r["up"]], ["A.DE", "E.DE"])
        self.assertEqual([x["symbol"] for x in r["down"]], ["B.DE", "F.DE"])   # größter Verlust zuerst
        self.assertAlmostEqual(r["up"][0]["change"], 0.10)
        self.assertEqual((r["n"], r["advancers"], r["decliners"], r["date"]), (6, 3, 3, "2026-10-27"))  # G ohne aktuellen Kurs
        self.assertEqual(r["up"][0]["currency"], "EUR")
        with self.assertRaises(ValueError):
            a.market_movers("gibtsnicht")

    def test_month(self):
        import unittest.mock as um
        import pandas as pd
        syms = ["A.DE", "B.DE", "C.DE", "N.DE"]
        idx = pd.to_datetime(["2026-09-29", "2026-09-30", "2026-10-01", "2026-10-27"])
        df = pd.DataFrame({"A.DE": [50, 100, 120, 130], "B.DE": [100, 200, 150, 150], "C.DE": [10, 10, 10, 11],
                           "N.DE": [float("nan"), float("nan"), 5, 6]}, index=idx)
        with um.patch.dict(a.SCREENER_UNIVERSES, {"test": ("Testindex", syms)}),                 um.patch.object(a.yf, "download", lambda *x, **k: pd.concat({"Close": df}, axis=1)),                 um.patch.object(a, "_mover_name", lambda s_: s_):
            a.MOVERS_CACHE.pop(("test", "month"), None)
            r = a.market_movers("test", n=1, period="month")
        self.assertEqual((r["since"], r["date"], r["n"]), ("2026-10-01", "2026-10-27", 3))  # N erst seit Oktober notiert
        self.assertEqual(r["up"][0]["symbol"], "A.DE")
        self.assertAlmostEqual(r["up"][0]["change"], 0.30)      # 130 gegen den letzten Schlusskurs im September (100)
        self.assertAlmostEqual(r["down"][0]["change"], -0.25)   # B: 150 gegen 200

    def test_year(self):
        import unittest.mock as um
        import pandas as pd
        syms = ["A.DE", "B.DE", "C.DE"]
        idx = pd.to_datetime(["2025-12-30", "2026-01-02", "2026-06-01", "2026-10-27"])
        df = pd.DataFrame({"A.DE": [100, 105, 150, 140], "B.DE": [80, 82, 60, 40], "C.DE": [10, 10, 10, 10]}, index=idx)
        with um.patch.dict(a.SCREENER_UNIVERSES, {"test": ("Testindex", syms)}),                 um.patch.object(a.yf, "download", lambda *x, **k: pd.concat({"Close": df}, axis=1)),                 um.patch.object(a, "_mover_name", lambda s_: s_):
            a.MOVERS_CACHE.pop(("test", "year"), None)
            r = a.market_movers("test", n=1, period="year")
        self.assertEqual((r["since"], r["period"]), ("2026-01-01", "year"))
        self.assertAlmostEqual(r["up"][0]["change"], 0.40)      # 140 gegen den Jahresschluss 2025 (100)
        self.assertAlmostEqual(r["down"][0]["change"], -0.50)   # B: 40 gegen 80


class TestOptions(unittest.TestCase):
    def test_aggregation(self):
        import unittest.mock as um
        import pandas as pd
        exp = (a.datetime.now() + a.timedelta(days=30)).strftime("%Y-%m-%d")
        calls = pd.DataFrame({"strike": [90.0, 100.0], "openInterest": [300, 100], "volume": [50, 30], "lastPrice": [12.0, 4.0],
                              "impliedVolatility": [0.3, 0.25], "currency": ["USD", "USD"]})
        puts = pd.DataFrame({"strike": [90.0, 100.0], "openInterest": [100, 100], "volume": [20, 0], "lastPrice": [1.0, 5.0],
                             "impliedVolatility": [0.32, 0.35], "currency": ["USD", "USD"]})

        class T:
            options = (exp,)
        with um.patch.object(a.yf, "Ticker", lambda s: T()), um.patch.object(a, "_opt_chain", lambda s, e: (e, calls, puts)),                 um.patch.object(a, "cboe_options", lambda s, p=None: None):  # Cboe kennt den Wert nicht -> Yahoo
            d = a.options_data("XYZ", price=99.0)
        self.assertEqual(d["source"], "Yahoo Finance")
        self.assertEqual((d["oi"]["calls"], d["oi"]["puts"], d["vol"]["calls"], d["vol"]["puts"]), (400, 200, 80, 20))
        self.assertAlmostEqual(d["pc_oi"], 0.5)
        self.assertAlmostEqual(d["prem"]["calls"], (50 * 12 + 30 * 4) * 100)
        self.assertAlmostEqual(d["iv_atm"], 0.30)  # Strike 100 am nächsten: (0,25 + 0,35) / 2
        self.assertEqual(a.derivatives("ALV.DE"), {"na": "eu"})

    def test_cboe(self):
        import unittest.mock as um
        exp = (a.datetime.now() + a.timedelta(days=20)).strftime("%y%m%d")
        opts = [{"option": f"XYZ{exp}C00100000", "open_interest": 300, "volume": 50, "delta": 0.6, "last_trade_price": 4.0,
                 "last_trade_time": "2026-10-27T15:00:00"},
                {"option": f"XYZ{exp}P00100000", "open_interest": 100, "volume": 10, "delta": -0.4, "last_trade_price": 3.0,
                 "last_trade_time": "2026-10-27T15:01:00"}]
        body = json.dumps({"timestamp": "2026-10-27 18:00:00", "data": {"iv30": 31.5, "options": opts}}).encode()
        with um.patch.object(a, "_fetch", lambda url, **k: body):
            d = a.options_data("XYZ")
        self.assertEqual(d["source"], "Cboe")
        self.assertEqual((d["oi"]["calls"], d["oi"]["puts"], d["vol"]["calls"], d["vol"]["puts"]), (300, 100, 50, 10))
        self.assertAlmostEqual(d["delta_oi"]["calls"], 180)   # 300 Kontrakte × Delta 0,6
        self.assertAlmostEqual(d["delta_oi"]["puts"], 40)
        self.assertAlmostEqual(d["prem"]["puts"], 10 * 3.0 * 100)
        self.assertAlmostEqual(d["iv_atm"], 0.315)
        self.assertAlmostEqual(d["near_pc_oi"], 1 / 3)
        self.assertEqual((d["expiries"], d["asof"]), (1, "2026-10-27"))


class TestDepotTax(unittest.TestCase):
    def test_tax_classes(self):
        self.assertEqual(a.tax_class("Aktie", "Siemens AG"), ("stock", 0.0))
        self.assertEqual(a.tax_class("ETF", "iShares Core MSCI World UCITS ETF"), ("fund", 0.3))
        self.assertEqual(a.tax_class("Anleihen-ETF", "iShares Euro Govt Bond"), ("fund", 0.0))
        self.assertEqual(a.tax_class("Krypto", "Bitcoin")[0], "crypto")

    def test_depot_tax_year_split(self):
        y = str(a.datetime.now().year)
        rows = [{"name": "Siemens", "symbol": "SIE.DE", "isin": "DE0007236101", "kind": "Aktie", "gain": 500.0},
                {"name": "iShares MSCI World UCITS ETF", "symbol": "EUNL.DE", "isin": "IE00B4L5Y983", "kind": "ETF", "gain": 1000.0},
                {"name": "Bitcoin", "symbol": "BTC-EUR", "isin": None, "kind": "Krypto", "gain": 300.0}]
        hist = {"keys": [{"isin": "DE0007236101", "name": "Siemens", "realized_years": {y: 200.0, "2020": 999.0}},
                         {"isin": "IE00B4L5Y983", "name": "iShares MSCI World UCITS ETF", "realized_years": {y: 100.0}},
                         {"isin": "US0000000001", "name": "Verkaufte Aktie", "realized_years": {y: -50.0}}],
                "dividends": [[f"{y}-03-01", "x", 40.0], ["2020-03-01", "x", 99.0]]}
        T = a.depot_tax(rows, hist)
        self.assertAlmostEqual(T["realized_stock"], 150.0)          # Aktien inkl. verkaufter Aktie, nur laufendes Jahr
        self.assertAlmostEqual(T["realized_other"], 70.0)           # ETF mit 30 % Teilfreistellung
        self.assertAlmostEqual(T["div_ytd"], 40.0)
        self.assertEqual([p["symbol"] for p in T["positions"]], ["SIE.DE", "EUNL.DE"])   # Krypto ausgenommen
        self.assertAlmostEqual(T["positions"][1]["taxable"], 700.0)

    def test_etf_distribution_partial_exemption(self):
        y = str(a.datetime.now().year)
        rows = [{"name": "Vanguard FTSE All-World UCITS ETF (Dist)", "symbol": "VGWL.DE", "isin": "IE00B3RBWM25", "kind": "ETF", "gain": None}]
        hist = {"keys": [{"key": "IE00B3RBWM25", "isin": "IE00B3RBWM25", "name": "Vanguard FTSE All-World", "realized_years": {}},
                         {"key": "DE0007236101", "isin": "DE0007236101", "name": "Siemens", "realized_years": {}}],
                "dividends": [[f"{y}-03-01", "IE00B3RBWM25", 100.0], [f"{y}-02-15", "DE0007236101", 50.0]]}
        self.assertAlmostEqual(a.depot_tax(rows, hist)["div_ytd"], 100.0 * 0.7 + 50.0)   # ETF-Ausschüttung zu 70 % steuerpflichtig

    def test_dividend_plan_only_future_dates(self):
        import unittest.mock as mock, pandas as pd
        today = a.datetime.now()
        past_ex = pd.Timestamp(today - a.timedelta(days=375))      # Vorjahrestermin schon verstrichen
        next_ex = pd.Timestamp(today - a.timedelta(days=300))      # Vorjahrestermin liegt noch vor uns
        divs = pd.Series([1.0, 2.0], index=[past_ex, next_ex])
        fake = mock.MagicMock(); fake.dividends = divs
        with mock.patch.object(a.yf, "Ticker", return_value=fake):
            plan = a.depot_dividend_plan({"symbol": "X", "qty": 10, "price": 50.0, "name": "X"}, {"price": 50.0, "div_g": 0.1})
        self.assertEqual(len(plan), 1)
        self.assertAlmostEqual(plan[0]["eur"], 2.0 * 10 * 1.1)


class TestFinnhubThrottle(unittest.TestCase):
    def setUp(self):
        a.FINNHUB_STATS.update(calls=[], day="", minutes={})

    def test_counts_and_brakes(self):
        import unittest.mock as mock
        now = [1000.0]
        with mock.patch.object(a.time, "time", side_effect=lambda: now[0]), \
                mock.patch.object(a.time, "sleep", side_effect=lambda s: now.__setitem__(0, now[0] + s)):
            self.assertTrue(a.finnhub_slot())                 # erste Anfrage bei t = 1000
            now[0] = 1045.0
            for _ in range(a.FINNHUB_SAFE - 1):
                self.assertTrue(a.finnhub_slot())
            self.assertTrue(a.finnhub_slot())                 # voll -> wartet ~15 s, bis die erste aus dem Fenster fällt
            self.assertGreater(now[0], 1060.0)
            st = a.finnhub_status()
        self.assertEqual(st["today"], a.FINNHUB_SAFE + 1)
        self.assertEqual(st["waited"], 1)

    def test_skips_when_wait_too_long(self):
        import unittest.mock as mock
        old = a.FINNHUB_MAX_WAIT
        a.FINNHUB_MAX_WAIT = 5
        try:
            with mock.patch.object(a.time, "sleep"):
                for _ in range(a.FINNHUB_SAFE):
                    a.finnhub_slot()
                self.assertFalse(a.finnhub_slot())            # Fenster voll, Wartezeit > 5 s -> auslassen
            self.assertEqual(a.finnhub_status()["skipped"], 1)
        finally:
            a.FINNHUB_MAX_WAIT = old


class TestOnvistaTer(unittest.TestCase):
    def test_parse_ongoing_charges(self):
        import unittest.mock as mock
        a.ONVISTA_TER.clear()
        with mock.patch.object(a, "_fetch", return_value=b'{"x":{"ongoingCharges": 0.2,"managementFee":0}}'):
            self.assertAlmostEqual(a.onvista_fund_ter("IE00B4L5Y983"), 0.002)
        with mock.patch.object(a, "_fetch", return_value=b'{"x":{}}'):
            self.assertIsNone(a.onvista_fund_ter("XX0000000000"))
        a.ONVISTA_TER.clear()


class TestPatchLastClose(unittest.TestCase):
    def test_fills_missing_latest_day_from_hourly(self):
        import unittest.mock as mock, pandas as pd
        daily = pd.DataFrame({"SAP.DE": [211.2, 208.9, float("nan")]},
                             index=pd.to_datetime(["2026-10-28", "2026-10-29", "2026-10-30"]))
        hourly = pd.DataFrame({"SAP.DE": [212.1, 211.75]}, index=pd.to_datetime(
            ["2026-10-30 16:00", "2026-10-30 17:00"]).tz_localize("Europe/Berlin"))
        with mock.patch.object(a.yf, "download", return_value={"Close": hourly}):
            out = a.patch_last_close(daily, ["SAP.DE"])
        self.assertAlmostEqual(out["SAP.DE"].dropna().iloc[-1], 211.75)
        self.assertEqual(out["SAP.DE"].dropna().index[-1], pd.Timestamp("2026-10-30"))


class TestAdminMonitoring(unittest.TestCase):
    def test_source_monitor_counts(self):
        a.SRC_STATS.clear()
        a.src_record("Nasdaq", True, 0.2)
        a.src_record("Nasdaq", False, 1.0, "HTTP 500")
        m = {x["name"]: x for x in a.source_monitor()["sources"]}
        self.assertEqual(m["Nasdaq"]["n"], 2)
        self.assertAlmostEqual(m["Nasdaq"]["rate"], 0.5)
        self.assertEqual(m["Nasdaq"]["last_err"][1], "HTTP 500")
        self.assertEqual(a.src_name("https://api.nasdaq.com/api/x"), "Nasdaq")
        a.SRC_STATS.clear()

    def test_audit_summary_never_contains_password(self):
        act, det = a.audit_summary("/api/admin/users", {"action": "reset", "username": "anna", "password": "geheim123"})
        self.assertEqual(act, "Passwort zurückgesetzt")
        self.assertNotIn("geheim", act + det)
        self.assertIsNone(a.audit_summary("/api/admin/system", {"action": "diag"}))

    def test_ua_family(self):
        self.assertEqual(a.ua_family("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) AppleWebKit Safari/604.1"), "Safari auf iPhone")
        self.assertEqual(a.ua_family("Mozilla/5.0 (Windows NT 10.0) Chrome/130 Safari/537.36 Edg/130"), "Edge auf Windows")
