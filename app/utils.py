from datetime import datetime
from .models import Assignment, Course

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']

def check_conflicts(lecturer_id, course_id):
    course = Course.query.get(course_id)
    existing_assignments = Assignment.query.filter_by(lecturer_id=lecturer_id).all()
    
    for assignment in existing_assignments:
        if (course.start_date <= assignment.course.end_date and 
            course.end_date >= assignment.course.start_date):
            return True
    return False 