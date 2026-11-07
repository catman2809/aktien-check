"""Englische Texte der Depot-Analyse (Startseite, Upload, Kennzahlen, Diagramme, Depot-Check)."""
DEPOT_EXACT = {
    "Depot-Analyse": "Portfolio analysis", "Mein Depot": "My portfolio", "Mein Depot analysieren": "Analyze my portfolio",
    "CSV-Export deines Depots hochladen: Aufteilung nach Positionen, Branchen, Ländern und Währungen, Rendite und Risiko, Dividenden und ein Depot-Check auf Klumpenrisiken.":
        "Upload your portfolio's CSV export: breakdown by positions, sectors, countries and currencies, return and risk, dividends and a portfolio check for concentration risks.",
    "Depot hochladen": "Upload portfolio", "CSV-Datei auswählen": "Choose CSV file",
    "CSV-Datei deines Depots hierher ziehen oder auswählen": "Drag your portfolio's CSV file here or choose it",
    "Neue Depot-Datei hochladen": "Upload a new portfolio file",
    "Export aus deinem Online-Depot (z. B. comdirect, Consorsbank, ING, DKB, flatex, Scalable, Trade Republic) oder eine eigene Tabelle mit den Spalten ISIN (oder Symbol/Name), Stück und optional Kaufkurs.":
        "Export from your online brokerage account (e.g. comdirect, Consorsbank, ING, DKB, flatex, Scalable, Trade Republic) or your own table with the columns ISIN (or symbol/name), quantity and optionally purchase price.",
    "Datei auswählen": "Choose file",
    "Vorlage herunterladen": "Download template", "Gespeichertes Depot löschen": "Delete saved portfolio",
    "Gespeichertes Depot wirklich löschen?": "Really delete the saved portfolio?",
    "Depot wird eingelesen und analysiert … (je nach Größe {0}–{1} Sekunden)": "Reading and analyzing the portfolio … ({0}–{1} seconds depending on size)",
    "Die Datei ist zu groß (höchstens {0} MB).": "The file is too large (max. {0} MB).",
    "Was die Depot-Analyse zeigt": "What the portfolio analysis shows",
    "Aufteilung nach Einzelpositionen, Branchen (mit Durchschau in ETFs), Ländern, Anlageklassen und Währungen":
        "Breakdown by individual positions, sectors (with look-through into ETFs), countries, asset classes and currencies",
    "Depotwert, Gewinn/Verlust je Position, erwartete Dividenden pro Jahr": "Portfolio value, gain/loss per position, expected dividends per year",
    "Rendite, Schwankung, größter Rückgang, Beta und Sharpe-Ratio der letzten {0} Monate im Vergleich zum MSCI World":
        "Return, volatility, maximum drawdown, beta and Sharpe ratio of the last {0} months compared with the MSCI World",
    "Depot-Check: Klumpenrisiken, Streuung, Heimatmarkt-Neigung, Währungsrisiko, ähnlich verlaufende Positionen":
        "Portfolio check: concentration risks, diversification, home bias, currency risk, positions that move alike",
    "Auf Wunsch die Einschätzung der App für jede Position": "On request, the app's rating for each position",
    "Die Datei wird nur auf dem Server ausgewertet. Gespeichert werden – wenn du es möchtest – nur Wertpapier, Stückzahl und Kaufkurs, verschlüsselt in deinem Konto.":
        "The file is only evaluated on the server. If you wish, only security, quantity and purchase price are stored – encrypted in your account.",
    "Nur die ersten {0} Positionen wurden übernommen.": "Only the first {0} positions were imported.",
    "Depotwert": "Portfolio value", "{0} Positionen": "{0} positions", "Gewinn/Verlust": "Gain/loss",
    "Kaufkurse fehlen in der Datei": "Purchase prices missing in the file", "{0} · für {1} des Depots": "{0} · for {1} of the portfolio",
    "Rendite {0} Monate": "Return {0} months", "MSCI World {0}": "MSCI World {0}", "Dividenden pro Jahr": "Dividends per year",
    "Rendite {0}": "Yield {0}", "Rendite {0} · auf Einstand {1}": "Yield {0} · on cost {1}",
    "Schwankung (Volatilität)": "Volatility", "pro Jahr": "per year", "Größter Rückgang": "Maximum drawdown",
    "vom Hoch, letzte {0} Monate": "from the high, last {0} months", "Beta zum MSCI World": "Beta vs. MSCI World",
    "schwankt stärker als der Markt": "moves more than the market", "schwankt weniger als der Markt": "moves less than the market",
    "etwa wie der Markt": "about like the market", "Sharpe-Ratio": "Sharpe ratio",
    "Rendite je Risikoeinheit (über {0} = gut)": "Return per unit of risk (above {0} = good)",
    "Top {0} / Top {1}": "Top {0} / Top {1}", "Anteil am Depot": "Share of portfolio",
    "Aufteilung": "Allocation", "Einzelpositionen": "Individual positions", "Anlageklassen": "Asset classes", "Währungen": "Currencies",
    "inkl. Durchschau in ETFs ({0} des Depots)": "incl. look-through into ETFs ({0} of the portfolio)",
    "Sitz der Unternehmen": "Company headquarters", "Heimatwährung der Unternehmen": "Companies' home currency",
    "Sonstige ({0})": "Other ({0})", "ETF (international)": "ETF (international)", "ETF (Währungsmix)": "ETF (currency mix)",
    "ETF (breit gestreut)": "ETF (broadly diversified)", "Krypto": "Crypto", "Aktie": "Stock", "Anleihen-ETF": "Bond ETF",
    "Nicht zugeordnet": "Not matched", "Unbekannt": "Unknown",
    "Depot-Check": "Portfolio check", "Ähnlich verlaufende Positionen": "Positions that move alike",
    "(Korrelation der Tagesrenditen, {0} Monate)": "(correlation of daily returns, {0} months)",
    "Durchschnittliche Korrelation der größeren Positionen: {0} (unter {1} = gute Streuung).":
        "Average correlation of the larger positions: {0} (below {1} = good diversification).",
    "Entwicklung der letzten {0} Monate": "Performance over the last {0} months", "indexiert auf {0}": "indexed to {0}",
    "Dein Depot (heutige Stückzahlen)": "Your portfolio (today's quantities)", "MSCI World (iShares Core, {0})": "MSCI World (iShares Core, {0})",
    "Depot {0}, MSCI World (iShares Core, {1}) {2} (Start = {3})": "Portfolio {0}, MSCI World (iShares Core, {1}) {2} (start = {3})",
    "Rückrechnung mit den heutigen Stückzahlen und Wechselkursen je Tag – zeigt, wie sich die aktuelle Zusammensetzung entwickelt hätte (ohne Käufe/Verkäufe, Dividenden nicht wieder angelegt).":
        "Back-calculation with today's quantities and daily exchange rates – shows how the current composition would have performed (no purchases/sales, dividends not reinvested).",
    "Positionen": "Positions", "Einschätzungen der App laden": "Load the app's ratings", "Einschätzungen aktualisieren": "Update ratings",
    "{0} von {1} bewertet": "{0} of {1} rated", "{0} von {1} bewertet …": "{0} of {1} rated …",
    "Analysiert jede Position einzeln (dauert etwa {0}–{1} Sekunden je Position).": "Analyzes each position individually (takes about {0}–{1} seconds per position).",
    "Kaufen {0}": "Buy {0}", "Halten {0}": "Hold {0}", "Verkaufen {0}": "Sell {0}",
    "nach Depotanteil der bewerteten Positionen": "by portfolio share of the rated positions",
    "Wertpapier": "Security", "Art": "Type", "Stück": "Qty", "Kurs €": "Price €", "Wert €": "Value €", "G/V": "Gain/loss",
    "{0} Monate": "{0} months", "Div.-Rendite": "Div. yield", "Land": "Country", "Einschätzung": "Rating",
    "fair {0}": "fair {0}", "nicht verfügbar": "not available",
    "Wert laut Datei – der gefundene Kurs passt nicht zur Stückzahl": "Value per file – the price found does not match the quantity",
    "Kurse und Wechselkurse von Yahoo Finance, Stand {0} {1}:{2}.": "Prices and exchange rates from Yahoo Finance, as of {0} {1}:{2}.",
    "Kurse und Wechselkurse von Yahoo Finance, Stand {0} {1}:{2}": "Prices and exchange rates from Yahoo Finance, as of {0} {1}:{2}",
    "Datei:": "File:", "· gespeichert am {0} {1}:{2}": "· saved on {0} {1}:{2}",
    "Kaufkurse werden in Euro angenommen, sofern die Datei keine andere Währung nennt.":
        "Purchase prices are assumed to be in euros unless the file states another currency.",
    "Die Datei ist leer.": "The file is empty.", "Bitte eine CSV-Datei hochladen.": "Please upload a CSV file.",
    "Keine Kopfzeile erkannt. Benötigt werden eine Spalte für das Wertpapier (ISIN, WKN, Symbol oder Name) und eine für die Stückzahl oder den Wert.":
        "No header row recognized. A column for the security (ISIN, WKN, symbol or name) and one for the quantity or value are required.",
    "Keine Positionen gefunden – bitte prüfe, ob die Datei Stückzahlen oder Werte enthält.":
        "No positions found – please check whether the file contains quantities or values.",
    "Keine der Positionen konnte einem Wertpapier mit aktuellem Kurs zugeordnet werden.":
        "None of the positions could be matched to a security with a current price.",
    "Klumpenrisiko Einzelaktie": "Single-stock concentration", "Keine übergroße Einzelaktie": "No oversized single stock",
    "Breite Streuung über ETFs": "Broad diversification via ETFs", "Geringe Streuung": "Low diversification",
    "Mittlere Streuung": "Medium diversification", "Gute Streuung": "Good diversification", "Branchen-Klumpen": "Sector concentration",
    "Branchen gemischt": "Sectors mixed", "Länderschwerpunkt": "Country focus", "Heimatmarkt-Neigung": "Home bias",
    "Währungsrisiko": "Currency risk", "Hoher Krypto-Anteil": "High crypto share", "Viele Kleinstpositionen": "Many tiny positions",
    "Größere Verlustpositionen": "Larger losing positions", "Hohe Schwankung": "High volatility", "Ruhiges Depot": "Calm portfolio",
    "Ähnliche Positionen": "Similar positions", "Dividendenstark": "High dividends",
    "Keine Aktie macht mehr als {0} des Depots aus.": "No stock makes up more than {0} of the portfolio.",
    "{0} des Depots liegen in ETFs – jeder ETF enthält viele Einzelwerte.": "{0} of the portfolio is in ETFs – each ETF holds many individual securities.",
    "Der Einzelaktien-Teil entspricht rechnerisch nur {0} gleich großen Positionen (Herfindahl-Index). Ab etwa {1}–{2} Einzelaktien aus verschiedenen Branchen sinkt das Einzelrisiko deutlich.":
        "The single-stock part is mathematically equivalent to only {0} equally sized positions (Herfindahl index). From about {1}–{2} individual stocks across sectors, single-stock risk drops markedly.",
    "Der Einzelaktien-Teil entspricht rechnerisch nur {0} gleich großen Positionen (Herfindahl-Index). Ab etwa {1}–{2} Einzelaktien aus verschiedenen Branchen sinkt das Einzelrisiko deutlich. ({3} des Depots liegen zusätzlich in breit gestreuten ETFs.)":
        "The single-stock part is mathematically equivalent to only {0} equally sized positions (Herfindahl index). From about {1}–{2} individual stocks across sectors, single-stock risk drops markedly. ({3} of the portfolio is additionally in broadly diversified ETFs.)",
    "Der Einzelaktien-Teil entspricht rechnerisch {0} gleich großen Positionen – ausreichend, wenn die Branchen gemischt sind.":
        "The single-stock part is mathematically equivalent to {0} equally sized positions – sufficient if the sectors are mixed.",
    "Der Einzelaktien-Teil entspricht rechnerisch {0} gleich großen Positionen – ausreichend, wenn die Branchen gemischt sind. ({1} des Depots liegen zusätzlich in breit gestreuten ETFs.)":
        "The single-stock part is mathematically equivalent to {0} equally sized positions – sufficient if the sectors are mixed. ({1} of the portfolio is additionally in broadly diversified ETFs.)",
    "Der Einzelaktien-Teil entspricht rechnerisch {0} gleich großen Positionen.": "The single-stock part is mathematically equivalent to {0} equally sized positions.",
    "Der Einzelaktien-Teil entspricht rechnerisch {0} gleich großen Positionen. ({1} des Depots liegen zusätzlich in breit gestreuten ETFs.)":
        "The single-stock part is mathematically equivalent to {0} equally sized positions. ({1} of the portfolio is additionally in broadly diversified ETFs.)",
    "{0} in deutschen Aktien – Deutschland macht nur rund {1} der weltweiten Börsenwerte aus („Home Bias“).":
        "{0} in German stocks – Germany accounts for only about {1} of global market capitalization (“home bias”).",
    "{0} des Depots in Aktien mit Heimatwährung außerhalb des Euro – Wechselkurse beeinflussen die Rendite spürbar (in beide Richtungen).":
        "{0} of the portfolio is in stocks whose home currency is not the euro – exchange rates noticeably affect returns (in both directions).",
    "{0} in Kryptowährungen – sehr schwankungsanfällig (Rückgänge von {1} und mehr kamen vor).":
        "{0} in cryptocurrencies – very volatile (declines of {1} and more have occurred).",
    "{0} Positionen unter {1} des Depots – sie beeinflussen das Ergebnis kaum, kosten aber Aufmerksamkeit und Gebühren.":
        "{0} positions below {1} of the portfolio – they barely affect the result but cost attention and fees.",
    "Volatilität {0} pro Jahr – deutlich über einem breiten Weltaktien-ETF ({1}).": "Volatility {0} per year – well above a broad global equity ETF ({1}).",
    "Volatilität {0} pro Jahr.": "Volatility {0} per year.",
    "Dividendenrendite {0} – auf Dividendensicherheit und Branchenmix achten.": "Dividend yield {0} – watch dividend safety and sector mix.",
}
DEPOT_WILD = [
    ("Nicht zugeordnet (fehlen in der Auswertung): {*}", "Not matched (missing from the analysis): {*}"),
    ("Über {0} des Depots in einer Aktie: {*}. Ein Kurseinbruch dieser Firma trifft das ganze Depot spürbar.",
     "More than {0} of the portfolio in a single stock: {*}. A price slump at this company would hit the whole portfolio noticeably."),
    ("{*} macht {0} des Depots aus (inkl. Durchschau in ETFs). Branchenkrisen schlagen dann voll durch.",
     "{*} makes up {0} of the portfolio (incl. look-through into ETFs). Sector crises then hit with full force."),
    ("{*} macht {0} des Depots aus. Branchenkrisen schlagen dann voll durch.",
     "{*} makes up {0} of the portfolio. Sector crises then hit with full force."),
    ("Größte Branche: {*} mit {0}.", "Largest sector: {*} with {0}."),
    ("{0} des Depots in Aktien aus {*}.", "{0} of the portfolio in stocks from {*}."),
    ("Mehr als {0} im Minus: {*}. Prüfen, ob die ursprüngliche Kaufidee noch gilt.",
     "More than {0} down: {*}. Check whether the original investment case still holds."),
    ("{*} und {*1} bewegen sich fast gleich (Korrelation {0}) – sie streuen das Risiko kaum.",
     "{*} and {*1} move almost identically (correlation {0}) – they barely spread the risk."),
    ("Einzelpositionen: {*}", "Individual positions: {*}"), ("Branchen: {*}", "Sectors: {*}"), ("Länder: {*}", "Countries: {*}"),
    ("Anlageklassen: {*}", "Asset classes: {*}"), ("Währungen: {*}", "Currencies: {*}"),
    ("Umsatzliste erkannt: {0} Käufe und {1} Verkäufe verrechnet, {2} andere Buchungen (z. B. Dividenden, Gebühren, Ein- und Auszahlungen) nicht berücksichtigt.",
     "Transaction list detected: {0} purchases and {1} sales netted, {2} other bookings (e.g. dividends, fees, deposits and withdrawals) ignored."),
]
DEPOT_WILD += [
    ("Aktiensplits berücksichtigt (Käufe/Verkäufe vor dem Split in heutige Stück umgerechnet): {*}.",
     "Stock splits taken into account (purchases/sales before the split converted into today's shares): {*}."),
    ("Mehr Verkäufe als Käufe in der Datei – nicht angezeigt: {*}. Vermutlich fehlen ältere Käufe im Export; bitte den Zeitraum ab Depoteröffnung exportieren.",
     "More sales than purchases in the file – not shown: {*}. Older purchases are probably missing from the export; please export the period since the account was opened."),
]
DEPOT_WILD += [("Ohne Kursdaten, daher nicht in der {0}-Monats-Rendite: {*}",
                "No price data, therefore not included in the {0}-month return: {*}")]
