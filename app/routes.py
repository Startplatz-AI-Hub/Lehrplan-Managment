from flask import Blueprint, render_template, request, jsonify, current_app, redirect, url_for, flash, send_file, Response
from . import db
import pandas as pd
from datetime import datetime, timedelta
from .models import Course, Lecturer, Assignment, Settings, Availability
import plotly.express as px
from bson import ObjectId
import os
import uuid
import numpy as np
from jinja2 import Template
import pdfkit
from io import BytesIO
from functools import lru_cache
from sqlalchemy import func
import icalendar
from icalendar import Calendar, Event, vText
import tempfile

main = Blueprint('main', __name__)

# Am Anfang der Datei die Farbliste definieren
COLORS = [
    {"hex": "#FF0000", "name": "Rot"},
    {"hex": "#00FF00", "name": "Grün"},
    {"hex": "#0000FF", "name": "Blau"},
    {"hex": "#FF00FF", "name": "Magenta"},
    {"hex": "#00FFFF", "name": "Cyan"},
    {"hex": "#FFD700", "name": "Gold"},
    {"hex": "#FF8C00", "name": "Orange"},
    {"hex": "#800080", "name": "Lila"},
    {"hex": "#008000", "name": "Dunkelgrün"},
    {"hex": "#4B0082", "name": "Indigo"}
]

@lru_cache(maxsize=32)
def get_sorted_curriculum_courses(curriculum_id):
    """Cache für häufig abgefragte Kurssequenzen"""
    return db.session.query(Course)\
        .filter(Course.curriculum_id == curriculum_id)\
        .filter(Course.active == True)\
        .order_by(Course.start_date)\
        .all()

def create_timeline_figure(courses, filter_options=None):
    """Erstellt die Timeline-Figur basierend auf den Kursen
    
    Parameters:
    -----------
    courses : list
        Liste der Kursobjekte
    filter_options : dict, optional
        Filteroptionen, z.B. {'lecturer_id': 1, 'date_range': [start_date, end_date]}
    """
    batches = {}
    color_map = {}
    batch_counter = 1
    
    # Filter courses if filter_options provided
    if filter_options:
        filtered_courses = []
        for course in courses:
            # Filter by lecturer
            if filter_options.get('lecturer_id') and course.lecturer_id != filter_options['lecturer_id']:
                continue
            
            # Filter by date range
            if filter_options.get('date_range'):
                start_date, end_date = filter_options['date_range']
                if course.end_date < start_date or course.start_date > end_date:
                    continue
                    
            # Filter by curriculum
            if filter_options.get('curriculum_id') and course.curriculum_id != filter_options['curriculum_id']:
                continue
                
            filtered_courses.append(course)
        courses = filtered_courses
    
    # Sortiere courses nach Startdatum
    curriculum_start_dates = {}
    for course in courses:
        if course.curriculum_id not in curriculum_start_dates:
            first_course = min([c for c in courses if c.curriculum_id == course.curriculum_id],
                             key=lambda x: x.start_date)
            curriculum_start_dates[course.curriculum_id] = first_course.start_date

    sorted_curriculum_ids = sorted(curriculum_start_dates.keys(), 
                                 key=lambda x: curriculum_start_dates[x])

    # Verarbeite Kurse in der sortierten Reihenfolge
    for curriculum_id in sorted_curriculum_ids:
        curriculum_courses = [c for c in courses if c.curriculum_id == curriculum_id]
        if not curriculum_courses:
            continue
            
        first_course = min(curriculum_courses, key=lambda x: x.start_date)
        batch_start = first_course.start_date
        
        # Format batch name with more details
        semester = "WS" if batch_start.month > 6 else "SS"
        year = batch_start.year
        batches[curriculum_id] = {
            'start_date': batch_start,
            'name': f"Batch {batch_counter} ({semester} {year}, Start: {batch_start.strftime('%d.%m.%Y')})",
            'courses': []
        }
        batch_counter += 1
        
        for course in curriculum_courses:
            lecturer_name = course.lecturer.name if course.lecturer else 'Nicht zugewiesen'
            if course.lecturer:
                color_map[lecturer_name] = course.lecturer.color or '#808080'
            
            # Calculate course duration in days
            duration_days = (course.end_date - course.start_date).days + 1
            
            batches[curriculum_id]['courses'].append({
                'Batch': batches[curriculum_id]['name'],
                'Thema': course.topic,
                'Start': course.start_date,
                'End': course.end_date,
                'Dozent': lecturer_name,
                'Dauer': f"{duration_days} Tage",
                'ID': course.id  # Add course ID for linking
            })

    # Erstelle DataFrame
    timeline_data = []
    sorted_batches = sorted(batches.values(), key=lambda x: x['start_date'])
    for batch in sorted_batches:
        timeline_data.extend(batch['courses'])
    
    if not timeline_data:
        # Create empty figure with message if no data is available
        empty_fig = px.scatter(title="Keine Kurse gefunden - Bitte passen Sie die Filter an")
        empty_fig.update_layout(
            height=400,
            annotations=[{
                'text': "Keine Kurse für die aktuellen Filtereinstellungen gefunden",
                'showarrow': False,
                'font': {'size': 16},
                'xref': 'paper',
                'yref': 'paper',
                'x': 0.5,
                'y': 0.5
            }]
        )
        return empty_fig
    
    df = pd.DataFrame(timeline_data)

    # Adaptive height based on number of batches
    min_height = max(600, len(batches) * 120)
    if len(batches) <= 2:
        min_height = 400  # Kompaktere Darstellung für wenige Batches
    
    fig = px.timeline(df,
                     x_start='Start',
                     x_end='End',
                     y='Batch',
                     color='Dozent',
                     hover_name='Thema',
                     color_discrete_map=color_map,
                     category_orders={'Batch': [b['name'] for b in sorted_batches]},
                     height=min_height,
                     custom_data=['ID', 'Dauer'])  # Add custom data for JavaScript interaction

    # Verbesserte Lesbarkeit der Zeitachse mit Wochenenden markiert
    fig.update_xaxes(
        tickangle=45,
        tickfont=dict(size=11),
        gridcolor='rgba(0,0,0,0.05)',
        minor_gridcolor='rgba(0,0,0,0.02)'
    )

    # Berechne Zeitbereiche
    tick_start = df['Start'].min().normalize() - pd.Timedelta(days=df['Start'].min().weekday())
    tick_end = df['End'].max().normalize() + pd.Timedelta(days=(7 - df['End'].max().weekday() - 1))
    months = pd.date_range(start=tick_start, end=tick_end, freq='MS')
    
    # Erstelle Shapes für Monatsmarkierungen und heute-Linie
    shapes = []
    
    # Monthly rectangles
    for i, month_start in enumerate(months):
        month_end = (month_start + pd.offsets.MonthEnd(1))
        month_name = month_start.strftime('%b %Y')
        shapes.append({
            'type': 'rect',
            'x0': month_start,
            'x1': month_end,
            'y0': -0.5,
            'y1': len(batches) - 0.5,
            'xref': 'x',
            'yref': 'y',
            'fillcolor': 'rgba(240,240,250,0.5)' if i % 2 == 0 else 'rgba(255,255,255,0.8)',
            'line': {'width': 0},
            'layer': 'below'
        })
        
        # Add month name annotation
        fig.add_annotation(
            x=month_start + (month_end - month_start) / 2,
            y=len(batches) - 0.2,
            text=month_name,
            showarrow=False,
            font=dict(size=10, color="rgba(0,0,0,0.6)"),
            bgcolor="rgba(255,255,255,0.7)",
            borderpad=2
        )
    
    # Add weekend highlights
    weekends = pd.date_range(start=tick_start, end=tick_end, freq='D')
    for weekend in weekends:
        if weekend.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
            shapes.append({
                'type': 'rect',
                'x0': weekend,
                'x1': weekend + pd.Timedelta(days=1),
                'y0': -0.5,
                'y1': len(batches) - 0.5,
                'xref': 'x',
                'yref': 'y',
                'fillcolor': 'rgba(255,235,235,0.5)',
                'line': {'width': 0},
                'layer': 'below'
            })

    # Today marker with enhanced visibility
    today = datetime.now()
    shapes.append({
        'type': 'line',
        'x0': today,
        'x1': today,
        'y0': -0.5,
        'y1': len(batches) - 0.5,
        'xref': 'x',
        'yref': 'y',
        'line': {
            'color': 'rgba(220,53,69,0.8)',
            'width': 2,
            'dash': 'solid'
        },
        'layer': 'above'
    })
    
    # Add "Today" label
    fig.add_annotation(
        x=today,
        y=-0.4,
        text="Heute",
        showarrow=True,
        arrowhead=1,
        arrowsize=1,
        arrowwidth=2,
        arrowcolor="rgba(220,53,69,0.8)",
        font=dict(size=10, color="rgba(220,53,69,1)"),
        bgcolor="white",
        bordercolor="rgba(220,53,69,0.8)",
        borderwidth=1,
        borderpad=4
    )

    # Füge Verfügbarkeiten hinzu mit verbesserter Lesbarkeit
    availabilities = Availability.query.all()
    for availability in availabilities:
        # Skip if outside visible range
        if availability.end_date < tick_start or availability.start_date > tick_end:
            continue
            
        availability_type = 'Urlaub' if availability.type == 'vacation' else 'Nicht verfügbar'
        fill_color = 'rgba(255,165,0,0.15)' if availability.type == 'vacation' else 'rgba(255,0,0,0.15)'
        line_color = 'rgba(255,165,0,0.6)' if availability.type == 'vacation' else 'rgba(255,0,0,0.6)'
        
        shapes.append({
            'type': 'rect',
            'x0': availability.start_date,
            'x1': availability.end_date,
            'y0': -0.5,
            'y1': len(batches) - 0.5,
            'xref': 'x',
            'yref': 'y',
            'fillcolor': fill_color,
            'line': {'width': 1, 'color': line_color},
            'layer': 'below',
            'name': f"{availability.lecturer.name}: {availability_type}"
        })
        
        # Add label for longer availability periods
        if (availability.end_date - availability.start_date).days >= 3:
            mid_point = availability.start_date + (availability.end_date - availability.start_date) / 2
            fig.add_annotation(
                x=mid_point,
                y=len(batches) - 0.5,
                text=f"{availability.lecturer.name}: {availability_type}",
                showarrow=False,
                font=dict(size=9, color="rgba(0,0,0,0.6)"),
                bgcolor="rgba(255,255,255,0.7)",
                borderpad=2,
                opacity=0.7
            )

    # Update Layout
    fig.update_layout(
        shapes=shapes,
        plot_bgcolor='white',
        paper_bgcolor='white',
        showlegend=True,
        legend_title_text='<b>Dozenten</b>',
        title={
            'text': '<b>Lehrplan Timeline</b>',
            'y': 0.95,
            'x': 0.5,
            'xanchor': 'center',
            'yanchor': 'top',
            'font': dict(size=20, family="Arial, sans-serif")
        },
        margin=dict(l=200, r=150, t=100, b=50),
        hovermode='closest'
    )

    # Optimiere Hover-Info
    fig.update_traces(
        hovertemplate="<b>%{hovertext}</b><br>" +
                     "<span style='color:rgba(0,0,0,0.6)'>Zeitraum:</span> %{base|%d.%m.%Y} - %{x|%d.%m.%Y}<br>" +
                     "<span style='color:rgba(0,0,0,0.6)'>Dauer:</span> %{customdata[1]}<br>" +
                     "<span style='color:rgba(0,0,0,0.6)'>Dozent:</span> %{color}<extra></extra>",
        marker=dict(line=dict(width=1, color='rgba(0,0,0,0.1)')),
        opacity=0.9
    )

    return fig

@main.route('/')
def index():
    return render_template('index.html')

