from flask import Flask, render_template, request, redirect, url_for, jsonify, abort, make_response
from datetime import datetime
from pathlib import Path
import sqlite3
import logging
from contextlib import closing
import pdfkit

# Initialize Flask app
app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# App configuration
app.secret_key = 'your_secret_key_here'  # Change this to a secure secret key
app.config['DATABASE'] = 'instance/payroll.db'

# PDFKit configuration for Windows
PDFKIT_CONFIG = pdfkit.configuration(wkhtmltopdf=r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe')

# Database setup
def get_db():
    db = sqlite3.connect(app.config['DATABASE'])
    db.row_factory = sqlite3.Row
    return db

def init_db():
    with app.app_context(), closing(get_db()) as db:
        db.execute('''
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                job_title TEXT,
                department TEXT,
                hourly_rate REAL NOT NULL,
                employment_type TEXT,
                tax_rate REAL DEFAULT 0.15,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        db.commit()

def query_db(query, args=(), one=False):
    with closing(get_db()) as db:
        cur = db.execute(query, args)
        rv = cur.fetchall()
        db.commit()
        return (rv[0] if rv else None) if one else rv

class Employee:
    def __init__(self, **kwargs):
        self.id = kwargs.get('id')
        self.name = kwargs.get('name')
        self.email = kwargs.get('email')
        self.phone = kwargs.get('phone')
        self.job_title = kwargs.get('job_title')
        self.department = kwargs.get('department')
        self.hourly_rate = kwargs.get('hourly_rate')
        self.employment_type = kwargs.get('employment_type')
        self.tax_rate = kwargs.get('tax_rate', 0.15)
    
    def calculate_pay(self, hours):
        hours = float(hours)
        regular_hours = min(hours, 40)
        overtime_hours = max(hours - 40, 0)
        regular_pay = regular_hours * self.hourly_rate
        overtime_pay = overtime_hours * self.hourly_rate * 1.5
        gross = regular_pay + overtime_pay
        
        return {
            'gross': round(gross, 2),
            'tax': round(gross * self.tax_rate, 2),
            'net': round(gross * (1 - self.tax_rate), 2),
            'regular_hours': regular_hours,
            'overtime_hours': overtime_hours,
            'regular_pay': round(regular_pay, 2),
            'overtime_pay': round(overtime_pay, 2)
        }

# Routes
@app.route('/')
def dashboard():
    employees = query_db('SELECT * FROM employees')
    avg_result = query_db('SELECT AVG(hourly_rate) FROM employees', one=True)[0]
    avg_rate = round(float(avg_result), 2) if avg_result else 0.00
    return render_template('dashboard.html', employees=employees, avg_rate=avg_rate)

@app.route('/add', methods=['POST'])
def add_employee():
    try:
        query_db('''
            INSERT INTO employees 
            (name, email, phone, job_title, department, hourly_rate, employment_type) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            request.form['name'],
            request.form.get('email'),
            request.form.get('phone'),
            request.form.get('job_title'),
            request.form.get('department'),
            float(request.form['hourly_rate']),
            request.form.get('employment_type')
        ))
        return redirect(url_for('dashboard'))
    except Exception as e:
        logger.error(f"Error adding employee: {e}")
        return str(e), 400

@app.route('/calculate/<int:emp_id>', methods=['POST'])
def calculate_pay(emp_id):
    emp = query_db('SELECT * FROM employees WHERE id = ?', [emp_id], one=True)
    if not emp:
        return jsonify({'error': 'Employee not found'}), 404
    
    try:
        employee = Employee(**dict(emp))
        return jsonify(employee.calculate_pay(request.form['hours']))
    except ValueError:
        return jsonify({'error': 'Invalid hours value'}), 400

@app.route('/delete/<int:emp_id>')
def delete_employee(emp_id):
    query_db('DELETE FROM employees WHERE id = ?', [emp_id])
    return redirect(url_for('dashboard'))

@app.route('/payslip/<int:emp_id>')
def generate_payslip(emp_id):
    try:
        db = get_db()
        employee = db.execute('SELECT * FROM employees WHERE id = ?', [emp_id]).fetchone()
        if not employee:
            abort(404, description="Employee not found")
        
        hours = float(request.args.get('hours', 40))
        emp = Employee(**dict(employee))
        pay_data = emp.calculate_pay(hours)
        
        # Prepare all required data for the template
        template_data = {
            'employee': employee,
            'pay_data': pay_data,
            'hours_worked': hours,
            'pay_period': datetime.now().strftime('%B %Y'),
            'current_date': datetime.now().strftime('%Y-%m-%d'),
            'hourly_rate': emp.hourly_rate,
            'overtime_rate': emp.hourly_rate * 1.5,
            'regular_pay': pay_data['regular_pay'],
            'overtime_pay': pay_data['overtime_pay']
        }
        
        html = render_template('payslip.html', **template_data)
        
        if 'download' in request.args:
            try:
                options = {
                    'encoding': 'UTF-8',
                    'quiet': '',
                    'margin-top': '0.5in',
                    'margin-right': '0.5in',
                    'margin-bottom': '0.5in',
                    'margin-left': '0.5in',
                    'enable-local-file-access': '',
                    'footer-center': '[page]/[topage]',
                    'print-media-type': ''
                }
                pdf = pdfkit.from_string(html, False, configuration=PDFKIT_CONFIG, options=options)
                response = make_response(pdf)
                response.headers['Content-Type'] = 'application/pdf'
                filename = f"payslip_{employee['name'].replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf"
                response.headers['Content-Disposition'] = f'inline; filename={filename}'
                return response
            except Exception as e:
                logger.error(f"PDF generation failed: {str(e)}")
                return f"PDF generation failed: {str(e)}", 500
        
        return html
        
    except ValueError as e:
        abort(400, description=f"Invalid hours value: {str(e)}")
    except Exception as e:
        logger.error(f"Payslip generation error: {str(e)}")
        abort(500, description=f"Internal server error: {str(e)}")

@app.route('/employee/<int:employee_id>')
def get_employee(employee_id):
    employee = query_db('SELECT * FROM employees WHERE id = ?', [employee_id], one=True)
    if not employee:
        return jsonify({"error": "Employee not found"}), 404
    return jsonify(dict(employee))

if __name__ == '__main__':
    # Create instance directory if it doesn't exist
    Path("instance").mkdir(exist_ok=True)
    
    # Initialize database
    init_db()
    
    # Run the app
    app.run(debug=True)