DEPOT_EXACT.update({
    "Gewinn/Verlust gesamt": "Total gain/loss", "Dein Depot (tatsächlich, zeitgewichtet)": "Your portfolio (actual, time-weighted)",
    "Tatsächliche Entwicklung mit allen Käufen und Verkäufen laut Umsatzliste, zeitgewichtet (Ein- und Auszahlungen verzerren die Rendite nicht); ausgezahlte Dividenden und Ordergebühren sind eingerechnet, Steuern nicht.":
        "Actual performance with all purchases and sales from the transaction list, time-weighted (deposits and withdrawals do not distort the return); dividends paid out and order fees are included, taxes are not.",
    "Rückrechnung mit den heutigen Stückzahlen – zeigt, wie sich die aktuelle Zusammensetzung entwickelt hätte (ohne Käufe/Verkäufe, Dividenden wieder angelegt). Mit einer Umsatzliste zeigt die App die tatsächliche Entwicklung.":
        "Back-calculation with today's quantities – shows how the current composition would have performed (no purchases/sales, dividends reinvested). With a transaction list the app shows the actual performance.",
    "offen {0} € ({1})": "unrealized {0} € ({1})", "realisiert {0} € · Dividenden {1} €": "realized {0} € · dividends {1} €",
    "realisiert {0} € · Dividenden {1} € · offen für {2} des Depots": "realized {0} € · dividends {1} € · unrealized for {2} of the portfolio", "realisiert {0} €": "realized {0} €", "Dividenden {0} €": "dividends {0} €",
    "zeitgewichtet": "time-weighted", "heutige Zusammensetzung": "current composition",
    "offen für {0} des Depots": "unrealized for {0} of the portfolio", "{0} (nicht realisiert)": "{0} (unrealized)",
    "Depot wird eingelesen und analysiert …": "Reading and analyzing the portfolio …",
    "Alle übrigen Positionen anzeigen": "Show all remaining positions",
    "{0} Positionen wurden vollständig verkauft und sind nicht mehr im Depot.": "{0} positions were sold completely and are no longer in the portfolio.",
    "{0} stornierte oder abgelehnte Aufträge übersprungen.": "{0} cancelled or rejected orders skipped.",
    "Bei {0} Positionen enthält die Datei mehr Verkäufe als Käufe – vermutlich fehlen ältere Käufe im Export. Diese Positionen werden nicht angezeigt; bitte den Zeitraum ab Depoteröffnung exportieren.":
        "For {0} positions the file contains more sales than purchases – older purchases are probably missing from the export. These positions are not shown; please export the period since the account was opened.",
    "{0} Aktiensplits in der Datei – die Stückzahl der betroffenen Positionen kann abweichen.": "{0} stock splits in the file – the quantity of the affected positions may differ.",
    "Nach Verrechnung aller Käufe und Verkäufe ist kein Bestand übrig.": "After netting all purchases and sales, no holdings remain.",
    "Auch Umsatzlisten mit Käufen und Verkäufen werden verrechnet – dann bitte den gesamten Zeitraum ab Depoteröffnung exportieren.":
        "Transaction lists with purchases and sales are netted too – in that case please export the entire period since the account was opened.",
})
DEPOT_EXACT.update({
    "Die Antwort des Servers war unvollständig. Bitte erneut versuchen.": "The server's response was incomplete. Please try again.",
    "Die Analyse dauert ungewöhnlich lange. Bitte später erneut öffnen.": "The analysis is taking unusually long. Please open it again later.",
    "Die Analyse wurde nicht gefunden. Bitte die Datei erneut hochladen.": "The analysis was not found. Please upload the file again.",
    "Die Depotanalyse ist fehlgeschlagen. Bitte in einigen Minuten erneut versuchen.": "The portfolio analysis failed. Please try again in a few minutes.",
})
DEPOT_WILD += [("Der Server ist gerade nicht erreichbar (Fehler {0}). Bitte in einer Minute erneut versuchen.",
                "The server is currently unavailable (error {0}). Please try again in a minute.")]
