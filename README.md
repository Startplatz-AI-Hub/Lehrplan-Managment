# Lehrplan-Management-System

Ein webbasiertes Lehrplan-Management-System entwickelt mit Flask, das es ermöglicht, Lehrpläne zu verwalten, Kurse in einer interaktiven Timeline darzustellen und Dozenten mit ihren Verfügbarkeiten zu verwalten.

## Features

- **Lehrpläne verwalten**: Hochladen und Parsen von Lehrplänen als CSV-Dateien
- **Interaktive Timeline**: Visualisierung von Kursen nach Batch/Lehrplan gruppiert
- **Dozentenverwaltung**: Zuweisung von Dozenten zu Kursen mit Konfliktprüfung
- **Exportfunktionen**: Export der Timeline als PNG, SVG oder PDF

## Deployment auf Replit

### Schritt 1: Projekt auf Replit erstellen

1. Besuche [Replit](https://replit.com) und melde dich an
2. Klicke auf "+ Create Repl"
3. Wähle "Import from GitHub" und gib deine GitHub-Repository-URL ein
   - Alternativ: Wähle "Python" und importiere die Dateien manuell
4. Benenne das Repl und klicke auf "Create Repl"

### Schritt 2: Konfiguration

1. Replit verwendet eine `replit.nix` und eine `.replit` Datei zur Konfiguration. Wenn diese nicht automatisch erstellt werden, füge folgende `.replit` Datei hinzu:

```
language = "python3"
entrypoint = "run.py"
run = "python run.py"
```

2. Erstelle eine Umgebungsvariable für das Flask-Secret:
   - Gehe zu "Secrets" (Schloss-Symbol)
   - Füge einen neuen Secret mit dem Namen "SECRET_KEY" hinzu und generiere einen zufälligen Wert

### Schritt 3: Datenbank einrichten

Bei der ersten Ausführung wird die Datenbank automatisch initialisiert. Alternativ kannst du die Datenbank manuell initialisieren:

1. Öffne die Replit Shell
2. Führe den Befehl aus: `python -c "from app import create_app, db; app = create_app(); app.app_context().push(); db.create_all()"`

### Schritt 4: Anwendung starten

1. Klicke auf "Run" um die Anwendung zu starten
2. Die Anwendung ist nun unter der von Replit bereitgestellten URL verfügbar

## PDF-Generierung auf Replit

Bitte beachte, dass die PDF-Generierung mit pdfkit/wkhtmltopdf auf Replit eingeschränkt sein kann. Falls der PDF-Export nicht funktioniert, kannst du folgende Alternativen verwenden:

1. Browser-basierter Export (mit JavaScript)
2. Verwendung der Plotly-Export-Funktionen für SVG/PNG statt PDF

## Wichtige Hinweise für Replit

1. **Persistenz**: Replit speichert Daten, aber bei längerer Inaktivität kann der Container neu gestartet werden. Für kritische Daten sollte ein externes Backup verwendet werden.

2. **Umgebungsvariablen**: Sensitive Daten sollten als Replit Secrets gespeichert werden.

3. **URL-Zugriff**: Die öffentliche URL deiner Anwendung findest du oben im Replit-Interface nach dem Start.

4. **Always On**: Für ständige Verfügbarkeit ohne "Sleep Mode" kann ein Replit "Hacker Plan" erforderlich sein.

## Lokale Entwicklung

```bash
# Repository klonen
git clone <repository-url>
cd Lehrplan-Managment

# Virtuelle Umgebung erstellen und aktivieren
python -m venv venv
source venv/bin/activate  # Unix/Mac
venv\Scripts\activate     # Windows

# Abhängigkeiten installieren
pip install -r requirements.txt

# Anwendung starten
python run.py
```

## Lizenz

Siehe `LICENSE` Datei für Details. 