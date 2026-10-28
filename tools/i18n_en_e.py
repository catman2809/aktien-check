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
