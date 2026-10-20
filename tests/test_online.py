"""Online-Tests mit echten Daten (Yahoo, Google News, CoinGecko). Nur mit RUN_ONLINE_TESTS=1:
    run_tests.bat online
Prüfen, dass die Datenquellen noch antworten und die Ergebnisse plausibel sind – z. B. nach einem Paket-Update.
"""
import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import aktien_check as a  # noqa: E402

a.LOG.setLevel("WARNING")
ONLINE = os.environ.get("RUN_ONLINE_TESTS") == "1"


def valid_json(obj):
    json.dumps(a.json_safe(obj), allow_nan=False)
    return True


@unittest.skipUnless(ONLINE, "Online-Tests nur mit RUN_ONLINE_TESTS=1")
class TestOnline(unittest.TestCase):
    def check_result(self, r):
        self.assertIn(r["rating"]["label"], [x[1] for x in a.RATING_SCALE])
        self.assertTrue(r["price"] and r["price"] > 0)
        for c in r["categories"]:
            self.assertIn(c["adjective"], a.ADJ[c["key"]] + ["nicht anwendbar"], c["key"])
        self.assertTrue(valid_json(r))

    def test_stock_full_data(self):
        a.CACHE.clear()
        r = a.analyze("SAP.DE")
        self.check_result(r)
        self.assertEqual(r["currency"], "EUR")
        self.assertGreater(r["news"]["count"], 5)
        self.assertGreaterEqual(len(r["competitors"]["peers"]), 3)

    def test_stock_server_mode(self):
        """Wie auf Render: Yahoo-Kennzahlen gesperrt -> Berechnung aus Geschäftsberichten."""
        os.environ["FORCE_FALLBACK"] = "1"
        try:
            a.CACHE.clear()
            r = a.analyze("ALV.DE")
            self.check_result(r)
            self.assertIsNotNone(r["facts"]["pe"])
        finally:
            os.environ.pop("FORCE_FALLBACK")
            a.CACHE.clear()

    def test_foreign_reporting_currency(self):
        """Bilanz in DKK, Kurs in USD: KGV muss plausibel sein (früherer Fehler: 1,5 statt ~9)."""
        import yfinance as yf
        t = yf.Ticker("NVO")
        fb = a.fill_info(t, {}, {"name": "Novo Nordisk"})
        real = num(t.info.get("trailingPE"))
        self.assertIsNotNone(fb.get("trailingPE"))
        if real:
            self.assertLess(abs(fb["trailingPE"] / real - 1), 0.5)

    def test_crypto(self):
        a.CACHE.clear()
        r = a.analyze("Bitcoin")
        self.check_result(r)
        self.assertEqual(r["asset"], "crypto")
        self.assertEqual(r["facts"]["rank"], 1)

    def test_chart_all_ranges(self):
        for rng in a.CHART_RANGES:
            d = a.chart_data("SAP.DE", rng)
            self.assertGreater(len(d["points"]), 5, rng)
            self.assertTrue(valid_json(d))


def num(x):
    return a.num(x)


if __name__ == "__main__":
    unittest.main(verbosity=2)