DEPOT_EXACT.update({
    "Gebühren {0} € (eingerechnet)": "fees {0} € (included)",
    "Steuern {0} € (nicht abgezogen)": "taxes {0} € (not deducted)",
})
DEPOT_WILD += [("Ordergebühren von {0} € sind in Einstand und Verkaufserlöse eingerechnet.",
                "Order fees of {0} € are included in the cost basis and sale proceeds.")]
DEPOT_EXACT.update({
    "Optionsdaten werden nachgeladen …": "Loading options data …",
    "Die Optionsdaten konnten gerade nicht geladen werden. Bitte die Analyse später erneut öffnen.":
        "The options data could not be loaded right now. Please open the analysis again later.",
})
DEPOT_EXACT.update({
    "Long / Short": "Long / short", "Long": "Long", "Short": "Short",
    "Offene Positionen": "Open positions", "Delta-gewichtet": "Delta-weighted",
    "Offene Kontrakte über alle Verfallstermine": "Open contracts across all expiries",
    "Heute gehandelte Kontrakte": "Contracts traded today",
    "Heute gehandelter Wert (Prämien)": "Value traded today (premiums)",
    "Offene Kontrakte gewichtet mit ihrem Delta – entspricht der Zahl der Aktien, auf die sie wirken":
        "Open contracts weighted by their delta – equals the number of shares they act on",
    "für 30 Tage": "for 30 days",
})
DEPOT_EXACT.update({"Gehandelter Wert": "Value traded", "{0} Aktien (Gegenwert)": "{0} share equivalents"})
DEPOT_EXACT.update({
    "Top & Flop heute": "Top & flop today", "Größte Gewinner": "Top gainers", "Größte Verlierer": "Top losers",
    "Kurse werden geladen …": "Loading prices …", "Die Kurse konnten gerade nicht geladen werden.": "Prices could not be loaded right now.",
    "Keine Daten": "No data", "Handelstag {0}": "Trading day {0}",
    "{0} im Plus, {1} im Minus": "{0} up, {1} down", "Stand {0}:{1} Uhr, ca. {2} Min. verzögert": "as of {0}:{1}, delayed approx. {2} min",
})
DEPOT_EXACT.update({"Top & Flop seit Monatsbeginn": "Top & flop month to date", "Heute": "Today", "Monat": "Month",
                    "seit Monatsbeginn: {0} bis {1}": "month to date: {0} to {1}"})
DEPOT_EXACT.update({"Top & Flop seit Jahresbeginn": "Top & flop year to date", "Jahr": "Year",
                    "seit Jahresbeginn: {0} bis {1}": "year to date: {0} to {1}"})
DEPOT_EXACT.update({"Lädt": "Loading"})
DEPOT_EXACT.update({"Passwort anzeigen": "Show password", "Passwort verbergen": "Hide password"})
DEPOT_EXACT.update({
    "Prognose": "Forecast", " (Prognose)": " (forecast)", "Reinertrag ohne Prognose": "Net income without forecast",
    "e = erwartet.": "e = expected.", "Fortschreibung des Trends, keine Analystenschätzung": "Trend extrapolation, no analyst estimate",
    "Reinertrag aus dem erwarteten Gewinn je Aktie berechnet.": "Net income calculated from expected earnings per share.",
})
DEPOT_WILD += [
    ("{*}: Analystenkonsens (Yahoo Finance).", "{*}: analyst consensus (Yahoo Finance)."),
    ("{*}: eigene Fortschreibung des Trends, dafür gibt es keine Analystenschätzung.", "{*}: own trend extrapolation, there is no analyst estimate for it."),
    ("Prognose · Konsens von {0} Analysten (Gewinn: {1})", "Forecast · consensus of {0} analysts (earnings: {1})"),
    ("Prognose · Konsens von {0} Analysten", "Forecast · consensus of {0} analysts"),
]
DEPOT_EXACT.update({
    "(abgeleitet)": "(derived)",
    "Operatives Ergebnis abgeleitet: erwartete Nettomarge plus die übliche Differenz zur operativen Marge (Median der letzten Perioden).":
        "Operating income derived: expected net margin plus the usual gap to the operating margin (median of recent periods).",
})
DEPOT_EXACT.update({
    "Free Cashflow abgeleitet: erwarteter Reinertrag mal übliche Cash-Umwandlung (Free Cashflow je Euro Gewinn, halb Median der letzten Perioden, halb jüngste Periode).":
        "Free cash flow derived: expected net income times the usual cash conversion (free cash flow per unit of profit, half median of recent periods, half latest period).",
})
DEPOT_WILD += [("Free Cashflow: {*}", "Free cash flow: {*}"), ("· FCF {*}", "· FCF {*}")]
DEPOT_EXACT.update({
    "e = erwartet (heller).": "e = expected (lighter).",
    "Prognose abgeleitet: Dividendenwachstum der letzten 5 Jahre, höchstens so stark wie das erwartete Gewinnwachstum, keine Kürzung angenommen.":
        "Forecast derived: dividend growth of the last 5 years, at most as strong as expected earnings growth, no cut assumed.",
})
DEPOT_WILD += [
    ("{*}: {0} {*1} (alle Zahlungen des Jahres erfolgt)", "{*}: {0} {*1} (all payments for the year made)"),
    ("{*}: {0} {*1} (Prognose, +{1} %, davon bereits gezahlt {2})", "{*}: {0} {*1} (forecast, +{1}%, of which already paid {2})"),
    ("{*}: {0} {*1} (Prognose, +{1} %)", "{*}: {0} {*1} (forecast, +{1}%)"),
]
DEPOT_EXACT.update({
    "KGV-Prognose": "P/E forecast", "KGV-Prognose = heutiger Kurs / erwarteter Gewinn je Aktie.": "P/E forecast = today's price / expected earnings per share.",
    "Bleibt der Kurs gleich und tritt der Gewinn ein, sinkt das KGV entsprechend.": "If the price stays the same and the earnings materialise, the P/E falls accordingly.",
})
DEPOT_WILD += [
    ("{*}: Analystenkonsens.", "{*}: analyst consensus."),
    ("{*}: Gewinnwachstum fortgeschrieben, keine Analystenschätzung.", "{*}: earnings growth extrapolated, no analyst estimate."),
    ("KGV {*}: {0} (Analystenkonsens)", "P/E {*}: {0} (analyst consensus)"),
    ("KGV {*}: {0} (Fortschreibung)", "P/E {*}: {0} (extrapolation)"),
]
DEPOT_EXACT.update({
    "Kennzahlen je Geschäftsjahr": "Key figures per fiscal year", "Bruttoergebnis": "Gross income", "Bruttomarge": "Gross margin",
    "EBIT-Marge": "EBIT margin", "e = erwartet: Umsatz und Reinertrag aus dem Analystenkonsens.": "e = expected: revenue and net income from the analyst consensus.",
    "* abgeleitet: Bruttomarge als Median der letzten Jahre, EBIT aus der erwarteten Nettomarge plus der üblichen Differenz.":
        "* derived: gross margin as the median of recent years, EBIT from the expected net margin plus the usual gap.",
})
DEPOT_EXACT.update({"abgelaufen": "ended", "laufend": "current", "nächstes GJ": "next FY",
    "* abgeleitet bzw. fortgeschrieben: Bruttomarge als Median der letzten Jahre, EBIT aus der erwarteten Nettomarge plus der üblichen Differenz.":
        "* derived or extrapolated: gross margin as the median of recent years, EBIT from the expected net margin plus the usual gap."})
