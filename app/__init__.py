from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from config import Config
import uuid

# Erstelle die SQLAlchemy-Instanz
db = SQLAlchemy()

def create_app():
    app = Flask(__name__,
                template_folder='templates',  # app/templates
                static_folder='static')       # app/static

    app.config.from_object(Config)

    # Initialisiere die Datenbank mit der App
    db.init_app(app)
    
    # Registriere die Blueprints
    from .routes import main
    app.register_blueprint(main)

    # Erstelle die Datenbanktabellen, falls sie nicht existieren
    with app.app_context():
        # Importiere models, damit die Tabellen erstellt werden können
        from . import models
        
        # Lösche und erstelle die Tabellen neu (nur beim ersten Start)
        import os
        if not os.path.exists('app.db'):
            db.create_all()
            
            # Füge Test-Kurs nur hinzu, wenn die Datenbank leer ist
            if not db.session.query(models.Course).first():
                from datetime import datetime, timedelta
                test_course = models.Course(
                    topic="Test-Kurs",
                    start_date=datetime.now(),
                    end_date=datetime.now() + timedelta(days=7),
                    curriculum_id=str(uuid.uuid4()),
                    active=True  # Setze den Test-Kurs als aktiv
                )
                db.session.add(test_course)
                db.session.commit()
        
    return app 