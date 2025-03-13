from app import create_app, db
from app.models import Lecturer, Course, Assignment, Settings, Availability
import os

app = create_app()

@app.cli.command("init-db")
def init_db():
    """Initialisiere die Datenbank neu"""
    with app.app_context():
        db.drop_all()
        db.create_all()
        print("Datenbank wurde neu initialisiert!")

if __name__ == '__main__':
    # Get port from environment variable for Replit compatibility
    port = int(os.environ.get('PORT', 8080))
    # Host '0.0.0.0' for Replit to make the app accessible externally
    app.run(host='0.0.0.0', port=port, debug=False) 