DEPOT_WILD += [
    ("{*}: Umsatz und Reinertrag aus dem Analystenkonsens (Yahoo Finance).", "{*}: revenue and net income from the analyst consensus (Yahoo Finance)."),
    ("{*}: Reinertrag aus dem Konsens für den Gewinn je Aktie (Nasdaq, Daten von Zacks, {0} Analysten), Umsatz fortgeschrieben.",
     "{*}: net income from the EPS consensus (Nasdaq, data from Zacks, {0} analysts), revenue extrapolated."),
    ("{*}: Umsatz und Reinertrag fortgeschrieben, dafür gibt es keine frei verfügbare Analystenschätzung.",
     "{*}: revenue and net income extrapolated, no freely available analyst estimate exists for it."),
]
DEPOT_WILD += [("Umsatz fortgeschrieben · Reinertrag aus dem Nasdaq-Konsens ({0} Analysten)", "Revenue extrapolated · net income from the Nasdaq consensus ({0} analysts)")]
DEPOT_WILD += [
    ("{*}: Reinertrag aus dem Konsens für den Gewinn je Aktie (Nasdaq, Daten von Zacks), Umsatz mit dem Wachstum der letzten Jahre fortgeschrieben.",
     "{*}: net income from the EPS consensus (Nasdaq, data from Zacks), revenue extrapolated with the growth of recent years."),
    ("Umsatz fortgeschrieben · Reinertrag aus dem Nasdaq-Konsens ({0} Analysten)", "Revenue extrapolated · net income from the Nasdaq consensus ({0} analysts)"),
]
DEPOT_WILD += [("{0} gegenüber Vorjahr", "{0} vs. prior year")]
DEPOT_WILD += [
    ("{*}: Umsatz fortgeschrieben, {*1}.", "{*}: revenue extrapolated, {*1}."),
    ("{*}: Umsatz aus dem Analystenkonsens (Yahoo Finance), {*1}.", "{*}: revenue from the analyst consensus (Yahoo Finance), {*1}."),
]
DEPOT_EXACT.update({
    "Reinertrag aus dem Konsens für den Gewinn je Aktie (Nasdaq, Daten von Zacks)": "net income from the EPS consensus (Nasdaq, data from Zacks)",
    "Reinertrag fortgeschrieben": "net income extrapolated", "Reinertrag aus dem Analystenkonsens (Yahoo Finance)": "net income from the analyst consensus (Yahoo Finance)",
    "kein Reinertrag (Margen zu schwankend)": "no net income (margins too volatile)",
})
DEPOT_WILD += [
    ("Prognose: Analystenkonsens ({*}).", "Forecast: analyst consensus ({*})."),
    ("Reinertrag aus dem Konsens für den Gewinn je Aktie ({*})", "net income from the EPS consensus ({*})"),
    ("Umsatz fortgeschrieben · Reinertrag aus dem {*}-Konsens ({0} Analysten)", "Revenue extrapolated · net income from the {*} consensus ({0} analysts)"),
    ("Umsatz fortgeschrieben · Reinertrag aus dem {*}-Konsens", "Revenue extrapolated · net income from the {*} consensus"),
    ("{*}: {0} {*1} (Konsens {*2}, {1} %)", "{*}: {0} {*1} (consensus {*2}, {1}%)"),
    ("{*}: {0} {*1} (Konsens {*2}, {1} %, davon bereits gezahlt {2})", "{*}: {0} {*1} (consensus {*2}, {1}%, of which already paid {2})"),
    ("{*}: {0} {*1} (Prognose, {1} %, davon bereits gezahlt {2})", "{*}: {0} {*1} (forecast, {1}%, of which already paid {2})"),
    ("{*}: {0} {*1} (Prognose, {1} %)", "{*}: {0} {*1} (forecast, {1}%)"),
]
DEPOT_EXACT.update({
    "Hinweis: Analysten schätzen den bereinigten Gewinn (ohne Sondereffekte wie Abschreibungen, Rechtsfälle oder Umbaukosten). Ein starker Anstieg gegenüber dem berichteten Reinertrag des Vorjahres kann daher teils aus Sonderbelastungen im Vorjahr stammen.":
        "Note: analysts estimate adjusted earnings (excluding one-offs such as write-downs, legal cases or restructuring costs). A sharp rise versus the prior year's reported net income may therefore partly reflect one-off charges in the prior year.",
})
# Mein Bereich
DEPOT_EXACT.update({
    "Mein Bereich": "My area", "Hallo": "Hello", "Guten Morgen": "Good morning", "Guten Abend": "Good evening",
    "Übersicht": "Overview", "Einstellungen": "Settings", "Konto": "Account", "Watchlist heute": "Watchlist today",
    "Öffnen": "Open", "Hochladen": "Upload", "Verwalten": "Manage", "Details": "Details", "Depot": "Portfolio",
    "Nächste Termine": "Upcoming events", "Alarme": "Alerts", "Abo": "Subscription", "Schnellzugriff": "Quick access",
    "☆ Watchlist": "☆ Watchlist", "Trefferquote & Verlauf": "Hit rate & history", "Glossar": "Glossary",
    "Lade deine Übersicht …": "Loading your overview …", "Übersicht nicht verfügbar": "Overview not available",
    "Noch leer. Öffne eine Aktie und tippe auf ☆, um sie zu beobachten.": "Still empty. Open a stock and tap ☆ to watch it.",
    "Noch kein Depot gespeichert. Lade die Depotübersicht oder Umsatzliste deiner Bank als CSV hoch.":
        "No portfolio saved yet. Upload your bank's portfolio overview or transaction list as CSV.",
    "Gewinn/Verlust (offen)": "Gain/loss (unrealised)", "Rendite 12 Monate": "12-month return",
    "Öffne das Depot, um Wert und Rendite neu zu berechnen.": "Open the portfolio to recalculate value and return.",
    "Keine Termine der Watchlist in den nächsten 60 Tagen bekannt. Termine erscheinen, sobald du die Aktien einmal analysiert hast.":
        "No watchlist events known for the next 60 days. Events appear once you have analysed the stocks.",
    "Alarm aktiv": "alert active", "Alarme aktiv": "alerts active", "Zuletzt wurde kein Alarm ausgelöst.": "No alert has fired recently.",
    "Darstellung": "Appearance", "Sprache": "Language", "Design": "Theme", "Automatisch (wie Gerät)": "Automatic (like device)",
    "Hell": "Light", "Dunkel": "Dark", "Startseite": "Start page", "Top & Flop für": "Top & flop for", "Zeitraum": "Period",
    "Seit Monatsbeginn": "Month to date", "Seit Jahresbeginn": "Year to date", "Push-Benachrichtigungen": "Push notifications",
    "Dein persönliches ntfy-Thema. In der ntfy-App abonnieren, dann kommen Alarme aufs Handy.":
        "Your personal ntfy topic. Subscribe to it in the ntfy app to get alerts on your phone.",
    "Änderungen werden sofort in deinem Konto gespeichert und gelten auf allen Geräten.":
        "Changes are saved to your account right away and apply on all your devices.",
    "Gespeichert – gilt auf allen deinen Geräten.": "Saved – applies on all your devices.",
    "Kontodaten werden geladen …": "Loading account data …",
})
DEPOT_WILD += [
    ("{0} Aktie · {1} im Plus · {2} im Minus", "{0} stock · {1} up · {2} down"),
    ("{0} Aktien · {1} im Plus · {2} im Minus", "{0} stocks · {1} up · {2} down"),
    ("{0} Positionen", "{0} positions"), ("Stand der Auswertung: {*}", "Analysed: {*}"),
    ("Positionen gespeichert · {*}", "positions saved · {*}"), ("{0} € pro Monat", "€{0} per month"),
]
DEPOT_EXACT.update({
    "Jede Kategorie erhält einen Teilscore von {0} bis {1} aus mehreren Kennzahlen (50 = neutral); daraus folgt das passende Adjektiv.":
        "Each category gets a sub-score from {0} to {1} from several figures (50 = neutral); the fitting adjective follows from it.",
})
DEPOT_EXACT.update({
    "Umsatz aus dem Gewinnkonsens abgeleitet": "revenue derived from the earnings consensus",
    "Umsatz aus dem Gewinnkonsens abgeleitet: Für den Umsatz gibt es keine frei verfügbare Analystenschätzung. Wächst der erwartete Gewinn deutlich stärker als der fortgeschriebene Umsatz, wird der Umsatz angehoben – zu drei Vierteln bis zu dem Wert, bei dem die Nettomarge 10 % über der besten Marge der letzten fünf Jahre läge.":
        "Revenue derived from the earnings consensus: no freely available analyst estimate exists for revenue. If expected earnings grow much faster than extrapolated revenue, revenue is raised – three quarters of the way to the level at which the net margin would be 10 % above the best margin of the last five years.",
})
DEPOT_WILD += [("Umsatz aus dem Gewinn abgeleitet · Reinertrag aus dem {*}-Konsens", "Revenue derived from earnings · net income from the {*} consensus"),
               ("{*}: Umsatz aus dem Gewinnkonsens abgeleitet, {*1}.", "{*}: revenue derived from the earnings consensus, {*1}.")]
DEPOT_EXACT.update({
    "Aus Vorjahresquartal und Jahresprognose abgeleitet": "Derived from the prior-year quarter and the annual forecast",
    "Umsatz aus Vorjahresquartal und Jahresprognose abgeleitet": "revenue derived from the prior-year quarter and the annual forecast",
    "Reinertrag aus Quartalsumsatz und erwarteter Jahresmarge abgeleitet": "net income derived from quarterly revenue and the expected annual margin",
})
DEPOT_WILD += [("{*}: Umsatz aus Vorjahresquartal und Jahresprognose abgeleitet, {*1}.", "{*}: revenue derived from the prior-year quarter and the annual forecast, {*1}."),
               ("Aus Vorjahresquartal und Jahresprognose abgeleitet · Reinertrag aus dem {*}-Konsens", "Derived from the prior-year quarter and the annual forecast · net income from the {*} consensus")]
