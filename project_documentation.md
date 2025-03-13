# Lehrplan-Timeline-System - Projektdokumentation

## Projektübersicht

Diese Anwendung ist ein webbasiertes Lehrplan-Management-System, das mithilfe von Flask entwickelt wurde. Es ermöglicht Nutzern, Lehrpläne zu verwalten, Kurse in einer interaktiven Timeline darzustellen und Dozenten mit ihren Verfügbarkeiten zu verwalten.

## Hauptfunktionen

1. **Lehrpläne verwalten**:
   - Hochladen von Lehrplänen als CSV-Dateien
   - Automatisches Parsen von Start- und Enddaten sowie Kursthemen
   - Duplizieren von Lehrplänen für neue Starttermine

2. **Interaktive Timeline**:
   - Visualisierung von Kursen nach Batch/Lehrplan gruppiert
   - Farbkodierung nach Dozenten
   - Anzeige von Urlaub und Nichtverfügbarkeiten
   - Darstellung in Wochen-Intervallen mit Monatsmarkierungen

3. **Dozentenverwaltung**:
   - Zuweisung von Dozenten zu Kursen
   - Konfliktprüfung und -markierung
   - Verwaltung von Urlaubszeiten und Verfügbarkeiten
   - Individuelle Farbzuweisung pro Dozent

4. **Exportfunktionen**:
   - Export der Timeline als PNG, SVG oder PDF
   - Detaillierter Berichtsexport als PDF mit Lehrplandetails

## Technische Architektur

### Backend (Python/Flask)

#### Datenbankmodelle (`app/models.py`):
- `Course`: Repräsentiert einen Kurs mit Thema, Start-/Enddatum und Zuordnung zum curriculum_id
- `Lecturer`: Dozenten mit Namen, Farbe und Zuordnungen
- `Assignment`: Verbindung zwischen Kursen und Dozenten
- `Availability`: Verfügbarkeiten/Urlaub für Dozenten
- `Settings`: Systemeinstellungen und Konfiguration

#### Hauptrouten (`app/routes.py`):
- `/`: Startseite mit Upload-Formular
- `/upload`: Verarbeitung hochgeladener Lehrplandateien
- `/timeline`: Visualisierung der Kurse als Timeline
- `/duplicate`: Duplizieren von Lehrplänen für neue Starttermine
- `/manage`: Verwaltung von Lehrplänen und Kursen
- `/assign`: Zuweisung von Dozenten zu Kursen
- `/lecturers`: Dozentenverwaltung mit Verfügbarkeiten
- `/export-report`: Generierung von PDF-Berichten

#### Hilfsfunktionen
- `create_timeline_figure()`: Generiert die Plotly-Timeline
- `parse_date()`: Flexible Datumsverarbeitung
- `format_batch_name()`: Konsistente Batch-Benennung

### Frontend

#### Templates (`app/templates/`):
- `base.html`: Grundlayout mit Navigation
- `index.html`: Startseite mit Upload-Formular
- `timeline.html`: Anzeige der interaktiven Timeline
- `manage.html`: Lehrplanverwaltung
- `assign.html`: Dozentenzuweisung mit Konfliktmarkierung
- `lecturers.html`: Dozentenverwaltung
- `duplicate.html`: Duplizieren von Lehrplänen

#### Statische Elemente (`app/static/`):
- CSS-Dateien für Layout und Design
- JavaScript für interaktive Elemente
- Hilfsdateien für PDF-Export

### Datenvisualisierung
- Verwendung von Plotly für die interaktive Timeline
- Farbkodierung für Dozenten
- Markierung von Monaten für bessere Übersicht
- "Heute"-Markierung
- Hover-Informationen für Kurse

## Datenfluss

1. **Lehrplan-Upload**:
   - CSV-Datei → Parser → Datenbank (Courses)
   - Daten können mit Start-/Enddatum und Themen verarbeitet werden
   - Jeder Lehrplan erhält eine curriculum_id für Gruppierung

2. **Timeline-Generierung**:
   - Kurse aus DB → gruppiert nach Batch → Plotly Figure
   - Dozentenzuweisungen bestimmen Farbkodierung
   - Verfügbarkeiten werden als Überlagerungen dargestellt

3. **Dozentenzuweisung**:
   - Benutzer wählt Dozent → Konfliktprüfung → Speicherung in DB
   - Automatische Validierung verhindert Doppelbuchungen

## Dependencies

- Flask: Web-Framework
- SQLAlchemy: ORM für Datenbankoperationen
- Plotly: Datenvisualisierung/Timeline
- Pandas: Datenverarbeitung
- pdfkit/wkhtmltopdf: PDF-Generierung

## Erweiterungsmöglichkeiten

- **Benutzerauthentifizierung**: Login-System für verschiedene Nutzerrollen
- **API-Schnittstellen**: Anbindung an externe Systeme
- **Echtzeit-Benachrichtigungen**: für Konflikte oder Änderungen
- **Statistik-Dashboard**: Auswertung der Dozenteneinsätze
- **Automatische Planung**: KI-gestützte Vorschläge für Dozentenzuweisung

## Hinweise für AI-Agenten

### Wichtige Codebereiche
- `create_timeline_figure()`: Kern der Visualisierung, beliebte Anpassungsregion
- `save_curriculum()`: Kritisch für die Verarbeitung hochgeladener Dateien
- Konfliktprüfungslogik in der assign-Route

### Häufige Anpassungen
- Timeline-Design (Farben, Layout, Hover-Informationen)
- Erweiterung der exportierten PDF-Berichte
- Anpassung der Batch-Gruppierungslogik

### Potenzielle Fehlerquellen
- Datumsformatierung und -parsing
- Datenbank-Migrations-Issues bei Schemaänderungen
- PDF-Export erfordert konfigurierte wkhtmltopdf-Pfade

## Deployment-Hinweise
- Lokale Entwicklung über `python run.py`
- Datenbank-Reset über `flask init-db`
- Für Produktionsumgebungen Flask mit WSGI-Server und Proxy verwenden 