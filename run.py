from app import create_app, db
from app.models import Lecturer, Course, Assignment, Settings, Availability

app = create_app()

@app.cli.command("init-db")
def init_db():
    """Initialisiere die Datenbank neu"""
    with app.app_context():
        db.drop_all()
        db.create_all()
        print("Datenbank wurde neu initialisiert!")

if __name__ == '__main__':
    app.run(debug=True) 