DEPOT_EXACT.update({
    "Free Cashflow abgeleitet: erwarteter Umsatz mal übliche Free-Cashflow-Marge (halb Median der letzten Perioden, halb jüngste Periode).":
        "Free cash flow derived: expected revenue times the usual free cash flow margin (half median of recent periods, half latest period).",
})
DEPOT_EXACT.update({
    "Free Cashflow abgeleitet: halb erwarteter Reinertrag mal übliche Cash-Umwandlung der letzten vier Quartale, halb Free-Cashflow-Marge desselben Quartals im Vorjahr (Saisonalität).":
        "Free cash flow derived: half expected net income times the usual cash conversion of the last four quarters, half the free cash flow margin of the same quarter a year earlier (seasonality).",
})
DEPOT_EXACT.update({
    "Prognose: Forward-KGV": "Forecast: forward P/E", "neg.": "neg.", "Verlust – kein KGV": "Loss – no P/E",
    "KGV: gemeldete Jahre = Kurs am Geschäftsjahresende ÷ Gewinn je Aktie; Prognosejahre = heutiger Kurs ÷ erwarteter Gewinn je Aktie (Forward-KGV).":
        "P/E: reported years = price at fiscal year end ÷ earnings per share; forecast years = today's price ÷ expected earnings per share (forward P/E).",
})
# Depot: Bewertung, Dividenden-Ausblick, Steuern, Kosten
DEPOT_EXACT.update({
    "Bewertung der Positionen": "Rating of holdings", "Depot-Score": "Portfolio score", "KGV (gewichtet)": "P/E (weighted)",
    "Forward-KGV (gewichtet)": "Forward P/E (weighted)", "Erwartetes Gewinnwachstum": "Expected earnings growth",
    "auf den erwarteten Gewinn": "on expected earnings", "nächstes Geschäftsjahr, gewichtet": "next fiscal year, weighted",
    "keine Aktien mit Gewinn": "no profitable stocks", "Score": "Score", "Potenzial": "Upside",
    "zum Kursziel der Analysten": "to the analysts' price target", "zum fairen Wert": "to fair value",
    "Dividenden-Ausblick": "Dividend outlook", "Erwartet in den nächsten 12 Monaten": "Expected in the next 12 months",
    "Ex-Tag": "Ex-date", "Wertpapier": "Security", "Betrag": "Amount", "geschätzt": "estimated", "bestätigt": "confirmed",
    "Keine Dividendenzahlungen in den nächsten 12 Monaten erwartet.": "No dividend payments expected in the next 12 months.",
    "Vor Steuern. Geschätzt aus den Zahlungen der letzten 12 Monate, hochgerechnet mit Stockys Dividendenprognose; bestätigte Ex-Tage ersetzen die Schätzung. Ausschüttende ETFs eingeschlossen, thesaurierende zahlen nichts aus.":
        "Before tax. Estimated from the payments of the last 12 months, scaled with Stocky's dividend forecast; confirmed ex-dates replace the estimate. Distributing ETFs included, accumulating ones pay nothing.",
    "Sparerpauschbetrag": "Saver's allowance", "1.000 € (einzeln)": "€1,000 (single)", "2.000 € (gemeinsam veranlagt)": "€2,000 (joint)",
    "Noch frei": "Still available", "Aktienverlusttopf (nur mit Aktiengewinnen verrechenbar)": "Stock loss pot (offsettable against stock gains only)",
    "Steuer, wenn du heute alles verkaufst (offene Gewinne, nach Freibetrag)": "Tax if you sold everything today (unrealised gains, after allowance)",
    "Positionen im Minus": "Holdings at a loss", "Aktie": "Stock",
    "– ein Verkauf würde den Verlust steuerlich nutzbar machen (Aktienverluste nur gegen Aktiengewinne)": "– selling would make the loss usable for tax (stock losses only against stock gains)",
    "Für den Verbrauch des Freibetrags im laufenden Jahr bitte eine Umsatzliste (Käufe, Verkäufe, Dividenden) hochladen.":
        "To see how much of the allowance is used this year, please upload a transaction list (buys, sells, dividends).",
    "Kosten": "Costs", "Laufende Fondskosten": "Ongoing fund costs", "Ordergebühren": "Order fees", "laut Umsatzliste, seit Beginn": "per transaction list, since start",
    "Wert": "Value", "TER": "TER", "Kosten / Jahr": "Cost / year",
    "teuer – breite Index-ETFs gibt es oft für 0,1–0,2 %": "expensive – broad index ETFs are often available for 0.1–0.2 %",
    "TER = jährliche Gesamtkostenquote, wird automatisch aus dem Fondsvermögen entnommen (steckt also schon in der Wertentwicklung).":
        "TER = total expense ratio per year, deducted automatically from fund assets (already included in performance).",
})
DEPOT_WILD += [
    ("Steuern {0}", "Taxes {0}"), ("{*} € im Monatsschnitt", "{*} € per month on average"),
    ("{0} bis 100 · gewichtet nach Wert{*}", "{0} to 100 · weighted by value{*}"),
    ("Aktien mit Gewinn, {*} des Depots", "profitable stocks, {*} of portfolio"),
    ("Ø TER {*} der ETFs", "avg. TER {*} of ETFs"), ("{*} € / Jahr", "{*} € / year"),
    ("Noch frei", "Still available"),
    ("{*} wird berechnet – jede Position wird mit Stockys Aktienanalyse bewertet{*1}. Das dauert beim ersten Mal 1–2 Minuten.",
     "{*} is being calculated – every holding is rated with Stocky's stock analysis{*1}. The first time takes 1–2 minutes."),
]
# Admin: Finnhub-Kontingent
DEPOT_EXACT.update({
    "Finnhub-Kontingent": "Finnhub quota", "Kein Finnhub-Schlüssel hinterlegt.": "No Finnhub key configured.",
    "Anfragen heute": "Requests today", "Höchstwert je Minute (letzte Stunde)": "Peak per minute (last hour)",
    "Gebremst (kurz gewartet)": "Throttled (short wait)", "Ausgelassen (zu lange Wartezeit)": "Skipped (wait too long)",
    "Von Finnhub abgelehnt (429)": "Rejected by Finnhub (429)", "jetzt": "now",
})
DEPOT_WILD += [
    ("Limit {0} pro Minute", "Limit {0} per minute"), ("/ {0} in den letzten 60 Sekunden", "/ {0} in the last 60 seconds"),
    ("Gezählt werden nur echte Anfragen (Zwischenspeicher-Treffer nicht). Ab {0} Anfragen pro Minute bremst Stocky und wartet, bis wieder Platz ist – so geht keine Antwort durch das Limit verloren. Zähler „heute“ setzt um Mitternacht zurück und beginnt bei einem Neustart des Servers neu.",
     "Only real requests are counted (not cache hits). From {0} requests per minute Stocky throttles and waits until there is room again – so no answer is lost to the limit. The “today” counter resets at midnight and restarts when the server restarts."),
]
DEPOT_EXACT.update({"Erwartet in den nächsten 12 Monaten (Prognose)": "Expected in the next 12 months (forecast)"})
DEPOT_WILD += [("letzte 12 Monate, heutiger Bestand · Rendite {*}", "last 12 months, current holdings · yield {*}"),
               ("Verbraucht {0} (Dividenden {*} steuerpflichtig, Kursgewinne {*1})", "Used {0} (dividends {*} taxable, capital gains {*1})")]
DEPOT_EXACT.update({"vom Hoch, 12 Monate, heutiger Bestand": "from peak, 12 months, current holdings"})
DEPOT_WILD += [("{*} · heutiger Bestand", "{*} · current holdings")]
# Admin: Quellen-Monitor, Sicherheit, Nutzung
DEPOT_EXACT.update({
    "Quellen-Monitor": "Source monitor", "Quelle": "Source", "Anfragen": "Requests", "Erfolg 24 h": "Success 24 h", "Erfolg 1 h": "Success 1 h",
    "Ø Antwort": "Avg. response", "Letzter Fehler": "Last error", "läuft": "working", "wackelt": "flaky", "gestört": "disrupted", "gesperrt": "blocked",
    "Noch keine Anfragen seit dem Start.": "No requests since start.", "Sicherheit": "Security", "Anmeldungen": "Logins", "Admin-Aktionen": "Admin actions",
    "Noch keine protokolliert.": "None logged yet.", "neues Gerät": "new device", "Nutzung": "Usage", "Funktion": "Feature", "Heute": "Today",
    "7 Tage": "7 days", "30 Tage": "30 days", "Nutzer": "Users", "Je Benutzer (30 Tage)": "Per user (30 days)",
    "Seit über 30 Tagen inaktiv": "Inactive for more than 30 days", "nie angemeldet": "never logged in",
    "Noch keine Nutzung gezählt (Zählung läuft seit diesem Update).": "No usage counted yet (counting started with this update).",
    "Herkunft der Gewinnprognosen (Jahresansicht, seit dem Start)": "Origin of earnings forecasts (annual view, since start)",
    "Yahoo sperrt die Unternehmensdaten (Schätzungen, Kennzahlen) für diesen Server – Stocky nutzt Ersatzquellen (Nasdaq, onvista, SEC).":
        "Yahoo blocks company data (estimates, metrics) for this server – Stocky uses fallback sources (Nasdaq, onvista, SEC).",
    "„Nicht gefunden“ (HTTP 404) zählt nicht als Ausfall. Gelb unter 90 %, rot unter 50 % Erfolg in der letzten Stunde.":
        "“Not found” (HTTP 404) does not count as a failure. Yellow below 90 %, red below 50 % success in the last hour.",
    "Neues Gerät = Browser und Netz, mit denen sich der Benutzer noch nie angemeldet hat. Beim Admin-Konto kommt dann eine Push-Nachricht. Passwörter werden nie protokolliert.":
        "New device = browser and network the user has never logged in from. For the admin account a push notification is sent. Passwords are never logged.",
})
DEPOT_WILD += [("{0} fehlgeschlagene Anmeldungen in 24 h{*}", "{0} failed logins in 24 h{*}"),
               ("aktive Benutzer: heute {0} · 7 Tage {1} · 30 Tage {2} von {3}", "active users: today {0} · 7 days {1} · 30 days {2} of {3}"),
               ("letzte 24 Stunden · seit dem letzten Neustart", "last 24 hours · since last restart")]

