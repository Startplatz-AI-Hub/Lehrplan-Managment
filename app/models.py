from datetime import datetime
from . import db  # Importiere db aus dem app-Paket

class Lecturer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    color = db.Column(db.String(7), nullable=True)  # Für Hex-Farbcodes wie #FF5733
    assignments = db.relationship('Assignment', backref='lecturer', lazy=True)
    availabilities = db.relationship('Availability', backref='lecturer', lazy=True)

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    topic = db.Column(db.String(200), nullable=False)
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=False)
    lecturer_id = db.Column(db.Integer, db.ForeignKey('lecturer.id'), nullable=True)
    lecturer = db.relationship('Lecturer', backref='courses')
    curriculum_id = db.Column(db.String(36), nullable=False)  # Gruppierung zusammengehöriger Kurse
    active = db.Column(db.Boolean, default=False)  # Neu: Flag für Timeline-Sichtbarkeit

class Assignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lecturer_id = db.Column(db.Integer, db.ForeignKey('lecturer.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    @classmethod
    def get(cls, key, default=None):
        setting = cls.query.filter_by(key=key).first()
        return setting.value if setting else default

    @classmethod
    def set(cls, key, value):
        setting = cls.query.filter_by(key=key).first()
        if setting:
            setting.value = value
            setting.updated_at = datetime.utcnow()
        else:
            setting = cls(key=key, value=value)
            db.session.add(setting)
        db.session.commit()

class Availability(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lecturer_id = db.Column(db.Integer, db.ForeignKey('lecturer.id'))
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=False)
    type = db.Column(db.String(20))  # 'vacation' oder 'unavailable'
    note = db.Column(db.String(200)) 