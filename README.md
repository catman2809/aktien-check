# Aktien-Check

Lokales Tool, das jede beliebige Aktie auf **Kaufen / Halten / Verkaufen** prüft
(Strong Buy … Strong Sell, 14 Abstufungen) und für 8 Kategorien das zutreffendste Adjektiv wählt.

## Starten
Doppelklick auf **`Aktien-Check starten.bat`** – installiert beim ersten Mal `yfinance` und öffnet
http://localhost:8765 im Browser. Beenden: Fenster schließen oder Strg+C.

Alternativ: `python aktien_check.py` (Web-Oberfläche) oder `python aktien_check.py SAP.DE` (Kurzergebnis in der Konsole).

## Datenquellen
- **Tier 1–3 News** (30 Tage): Google-News-RSS + Yahoo-Finance-RSS, nach Quelle eingestuft
  (Tier 1 Reuters/CNBC/finanzen.net …, Tier 2 Bloomberg/FT/WSJ/Handelsblatt …, Tier 3 Business Wire/PR Newswire/Unternehmensseiten).
  Tier-3-Meldungen werden gegen Tier-1/2 abgeglichen („bestätigt“/„unbestätigt“).
- **Tier 4 Fundamentaldaten**: Yahoo Finance (Margen, FCF, Verschuldung, ROE/ROIC, Kapitalallokation,
  KGV historisch & Branche, Reverse-DCF, US-Zinsen, Wechselkurs zum Euro).

Keine Anlageberatung – regelbasiertes Modell, Gewichte und Schwellen stehen oben in `aktien_check.py`.