@main.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        flash('Keine Datei hochgeladen', 'error')
        return redirect(url_for('main.index'))
    
    file = request.files['file']
    if file.filename == '':
        flash('Keine Datei ausgewählt', 'error')
        return redirect(url_for('main.index'))

    try:
        # Lese CSV ein
        df = pd.read_csv(file)
        
        # Überprüfe erforderliche Spalten
        required_columns = ['Startdatum', 'Enddatum', 'Thema']
        if not all(col in df.columns for col in required_columns):
            raise Exception(f"CSV muss die Spalten {', '.join(required_columns)} enthalten")
        
        start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d')
        duplicate_count = int(request.form.get('duplicate_count', 0))

        # Berechne Lehrplandauer
        first_start = pd.to_datetime(df['Startdatum'].iloc[0], format='%d.%m.%Y')
        last_end = pd.to_datetime(df['Enddatum'].iloc[-1], format='%d.%m.%Y')
        duration = (last_end - first_start).days

        # Speichere Original und Duplikate
        save_curriculum(df, start_date)
        for i in range(duplicate_count):
            new_start = start_date + timedelta(days=(duration + 1) * (i + 1))
            save_curriculum(df, new_start)

        flash('Lehrplan erfolgreich hochgeladen!', 'success')
        return redirect(url_for('main.show_timeline'))

    except Exception as e:
        flash(f'Fehler beim Upload: {str(e)}', 'error')
        return redirect(url_for('main.index'))

def save_curriculum(df, start_date):
    """Hilfsfunktion zum Speichern eines Lehrplans mit angepasstem Startdatum"""
    # Generiere eine eindeutige ID für diesen Lehrplan
    curriculum_id = str(uuid.uuid4())
    
    original_start = pd.to_datetime(df['Startdatum'].iloc[0], format='%d.%m.%Y')
    date_diff = start_date - original_start

    for _, row in df.iterrows():
        new_start = pd.to_datetime(row['Startdatum'], format='%d.%m.%Y') + date_diff
        new_end = pd.to_datetime(row['Enddatum'], format='%d.%m.%Y') + date_diff
        
        course = Course(
            topic=row['Thema'],
            start_date=new_start,
            end_date=new_end,
            curriculum_id=curriculum_id,
            active=True  # Neue Kurse sind standardmäßig aktiv
        )
        db.session.add(course)
    
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Error saving curriculum: {str(e)}")
        raise

@main.route('/add_lecturer', methods=['GET', 'POST'])
def add_lecturer():
    if request.method == 'POST':
        try:
            name = request.form.get('name')
            color = request.form.get('color')
            
            if not name or not color:
                flash('Name und Farbe sind erforderlich', 'error')
                return redirect(url_for('main.add_lecturer'))
            
            # Prüfe ob Farbe bereits verwendet
            existing = db.session.query(Lecturer).filter_by(color=color).first()
            if existing:
                flash('Diese Farbe ist bereits vergeben!', 'error')
                return redirect(url_for('main.add_lecturer'))
            
            lecturer = Lecturer(name=name, color=color)
            db.session.add(lecturer)
            db.session.commit()
            
            flash('Dozent erfolgreich hinzugefügt!', 'success')
            return redirect(url_for('main.assign'))
            
        except Exception as e:
            flash(f'Fehler: {str(e)}', 'error')
            return redirect(url_for('main.add_lecturer'))

    # Hole verfügbare Farben
    used_colors = {l.color for l in db.session.query(Lecturer).all()}
    available_colors = [c for c in COLORS if c['hex'] not in used_colors]
    
    return render_template('add_lecturer.html', available_colors=available_colors)

@main.route('/assign', methods=['GET', 'POST'])
def assign():
    if request.method == 'POST':
        try:
            assignments = request.form.getlist('assignments[]')  # Format: "course_id:lecturer_id"
            
            for assignment in assignments:
                if not assignment:  # Überspringe leere Zuweisungen
                    continue
                    
                course_id, lecturer_id = assignment.split(':')
                course = db.session.query(Course).get(course_id)
                
                if lecturer_id == "0":  # Dozent entfernen
                    course.lecturer_id = None
                else:
                    # Prüfe auf Konflikte
                    conflicting_course = db.session.query(Course).filter(
                        Course.lecturer_id == lecturer_id,
                        Course.id != course.id,
                        Course.start_date < course.end_date,
                        Course.end_date > course.start_date
                    ).first()
                    
                    if conflicting_course:
                        flash(f'Konflikt: {course.topic} überschneidet sich mit {conflicting_course.topic}', 'error')
                        continue
                        
                    course.lecturer_id = lecturer_id
            
            db.session.commit()
            flash('Zuweisungen erfolgreich aktualisiert!', 'success')
            
        except Exception as e:
            db.session.rollback()
            flash(f'Fehler bei der Zuweisung: {str(e)}', 'error')
            
        return redirect(url_for('main.assign'))

    # Gruppiere Kurse nach curriculum_id für bessere Übersicht
    curricula = db.session.query(
        Course.curriculum_id,
        db.func.min(Course.start_date).label('start_date'),
        db.func.count(Course.id).label('course_count')
    ).group_by(Course.curriculum_id)\
     .order_by('start_date')\
     .all()
     
    courses = db.session.query(Course).order_by(Course.start_date).all()
    lecturers = db.session.query(Lecturer).all()
    
    # Erstelle ein Dict mit allen Konflikten
    conflicts = {}
    for course in courses:
        if course.lecturer_id:
            conflicts[course.id] = []
            for other_course in courses:
                if (other_course.id != course.id and 
                    other_course.lecturer_id == course.lecturer_id and
                    other_course.start_date < course.end_date and
                    other_course.end_date > course.start_date):
                    conflicts[course.id].append(other_course)
    
    return render_template('assign.html', 
                         curricula=curricula,
                         courses=courses,
                         lecturers=lecturers,
                         conflicts=conflicts)

@main.route('/timeline')
def show_timeline():
    courses = db.session.query(Course)\
        .filter(Course.active == True)\
        .order_by(Course.curriculum_id, Course.start_date)\
        .all()

    if not courses:
        flash('Keine aktiven Kurse in der Timeline.', 'info')
        return redirect(url_for('main.manage_curriculum'))

    # Get filter options
    filter_options = {}
    if request.args.get('lecturer_id'):
        filter_options['lecturer_id'] = int(request.args.get('lecturer_id'))
    if request.args.get('curriculum_id'):
        filter_options['curriculum_id'] = request.args.get('curriculum_id')
    if request.args.get('start_date') and request.args.get('end_date'):
        start_date = datetime.strptime(request.args.get('start_date'), '%Y-%m-%d')
        end_date = datetime.strptime(request.args.get('end_date'), '%Y-%m-%d')
        filter_options['date_range'] = [start_date, end_date]

    # Get all lecturers and curricula for filter form
    lecturers = Lecturer.query.all()
    curricula = db.session.query(
        Course.curriculum_id,
        db.func.min(Course.start_date).label('start_date')
    ).filter(Course.active == True).group_by(Course.curriculum_id).all()

    fig = create_timeline_figure(courses, filter_options)

    return render_template('timeline.html',
                         timeline=fig.to_html(
                             full_html=False,
                             include_plotlyjs=True,
                             config={
                                 'displayModeBar': True,
                                 'scrollZoom': True,
                                 'modeBarButtonsToAdd': [
                                     'resetScale2d',
                                     'zoomIn2d',
                                     'zoomOut2d',
                                     'pan2d',
                                     'toImage'
                                 ],
                                 'displaylogo': False,
                                 'toImageButtonOptions': {
                                     'format': 'svg',
                                     'filename': 'Lehrplan_Timeline',
                                     'height': 1080,
                                     'width': 1920,
                                     'scale': 2
                                 }
                             }
                         ),
                         lecturers=lecturers,
                         curricula=curricula)

@main.route('/download-template')
def download_template():
    template_content = "Thema,Startdatum,Enddatum\n" \
                      "Einführung Python,01.01.2024,05.01.2024\n" \
                      "Datenstrukturen,08.01.2024,12.01.2024\n" \
                      "Algorithmen,15.01.2024,19.01.2024"
    
    # Erstelle temporäre Datei
    template_path = os.path.join(current_app.root_path, 'static', 'downloads')
    os.makedirs(template_path, exist_ok=True)
    file_path = os.path.join(template_path, 'lehrplan_vorlage.csv')
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(template_content)
    
    return send_file(file_path,
                    mimetype='text/csv',
                    as_attachment=True,
                    download_name='lehrplan_vorlage.csv')

@main.route('/duplicate', methods=['GET', 'POST'])
def duplicate_curriculum():
    if request.method == 'POST':
        try:
            start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d')
            curriculum_id = request.form.get('curriculum_id')
            
            # Hole alle Kurse des ausgewählten Lehrplans
            source_courses = db.session.query(Course)\
                .filter(Course.curriculum_id == curriculum_id)\
                .order_by(Course.start_date)\
                .all()
            
            if not source_courses:
                flash('Keine Kurse für den ausgewählten Lehrplan gefunden.', 'error')
                return redirect(url_for('main.duplicate_curriculum'))
            
            # Berechne Zeitdifferenz
            date_diff = start_date - source_courses[0].start_date
            
            # Generiere neue curriculum_id für das Duplikat
            new_curriculum_id = str(uuid.uuid4())
            
            # Dupliziere jeden Kurs mit neuem Startdatum
            for source_course in source_courses:
                new_course = Course(
                    topic=source_course.topic,
                    start_date=source_course.start_date + date_diff,
                    end_date=source_course.end_date + date_diff,
                    lecturer_id=source_course.lecturer_id,
                    curriculum_id=new_curriculum_id,
                    active=source_course.active  # Kopiere active-Status
                )
                db.session.add(new_course)
            
            db.session.commit()
            flash('Lehrplan erfolgreich dupliziert!', 'success')
            return redirect(url_for('main.show_timeline'))
            
        except Exception as e:
            flash(f'Fehler beim Duplizieren: {str(e)}', 'error')
            return redirect(url_for('main.duplicate_curriculum'))
    
    # Hole alle unterschiedlichen Lehrpläne für die Auswahl
    curricula = db.session.query(
        Course.curriculum_id,
        db.func.min(Course.start_date).label('start_date'),
        db.func.count(Course.id).label('course_count')
    ).group_by(Course.curriculum_id)\
     .order_by('start_date')\
     .all()
    
    return render_template('duplicate.html', curricula=curricula)