# Admin: Fehlerprotokoll, Antwortzeiten, Laufzeit, Zwischenspeicher, Kontingente, Datenqualität, Push
DEPOT_EXACT.update({
    "Fehlerprotokoll": "Error log", "Keine Ausnahmen protokolliert. ✓": "No exceptions logged. ✓", "Protokoll leeren": "Clear log",
    "Gruppiert nach Fehlerart und Codestelle; bleibt über Neustarts erhalten. Schlüssel und Passwörter in Meldungen werden ausgeblendet.":
        "Grouped by error type and code location; kept across restarts. Keys and passwords in messages are masked.",
    "Antwortzeiten je Funktion": "Response times by feature", "letzte 7 Tage · nach 95-%-Wert sortiert": "last 7 days · sorted by 95th percentile",
    "Funktion": "Feature", "24 Std.": "24 h", "Median": "Median", "95 %": "95 %", "Max": "Max", "Fehler": "Errors", "Trend 95 %": "Trend 95 %",
    "Noch keine Anfragen gemessen.": "No requests measured yet.",
    "95 % = so lange dauerten 95 von 100 Anfragen höchstens. Trend: 95-%-Wert der letzten 24 Std. gegenüber den Tagen davor. Fehler = Serverfehler (HTTP 5xx). Warten auf Hintergrundaufträge zählt nicht, deren Gesamtdauer steht als „(Hintergrund)“.":
        "95 % = 95 out of 100 requests took at most this long. Trend: 95th percentile of the last 24 h vs. the days before. Errors = server errors (HTTP 5xx). Waiting for background jobs is not counted; their total duration is listed as “(Hintergrund)”.",
    "Top & Flop": "Top & Flop", "Chart": "Chart", "Suche": "Search", "Admin-Dashboard": "Admin dashboard",
    "Depotanalyse (Hintergrund)": "Portfolio analysis (background)", "Depot-Ausblick (Hintergrund)": "Portfolio outlook (background)",
    "Laufzeit & Version": "Uptime & version", "Online-Anteil": "Online share", "Online": "Online", "Längste Laufzeit": "Longest run",
    "Version": "Version", "Neustarts 30 Tage": "Restarts 30 days", "jetzt": "now",
    "Grün = Server lief. Lücken entstehen v. a. durch Einschlafen im kostenlosen Render-Tarif (nach 15 Min. ohne Aufrufe); Ende einer Laufzeit = letztes Lebenszeichen (alle 5 Min.).":
        "Green = server was running. Gaps mostly come from sleeping on Render's free plan (after 15 min without requests); end of a run = last heartbeat (every 5 min).",
    "Cache für diese Aktie leeren": "Clear cache for this stock",
    "Hilft, wenn eine Analyse veraltete oder falsche Daten zeigt – die nächste Analyse lädt alles neu.":
        "Helps when an analysis shows stale or wrong data – the next analysis reloads everything.",
    "Kürzel, z. B. SIE.DE oder AAPL": "Ticker, e.g. SIE.DE or AAPL",
    "Einträge": "Entries", "Cache-Treffer": "Cache hits", "Größe ca.": "Size approx.", "Gültig": "Valid",
    "Kontingente": "Quotas",
    "Gezählt werden echte Anfragen an die Quelle (keine Zwischenspeicher-Treffer). Monatszähler wird alle 5 Minuten gesichert. Ab 80 % kommt eine Push-Nachricht, wenn unten eingeschaltet.":
        "Counts real requests to the source (no cache hits). The monthly counter is saved every 5 minutes. From 80 % you get a push notification if enabled below.",
    "kostenloser Tarif; Stocky bremst ab 55/Min.": "free plan; Stocky throttles from 55/min",
    "Demo-Schlüssel: 30/Min., 10.000/Monat": "Demo key: 30/min, 10,000/month",
    "ohne Schlüssel: ca. 5–15/Min., schwankt mit der Server-IP": "without key: approx. 5–15/min, varies with the server IP",
    "höchstens 10 Anfragen pro Sekunde": "at most 10 requests per second", "ohne Schlüssel: 25 Anfragen pro Minute": "without key: 25 requests per minute",
    "mit Token: 5.000 Anfragen pro Stunde (Speichern + Backup)": "with token: 5,000 requests per hour (saving + backup)",
    "Datenqualität": "Data quality", "Bei den zuletzt analysierten Aktien fehlte nichts. ✓": "Nothing was missing in recently analyzed stocks. ✓",
    "Wird bei jeder Analyse aktualisiert; ist alles wieder da, verschwindet die Aktie aus der Liste. ↻ = Plausibilitätsregel hat Daten korrigiert (Ausreißer, Split, Größenordnung, veralteter Konsens) – zum gezielten Nachprüfen.":
        "Updated with every analysis; once everything is back, the stock disappears from the list. ↻ = a plausibility rule corrected data (outlier, split, magnitude, stale consensus) – for targeted review.",
    "kein Kursziel": "no price target", "keine Gewinnprognose": "no earnings forecast", "keine Umsatzprognose": "no revenue forecast",
    "keine Dividendenprognose": "no dividend forecast", "kein fairer Wert": "no fair value",
    "Push an den Admin": "Push to the admin", "über ntfy, wie die Preisalarme": "via ntfy, like the price alerts",
    "Datenquelle gestört": "Data source disrupted", "Viele Fehlversuche beim Login": "Many failed login attempts",
    "Kontingent über 80 %": "Quota above 80 %", "Neue Fehlerart": "New error type", "Test senden": "Send test", "Zuletzt gesendet": "Recently sent",
    "Gleiche Meldung höchstens alle 3 Std. (Fehlversuche 1 Std., neue Fehlerart 1 Tag, Monatskontingent 1 Woche). Quelle gestört = unter 50 % Erfolg in der letzten Stunde bei mindestens 5 Anfragen.":
        "Same alert at most every 3 h (failed logins 1 h, new error type 1 day, monthly quota 1 week). Source disrupted = below 50 % success in the last hour with at least 5 requests.",
    "Fehlerprotokoll leeren?": "Clear error log?", "Benachrichtigungen gespeichert": "Notifications saved",
    "Fehlerprotokoll geleert": "Error log cleared", "Test-Nachricht gesendet": "Test message sent", "Ungültiges Kürzel": "Invalid ticker",
})
DEPOT_WILD += [("{0} Fehlerart(en) · {1} Vorkommen · {2} in den letzten 24 Std.", "{0} error type(s) · {1} occurrences · {2} in the last 24 h"),
               ("Erstmals {*}", "First {*}"), ("zuletzt {*}", "last {*}"), ("letzte {0} Tage", "last {0} days"),
               ("geschätzt {*} · Trefferquote seit dem Start", "estimated {*} · hit rate since start"),
               ("Monat {0} · Balken: höchste Auslastung der letzten Stunde bzw. Hochrechnung bis Monatsende",
                "Month {0} · bars: peak usage in the last hour or projection to month end"),
               ("pro Minute: jetzt {0} · Spitze 1 Std. {1} / {2}", "per minute: now {0} · peak 1 h {1} / {2}"),
               ("pro Sekunde: jetzt {0} · Spitze 1 Std. {1} / {2}", "per second: now {0} · peak 1 h {1} / {2}"),
               ("pro Stunde: jetzt {0} · Spitze 1 Std. {1} / {2}", "per hour: now {0} · peak 1 h {1} / {2}"),
               ("heute {0} · Monat {1}{*}", "today {0} · month {1}{*}"), ("Monat: {0} / {1} · Hochrechnung {2}", "Month: {0} / {1} · projection {2}"),
               ("{0} Aktie(n) mit Lücken oder Korrekturen · letzte 30 Tage", "{0} stock(s) with gaps or corrections · last 30 days"),
               ("{0} Einträge gelöscht{*}", "{0} entries deleted{*}"), ("seit {*}", "since {*}")]
DEPOT_EXACT.update({"Alle löschen": "Delete all", "Alle Bewertungen löschen und Arbeitsspeicher freigeben": "Delete all ratings and free memory",
                    "Der Screener läuft gerade – bitte zuerst stoppen.": "The screener is running – please stop it first."})
DEPOT_WILD += [("Alle {0} bewerteten Werte aus dem Screener löschen?\n\nDas gibt Arbeitsspeicher frei. Die Bewertungen lassen sich nur durch ein neues Screening wiederherstellen (dauert je Index länger).",
                "Delete all {0} rated stocks from the screener?\n\nThis frees memory. The ratings can only be restored by running a new screening (takes a while per index)."),
               ("{0} bewertete Werte gelöscht{*}", "{0} rated stocks deleted{*}")]
DEPOT_EXACT.update({"Kann bis zu 90 Sekunden dauern": "Can take up to 90 seconds"})
DEPOT_WILD += [
    ("{*}: Umsatz mit dem Wachstum laut Analystenkonsens (Yahoo Finance) – der Konsens grenzt den Umsatz anders ab, daher auf den gemeldeten Umsatz übertragen, {*1}.",
     "{*}: revenue with the growth from the analyst consensus (Yahoo Finance) – the consensus defines revenue differently, so the growth is applied to reported revenue, {*1}."),
    ("Prognose · Konsens von {0} Analysten (Gewinn: {1}) · Umsatzwachstum auf den gemeldeten Umsatz übertragen",
     "Forecast · consensus of {0} analysts (earnings: {1}) · revenue growth applied to reported revenue"),
    ("Prognose · Konsens von {0} Analysten · Umsatzwachstum auf den gemeldeten Umsatz übertragen",
     "Forecast · consensus of {0} analysts · revenue growth applied to reported revenue"),
]
DEPOT_WILD += [
    ("Potenzial {0} · Konsens von {1} Analysten (S&P Global über stockanalysis.com)",
     "Upside {0} · consensus of {1} analysts (S&P Global via stockanalysis.com)"),
    ("Potenzial {0} · Konsens von {1} Analysten (Nasdaq), über die US-Notierung {*}",
     "Upside {0} · consensus of {1} analysts (Nasdaq), via the US listing {*}"),
    ("Potenzial {0} · Konsens von {1} Analysten ({*})", "Upside {0} · consensus of {1} analysts ({*})"),
    ("Potenzial {0} · Median aus {1} Analysten-Kurszielen in Nachrichten, 90 Tage",
     "Upside {0} · median of {1} analyst price targets in the news, 90 days"),
]
DEPOT_EXACT.update({"Nicht im Tarif (24 Std. ausgelassen)": "Not in plan (skipped for 24 h)"})
DEPOT_WILD += [("Stand {0}, laut Wikidata", "as of {0}, per Wikidata")]
DEPOT_WILD += [("Das Geschäftsjahr {0} ist abgeschlossen, seine Zahlen sind aber noch nicht veröffentlicht – die Prognosen beginnen deshalb mit {1}.",
                "Fiscal year {0} has ended, but its figures have not been published yet – the forecasts therefore start with {1}.")]

