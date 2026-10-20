# Aktien-Check online stellen (Render.com, kostenlos)

Dauer: ca. 15 Minuten, einmalig. Danach ist der Aktien-Check unter einer festen Adresse
(z. B. `https://aktien-check-xxxx.onrender.com`) von jedem Gerät erreichbar – passwortgeschützt.

## 1. Code zu GitHub hochladen
1. Auf https://github.com/signup ein kostenloses Konto anlegen (falls noch keins vorhanden).
2. Oben rechts **+ → New repository**
   - Repository name: `aktien-check`
   - **Private** auswählen
   - **Create repository** klicken
3. Auf der neuen Seite den Link **„uploading an existing file“** anklicken.
4. Aus dem Ordner `Aktien-Check` diese Dateien in das Browserfenster ziehen:
   - `aktien_check.py`
   - `index.html`
   - `requirements.txt`
   - `render.yaml`
   - `.gitignore`
   - `README.md`
5. Unten **Commit changes** klicken.

## 2. Bei Render veröffentlichen
1. Auf https://render.com → **Get Started** → **Sign up with GitHub** (gleiches Konto).
   Render fragt nach Zugriff auf GitHub → Zugriff auf das Repository `aktien-check` erlauben.
2. Im Dashboard **+ New → Blueprint** wählen und das Repository `aktien-check` auswählen.
3. Render liest die Datei `render.yaml` und fragt nach **APP_PASSWORD**:
   ein eigenes Passwort eintragen (das brauchst du später zum Öffnen).
4. **Apply / Deploy Blueprint** klicken. Der erste Aufbau dauert ca. 3–5 Minuten.
5. Wenn der Status **Live** ist, oben die Adresse `https://aktien-check-….onrender.com` anklicken.
   Im Anmeldefenster: Benutzername **beliebig**, Passwort = dein APP_PASSWORD.

Tipp: Auf dem Handy die Seite über „Zum Startbildschirm hinzufügen“ wie eine App ablegen.

## 3. Finnhub als zweite Datenquelle (Analystendaten online)
Yahoo liefert Cloud-Servern keine Analystendaten. Finnhub ergänzt sie:
1. Auf https://finnhub.io/register kostenlos registrieren.
2. Im Dashboard den **API Key** kopieren.
3. Render → Service `aktien-check` → **Environment** → **Add Environment Variable**
   - Key: `FINNHUB_API_KEY`
   - Value: dein API Key
4. **Save, rebuild, and deploy**.

Der kostenlose Tarif deckt vor allem US-Börsen ab. Für deutsche Aktien nimmt das Programm automatisch
die US-Notierung desselben Unternehmens (z. B. SAP statt SAP.DE). Kursziele sind teils nur im
Bezahltarif enthalten – dann fehlen sie, die Analystenempfehlungen kommen trotzdem.

## Gut zu wissen
- **Kostenloser Tarif schläft** nach ca. 15 Minuten ohne Nutzung ein. Der erste Aufruf danach
  dauert 30–60 Sekunden, danach läuft es normal.
- **Änderungen übernehmen:** geänderte Datei auf GitHub erneut hochladen (gleicher Weg wie oben,
  „Add file → Upload files“) – Render baut automatisch neu.
- **Passwort ändern:** Render → Service `aktien-check` → *Environment* → `APP_PASSWORD`.
- Yahoo Finance begrenzt manchmal Anfragen von Cloud-Servern. Falls online Daten fehlen,
  lokal aber alles geht, liegt es daran – dann einfach später erneut versuchen.

## Nur im Heimnetz (ohne Cloud)
`Aktien-Check im Netzwerk starten.bat` doppelklicken. Das Fenster zeigt die Adresse
(z. B. `http://192.168.178.82:8765`), die du auf Handy/Tablet im selben WLAN öffnest.
Fragt Windows nach der Firewall: Zugriff für **Private Netzwerke** erlauben.
