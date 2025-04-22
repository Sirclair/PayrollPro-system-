"""
PayrollPro System - Flask Application
Main application file for employee management and payslip generation.

Key Features:
- Employee CRUD operations
- Pay calculation logic
- PDF payslip generation using WeasyPrint
- SQLite database backend
"""

import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from contextlib import closing
from flask import Flask, render_template, request, redirect, url_for, jsonify, abort, make_response
from weasyprint import HTML, CSS
from weasyprint.text.fonts import FontConfiguration

# Initialize Flask application
app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Application Configuration
# Note: In production, use environment variables for secrets
app.secret_key = 'your-secret-key-here'  # Change for production
app.config['DATABASE'] = '/tmp/payroll.db'  # Using /tmp for Render compatibility

# Database Helper Functions
def get_db():
    """
    Establish and return a database connection.
    Uses SQLite and configures row factory for dictionary-like access.
    """
    db = sqlite3.connect(app.config['DATABASE'])
    db.row_factory = sqlite3.Row  # Enable column access by name
    return db

def init_db():
    """
    Initialize the database with required schema.
    Creates the employees table if it doesn't exist.
    """
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
        logger.info("Database initialized successfully")

def query_db(query, args=(), one=False):
    """
    Execute a database query with safe parameter binding.
    
    Args:
        query: SQL query string
        args: Tuple of parameters for the query
        one: If True, return only the first result
        
    Returns:
        Single dictionary if one=True, else list of dictionaries
    """
    with closing(get_db()) as db:
        try:
            cur = db.execute(query, args)
            rv = cur.fetchall()
            db.commit()
            return (rv[0] if rv else None) if one else rv
        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            raise

# Employee Class for Business Logic
class Employee:
    """Handles employee data and pay calculations."""
    
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
        Calculate pay details including overtime.
        
        Args:
            hours: Total hours worked
            
        Returns:
            Dictionary with pay breakdown (gross, tax, net, etc.)
        """
        try:
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
        except ValueError as e:
            logger.error(f"Invalid hours value: {hours}")
            raise ValueError("Hours must be a valid number")

# Application Routes
@app.route('/')
def dashboard():
    """Display the main dashboard with employee list and average pay rate."""
    try:
        employees = query_db('SELECT * FROM employees ORDER BY name')
        avg_result = query_db('SELECT AVG(hourly_rate) FROM employees', one=True)[0]
        avg_rate = round(float(avg_result), 2) if avg_result else 0.00
        return render_template('dashboard.html', 
                             employees=employees, 
                             avg_rate=avg_rate)
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return render_template('error.html', message="Failed to load dashboard"), 500

@app.route('/add', methods=['POST'])
def add_employee():
    """Handle new employee form submission."""
    if request.method == 'POST':
        try:
            required_fields = ['name', 'hourly_rate']
            if not all(field in request.form for field in required_fields):
                return "Missing required fields", 400
                
            query_db('''
                INSERT INTO employees 
                (name, email, phone, job_title, department, hourly_rate, employment_type) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                request.form['name'].strip(),
                request.form.get('email', '').strip(),
                request.form.get('phone', '').strip(),
                request.form.get('job_title', '').strip(),
                request.form.get('department', '').strip(),
                float(request.form['hourly_rate']),
                request.form.get('employment_type', 'full-time').strip()
            ))
            return redirect(url_for('dashboard'))
        except ValueError:
            return "Invalid hourly rate", 400
        except Exception as e:
            logger.error(f"Error adding employee: {e}")
            return str(e), 500

@app.route('/calculate/<int:emp_id>', methods=['POST'])
def calculate_pay(emp_id):
    """Calculate and return pay details as JSON (AJAX endpoint)."""
    try:
        emp = query_db('SELECT * FROM employees WHERE id = ?', [emp_id], one=True)
        if not emp:
            return jsonify({'error': 'Employee not found'}), 404
            
        employee = Employee(**dict(emp))
        return jsonify(employee.calculate_pay(request.form['hours']))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Pay calculation error: {e}")
        return jsonify({'error': 'Server error'}), 500

@app.route('/delete/<int:emp_id>')
def delete_employee(emp_id):
    """Delete an employee record."""
    try:
        query_db('DELETE FROM employees WHERE id = ?', [emp_id])
        return redirect(url_for('dashboard'))
    except Exception as e:
        logger.error(f"Delete error: {e}")
        return "Failed to delete employee", 500

@app.route('/payslip/<int:emp_id>')
def generate_payslip(emp_id):
    """
    Generate and display payslip for an employee.
    Supports both HTML view and PDF download.
    """
    try:
        # Get employee data
        employee = query_db('SELECT * FROM employees WHERE id = ?', [emp_id], one=True)
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
                            font-size: 10pt;
                        }
                    }
                    body {
                        font-family: Arial, sans-serif;
                        line-height: 1.6;
                    }
                    h1 {
                        color: #2c3e50;
                    }
                    table {
                        width: 100%;
                        border-collapse: collapse;
                        margin: 20px 0;
                    }
                    th, td {
                        border: 1px solid #ddd;
                        padding: 8px;
                        text-align: left;
                    }
                    th {
                        background-color: #f2f2f2;
                    }
                    .total-row {
                        font-weight: bold;
                        background-color: #f9f9f9;
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
                logger.error(f"PDF generation failed: {e}")
                return render_template('error.html', 
                                    message="Failed to generate PDF"), 500
        
        return html
        
    except ValueError as e:
        abort(400, description=f"Invalid hours value: {e}")
    except Exception as e:
        logger.error(f"Payslip generation error: {e}")
        abort(500, description="Internal server error")

@app.route('/employee/<int:employee_id>')
def get_employee(employee_id):
    """API endpoint to get employee data in JSON format."""
    try:
        employee = query_db('SELECT * FROM employees WHERE id = ?', [employee_id], one=True)
        if not employee:
            return jsonify({"error": "Employee not found"}), 404
        return jsonify(dict(employee))
    except Exception as e:
        logger.error(f"Employee API error: {e}")
        return jsonify({"error": "Server error"}), 500

# Application Entry Point
if __name__ == '__main__':
    # Create database directory if needed
    db_path = Path(app.config['DATABASE'])
    if not db_path.parent.exists():
        db_path.parent.mkdir(parents=True)
        logger.info(f"Created database directory at {db_path.parent}")
    
    # Initialize database
    init_db()
    
    # Run the application
    logger.info("Starting PayrollPro application")
    app.run(host='0.0.0.0', port=5000, debug=True)