# Aktienkursrechner
DEPOT_EXACT.update({
    "Aktienkursrechner": "Stock price calculator",
    "Mögliche Kursspanne der nächsten fünf Jahre aus Umsatzwachstum, Gewinnwachstum und KGV – mit Bear-, Base- und Bull-Szenario nach einem DCF-Modell. Alle Annahmen lassen sich danach selbst überschreiben.":
        "Possible price range over the next five years from revenue growth, earnings growth and P/E – with bear, base and bull scenarios based on a DCF model. All assumptions can be overwritten afterwards.",
    "Aktie, z. B. Apple, SAP.DE oder Allianz": "Stock, e.g. Apple, SAP.DE or Allianz",
    "Berechnen": "Calculate",
    "Wohin kann der Kurs in fünf Jahren laufen? Umsatz- und Gewinnwachstum mit konservativem und optimistischem KGV – Bear-, Base- und Bull-Szenario nach einem DCF-Modell, alle Annahmen selbst änderbar.":
        "Where could the price be in five years? Revenue and earnings growth with a conservative and an optimistic P/E – bear, base and bull scenarios based on a DCF model, all assumptions editable.",
    "Kurs berechnen": "Calculate price",
    "Umsatzwachstum": "Revenue growth", "Gewinnwachstum": "Earnings growth", "Nettomarge": "Net margin",
    "KGV konservativ": "P/E conservative", "KGV optimistisch": "P/E optimistic",
    "Kurs konservativ": "Price conservative", "Kurs optimistisch": "Price optimistic",
    "Rendite p. a. konservativ": "Return p.a. conservative", "Rendite p. a. optimistisch": "Return p.a. optimistic",
    "änderbar": "editable", "ab heute": "from today",
    "Werte des Szenarios wiederherstellen": "Restore scenario values",
    "Umsatz- und Gewinnwachstum (in %) und KGV lassen sich je Jahr überschreiben – alles rechnet sofort neu.":
        "Revenue and earnings growth (in %) and P/E can be overwritten for each year – everything recalculates instantly.",
    "So wird gerechnet": "How it is calculated",
    "Diskontsatz (WACC)": "Discount rate (WACC)", "KGV heute / Median 5 J.": "P/E today / 5-yr median",
    "konservativ – optimistisch": "conservative – optimistic",
    "nicht berechenbar (negativer Free Cashflow)": "not computable (negative free cash flow)",
    "Ewiges Wachstum": "Terminal growth", "Anteil Endwert am Unternehmenswert": "Terminal value share of enterprise value",
    "DCF-Wert je Aktie": "DCF value per share", "KGV konservativ / optimistisch": "P/E conservative / optimistic",
    "Kurs = Gewinn je Aktie × KGV.": "Price = earnings per share × P/E.",
    "Umsatz und Reinertrag wachsen vom letzten abgeschlossenen Geschäftsjahr aus mit den Raten der Tabelle; Gewinn je Aktie = Reinertrag ÷ heutige Aktienzahl.":
        "Revenue and net income grow from the last completed fiscal year at the rates in the table; earnings per share = net income ÷ today's share count.",
    "Die Rendite p. a. vergleicht den Kurs am jeweiligen Geschäftsjahresende mit dem heutigen Kurs (ohne Dividenden).":
        "The return p.a. compares the price at the respective fiscal year end with today's price (excluding dividends).",
    "Szenarien nach dem DCF-Modell": "Scenarios based on the DCF model",
    "Umsatzwachstum im Basisfall:": "Revenue growth in the base case:",
    "KGV:": "P/E:",
    "Bank/Versicherer: Eigenkapital-DCF mit dem Reinertrag statt Free Cashflow.": "Bank/insurer: equity DCF using net income instead of free cash flow.",
    "Keine Anlageberatung – eine Modellrechnung mit den angezeigten Annahmen.": "Not investment advice – a model calculation using the assumptions shown.",
    "Der Kursrechner ist nur für Aktien – ETFs haben keinen eigenen Gewinn.": "The price calculator is for stocks only – ETFs have no earnings of their own.",
    "Zu wenige Geschäftsjahre für eine Berechnung.": "Too few fiscal years for a calculation.",
    "Kein aktueller Kurs bzw. Börsenwert verfügbar.": "No current price or market value available.",
    "Wechselkurs nicht verfügbar.": "Exchange rate not available.",
    "Konsens": "consensus", "fortgeschrieben": "extrapolated",
})
DEPOT_WILD += [
    ("DCF-Wert je Aktie ({*})", "DCF value per share ({*})"),
    ("ewiges Wachstum {0}", "terminal growth {0}"),
    ("DCF-KGV Jahr {0}: {1}", "DCF P/E year {0}: {1}"), ("DCF-KGV Jahr {0}: {*}", "DCF P/E year {0}: {*}"),
    ("Kursspanne {0}", "Price range {0}"), ("{0} ggü. Kurs", "{0} vs. price"),
    ("Aktueller Kurs {0} {1} · Basisjahr {2} (letztes abgeschlossenes Geschäftsjahr)",
     "Current price {0} {1} · base year {2} (last completed fiscal year)"),
    ("Umsatzwachstum Jahr {0} / {1}", "Revenue growth year {0} / {1}"), ("Nettomarge Jahr {0}", "Net margin year {0}"),
    ("Berechne Szenarien für {*} …", "Calculating scenarios for {*} …"), ("Kann bis zu {0} Sekunden dauern", "Can take up to {0} seconds"),
    ("Berechnung nicht möglich: {*}", "Calculation not possible: {*}"),
    ("Umgerechnet von {0} in {1}.", "Converted from {0} to {1}."),
    ("{0}: Konsens", "{0}: consensus"), ("{0}: fortgeschrieben", "{0}: extrapolated"),
    ("({0} Jahre, Diskontsatz nach CAPM, Abzinsung zur Jahresmitte, ewiges Wachstum danach). Base: Analystenkonsens, danach schrittweise Richtung langfristiges Wachstum. Bear/Bull: Umsatzwachstum {1} niedriger/höher (mindestens {2} Prozentpunkte), Nettomarge bis Jahr {3} um {4} niedriger/höher, Diskontsatz ±{5} Prozentpunkte, ewiges Wachstum {6} / {7} / {8}.",
     "({0} years, discount rate via CAPM, mid-year discounting, perpetual growth thereafter). Base: analyst consensus, then gradually towards long-term growth. Bear/Bull: revenue growth {1} lower/higher (at least {2} percentage points), net margin by year {3} {4} lower/higher, discount rate ±{5} percentage points, terminal growth {6} / {7} / {8}."),
    ("konservativ = niedrigeres, optimistisch = höheres aus aktuellem KGV und Median der letzten fünf Jahre; für Bear/Bull im Verhältnis der DCF-Werte zum Basisfall angepasst. Das reine DCF-KGV (Endwert ÷ Reinertrag in Jahr {0}) ist meist deutlich niedriger, weil es nach Jahr {1} nur noch {2} Wachstum unterstellt.",
     "conservative = the lower, optimistic = the higher of the current P/E and the five-year median; adjusted for bear/bull in proportion to the DCF values versus the base case. The pure DCF P/E (terminal value ÷ net income in year {0}) is usually much lower because it assumes only {2} growth after year {1}."),
    ("Eigenkapitalkosten {0} = risikoloser Zins {1} + Beta {2} (angepasst {3}) × Marktrisikoprämie {4}",
     "Cost of equity {0} = risk-free rate {1} + beta {2} (adjusted {3}) × equity risk premium {4}"),
    ("Eigenkapitalkosten {0} = risikoloser Zins {1} + Beta – (angepasst {2}) × Marktrisikoprämie {3}",
     "Cost of equity {0} = risk-free rate {1} + beta – (adjusted {2}) × equity risk premium {3}"),
    ("+ Länderrisiko {0}", "+ country risk {0}"),
    ("Free-Cashflow-Marge zuletzt {0}.", "Most recent free cash flow margin {0}."),
    ("Kein aussagekräftiges KGV (Verluste oder zu kurze Historie) – Startwerte {0} bzw. {1}, bitte anpassen.",
     "No meaningful P/E (losses or too short a history) – starting values {0} and {1}, please adjust."),
    ("Das Geschäftsjahr {0} ist abgeschlossen, seine Zahlen sind aber noch nicht veröffentlicht – Basisjahr ist deshalb {1}.",
     "Fiscal year {0} has ended, but its figures have not been published yet – the base year is therefore {1}."),
]
DEPOT_WILD += [("{0}: aus Gewinnkonsens abgeleitet", "{0}: derived from the earnings consensus")]
DEPOT_EXACT.update({"Aktienrückkäufe berücksichtigen": "Include share buybacks", "Aktienrückkauf": "Share buyback",
                    "Aktienzahl": "Share count", "änderbar · weniger Aktien pro Jahr": "editable · fewer shares per year",
                    "Keine Daten zur Aktienzahl – Prognose 0 %, bitte selbst eintragen": "No share count data – forecast 0%, please enter your own",
                    "Mit Aktienrückkäufen sinkt die Aktienzahl jedes Jahr um die eingetragene Rate – derselbe Reinertrag verteilt sich auf weniger Aktien. Ein negativer Wert bedeutet mehr Aktien (Verwässerung, z. B. durch Aktienvergütung).":
                        "With share buybacks the share count falls each year by the rate entered – the same net income is spread over fewer shares. A negative value means more shares (dilution, e.g. from stock-based compensation)."})
DEPOT_WILD += [("Prognose: {0} weniger Aktien pro Jahr – Durchschnitt {1}–{2}", "Forecast: {0} fewer shares per year – average {1}–{2}"),
               ("Prognose: {0} mehr Aktien pro Jahr (Verwässerung) – Durchschnitt {1}–{2}", "Forecast: {0} more shares per year (dilution) – average {1}–{2}")]