@main.route('/manage', methods=['GET', 'POST', 'DELETE'])
def manage_curriculum():
    if request.method == 'POST':
        try:
            action = request.form.get('action')
            
            if action == 'toggle_timeline':
                curriculum_id = request.form.get('curriculum_id')
                show_in_timeline = request.form.get('show_in_timeline') == 'true'
                
                # Aktualisiere alle Kurse des Lehrplans
                db.session.query(Course)\
                    .filter(Course.curriculum_id == curriculum_id)\
                    .update({Course.active: show_in_timeline})
                
                db.session.commit()
                flash('Timeline-Ansicht aktualisiert!', 'success')
                return redirect(url_for('main.manage_curriculum'))
            
            course_id = request.form.get('course_id')
            course = db.session.query(Course).get(course_id)
            
            if not course:
                flash('Kurs nicht gefunden.', 'error')
                return redirect(url_for('main.manage_curriculum'))
            
            if action == 'delete':
                db.session.delete(course)
                db.session.commit()
                flash('Kurs erfolgreich gelöscht!', 'success')
                
            elif action == 'update':
                # Update Kurs
                course.topic = request.form.get('topic')
                course.start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d')
                course.end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d')
                db.session.commit()
                flash('Kurs erfolgreich aktualisiert!', 'success')
                
            return redirect(url_for('main.manage_curriculum'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Fehler: {str(e)}', 'error')
            return redirect(url_for('main.manage_curriculum'))
    
    # Gruppiere Kurse nach Lehrplan statt nach Datum
    curricula = {}
    courses = db.session.query(Course).order_by(Course.start_date).all()
    
    for course in courses:
        if course.curriculum_id not in curricula:
            start_date = course.start_date
            curricula[course.curriculum_id] = {
                'start_date': start_date,
                'courses': [],
                'active': course.active,
                'batch_name': f"Batch {len(curricula) + 1}"
            }
        curricula[course.curriculum_id]['courses'].append(course)
    
    return render_template('manage.html', curricula=curricula)

@main.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        try:
            # Speichere Standard-Arbeitszeiten
            Settings.set('working_hours_start', request.form.get('working_hours_start', '09:00'))
            Settings.set('working_hours_end', request.form.get('working_hours_end', '17:00'))
            Settings.set('working_days', ','.join(request.form.getlist('working_days')))
            
            # Speichere Farbschema
            Settings.set('color_scheme', request.form.get('color_scheme', 'default'))
            
            # Speichere Benachrichtigungseinstellungen
            Settings.set('notify_conflicts', request.form.get('notify_conflicts', 'true'))
            Settings.set('notify_assignments', request.form.get('notify_assignments', 'true'))
            
            flash('Einstellungen gespeichert!', 'success')
        except Exception as e:
            flash(f'Fehler beim Speichern: {str(e)}', 'error')
        
        return redirect(url_for('main.settings'))
    
    return render_template('settings.html', 
                         settings={
                             'working_hours_start': Settings.get('working_hours_start', '09:00'),
                             'working_hours_end': Settings.get('working_hours_end', '17:00'),
                             'working_days': Settings.get('working_days', '1,2,3,4,5').split(','),
                             'color_scheme': Settings.get('color_scheme', 'default'),
                             'notify_conflicts': Settings.get('notify_conflicts', 'true'),
                             'notify_assignments': Settings.get('notify_assignments', 'true')
                         })

@main.route('/export-report', methods=['GET', 'POST'])
def export_report():
    try:
        # Get filter parameters
        filter_options = {}
        if request.method == 'POST':
            if request.form.get('lecturer_id'):
                filter_options['lecturer_id'] = int(request.form.get('lecturer_id'))
            if request.form.get('curriculum_id'):
                filter_options['curriculum_id'] = request.form.get('curriculum_id')
            if request.form.get('start_date') and request.form.get('end_date'):
                start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d')
                end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d')
                filter_options['date_range'] = [start_date, end_date]
            
            report_type = request.form.get('report_type', 'standard')
            include_statistics = request.form.get('include_statistics') == 'on'
            include_availabilities = request.form.get('include_availabilities') == 'on'
        else:
            report_type = request.args.get('report_type', 'standard')
            include_statistics = request.args.get('include_statistics') == 'true'
            include_availabilities = request.args.get('include_availabilities') == 'true'
        
        # Debug logging
        current_app.logger.info(f"Export report requested - Type: {report_type}, Stats: {include_statistics}, Avail: {include_availabilities}")
        current_app.logger.info(f"Filter options: {filter_options}")
        
        # Check for wkhtmltopdf
        wkhtmltopdf_path = os.environ.get('WKHTMLTOPDF_PATH', r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe')
        current_app.logger.info(f"Using wkhtmltopdf path: {wkhtmltopdf_path}")
        
        if not os.path.exists(wkhtmltopdf_path):
            error_msg = f'wkhtmltopdf nicht gefunden unter {wkhtmltopdf_path}. Bitte installieren Sie wkhtmltopdf oder prüfen Sie den Pfad.'
            current_app.logger.error(error_msg)
            flash(error_msg, 'error')
            return redirect(url_for('main.show_timeline'))
        
        try:    
            config = pdfkit.configuration(wkhtmltopdf=wkhtmltopdf_path)
            current_app.logger.info("PDF configuration created successfully")
        except Exception as config_error:
            error_msg = f"Fehler bei der Konfiguration von pdfkit: {str(config_error)}"
            current_app.logger.error(error_msg)
            flash(error_msg, 'error')
            return redirect(url_for('main.show_timeline'))
            
        # Hole aktive Kurse basierend auf den Filteroptionen
        query = db.session.query(Course).filter(Course.active == True)
        
        if filter_options.get('lecturer_id'):
            query = query.filter(Course.lecturer_id == filter_options['lecturer_id'])
        
        if filter_options.get('curriculum_id'):
            query = query.filter(Course.curriculum_id == filter_options['curriculum_id'])
            
        if filter_options.get('date_range'):
            start_date, end_date = filter_options['date_range']
            query = query.filter(Course.end_date >= start_date, Course.start_date <= end_date)
            
        courses = query.order_by(Course.curriculum_id, Course.start_date).all()
        current_app.logger.info(f"Found {len(courses)} courses matching filter criteria")
        
        if not courses:
            flash('Keine Kurse gefunden, die den Filterkriterien entsprechen.', 'warning')
            return redirect(url_for('main.show_timeline'))

        # Statistikdaten sammeln, wenn gewünscht
        statistics_data = {}
        if include_statistics:
            # Kursstatistiken
            total_days = 0
            course_count = len(courses)
            for course in courses:
                delta = (course.end_date - course.start_date).days
                total_days += delta if delta > 0 else 1
            
            avg_duration = round(total_days / course_count, 1) if course_count > 0 else 0
            
            # Dozentenstatistiken
            lecturer_stats = {}
            for course in courses:
                if course.lecturer_id and course.lecturer:
                    lecturer_id = course.lecturer_id
                    if lecturer_id not in lecturer_stats:
                        lecturer_stats[lecturer_id] = {
                            'name': course.lecturer.name,
                            'color': course.lecturer.color or '#808080',
                            'course_count': 0,
                            'total_days': 0
                        }
                    
                    lecturer_stats[lecturer_id]['course_count'] += 1
                    lecturer_stats[lecturer_id]['total_days'] += (course.end_date - course.start_date).days + 1
            
            # Sortiere nach Gesamttagen (absteigend)
            top_lecturers = sorted(
                lecturer_stats.values(), 
                key=lambda x: x['total_days'], 
                reverse=True
            )[:5]  # Top 5 Dozenten
            
            # Kursthemenstatistiken
            topic_stats = {}
            for course in courses:
                if course.topic not in topic_stats:
                    topic_stats[course.topic] = 0
                topic_stats[course.topic] += 1
            
            # Sortiere nach Häufigkeit (absteigend)
            top_topics = sorted(
                [{'topic': topic, 'count': count} for topic, count in topic_stats.items()],
                key=lambda x: x['count'],
                reverse=True
            )[:5]  # Top 5 Themen
            
            statistics_data = {
                'course_count': course_count,
                'avg_duration': avg_duration,
                'total_days': total_days,
                'top_lecturers': top_lecturers,
                'top_topics': top_topics
            }
        
        # Verfügbarkeiten
        availabilities = []
        if include_availabilities:
            # Alle relevanten Verfügbarkeiten finden
            all_lecturers = set()
            for course in courses:
                if course.lecturer_id:
                    all_lecturers.add(course.lecturer_id)
            
            # Zeitbereich bestimmen
            min_date = min([course.start_date for course in courses])
            max_date = max([course.end_date for course in courses])
            
            # Verfügbarkeiten abfragen
            availabilities = db.session.query(Availability)\
                .filter(Availability.lecturer_id.in_(all_lecturers))\
                .filter(Availability.end_date >= min_date, Availability.start_date <= max_date)\
                .order_by(Availability.start_date)\
                .all()

        # Erstelle Timeline-Bild
        try:
            fig = create_timeline_figure(courses, filter_options)
            # Reduce image quality to avoid rendering issues with wkhtmltopdf
            timeline_img = fig.to_image(format="png", width=1000, height=500, scale=1.5)
            import base64
            timeline_image = base64.b64encode(timeline_img).decode('utf-8')
            current_app.logger.info("Timeline image created successfully")
        except Exception as img_error:
            error_msg = f"Fehler beim Erstellen des Timeline-Bildes: {str(img_error)}"
            current_app.logger.error(error_msg)
            flash(error_msg, 'error')
            return redirect(url_for('main.show_timeline'))

        # Organisiere Kurse nach Batches
        batches = []
        current_batch = None
        
        # Zuerst nach curriculum_id gruppieren
        curriculum_courses = {}
        for course in courses:
            if course.curriculum_id not in curriculum_courses:
                curriculum_courses[course.curriculum_id] = []
            curriculum_courses[course.curriculum_id].append(course)
        
        # Dann nach Startdatum des ersten Kurses sortieren
        sorted_curriculum_ids = sorted(
            curriculum_courses.keys(),
            key=lambda cid: min([c.start_date for c in curriculum_courses[cid]])
        )
        
        # Batches erstellen
        for i, curriculum_id in enumerate(sorted_curriculum_ids):
            first_course = min(curriculum_courses[curriculum_id], key=lambda c: c.start_date)
            
            # Batch-Name formatieren
            semester = "SoSe" if first_course.start_date.month >= 3 and first_course.start_date.month <= 8 else "WiSe"
            year = first_course.start_date.year
            
            batches.append({
                'curriculum_id': curriculum_id,
                'name': f"Batch {i + 1} ({semester} {year})",
                'start_date': first_course.start_date,
                'courses': sorted(curriculum_courses[curriculum_id], key=lambda c: c.start_date)
            })

        # Wähle das richtige Template basierend auf dem Berichtstyp
        try:
            if report_type == 'lecturer':
                report_template_path = 'pdf_templates/lecturer_report.html'
            elif report_type == 'curriculum':
                report_template_path = 'pdf_templates/curriculum_report.html'
            else:
                report_template_path = 'pdf_templates/standard_report.html'

            # Stelle sicher, dass die Verzeichnisse existieren
            pdf_template_dir = os.path.join(current_app.root_path, 'templates', 'pdf_templates')
            os.makedirs(pdf_template_dir, exist_ok=True)
            current_app.logger.info(f"Template directory created at: {pdf_template_dir}")

            # Wähle das Standard-Template, wenn die spezielle Vorlage nicht existiert
            report_template_path = os.path.join(current_app.root_path, 'templates', report_template_path)
            current_app.logger.info(f"Attempting to load template from: {report_template_path}")
            
            if not os.path.exists(report_template_path):
                report_template_path = os.path.join(current_app.root_path, 'templates', 'pdf_templates/standard_report.html')
                current_app.logger.info(f"Falling back to standard template: {report_template_path}")
                
                if not os.path.exists(report_template_path):
                    # Erstelle das Standard-Template, wenn es nicht existiert
                    current_app.logger.info("Standard template not found, creating it")
                    os.makedirs(os.path.dirname(report_template_path), exist_ok=True)
                    with open(report_template_path, 'w', encoding='utf-8') as f:
                        f.write(get_standard_report_template())
            
            # Lese Template-Inhalt
            with open(report_template_path, 'r', encoding='utf-8') as f:
                report_template = f.read()
                current_app.logger.info(f"Template loaded, size: {len(report_template)} bytes")
        except Exception as template_error:
            error_msg = f"Fehler beim Laden des Templates: {str(template_error)}"
            current_app.logger.error(error_msg)
            flash(error_msg, 'error')
            return redirect(url_for('main.show_timeline'))

        # Rendere Template
        try:
            template = Template(report_template)
            current_app.logger.info("Template object created")
            
            render_context = {
                'current_date': datetime.now().strftime('%d.%m.%Y'),
                'timeline_image': timeline_image,
                'batches': batches,
                'statistics': statistics_data,
                'availabilities': availabilities,
                'include_statistics': include_statistics,
                'include_availabilities': include_availabilities,
                'report_type': report_type
            }
            current_app.logger.info(f"Rendering template with context (image size: {len(timeline_image)} bytes)")
            
            html_content = template.render(**render_context)
            current_app.logger.info(f"Template rendered, HTML size: {len(html_content)} bytes")
        except Exception as render_error:
            error_msg = f"Fehler beim Rendern des Templates: {str(render_error)}"
            current_app.logger.error(error_msg)
            flash(error_msg, 'error')
            return redirect(url_for('main.show_timeline'))

        # PDF-Optionen
        pdf_options = {
            'page-size': 'A4',
            'margin-top': '20mm',
            'margin-right': '20mm',
            'margin-bottom': '20mm',
            'margin-left': '20mm',
            'encoding': 'UTF-8',
            'title': 'Lehrplan Bericht',
            'footer-right': '[page]/[topage]',
            'footer-left': f'Erstellt am {datetime.now().strftime("%d.%m.%Y")}',
            'footer-font-size': '8',
            'header-html': '',
            'footer-line': '',
            'disable-smart-shrinking': '',  # This helps with image rendering
            'no-stop-slow-scripts': '',     # Prevent timeout on complex scripts
            'quiet': ''
        }

        # Convert to PDF with configuration
        try:
            current_app.logger.info("Attempting to generate PDF from HTML content")
            
            # Try to save the HTML content to a temporary file and convert that instead
            # This approach often works better for complex content
            with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as temp_html:
                temp_html_path = temp_html.name
                temp_html.write(html_content.encode('utf-8'))
                
            current_app.logger.info(f"Saved HTML to temporary file: {temp_html_path}")
            
            try:
                # Try file-based conversion first (often more reliable with large content)
                pdf = pdfkit.from_file(temp_html_path, False, options=pdf_options, configuration=config)
                current_app.logger.info("PDF generated successfully from file")
            except Exception as file_error:
                current_app.logger.warning(f"File-based PDF generation failed: {str(file_error)}. Trying string method...")
                # Fall back to string-based conversion
                pdf = pdfkit.from_string(html_content, False, options=pdf_options, configuration=config)
                current_app.logger.info("PDF generated successfully from string")
            
            # Clean up temporary file
            try:
                os.unlink(temp_html_path)
            except:
                pass
                
        except Exception as pdf_error:
            error_msg = f"Fehler beim Erstellen des PDFs: {str(pdf_error)}"
            current_app.logger.error(error_msg)
            flash(error_msg, 'error')
            return redirect(url_for('main.show_timeline'))

        # Send PDF
        try:
            pdf_io = BytesIO(pdf)
            pdf_io.seek(0)
            
            # Generate filename based on filter options
            filename_parts = ['Lehrplan_Bericht']
            if filter_options.get('lecturer_id'):
                lecturer = Lecturer.query.get(filter_options['lecturer_id'])
                if lecturer:
                    filename_parts.append(f"Dozent_{lecturer.name.replace(' ', '_')}")
            
            if filter_options.get('curriculum_id'):
                filename_parts.append(f"Batch_{filter_options['curriculum_id'][:8]}")
                
            if filter_options.get('date_range'):
                start, end = filter_options['date_range']
                filename_parts.append(f"{start.strftime('%Y%m%d')}-{end.strftime('%Y%m%d')}")
                
            filename = '_'.join(filename_parts) + '.pdf'
            current_app.logger.info(f"Sending PDF with filename: {filename}")
            
            return send_file(
                pdf_io,
                download_name=filename,
                mimetype='application/pdf'
            )
        except Exception as send_error:
            error_msg = f"Fehler beim Senden des PDFs: {str(send_error)}"
            current_app.logger.error(error_msg)
            flash(error_msg, 'error')
            return redirect(url_for('main.show_timeline'))

    except Exception as e:
        error_msg = f'Fehler beim Erstellen des PDF-Berichts: {str(e)}'
        current_app.logger.error(error_msg)
        flash(error_msg, 'error')
        return redirect(url_for('main.show_timeline'))

@main.route('/export-report-html', methods=['GET', 'POST'])
def export_report_html():
    """
    Alternative export method that returns HTML directly instead of attempting PDF conversion.
    This can help diagnose if the issue is with pdfkit or with the template rendering.
    """
    try:
        # Get filter parameters
        filter_options = {}
        if request.method == 'POST':
            if request.form.get('lecturer_id'):
                filter_options['lecturer_id'] = int(request.form.get('lecturer_id'))
            if request.form.get('curriculum_id'):
                filter_options['curriculum_id'] = request.form.get('curriculum_id')
            if request.form.get('start_date') and request.form.get('end_date'):
                start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d')
                end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d')
                filter_options['date_range'] = [start_date, end_date]
            
            report_type = request.form.get('report_type', 'standard')
            include_statistics = request.form.get('include_statistics') == 'on'
            include_availabilities = request.form.get('include_availabilities') == 'on'
        else:
            report_type = request.args.get('report_type', 'standard')
            include_statistics = request.args.get('include_statistics') == 'true'
            include_availabilities = request.args.get('include_availabilities') == 'true'
        
        # Hole aktive Kurse basierend auf den Filteroptionen
        query = db.session.query(Course).filter(Course.active == True)
        
        if filter_options.get('lecturer_id'):
            query = query.filter(Course.lecturer_id == filter_options['lecturer_id'])
        
        if filter_options.get('curriculum_id'):
            query = query.filter(Course.curriculum_id == filter_options['curriculum_id'])
            
        if filter_options.get('date_range'):
            start_date, end_date = filter_options['date_range']
            query = query.filter(Course.end_date >= start_date, Course.start_date <= end_date)
            
        courses = query.order_by(Course.curriculum_id, Course.start_date).all()
        
        if not courses:
            flash('Keine Kurse gefunden, die den Filterkriterien entsprechen.', 'warning')
            return redirect(url_for('main.show_timeline'))

        # Statistikdaten sammeln, wenn gewünscht
        statistics_data = {}
        if include_statistics:
            # Kursstatistiken
            total_days = sum([(course.end_date - course.start_date).days + 1 for course in courses])
            avg_duration = round(total_days / len(courses), 1) if courses else 0
            statistics_data = {
                'course_count': len(courses),
                'total_days': total_days,
                'avg_duration': avg_duration
            }
            
            # Top-Dozenten
            lecturer_stats = {}
            for course in courses:
                if course.lecturer:
                    if course.lecturer.id not in lecturer_stats:
                        lecturer_stats[course.lecturer.id] = {
                            'name': course.lecturer.name,
                            'color': course.lecturer.color or '#808080',
                            'course_count': 0,
                            'total_days': 0
                        }
                    lecturer_stats[course.lecturer.id]['course_count'] += 1
                    lecturer_stats[course.lecturer.id]['total_days'] += (course.end_date - course.start_date).days + 1
            
            statistics_data['top_lecturers'] = sorted(
                lecturer_stats.values(),
                key=lambda x: x['total_days'],
                reverse=True
            )[:5]  # Top 5 Dozenten
            
            # Häufigste Themen
            topic_counts = {}
            for course in courses:
                topic = course.topic
                if topic not in topic_counts:
                    topic_counts[topic] = 0
                topic_counts[topic] += 1
            
            statistics_data['top_topics'] = [
                {'topic': topic, 'count': count}
                for topic, count in sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)
            ][:5]  # Top 5 Themen
        
        # Verfügbarkeiten sammeln, wenn gewünscht
        availabilities = []
        if include_availabilities:
            # Finde alle beteiligten Dozenten
            all_lecturers = set()
            for course in courses:
                if course.lecturer_id:
                    all_lecturers.add(course.lecturer_id)
            
            # Finde den Gesamtzeitraum
            min_date = min([course.start_date for course in courses])
            max_date = max([course.end_date for course in courses])
            
            # Verfügbarkeiten abfragen
            availabilities = db.session.query(Availability)\
                .filter(Availability.lecturer_id.in_(all_lecturers))\
                .filter(Availability.end_date >= min_date, Availability.start_date <= max_date)\
                .order_by(Availability.start_date)\
                .all()

        # Create timeline image
        fig = create_timeline_figure(courses, filter_options)
        timeline_img = fig.to_image(format="png", width=1200, height=600, scale=2)
        import base64
        timeline_image = base64.b64encode(timeline_img).decode('utf-8')

        # Organize courses by batches
        batches = []
        current_batch = None
        
        # First group by curriculum_id
        curriculum_courses = {}
        for course in courses:
            if course.curriculum_id not in curriculum_courses:
                curriculum_courses[course.curriculum_id] = []
            curriculum_courses[course.curriculum_id].append(course)
        
        # Then sort by start date of first course
        sorted_curriculum_ids = sorted(
            curriculum_courses.keys(),
            key=lambda cid: min([c.start_date for c in curriculum_courses[cid]])
        )
        
        # Create batches
        for i, curriculum_id in enumerate(sorted_curriculum_ids):
            first_course = min(curriculum_courses[curriculum_id], key=lambda c: c.start_date)
            
            # Format batch name
            semester = "SoSe" if first_course.start_date.month >= 3 and first_course.start_date.month <= 8 else "WiSe"
            year = first_course.start_date.year
            
            batches.append({
                'curriculum_id': curriculum_id,
                'name': f"Batch {i + 1} ({semester} {year})",
                'start_date': first_course.start_date,
                'courses': sorted(curriculum_courses[curriculum_id], key=lambda c: c.start_date)
            })

        # Select the correct template based on report type
        if report_type == 'lecturer':
            report_template_path = 'pdf_templates/lecturer_report.html'
        elif report_type == 'curriculum':
            report_template_path = 'pdf_templates/curriculum_report.html'
        else:
            report_template_path = 'pdf_templates/standard_report.html'

        # Ensure directories exist
        pdf_template_dir = os.path.join(current_app.root_path, 'templates', 'pdf_templates')
        os.makedirs(pdf_template_dir, exist_ok=True)

        # Use standard template if special one doesn't exist
        report_template_path = os.path.join(current_app.root_path, 'templates', report_template_path)
        if not os.path.exists(report_template_path):
            report_template_path = os.path.join(current_app.root_path, 'templates', 'pdf_templates/standard_report.html')
            if not os.path.exists(report_template_path):
                # Create standard template if it doesn't exist
                with open(report_template_path, 'w', encoding='utf-8') as f:
                    f.write(get_standard_report_template())

        # Read template
        with open(report_template_path, 'r', encoding='utf-8') as f:
            report_template = f.read()

        # Render template
        template = Template(report_template)
        html_content = template.render(
            current_date=datetime.now().strftime('%d.%m.%Y'),
            timeline_image=timeline_image,
            batches=batches,
            statistics=statistics_data,
            availabilities=availabilities,
            include_statistics=include_statistics,
            include_availabilities=include_availabilities,
            report_type=report_type
        )

        # Return HTML directly instead of converting to PDF
        return html_content

    except Exception as e:
        flash(f'Fehler beim Erstellen des HTML-Berichts: {str(e)}', 'error')
        return redirect(url_for('main.show_timeline'))

def get_standard_report_template():
    """Rückgabe des Standard-Report-Templates als HTML-String"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Lehrplan Bericht</title>
        <style>
            @page {
                size: A4;
                margin: 2cm;
            }
            body { 
                font-family: Arial, sans-serif; 
                margin: 0;
                padding: 0;
                color: #333;
                line-height: 1.4;
            }
            .header { 
                text-align: center; 
                margin-bottom: 30px;
                border-bottom: 1px solid #ddd;
                padding-bottom: 15px;
                color: #1a5276;
            }
            .header h1 {
                margin-bottom: 5px;
            }
            .header p {
                color: #777;
                margin-top: 0;
            }
            .section {
                margin-bottom: 25px;
                page-break-inside: avoid;
            }
            .section h2 {
                color: #2874a6;
                border-bottom: 1px solid #eee;
                padding-bottom: 7px;
            }
            .timeline-section { 
                margin-bottom: 40px; 
                text-align: center;
            }
            .curriculum-section { 
                margin-bottom: 30px; 
            }
            .stats-section {
                margin: 30px 0;
                background-color: #f8f9fa;
                padding: 15px;
                border-radius: 5px;
            }
            .stats-grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 20px;
            }
            .stat-card {
                padding: 15px;
                background-color: white;
                border-radius: 5px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            }
            .stat-title {
                font-weight: bold;
                margin-bottom: 10px;
                color: #2874a6;
            }
            .stat-value {
                font-size: 1.2em;
                font-weight: bold;
            }
            .batch-header { 
                background-color: #f8f9fa;
                padding: 10px;
                margin: 20px 0 10px 0;
                border-radius: 4px;
                color: #2874a6;
            }
            .page-break { 
                page-break-before: always; 
            }
            table { 
                width: 100%; 
                border-collapse: collapse; 
                margin: 15px 0; 
            }
            th, td { 
                padding: 8px; 
                text-align: left; 
                border: 1px solid #ddd; 
            }
            th { 
                background-color: #f8f9fa; 
                font-weight: bold;
                color: #2874a6;
            }
            tr:nth-child(even) {
                background-color: #f9f9f9;
            }
            .availability-section {
                margin-top: 30px;
            }
            .availability-type {
                display: inline-block;
                padding: 3px 6px;
                border-radius: 3px;
                margin-right: 5px;
                font-size: 0.85em;
            }
            .vacation {
                background-color: rgba(255,165,0,0.2);
                border: 1px solid rgba(255,165,0,0.5);
            }
            .unavailable {
                background-color: rgba(255,0,0,0.1);
                border: 1px solid rgba(255,0,0,0.3);
            }
            .lecturer-info {
                color: #666;
                font-style: italic;
            }
            .color-indicator {
                display: inline-block;
                width: 12px;
                height: 12px;
                border-radius: 50%;
                margin-right: 5px;
            }
            .footer {
                font-size: 0.8em;
                text-align: center;
                margin-top: 30px;
                border-top: 1px solid #eee;
                padding-top: 10px;
                color: #777;
            }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Lehrplan Übersicht</h1>
            <p>Erstellt am {{ current_date }}</p>
        </div>

        <div class="timeline-section section">
            <h2>Timeline Übersicht</h2>
            <img src="data:image/png;base64,{{ timeline_image }}" 
                 style="max-width: 100%; height: auto; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
        </div>

        {% if include_statistics and statistics %}
        <div class="stats-section section">
            <h2>Statistische Übersicht</h2>
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-title">Anzahl Kurse</div>
                    <div class="stat-value">{{ statistics.course_count }}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-title">Durchschnittliche Kursdauer</div>
                    <div class="stat-value">{{ statistics.avg_duration }} Tage</div>
                </div>
                <div class="stat-card">
                    <div class="stat-title">Gesamtzahl Kurstage</div>
                    <div class="stat-value">{{ statistics.total_days }} Tage</div>
                </div>
            </div>
            
            {% if statistics.top_lecturers %}
            <h3>Top Dozenten</h3>
            <table>
                <thead>
                    <tr>
                        <th>Dozent</th>
                        <th>Anzahl Kurse</th>
                        <th>Gesamttage</th>
                        <th>Tage/Kurs</th>
                    </tr>
                </thead>
                <tbody>
                    {% for lecturer in statistics.top_lecturers %}
                    <tr>
                        <td>
                            <span class="color-indicator" style="background-color: {{ lecturer.color }};"></span>
                            {{ lecturer.name }}
                        </td>
                        <td>{{ lecturer.course_count }}</td>
                        <td>{{ lecturer.total_days }}</td>
                        <td>{{ (lecturer.total_days / lecturer.course_count)|round(1) if lecturer.course_count > 0 else 0 }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% endif %}
            
            {% if statistics.top_topics %}
            <h3>Häufigste Kursthemen</h3>
            <table>
                <thead>
                    <tr>
                        <th>Thema</th>
                        <th>Anzahl</th>
                    </tr>
                </thead>
                <tbody>
                    {% for topic in statistics.top_topics %}
                    <tr>
                        <td>{{ topic.topic }}</td>
                        <td>{{ topic.count }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% endif %}
        </div>
        {% endif %}

        <div class="page-break"></div>

        <div class="curriculum-section section">
            <h2>Detaillierte Lehrplan Informationen</h2>
            {% for batch in batches %}
            <div class="batch-header">
                <h3>{{ batch.name }}</h3>
                <p>Startdatum: {{ batch.start_date.strftime('%d.%m.%Y') }}</p>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Thema</th>
                        <th>Zeitraum</th>
                        <th>Dauer</th>
                        <th>Dozent</th>
                    </tr>
                </thead>
                <tbody>
                    {% for course in batch.courses %}
                    <tr>
                        <td>{{ course.topic }}</td>
                        <td>{{ course.start_date.strftime('%d.%m.%Y') }} - {{ course.end_date.strftime('%d.%m.%Y') }}</td>
                        <td>{{ (course.end_date - course.start_date).days + 1 }} Tage</td>
                        <td>
                            {% if course.lecturer %}
                            <span class="color-indicator" style="background-color: {{ course.lecturer.color or '#808080' }};"></span>
                            {{ course.lecturer.name }}
                            {% else %}
                            <span class="lecturer-info">Nicht zugewiesen</span>
                            {% endif %}
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% endfor %}
        </div>

        {% if include_availabilities and availabilities %}
        <div class="availability-section section">
            <h2>Dozenten-Verfügbarkeiten</h2>
            <table>
                <thead>
                    <tr>
                        <th>Dozent</th>
                        <th>Typ</th>
                        <th>Zeitraum</th>
                        <th>Dauer</th>
                        <th>Notiz</th>
                    </tr>
                </thead>
                <tbody>
                    {% for availability in availabilities %}
                    <tr>
                        <td>{{ availability.lecturer.name }}</td>
                        <td>
                            {% if availability.type == 'vacation' %}
                            <span class="availability-type vacation">Urlaub</span>
                            {% else %}
                            <span class="availability-type unavailable">Nicht verfügbar</span>
                            {% endif %}
                        </td>
                        <td>{{ availability.start_date.strftime('%d.%m.%Y') }} - {{ availability.end_date.strftime('%d.%m.%Y') }}</td>
                        <td>{{ (availability.end_date - availability.start_date).days + 1 }} Tage</td>
                        <td>{{ availability.note }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% endif %}

        <div class="footer">
            Lehrplan-Timeline-System | Berichtsdatum: {{ current_date }}
        </div>
    </body>
    </html>
    """

def format_batch_name(counter, start_date):
    """Konsistente Batch-Namensgebung"""
    semester = "SoSe" if start_date.month >= 3 and start_date.month <= 8 else "WiSe"
    year = start_date.year
    return f"Batch {counter} ({semester} {year})"

def parse_date(date_str):
    """Flexiblere Datumsverarbeitung"""
    try:
        # Versuche verschiedene Datumsformate
        for fmt in ['%d.%m.%Y', '%Y-%m-%d', '%d/%m/%Y']:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        raise ValueError(f"Ungültiges Datumsformat: {date_str}")
    except Exception as e:
        raise ValueError(f"Fehler beim Parsen des Datums: {str(e)}")

@main.route('/lecturers', methods=['GET', 'POST'])
def manage_lecturers():
    if request.method == 'POST':
        action = request.form.get('action', '')
        
        # Löschen eines Dozenten
        if action == 'delete_lecturer':
            lecturer_id = request.form.get('lecturer_id')
            lecturer = Lecturer.query.get(lecturer_id)
            
            if lecturer:
                try:
                    # Setze lecturer_id für alle Kurse dieses Dozenten auf NULL
                    db.session.query(Course).filter_by(lecturer_id=lecturer_id).update({Course.lecturer_id: None})
                    
                    # Lösche alle Verfügbarkeiten dieses Dozenten
                    db.session.query(Availability).filter_by(lecturer_id=lecturer_id).delete()
                    
                    # Lösche den Dozenten
                    db.session.delete(lecturer)
                    db.session.commit()
                    flash(f'Dozent "{lecturer.name}" wurde erfolgreich gelöscht.', 'success')
                except Exception as e:
                    db.session.rollback()
                    flash(f'Fehler beim Löschen des Dozenten: {str(e)}', 'error')
            
            return redirect(url_for('main.manage_lecturers'))
            
        # Hinzufügen einer Verfügbarkeit
        elif action == 'add_availability':
            try:
                lecturer_id = request.form.get('lecturer_id')
                availability_type = request.form.get('type')
                start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d')
                end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d')
                note = request.form.get('note', '')
                check_conflicts = request.form.get('check_conflicts') == 'on'
                
                # Validiere Daten
                if start_date > end_date:
                    flash('Das Enddatum muss nach dem Startdatum liegen.', 'error')
                    return redirect(url_for('main.manage_lecturers'))
                
                # Prüfe auf Konflikte, falls gewünscht
                if check_conflicts:
                    conflicts = Course.query.filter(
                        Course.lecturer_id == lecturer_id,
                        Course.start_date <= end_date,
                        Course.end_date >= start_date
                    ).all()
                    
                    if conflicts:
                        conflict_info = ', '.join([f'"{c.topic}" ({c.start_date.strftime("%d.%m.%Y")})' for c in conflicts[:3]])
                        if len(conflicts) > 3:
                            conflict_info += f' und {len(conflicts) - 3} weitere'
                        
                        flash(f'Warnung: Es bestehen Konflikte mit zugewiesenen Kursen: {conflict_info}', 'warning')
                
                # Erstelle Verfügbarkeit
                availability = Availability(
                    lecturer_id=lecturer_id,
                    type=availability_type,
                    start_date=start_date,
                    end_date=end_date,
                    note=note
                )
                
                db.session.add(availability)
                db.session.commit()
                
                lecturer_name = Lecturer.query.get(lecturer_id).name if Lecturer.query.get(lecturer_id) else 'Unbekannt'
                flash(f'Verfügbarkeit für "{lecturer_name}" wurde erfolgreich hinzugefügt.', 'success')
                
            except Exception as e:
                db.session.rollback()
                flash(f'Fehler beim Hinzufügen der Verfügbarkeit: {str(e)}', 'error')
                
            return redirect(url_for('main.manage_lecturers'))
            
        # Löschen einer Verfügbarkeit
        elif action == 'delete_availability':
            availability_id = request.form.get('availability_id')
            availability = Availability.query.get(availability_id)
            
            if availability:
                try:
                    db.session.delete(availability)
                    db.session.commit()
                    flash('Verfügbarkeit wurde erfolgreich gelöscht.', 'success')
                except Exception as e:
                    db.session.rollback()
                    flash(f'Fehler beim Löschen der Verfügbarkeit: {str(e)}', 'error')
            
            return redirect(url_for('main.manage_lecturers'))
    
    # GET-Anfrage: Zeige alle Dozenten und Verfügbarkeiten
    lecturers = Lecturer.query.all()
    availabilities = Availability.query.join(Lecturer).order_by(Availability.start_date.desc()).all()
    
    return render_template('lecturers.html', 
                         lecturers=lecturers, 
                         availabilities=availabilities,
                         colors=COLORS,
                         current_date=datetime.now())

@main.route('/calendar')
def calendar_view():
    """Kalenderansicht für Kurse und Dozentenverfügbarkeiten"""
    # Hole aktive Kurse
    courses = db.session.query(Course)\
        .filter(Course.active == True)\
        .all()
    
    # Hole Verfügbarkeiten
    availabilities = Availability.query.all()
    
    # Dozenten für Filterung
    lecturers = Lecturer.query.all()
    
    # Konvertiere zu JSON für Kalender
    events = []
    
    # Füge Kurse hinzu
    for course in courses:
        lecturer_name = course.lecturer.name if course.lecturer else 'Nicht zugewiesen'
        lecturer_color = course.lecturer.color if course.lecturer else '#808080'
        
        events.append({
            'id': f'course_{course.id}',
            'title': f'{course.topic} ({lecturer_name})',
            'start': course.start_date.strftime('%Y-%m-%d'),
            'end': (course.end_date + timedelta(days=1)).strftime('%Y-%m-%d'),  # FullCalendar verwendet nicht-inklusive Enddaten
            'color': lecturer_color,
            'textColor': '#fff',
            'type': 'course',
            'url': f'/manage#course-{course.id}',
            'extendedProps': {
                'course_id': course.id,
                'lecturer_id': course.lecturer_id,
                'lecturer_name': lecturer_name,
                'topic': course.topic
            }
        })
    
    # Füge Verfügbarkeiten hinzu
    for availability in availabilities:
        if availability.type == 'vacation':
            color = 'rgba(255,165,0,0.5)'
            title = f'{availability.lecturer.name}: Urlaub'
            icon = 'fas fa-umbrella-beach'
        else:
            color = 'rgba(255,0,0,0.5)'
            title = f'{availability.lecturer.name}: Nicht verfügbar'
            icon = 'fas fa-ban'
            
        if availability.note:
            title += f' - {availability.note}'
            
        events.append({
            'id': f'availability_{availability.id}',
            'title': title,
            'start': availability.start_date.strftime('%Y-%m-%d'),
            'end': (availability.end_date + timedelta(days=1)).strftime('%Y-%m-%d'),
            'color': color,
            'textColor': '#000',
            'type': 'availability',
            'classNames': ['availability-event'],
            'extendedProps': {
                'availability_id': availability.id,
                'lecturer_id': availability.lecturer_id,
                'lecturer_name': availability.lecturer.name,
                'icon': icon,
                'note': availability.note
            }
        })
        
    return render_template('calendar.html', 
                          events=events, 
                          lecturers=lecturers)

@main.route('/calendar/ical')
def calendar_ical():
    """Export des Kalenders als iCalendar-Datei"""
    # Filter options
    lecturer_id = request.args.get('lecturer_id', type=int)
    event_type = request.args.get('event_type')  # 'course' oder 'availability'
    curriculum_id = request.args.get('curriculum_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if start_date:
        start_date = datetime.strptime(start_date, '%Y-%m-%d')
    
    if end_date:
        end_date = datetime.strptime(end_date, '%Y-%m-%d')
    
    # Erstelle iCalendar
    cal = Calendar()
    cal.add('prodid', '-//Lehrplan-Timeline-System//DE')
    cal.add('version', '2.0')
    cal.add('calscale', 'GREGORIAN')
    cal.add('method', 'PUBLISH')
    cal.add('X-WR-CALNAME', 'Lehrplan-Kalender')
    cal.add('X-WR-TIMEZONE', 'Europe/Berlin')
    
    # Hole Kurse und Verfügbarkeiten basierend auf den Filtern
    courses_query = db.session.query(Course).filter(Course.active == True)
    availabilities_query = db.session.query(Availability)
    
    if lecturer_id:
        courses_query = courses_query.filter(Course.lecturer_id == lecturer_id)
        availabilities_query = availabilities_query.filter(Availability.lecturer_id == lecturer_id)
    
    if curriculum_id:
        courses_query = courses_query.filter(Course.curriculum_id == curriculum_id)
    
    if start_date and end_date:
        courses_query = courses_query.filter(Course.end_date >= start_date, Course.start_date <= end_date)
        availabilities_query = availabilities_query.filter(Availability.end_date >= start_date, Availability.start_date <= end_date)
    
    # Füge Kurse zum Kalender hinzu
    if event_type is None or event_type == 'course':
        courses = courses_query.all()
        
        for course in courses:
            event = Event()
            
            lecturer_name = course.lecturer.name if course.lecturer else 'Nicht zugewiesen'
            
            event.add('summary', f'{course.topic} ({lecturer_name})')
            event.add('dtstart', course.start_date.date())
            # iCalendar end date ist exklusiv, daher +1 Tag
            event.add('dtend', (course.end_date + timedelta(days=1)).date())
            event.add('dtstamp', datetime.now())
            event.add('uid', f'course-{course.id}@lehrplan-timeline.de')
            
            # Füge Beschreibung mit Details hinzu
            description = f'Kurs: {course.topic}\n'
            description += f'Dozent: {lecturer_name}\n'
            description += f'Zeitraum: {course.start_date.strftime("%d.%m.%Y")} bis {course.end_date.strftime("%d.%m.%Y")}\n'
            description += f'Dauer: {(course.end_date - course.start_date).days + 1} Tage\n'
            event.add('description', description)
            
            # Kategorie
            event.add('categories', 'Kurs')
            
            # Farbe basierend auf Dozent (wird nicht von allen Kalendern unterstützt)
            if course.lecturer and course.lecturer.color:
                event['X-APPLE-CALENDAR-COLOR'] = course.lecturer.color
                event['X-MICROSOFT-CDO-BUSYSTATUS'] = 'BUSY'
            
            cal.add_component(event)
    
    # Füge Verfügbarkeiten zum Kalender hinzu
    if event_type is None or event_type == 'availability':
        availabilities = availabilities_query.all()
        
        for availability in availabilities:
            event = Event()
            
            if availability.type == 'vacation':
                title = f'{availability.lecturer.name}: Urlaub'
                categories = 'Urlaub'
                transp = 'TRANSPARENT'  # Zeigt als "frei" an
            else:
                title = f'{availability.lecturer.name}: Nicht verfügbar'
                categories = 'Nicht verfügbar'
                transp = 'OPAQUE'  # Zeigt als "beschäftigt" an
            
            if availability.note:
                title += f' - {availability.note}'
            
            event.add('summary', title)
            event.add('dtstart', availability.start_date.date())
            # iCalendar end date ist exklusiv, daher +1 Tag
            event.add('dtend', (availability.end_date + timedelta(days=1)).date())
            event.add('dtstamp', datetime.now())
            event.add('uid', f'availability-{availability.id}@lehrplan-timeline.de')
            
            # Beschreibung
            description = f'Typ: {categories}\n'
            description += f'Dozent: {availability.lecturer.name}\n'
            if availability.note:
                description += f'Notiz: {availability.note}\n'
            event.add('description', description)
            
            # Kategorie
            event.add('categories', categories)
            event.add('transp', transp)
            
            cal.add_component(event)
    
    # Generiere Dateinamen basierend auf Filtern
    filename_parts = ['lehrplan_kalender']
    if lecturer_id:
        lecturer = Lecturer.query.get(lecturer_id)
        if lecturer:
            filename_parts.append(f'dozent_{lecturer.name.replace(" ", "_")}')
    
    if event_type:
        filename_parts.append(event_type)
    
    if curriculum_id:
        filename_parts.append(f'lehrplan_{curriculum_id[:8]}')
    
    if start_date and end_date:
        filename_parts.append(f'{start_date.strftime("%Y%m%d")}-{end_date.strftime("%Y%m%d")}')
    
    filename = '_'.join(filename_parts) + '.ics'
    
    response = Response(cal.to_ical(), mimetype='text/calendar')
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

@main.route('/calendar/event/<int:event_id>/ical')
def event_ical(event_id):
    """Export eines einzelnen Kurses als iCalendar-Datei"""
    event_type = request.args.get('type', 'course')
    
    cal = Calendar()
    cal.add('prodid', '-//Lehrplan-Timeline-System//DE')
    cal.add('version', '2.0')
    
    if event_type == 'course':
        course = Course.query.get_or_404(event_id)
        
        event = Event()
        lecturer_name = course.lecturer.name if course.lecturer else 'Nicht zugewiesen'
        
        event.add('summary', f'{course.topic} ({lecturer_name})')
        event.add('dtstart', course.start_date.date())
        # iCalendar end date ist exklusiv, daher +1 Tag
        event.add('dtend', (course.end_date + timedelta(days=1)).date())
        event.add('dtstamp', datetime.now())
        event.add('uid', f'course-{course.id}@lehrplan-timeline.de')
        
        description = f'Kurs: {course.topic}\n'
        description += f'Dozent: {lecturer_name}\n'
        description += f'Zeitraum: {course.start_date.strftime("%d.%m.%Y")} bis {course.end_date.strftime("%d.%m.%Y")}\n'
        description += f'Dauer: {(course.end_date - course.start_date).days + 1} Tage\n'
        event.add('description', description)
        
        event.add('categories', 'Kurs')
        
        if course.lecturer and course.lecturer.color:
            event['X-APPLE-CALENDAR-COLOR'] = course.lecturer.color
        
        cal.add_component(event)
        filename = f'kurs_{course.topic.replace(" ", "_")}.ics'
        
    elif event_type == 'availability':
        availability = Availability.query.get_or_404(event_id)
        
        event = Event()
        
        if availability.type == 'vacation':
            title = f'{availability.lecturer.name}: Urlaub'
            categories = 'Urlaub'
        else:
            title = f'{availability.lecturer.name}: Nicht verfügbar'
            categories = 'Nicht verfügbar'
        
        if availability.note:
            title += f' - {availability.note}'
        
        event.add('summary', title)
        event.add('dtstart', availability.start_date.date())
        event.add('dtend', (availability.end_date + timedelta(days=1)).date())
        event.add('dtstamp', datetime.now())
        event.add('uid', f'availability-{availability.id}@lehrplan-timeline.de')
        
        description = f'Typ: {categories}\n'
        description += f'Dozent: {availability.lecturer.name}\n'
        if availability.note:
            description += f'Notiz: {availability.note}\n'
        event.add('description', description)
        
        event.add('categories', categories)
        
        cal.add_component(event)
        filename = f'verfuegbarkeit_{availability.lecturer.name.replace(" ", "_")}_{availability.start_date.strftime("%Y%m%d")}.ics'
    
    else:
        flash('Ungültiger Ereignistyp', 'error')
        return redirect(url_for('main.calendar_view'))
    
    response = Response(cal.to_ical(), mimetype='text/calendar')
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

@main.route('/statistics')
def statistics_dashboard():
    """Statistik-Dashboard mit Analysen zu Dozenten, Kursen und Zeitplanung"""
    # Basisstatistiken
    active_courses = Course.query.filter(Course.active == True).all()
    course_count = len(active_courses)
    lecturer_count = Lecturer.query.count()
    curriculum_count = db.session.query(Course.curriculum_id).distinct().count()
    
    # Durchschnittliche Kursdauer berechnen
    total_days = 0
    for course in active_courses:
        if course.start_date and course.end_date:
            delta = (course.end_date - course.start_date).days
            total_days += delta if delta > 0 else 1
    
    avg_duration = round(total_days / course_count, 1) if course_count > 0 else 0
    
    # Dozenten-Auslastung (Top 10)
    lecturer_workload = db.session.query(
        Lecturer.id, 
        Lecturer.name,
        Lecturer.color,
        func.count(Course.id).label('course_count'),
        func.sum(
            func.julianday(Course.end_date) - func.julianday(Course.start_date)
        ).label('total_days')
    ).outerjoin(Course, Course.lecturer_id == Lecturer.id)\
     .filter(Course.active == True)\
     .group_by(Lecturer.id)\
     .order_by(db.desc('total_days'))\
     .limit(10)\
     .all()
    
    # Kursthemen-Verteilung (Top 10)
    topics = db.session.query(
        Course.topic,
        func.count(Course.id).label('count')
    ).filter(Course.active == True)\
     .group_by(Course.topic)\
     .order_by(db.desc('count'))\
     .limit(10)\
     .all()
    
    # Zeitliche Verteilung der Kurse (Kurse pro Monat)
    now = datetime.now()
    six_months_ago = now - timedelta(days=180)
    six_months_future = now + timedelta(days=180)
    
    # Kurse nach Monat gruppieren
    monthly_courses = db.session.query(
        func.strftime('%Y-%m', Course.start_date).label('month'),
        func.count().label('count')
    ).filter(Course.active == True)\
     .filter(Course.start_date.between(six_months_ago, six_months_future))\
     .group_by('month')\
     .order_by('month')\
     .all()
    
    months = []
    course_counts = []
    for month, count in monthly_courses:
        if month:
            year, month_num = month.split('-')
            month_name = datetime(int(year), int(month_num), 1).strftime('%b %Y')
            months.append(month_name)
            course_counts.append(count)
    
    # Kursverteilung nach Wochentagen
    weekday_counts = db.session.query(
        func.strftime('%w', Course.start_date).label('weekday'),
        func.count().label('count')
    ).filter(Course.active == True)\
     .group_by('weekday')\
     .all()
    
    weekdays = ['Sonntag', 'Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag']
    weekday_data = [0] * 7  # Initialize with zeros for all weekdays
    
    for weekday, count in weekday_counts:
        if weekday:
            day_index = int(weekday)
            weekday_data[day_index] = count
    
    # Kursdauer-Verteilung
    duration_bins = [1, 3, 5, 7, 14, 30, 60, 90, 180]
    durations = ['1-2', '3-4', '5-6', '7-13', '14-29', '30-59', '60-89', '90+']
    duration_counts = [0] * len(durations)
    
    for course in active_courses:
        if course.start_date and course.end_date:
            days = (course.end_date - course.start_date).days
            days = max(1, days)  # Ensure minimum of 1 day
            
            for i, bin_value in enumerate(duration_bins):
                if i == len(duration_bins) - 1:  # Last bin
                    if days >= bin_value:
                        duration_counts[i] += 1
                elif days < duration_bins[i + 1]:
                    duration_counts[i] += 1
                    break
    
    # Dozenten mit den meisten Verfügbarkeitseinträgen
    lecturers_with_availabilities = db.session.query(
        Lecturer.id,
        Lecturer.name,
        func.count(Availability.id).label('availability_count')
    ).join(Availability, Availability.lecturer_id == Lecturer.id)\
     .group_by(Lecturer.id)\
     .order_by(db.desc('availability_count'))\
     .limit(5)\
     .all()
    
    return render_template(
        'statistics.html',
        course_count=course_count,
        lecturer_count=lecturer_count,
        curriculum_count=curriculum_count,
        avg_duration=avg_duration,
        lecturer_workload=lecturer_workload,
        topics=topics,
        months=months,
        course_counts=course_counts,
        weekdays=weekdays,
        weekday_data=weekday_data,
        durations=durations,
        duration_counts=duration_counts,
        lecturers_with_availabilities=lecturers_with_availabilities
    ) 

@main.route('/create_curriculum', methods=['GET', 'POST'])
def create_curriculum():
    """Lehrplan manuell erstellen"""
    if request.method == 'POST':
        try:
            curriculum_name = request.form.get('curriculum_name')
            start_date = datetime.strptime(request.form.get('curriculum_start_date'), '%Y-%m-%d')
            is_active = 'is_active' in request.form
            
            # Hole Kursdaten aus dem Formular
            topics = request.form.getlist('course_topic[]')
            start_dates = request.form.getlist('course_start_date[]')
            end_dates = request.form.getlist('course_end_date[]')
            
            # Validiere Daten
            if not topics or len(topics) != len(start_dates) or len(topics) != len(end_dates):
                flash('Bitte füllen Sie alle Kursfelder aus.', 'error')
                return redirect(url_for('main.create_curriculum'))
            
            # Generiere neue curriculum_id
            curriculum_id = str(uuid.uuid4())
            
            # Erstelle die Kurse
            for i in range(len(topics)):
                course = Course(
                    topic=topics[i],
                    start_date=datetime.strptime(start_dates[i], '%Y-%m-%d'),
                    end_date=datetime.strptime(end_dates[i], '%Y-%m-%d'),
                    curriculum_id=curriculum_id,
                    active=is_active
                )
                db.session.add(course)
            
            db.session.commit()
            
            # Speichere den Namen als Einstellung
            setting_key = f"curriculum_name_{curriculum_id}"
            setting = Settings.query.filter_by(key=setting_key).first()
            if setting:
                setting.value = curriculum_name
            else:
                setting = Settings(key=setting_key, value=curriculum_name)
                db.session.add(setting)
            
            db.session.commit()
            
            flash(f'Lehrplan "{curriculum_name}" wurde erfolgreich erstellt!', 'success')
            return redirect(url_for('main.manage_curriculum'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Fehler beim Erstellen des Lehrplans: {str(e)}', 'error')
            return redirect(url_for('main.create_curriculum'))
    
    return render_template('create_curriculum.html')

@main.route('/add_course', methods=['GET', 'POST'])
def add_course():
    """Kurs manuell zu bestehendem Lehrplan hinzufügen"""
    if request.method == 'POST':
        try:
            curriculum_id = request.form.get('curriculum_id')
            topic = request.form.get('course_topic')
            start_date = datetime.strptime(request.form.get('course_start_date'), '%Y-%m-%d')
            end_date = datetime.strptime(request.form.get('course_end_date'), '%Y-%m-%d')
            lecturer_id = request.form.get('lecturer_id')
            is_active = 'is_active' in request.form
            
            # Validiere Daten
            if not curriculum_id or not topic or not start_date or not end_date:
                flash('Bitte füllen Sie alle Pflichtfelder aus.', 'error')
                return redirect(url_for('main.add_course'))
            
            if lecturer_id == '':
                lecturer_id = None
                
            # Erstelle den Kurs
            course = Course(
                topic=topic,
                start_date=start_date,
                end_date=end_date,
                lecturer_id=lecturer_id,
                curriculum_id=curriculum_id,
                active=is_active
            )
            
            db.session.add(course)
            db.session.commit()
            
            flash(f'Kurs "{topic}" wurde erfolgreich hinzugefügt!', 'success')
            return redirect(url_for('main.manage_curriculum'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Fehler beim Hinzufügen des Kurses: {str(e)}', 'error')
            return redirect(url_for('main.add_course'))
    
    # Hole alle unterschiedlichen Lehrpläne für die Auswahl
    curricula = {}
    courses = db.session.query(Course).order_by(Course.start_date).all()
    
    for course in courses:
        if course.curriculum_id not in curricula:
            curricula[course.curriculum_id] = {
                'start_date': course.start_date,
                'courses': [],
                'active': course.active,
                'batch_name': f"Batch {len(curricula) + 1}"
            }
        curricula[course.curriculum_id]['courses'].append(course)
    
    # Hole alle Dozenten
    lecturers = Lecturer.query.all()
    
    return render_template('add_course.html', curricula=curricula, lecturers=lecturers)

@main.route('/export-report-download', methods=['GET', 'POST'])
def export_report_download():
    """
    Export the report as a downloadable HTML file that can be printed to PDF from the browser.
    This bypasses wkhtmltopdf completely.
    """
    try:
        # Get filter parameters
        filter_options = {}
        if request.method == 'POST':
            if request.form.get('lecturer_id'):
                filter_options['lecturer_id'] = int(request.form.get('lecturer_id'))
            if request.form.get('curriculum_id'):
                filter_options['curriculum_id'] = request.form.get('curriculum_id')
            if request.form.get('start_date') and request.form.get('end_date'):
                start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d')
                end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d')
                filter_options['date_range'] = [start_date, end_date]
            
            report_type = request.form.get('report_type', 'standard')
            include_statistics = request.form.get('include_statistics') == 'on'
            include_availabilities = request.form.get('include_availabilities') == 'on'
        else:
            report_type = request.args.get('report_type', 'standard')
            include_statistics = request.args.get('include_statistics') == 'true'
            include_availabilities = request.args.get('include_availabilities') == 'true'
        
        # Hole aktive Kurse basierend auf den Filteroptionen
        query = db.session.query(Course).filter(Course.active == True)
        
        if filter_options.get('lecturer_id'):
            query = query.filter(Course.lecturer_id == filter_options['lecturer_id'])
        
        if filter_options.get('curriculum_id'):
            query = query.filter(Course.curriculum_id == filter_options['curriculum_id'])
            
        if filter_options.get('date_range'):
            start_date, end_date = filter_options['date_range']
            query = query.filter(Course.end_date >= start_date, Course.start_date <= end_date)
            
        courses = query.order_by(Course.curriculum_id, Course.start_date).all()
        
        if not courses:
            flash('Keine Kurse gefunden, die den Filterkriterien entsprechen.', 'warning')
            return redirect(url_for('main.show_timeline'))

        # Similar preparation as in export_report_html
        statistics_data = {}
        if include_statistics:
            # Compute statistics...
            total_days = sum([(course.end_date - course.start_date).days + 1 for course in courses])
            avg_duration = round(total_days / len(courses), 1) if courses else 0
            statistics_data = {
                'course_count': len(courses),
                'total_days': total_days,
                'avg_duration': avg_duration
            }
            
            # Additional statistics calculation...
            lecturer_stats = {}
            for course in courses:
                if course.lecturer:
                    if course.lecturer.id not in lecturer_stats:
                        lecturer_stats[course.lecturer.id] = {
                            'name': course.lecturer.name,
                            'color': course.lecturer.color or '#808080',
                            'course_count': 0,
                            'total_days': 0
                        }
                    lecturer_stats[course.lecturer.id]['course_count'] += 1
                    lecturer_stats[course.lecturer.id]['total_days'] += (course.end_date - course.start_date).days + 1
            
            statistics_data['top_lecturers'] = sorted(
                lecturer_stats.values(),
                key=lambda x: x['total_days'],
                reverse=True
            )[:5]  # Top 5 Dozenten
            
            # Häufigste Themen
            topic_counts = {}
            for course in courses:
                topic = course.topic
                if topic not in topic_counts:
                    topic_counts[topic] = 0
                topic_counts[topic] += 1
            
            statistics_data['top_topics'] = [
                {'topic': topic, 'count': count}
                for topic, count in sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)
            ][:5]  # Top 5 Themen
        
        # Get availabilities
        availabilities = []
        if include_availabilities:
            # Find all lecturers
            all_lecturers = set()
            for course in courses:
                if course.lecturer_id:
                    all_lecturers.add(course.lecturer_id)
            
            # Find date range
            min_date = min([course.start_date for course in courses])
            max_date = max([course.end_date for course in courses])
            
            # Query availabilities
            availabilities = db.session.query(Availability)\
                .filter(Availability.lecturer_id.in_(all_lecturers))\
                .filter(Availability.end_date >= min_date, Availability.start_date <= max_date)\
                .order_by(Availability.start_date)\
                .all()

        # Create timeline image
        fig = create_timeline_figure(courses, filter_options)
        timeline_img = fig.to_image(format="png", width=1000, height=500, scale=1.5)
        import base64
        timeline_image = base64.b64encode(timeline_img).decode('utf-8')

        # Group courses by batch
        batches = []
        curriculum_courses = {}
        for course in courses:
            if course.curriculum_id not in curriculum_courses:
                curriculum_courses[course.curriculum_id] = []
            curriculum_courses[course.curriculum_id].append(course)
        
        sorted_curriculum_ids = sorted(
            curriculum_courses.keys(),
            key=lambda cid: min([c.start_date for c in curriculum_courses[cid]])
        )
        
        for i, curriculum_id in enumerate(sorted_curriculum_ids):
            first_course = min(curriculum_courses[curriculum_id], key=lambda c: c.start_date)
            semester = "SoSe" if first_course.start_date.month >= 3 and first_course.start_date.month <= 8 else "WiSe"
            year = first_course.start_date.year
            
            batches.append({
                'curriculum_id': curriculum_id,
                'name': f"Batch {i + 1} ({semester} {year})",
                'start_date': first_course.start_date,
                'courses': sorted(curriculum_courses[curriculum_id], key=lambda c: c.start_date)
            })

        # Get template
        if report_type == 'lecturer':
            report_template_path = 'pdf_templates/lecturer_report.html'
        elif report_type == 'curriculum':
            report_template_path = 'pdf_templates/curriculum_report.html'
        else:
            report_template_path = 'pdf_templates/standard_report.html'

        pdf_template_dir = os.path.join(current_app.root_path, 'templates', 'pdf_templates')
        os.makedirs(pdf_template_dir, exist_ok=True)

        report_template_path = os.path.join(current_app.root_path, 'templates', report_template_path)
        if not os.path.exists(report_template_path):
            report_template_path = os.path.join(current_app.root_path, 'templates', 'pdf_templates/standard_report.html')
            if not os.path.exists(report_template_path):
                with open(report_template_path, 'w', encoding='utf-8') as f:
                    f.write(get_standard_report_template())

        with open(report_template_path, 'r', encoding='utf-8') as f:
            report_template = f.read()

        # Add print-specific CSS for browser printing
        print_css = """
        <style>
        @media print {
            @page {
                size: A4;
                margin: 2cm;
            }
            body {
                font-size: 12pt;
            }
            .timeline-img {
                max-width: 100% !important;
                height: auto !important;
            }
            .page-break {
                page-break-before: always;
            }
            table { 
                page-break-inside: avoid;
            }
            /* Hide non-printing elements */
            .no-print {
                display: none !important;
            }
            /* Force background colors to print */
            * {
                -webkit-print-color-adjust: exact !important;
                print-color-adjust: exact !important;
            }
        }
        
        /* Print button */
        .print-button {
            position: fixed;
            top: 20px;
            right: 20px;
            background-color: #007bff;
            color: white;
            border: none;
            padding: 10px 15px;
            border-radius: 4px;
            cursor: pointer;
            z-index: 1000;
        }
        .print-button:hover {
            background-color: #0056b3;
        }
        </style>
        <script>
        function printReport() {
            document.querySelector('.print-button').style.display = 'none';
            window.print();
            setTimeout(function() {
                document.querySelector('.print-button').style.display = 'block';
            }, 500);
        }
        </script>
        """
        
        # Insert print CSS and button into the template
        report_template = report_template.replace('</head>', print_css + '</head>')
        report_template = report_template.replace('<body>', '<body><button class="print-button no-print" onclick="printReport()">Als PDF drucken</button>')

        # Render template
        template = Template(report_template)
        html_content = template.render(
            current_date=datetime.now().strftime('%d.%m.%Y'),
            timeline_image=timeline_image,
            batches=batches,
            statistics=statistics_data,
            availabilities=availabilities,
            include_statistics=include_statistics,
            include_availabilities=include_availabilities,
            report_type=report_type
        )

        # Generate filename
        filename_parts = ['Lehrplan_Bericht']
        if filter_options.get('lecturer_id'):
            lecturer = Lecturer.query.get(filter_options['lecturer_id'])
            if lecturer:
                filename_parts.append(f"Dozent_{lecturer.name.replace(' ', '_')}")
        
        if filter_options.get('curriculum_id'):
            filename_parts.append(f"Batch_{filter_options['curriculum_id'][:8]}")
            
        if filter_options.get('date_range'):
            start, end = filter_options['date_range']
            filename_parts.append(f"{start.strftime('%Y%m%d')}-{end.strftime('%Y%m%d')}")
            
        filename = '_'.join(filename_parts) + '.html'

        # Return as attachment
        response = Response(html_content, mimetype='text/html')
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    except Exception as e:
        flash(f'Fehler beim Erstellen des HTML-Berichts: {str(e)}', 'error')
        return redirect(url_for('main.show_timeline'))

@main.route('/export-report-direct', methods=['GET', 'POST'])
def export_report_direct():
    """
    Direct PDF generation using ReportLab instead of wkhtmltopdf.
    This avoids the QPaintDevice error that occurs with wkhtmltopdf.
    """
    try:
        # Get filter parameters - same as export_report
        filter_options = {}
        if request.method == 'POST':
            if request.form.get('lecturer_id'):
                filter_options['lecturer_id'] = int(request.form.get('lecturer_id'))
            if request.form.get('curriculum_id'):
                filter_options['curriculum_id'] = request.form.get('curriculum_id')
            if request.form.get('start_date') and request.form.get('end_date'):
                start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d')
                end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d')
                filter_options['date_range'] = [start_date, end_date]
            
            report_type = request.form.get('report_type', 'standard')
            include_statistics = request.form.get('include_statistics') == 'on'
            include_availabilities = request.form.get('include_availabilities') == 'on'
        else:
            report_type = request.args.get('report_type', 'standard')
            include_statistics = request.args.get('include_statistics') == 'true'
            include_availabilities = request.args.get('include_availabilities') == 'true'
        
        # Get courses based on filter options
        query = db.session.query(Course).filter(Course.active == True)
        
        if filter_options.get('lecturer_id'):
            query = query.filter(Course.lecturer_id == filter_options['lecturer_id'])
        
        if filter_options.get('curriculum_id'):
            query = query.filter(Course.curriculum_id == filter_options['curriculum_id'])
            
        if filter_options.get('date_range'):
            start_date, end_date = filter_options['date_range']
            query = query.filter(Course.end_date >= start_date, Course.start_date <= end_date)
            
        courses = query.order_by(Course.curriculum_id, Course.start_date).all()
        
        if not courses:
            flash('Keine Kurse gefunden, die den Filterkriterien entsprechen.', 'warning')
            return redirect(url_for('main.show_timeline'))

        # Create statistics data
        statistics_data = {}
        if include_statistics:
            total_days = sum([(course.end_date - course.start_date).days + 1 for course in courses])
            avg_duration = round(total_days / len(courses), 1) if courses else 0
            statistics_data = {
                'course_count': len(courses),
                'total_days': total_days,
                'avg_duration': avg_duration
            }
            
            # Get lecturer statistics
            lecturer_stats = {}
            for course in courses:
                if course.lecturer:
                    if course.lecturer.id not in lecturer_stats:
                        lecturer_stats[course.lecturer.id] = {
                            'name': course.lecturer.name,
                            'course_count': 0,
                            'total_days': 0
                        }
                    lecturer_stats[course.lecturer.id]['course_count'] += 1
                    lecturer_stats[course.lecturer.id]['total_days'] += (course.end_date - course.start_date).days + 1
            
            statistics_data['top_lecturers'] = sorted(
                lecturer_stats.values(),
                key=lambda x: x['total_days'],
                reverse=True
            )[:5]
            
            # Get topic statistics
            topic_counts = {}
            for course in courses:
                topic = course.topic
                if topic not in topic_counts:
                    topic_counts[topic] = 0
                topic_counts[topic] += 1
            
            statistics_data['top_topics'] = [
                {'topic': topic, 'count': count}
                for topic, count in sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)
            ][:5]

        # Get availabilities if needed
        availabilities = []
        if include_availabilities:
            all_lecturers = set()
            for course in courses:
                if course.lecturer_id:
                    all_lecturers.add(course.lecturer_id)
            
            min_date = min([course.start_date for course in courses])
            max_date = max([course.end_date for course in courses])
            
            availabilities = db.session.query(Availability)\
                .filter(Availability.lecturer_id.in_(all_lecturers))\
                .filter(Availability.end_date >= min_date, Availability.start_date <= max_date)\
                .order_by(Availability.start_date)\
                .all()

        # Create timeline image
        fig = create_timeline_figure(courses, filter_options)
        timeline_img = fig.to_image(format="png", width=1000, height=500, scale=1.5)
        
        # Organize courses by batch
        batches = []
        curriculum_courses = {}
        
        for course in courses:
            if course.curriculum_id not in curriculum_courses:
                curriculum_courses[course.curriculum_id] = []
            curriculum_courses[course.curriculum_id].append(course)
        
        sorted_curriculum_ids = sorted(
            curriculum_courses.keys(),
            key=lambda cid: min([c.start_date for c in curriculum_courses[cid]])
        )
        
        for i, curriculum_id in enumerate(sorted_curriculum_ids):
            first_course = min(curriculum_courses[curriculum_id], key=lambda c: c.start_date)
            semester = "SoSe" if first_course.start_date.month >= 3 and first_course.start_date.month <= 8 else "WiSe"
            year = first_course.start_date.year
            
            batches.append({
                'curriculum_id': curriculum_id,
                'name': f"Batch {i + 1} ({semester} {year})",
                'start_date': first_course.start_date,
                'courses': sorted(curriculum_courses[curriculum_id], key=lambda c: c.start_date)
            })

        # Now use reportlab to generate PDF
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from io import BytesIO
        
        # Set up the document
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, 
                               rightMargin=20*mm, leftMargin=20*mm,
                               topMargin=20*mm, bottomMargin=20*mm)
        
        # Styles
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name='Title', 
                                 fontName='Helvetica-Bold', 
                                 fontSize=18, 
                                 alignment=1,  # 0=left, 1=center, 2=right
                                 spaceAfter=6))
        styles.add(ParagraphStyle(name='Heading2', 
                                 fontName='Helvetica-Bold', 
                                 fontSize=14,
                                 spaceAfter=6))
        styles.add(ParagraphStyle(name='Heading3', 
                                 fontName='Helvetica-Bold', 
                                 fontSize=12,
                                 spaceAfter=6))
        styles.add(ParagraphStyle(name='Normal', 
                                 fontName='Helvetica', 
                                 fontSize=10,
                                 spaceAfter=6))
        
        # Content elements
        elements = []
        
        # Title
        elements.append(Paragraph('Lehrplan Übersicht', styles['Title']))
        elements.append(Paragraph(f'Erstellt am {datetime.now().strftime("%d.%m.%Y")}', styles['Normal']))
        elements.append(Spacer(1, 10*mm))
        
        # Timeline image
        img_data = BytesIO(timeline_img)
        img = Image(img_data, width=160*mm, height=80*mm)
        elements.append(Paragraph('Timeline Übersicht', styles['Heading2']))
        elements.append(img)
        elements.append(Spacer(1, 5*mm))
        
        # Statistics if included
        if include_statistics and statistics_data:
            elements.append(Paragraph('Statistische Übersicht', styles['Heading2']))
            
            # Basic statistics
            data = [
                ['Anzahl Kurse', str(statistics_data['course_count'])],
                ['Durchschnittliche Kursdauer', f"{statistics_data['avg_duration']} Tage"],
                ['Gesamtzahl Kurstage', f"{statistics_data['total_days']} Tage"]
            ]
            
            table = Table(data, colWidths=[100*mm, 50*mm])
            table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            elements.append(table)
            elements.append(Spacer(1, 5*mm))
            
            # Top lecturers if available
            if statistics_data.get('top_lecturers'):
                elements.append(Paragraph('Top Dozenten', styles['Heading3']))
                
                lecturer_data = [['Dozent', 'Anzahl Kurse', 'Gesamttage', 'Tage/Kurs']]
                for lecturer in statistics_data['top_lecturers']:
                    avg = round(lecturer['total_days'] / lecturer['course_count'], 1) if lecturer['course_count'] > 0 else 0
                    lecturer_data.append([
                        lecturer['name'],
                        str(lecturer['course_count']),
                        str(lecturer['total_days']),
                        str(avg)
                    ])
                
                table = Table(lecturer_data, colWidths=[70*mm, 30*mm, 30*mm, 30*mm])
                table.setStyle(TableStyle([
                    ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 0), (-1, -1), 10),
                    ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ]))
                elements.append(table)
                elements.append(Spacer(1, 5*mm))
            
            # Top topics if available
            if statistics_data.get('top_topics'):
                elements.append(Paragraph('Häufigste Kursthemen', styles['Heading3']))
                
                topic_data = [['Thema', 'Anzahl']]
                for topic in statistics_data['top_topics']:
                    topic_data.append([topic['topic'], str(topic['count'])])
                
                table = Table(topic_data, colWidths=[130*mm, 30*mm])
                table.setStyle(TableStyle([
                    ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 0), (-1, -1), 10),
                    ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ]))
                elements.append(table)
                elements.append(Spacer(1, 5*mm))
        
        # Page break before courses
        elements.append(PageBreak())
        
        # Course details by batch
        elements.append(Paragraph('Detaillierte Lehrplan Informationen', styles['Heading2']))
        
        for batch in batches:
            elements.append(Paragraph(f"{batch['name']} (Start: {batch['start_date'].strftime('%d.%m.%Y')})", styles['Heading3']))
            
            course_data = [['Thema', 'Zeitraum', 'Dauer', 'Dozent']]
            for course in batch['courses']:
                duration = (course.end_date - course.start_date).days + 1
                lecturer_name = course.lecturer.name if course.lecturer else 'Nicht zugewiesen'
                
                course_data.append([
                    course.topic,
                    f"{course.start_date.strftime('%d.%m.%Y')} - {course.end_date.strftime('%d.%m.%Y')}",
                    f"{duration} Tage",
                    lecturer_name
                ])
            
            table = Table(course_data, colWidths=[70*mm, 50*mm, 20*mm, 30*mm])
            table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            elements.append(table)
            elements.append(Spacer(1, 5*mm))
        
        # Availabilities if included
        if include_availabilities and availabilities:
            # Add page break before availabilities
            elements.append(PageBreak())
            elements.append(Paragraph('Dozenten-Verfügbarkeiten', styles['Heading2']))
            
            avail_data = [['Dozent', 'Typ', 'Zeitraum', 'Dauer', 'Notiz']]
            for avail in availabilities:
                duration = (avail.end_date - avail.start_date).days + 1
                avail_type = 'Urlaub' if avail.type == 'vacation' else 'Nicht verfügbar'
                
                avail_data.append([
                    avail.lecturer.name,
                    avail_type,
                    f"{avail.start_date.strftime('%d.%m.%Y')} - {avail.end_date.strftime('%d.%m.%Y')}",
                    f"{duration} Tage",
                    avail.note or ''
                ])
            
            table = Table(avail_data, colWidths=[40*mm, 25*mm, 45*mm, 20*mm, 40*mm])
            table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            elements.append(table)
        
        # Build the PDF
        doc.build(elements)
        
        # Generate filename
        filename_parts = ['Lehrplan_Bericht']
        if filter_options.get('lecturer_id'):
            lecturer = Lecturer.query.get(filter_options['lecturer_id'])
            if lecturer:
                filename_parts.append(f"Dozent_{lecturer.name.replace(' ', '_')}")
        
        if filter_options.get('curriculum_id'):
            filename_parts.append(f"Batch_{filter_options['curriculum_id'][:8]}")
            
        if filter_options.get('date_range'):
            start, end = filter_options['date_range']
            filename_parts.append(f"{start.strftime('%Y%m%d')}-{end.strftime('%Y%m%d')}")
            
        filename = '_'.join(filename_parts) + '.pdf'
        
        # Return the PDF
        buffer.seek(0)
        return send_file(
            buffer,
            download_name=filename,
            mimetype='application/pdf'
        )
        
    except Exception as e:
        error_msg = f'Fehler beim Erstellen des direkten PDF-Berichts: {str(e)}'
        current_app.logger.error(error_msg)
        flash(error_msg, 'error')
        return redirect(url_for('main.show_timeline'))