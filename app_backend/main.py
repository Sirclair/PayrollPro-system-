"""
PayrollPro System - Flask Application
Main application file handling employee management and payslip generation.
"""

# Import required libraries
from flask import Flask, render_template, request, redirect, url_for, jsonify, abort, make_response
from datetime import datetime
from pathlib import Path  # For path operations
import sqlite3  # Database operations
import logging  # Application logging
from contextlib import closing  # For proper DB connection handling
from weasyprint import HTML, CSS  # PDF generation
from weasyprint.text.fonts import FontConfiguration  # PDF font handling

# Initialize Flask application
app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Application configuration
app.secret_key = 'your_secret_key_here'  # Should be changed to a secure random key in production
app.config['DATABASE'] = 'instance/payroll.db'  # SQLite database file path

# Database helper functions
def get_db():
    """Establish and return a new database connection."""
    db = sqlite3.connect(app.config['DATABASE'])
    db.row_factory = sqlite3.Row  # Return rows as dictionaries
    return db

def init_db():
    """Initialize the database with required tables."""
    with app.app_context(), closing(get_db()) as db:
        # Create employees table if it doesn't exist
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
    """
    Execute a database query.
    Args:
        query: SQL query string
        args: Tuple of query parameters
        one: If True, return only the first result
    Returns:
        Query results as dictionary or list of dictionaries
    """
    with closing(get_db()) as db:
        cur = db.execute(query, args)
        rv = cur.fetchall()
        db.commit()
        return (rv[0] if rv else None) if one else rv

class Employee:
    """Employee class to handle employee data and pay calculations."""
    
    def __init__(self, **kwargs):
        """Initialize employee with provided attributes."""
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
        """
        Calculate pay details for the employee.
        Args:
            hours: Number of hours worked
        Returns:
            Dictionary with pay breakdown (gross, tax, net, etc.)
        """
        hours = float(hours)
        regular_hours = min(hours, 40)  # First 40 hours are regular
        overtime_hours = max(hours - 40, 0)  # Hours beyond 40 are overtime
        regular_pay = regular_hours * self.hourly_rate
        overtime_pay = overtime_hours * self.hourly_rate * 1.5  # 1.5x rate for overtime
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

# Application routes
@app.route('/')
def dashboard():
    """Display the main dashboard with employee list and average pay rate."""
    employees = query_db('SELECT * FROM employees')
    avg_result = query_db('SELECT AVG(hourly_rate) FROM employees', one=True)[0]
    avg_rate = round(float(avg_result), 2) if avg_result else 0.00
    return render_template('dashboard.html', employees=employees, avg_rate=avg_rate)

@app.route('/add', methods=['POST'])
def add_employee():
    """Handle new employee form submission."""
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
    """Calculate and return pay details for an employee (AJAX endpoint)."""
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
    """Delete an employee record."""
    query_db('DELETE FROM employees WHERE id = ?', [emp_id])
    return redirect(url_for('dashboard'))

@app.route('/payslip/<int:emp_id>')
def generate_payslip(emp_id):
    """
    Generate and display payslip for an employee.
    Supports both HTML view and PDF download.
    """
    try:
        # Get employee data
        db = get_db()
        employee = db.execute('SELECT * FROM employees WHERE id = ?', [emp_id]).fetchone()
        if not employee:
            abort(404, description="Employee not found")
        
        # Calculate pay details
        hours = float(request.args.get('hours', 40))
        emp = Employee(**dict(employee))
        pay_data = emp.calculate_pay(hours)
        
        # Prepare template data
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
        
        # Render HTML template
        html = render_template('payslip.html', **template_data)
        
        # Handle PDF download request
        if 'download' in request.args:
            try:
                # PDF styling configuration
                font_config = FontConfiguration()
                css = CSS(string='''
                    @page {
                        size: A4;
                        margin: 0.5in;
                        @bottom-center {
                            content: counter(page) " / " counter(pages);
                        }
                    }
                    body {
                        font-family: Arial, sans-serif;
                    }
                    table {
                        width: 100%;
                        border-collapse: collapse;
                    }
                    th, td {
                        border: 1px solid #ddd;
                        padding: 8px;
                        text-align: left;
                    }
                ''', font_config=font_config)
                
                # Generate PDF
                pdf = HTML(string=html).write_pdf(stylesheets=[css])
                
                # Create response with PDF
                response = make_response(pdf)
                response.headers['Content-Type'] = 'application/pdf'
                filename = f"payslip_{employee['name'].replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf"
                response.headers['Content-Disposition'] = f'inline; filename={filename}'
                return response
            except Exception as e:
                logger.error(f"PDF generation failed: {str(e)}")
                return f"PDF generation failed: {str(e)}", 500
        
        # Return HTML view by default
        return html
        
    except ValueError as e:
        abort(400, description=f"Invalid hours value: {str(e)}")
    except Exception as e:
        logger.error(f"Payslip generation error: {str(e)}")
        abort(500, description=f"Internal server error: {str(e)}")

@app.route('/employee/<int:employee_id>')
def get_employee(employee_id):
    """API endpoint to get employee data (JSON format)."""
    employee = query_db('SELECT * FROM employees WHERE id = ?', [employee_id], one=True)
    if not employee:
        return jsonify({"error": "Employee not found"}), 404
    return jsonify(dict(employee))

# Application entry point
if __name__ == '__main__':
    # Create instance directory if it doesn't exist
    Path("instance").mkdir(exist_ok=True)
    
    # Initialize database
    init_db()
    
    # Run the application
    app.run(debug=True)