# Earnings Reviewer
DEPOT_EXACT.update({
    "Earnings Reviewer": "Earnings Reviewer",
    "Das letzte Quartal einer Aktie auf einen Blick: über oder unter den Erwartungen, die wichtigsten Zahlen und der Ausblick als Stichpunkte – dazu ein One-Pager (A4) zum Ansehen und Drucken.":
        "A stock's latest quarter at a glance: above or below expectations, the key figures and the outlook as bullet points – plus a one-pager (A4) to view and print.",
    "Quartal auswerten": "Review quarter",
    "Das letzte Quartal auf einen Blick: Ergebnis ggü. den Erwartungen der Analysten, die wichtigsten Kennzahlen, der Ausblick des Managements und geänderte Schätzungen – kurz als Stichpunkte und ausführlich als One-Pager (A4).":
        "The latest quarter at a glance: results versus analyst expectations, the key figures, management's outlook and revised estimates – briefly as bullet points and in detail as a one-pager (A4).",
    "Auswerten": "Review",
    "Über den Erwartungen": "Above expectations", "Unter den Erwartungen": "Below expectations", "Im Rahmen der Erwartungen": "In line with expectations",
    "Prognose angehoben": "Guidance raised", "Prognose bestätigt": "Guidance confirmed", "Prognose gesenkt": "Guidance lowered", "Neue Prognose": "New guidance",
    "Die wichtigsten Punkte": "Key points", "Ausblick:": "Outlook:", "Ausblick": "Outlook",
    "One-Pager ansehen (A4)": "View one-pager (A4)",
    "Die Tiefenanalyse der Pressemitteilung braucht einen Claude-Schlüssel auf dem Server.": "The in-depth analysis of the press release requires a Claude key on the server.",
    "Ausführliche Analyse der Pressemitteilung nur für Werte mit US-Börsenmeldung (8-K).": "Detailed press release analysis only for stocks with a US filing (8-K).",
    "Keine Kennzahlen zum letzten Quartal verfügbar.": "No figures available for the latest quarter.",
    "Drucken / als PDF speichern": "Print / save as PDF", "Schließen": "Close",
    "Kennzahlen ggü. Vorjahresquartal": "Key figures vs. prior-year quarter", "Operative Marge": "Operating margin",
    "Konsens Gewinn je Aktie": "Consensus EPS", "Gewinn je Aktie: Ist (Punkt) ggü. Konsens (Strich)": "EPS: actual (dot) vs. consensus (line)",
    "Umsatz je Quartal": "Revenue per quarter", "(hell = Analystenprognose)": "(light = analyst forecast)",
    "Geänderte Gewinnschätzungen": "Revised earnings estimates", "aktuell": "current",
    "laufendes Quartal": "current quarter", "nächstes Quartal": "next quarter", "laufendes Geschäftsjahr": "current fiscal year", "nächstes Geschäftsjahr": "next fiscal year",
    "Geschäftsbereiche": "Business segments", "Positiv": "Positive", "Negativ": "Negative", "Fazit": "Conclusion",
    "Pressestimmen": "Press coverage", "Quellen:": "Sources:", "Quartalszahlen im Überblick": "Quarterly results at a glance",
    "Alle Pflichtmeldungen bei SEC EDGAR": "All filings at SEC EDGAR",
    "Keine Anlageberatung – automatisch erstellte Zusammenfassung aus öffentlichen Daten.": "Not investment advice – automatically generated summary from public data.",
    "Der Earnings Reviewer ist nur für Aktien – ETFs veröffentlichen keine Quartalszahlen.": "The Earnings Reviewer is for stocks only – ETFs do not publish quarterly results.",
    "Keine Quartalszahlen verfügbar.": "No quarterly figures available.",
})
DEPOT_WILD += [
    ("Quartal bis {0} · veröffentlicht am {1}", "Quarter ended {0} · published {1}"), ("Quartal bis {0}", "Quarter ended {0}"),
    ("{0} von {1} Quartalen über dem Konsens", "{0} of {1} quarters above consensus"),
    ("Nächste Quartalszahlen: {0} (geschätzt)", "Next quarterly results: {0} (estimated)"), ("Nächste Quartalszahlen: {0}", "Next quarterly results: {0}"),
    ("Nächste Quartalszahlen:", "Next quarterly results:"),
    ("Werte die Quartalszahlen von {*} aus …", "Reviewing the quarterly results of {*} …"),
    ("Auswertung nicht möglich: {*}", "Review not possible: {*}"),
    ("One-Pager {*}", "One-pager {*}"),
    ("{*} · Earnings Update · Quartal bis {0} · veröffentlicht {1}", "{*} · Earnings Update · quarter ended {0} · published {1}"),
    ("{*} · Earnings Update · Quartal bis {0}", "{*} · Earnings Update · quarter ended {0}"),
    ("Kurs {0} {1}", "Price {0} {1}"), ("Stand {0} {1}", "As of {0} {1}"),
    ("Analysten erwarten für das Quartal bis {0} einen Umsatz von {1} {2} ({3} ggü. Vorjahresquartal)",
     "Analysts expect revenue of {1} {2} for the quarter ending {0} ({3} vs. prior-year quarter)"),
    ("Analysten erwarten für das Quartal bis {0} einen Umsatz von {1} {2}", "Analysts expect revenue of {1} {2} for the quarter ending {0}"),
    ("Gewinnschätzung für das laufende Geschäftsjahr in den letzten {0} Tagen kaum verändert", "Earnings estimate for the current fiscal year barely changed over the last {0} days"),
    ("Gewinnschätzung für das laufende Geschäftsjahr in den letzten {0} Tagen angehoben ({1})", "Earnings estimate for the current fiscal year raised over the last {0} days ({1})"),
    ("Gewinnschätzung für das laufende Geschäftsjahr in den letzten {0} Tagen gesenkt ({1})", "Earnings estimate for the current fiscal year lowered over the last {0} days ({1})"),
    ("{*} – Umsatz {0} ggü. Vorjahresquartal", "{*} – revenue {0} vs. prior-year quarter"),
    ("{0} Überraschung", "{0} surprise"), ("{0} Tage", "{0} days"),
    ("Ergebnis-Pressemitteilung (SEC, Anlage {0}, {1})", "Earnings press release (SEC, exhibit {0}, {1})"),
    ("Ergebnis-Pressemitteilung (SEC, Anlage {0})", "Earnings press release (SEC, exhibit {0})"),
    ("Kennzahlen: {*}", "Figures: {*}"),
]
DEPOT_WILD += [
    ("Gewinn je Aktie {0} statt erwartet {1} – {2} über der Erwartung", "EPS {0} vs. {1} expected – {2} above expectations"),
    ("Gewinn je Aktie {0} statt erwartet {1} – {2} unter der Erwartung", "EPS {0} vs. {1} expected – {2} below expectations"),
    ("Gewinn je Aktie {0} statt erwartet {1} – im Rahmen der Erwartung", "EPS {0} vs. {1} expected – in line with expectations"),
    ("Stand {0} {1}:{2}", "As of {0} {1}:{2}"), ("Erwarteter Gewinn je Aktie: {0}", "Expected EPS: {0}"),
    ("Kennzahlen: {*}", "Figures: {*}"), ("Konsens Gewinn je Aktie: {*}", "EPS consensus: {*}"),
    ("Schätzungsänderungen: {*}", "Estimate revisions: {*}"), ("Analyse der Pressemitteilung: Claude ({*})", "Press release analysis: Claude ({*})"),
]

# Earnings Reviewer: Strategie & Entscheidungen
DEPOT_EXACT.update({
    "Strategie & wichtige Entscheidungen": "Strategy & key decisions", "Quartal": "Quarter", "Vorjahr": "Prior year",
    "Free Cashflow": "Free cash flow", "Aktienrückkäufe": "Share buybacks", "Dividenden gezahlt": "Dividends paid",
    "Investitionen (Sachanlagen)": "Capital expenditure", "Zukäufe von Unternehmen (netto)": "Acquisitions (net)",
    "Schulden aufgenommen (+) / getilgt (−)": "Debt raised (+) / repaid (−)",
    "Pflichtmeldungen an die US-Börsenaufsicht (8-K)": "Filings with the US SEC (8-K)",
    "Meldungen der letzten Monate": "News from recent months", "Keine Angaben zur Kapitalverwendung.": "No capital allocation data.",
    "Wesentlicher Vertrag abgeschlossen": "Material agreement entered", "Wesentlicher Vertrag beendet": "Material agreement terminated",
    "Cybersicherheitsvorfall": "Cybersecurity incident", "Kauf oder Verkauf von Unternehmensteilen abgeschlossen": "Acquisition or disposition completed",
    "Neue Finanzierung (Anleihe oder Kredit)": "New financing (bond or loan)", "Umbau mit Restrukturierungskosten": "Restructuring with costs",
    "Wertminderung von Vermögenswerten": "Asset impairment", "Ausgabe neuer Aktien": "Issuance of new shares",
    "Änderung von Aktionärsrechten": "Change in shareholder rights", "Wechsel des Wirtschaftsprüfers": "Change of auditor",
    "Wechsel der Kontrolle": "Change in control", "Wechsel im Vorstand oder Aufsichtsrat": "Change of directors or officers",
    "Satzungsänderung": "Amendment to articles", "Abstimmungen der Hauptversammlung": "Shareholder meeting votes",
    "Information an Investoren": "Investor information (Reg FD)", "Sonstiges wichtiges Ereignis": "Other material event",
})
DEPOT_WILD += [
    ("Kapitalverwendung (Quartal bis {0})", "Capital allocation (quarter ended {0})"),
    ("Dividende je Aktie zuletzt {0} ({1}) – unverändert ggü. {2} ({3})", "Latest dividend per share {0} ({1}) – unchanged vs. {2} ({3})"),
    ("Dividende je Aktie zuletzt {0} ({1}) – erhöht um {2} ggü. {3} ({4})", "Latest dividend per share {0} ({1}) – raised by {2} vs. {3} ({4})"),
    ("Dividende je Aktie zuletzt {0} ({1}) – gesenkt um {2} ggü. {3} ({4})", "Latest dividend per share {0} ({1}) – cut by {2} vs. {3} ({4})"),
    ("Kapitalverwendung und Dividende: {*}", "Capital allocation and dividend: {*}"), ("Meldungen: {*}", "News: {*}"),
]
DEPOT_EXACT.update({"Strategische Entscheidungen": "Strategic decisions"})
DEPOT_WILD += [("Aktienrückkäufe im Quartal: {0} {1} (Vorjahresquartal {2} {3})", "Share buybacks in the quarter: {0} {1} (prior-year quarter {2} {3})"),
               ("Aktienrückkäufe im Quartal: {0} {1}", "Share buybacks in the quarter: {0} {1}"),
               ("Zukäufe von Unternehmen im Quartal: {0} {1}", "Acquisitions in the quarter: {0} {1}"),
               ("Dividende je Aktie erhöht um {0} auf {1} ({2})", "Dividend per share raised by {0} to {1} ({2})"),
               ("Dividende je Aktie gesenkt um {0} auf {1} ({2})", "Dividend per share cut by {0} to {1} ({2})")]
DEPOT_EXACT.update({"Ausblick des Managements": "Management outlook",
                    "Wörtlich aus der Ergebnis-Pressemitteilung (englisch)": "Verbatim from the earnings press release",
                    "Pressemitteilung öffnen": "Open press release"})
DEPOT_EXACT.update({"Aus der Ergebnis-Pressemitteilung, maschinell übersetzt": "From the earnings press release, machine-translated",
                    "Original öffnen": "Open original"})
DEPOT_EXACT.update({"(übersetzt)": "(translated)"})
DEPOT_WILD += [("(Umsatzanteil, Geschäftsjahr bis {0})", "(share of revenue, fiscal year ended {0})"), ("{0} ggü. Vorjahr", "{0} vs. prior year")]
DEPOT_EXACT.update({"Umsatz nach Regionen": "Revenue by region"})
DEPOT_WILD += [("±{0} ggü. Vorjahr", "±{0} vs. prior year")]
DEPOT_EXACT.update({"Freier Cashflow": "Free cash flow", "Erwarteter Gewinn je Aktie (Konsens)": "Expected EPS (consensus)"})
DEPOT_WILD += [("{0} Prozentpunkte", "{0} pp")]
DEPOT_EXACT.update({"Quartalszahlen im Überblick": "Quarterly results at a glance"})
DEPOT_WILD += [("Kurzbericht {*} (A4)", "Brief report {*} (A4)"), ("{*} · Quartalszahlen im Überblick · Quartal bis {0} · veröffentlicht {1}", "{*} · Quarterly results at a glance · quarter ended {0} · published {1}"),
               ("{*} · Quartalszahlen im Überblick · Quartal bis {0}", "{*} · Quarterly results at a glance · quarter ended {0}"),
               ("Erwarteter Gewinn je Aktie: {*}", "Expected EPS: {*}")]
