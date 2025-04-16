# PayrollPro System

![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![Flask](https://img.shields.io/badge/flask-2.0+-green.svg)
![License](https://img.shields.io/badge/license-MIT-orange.svg)

A secure Flask-based payroll management system with PDF payslip generation.

## Features

- Employee management (CRUD operations)
- Payroll calculation with overtime support
- PDF payslip generation
- Responsive web interface
- SQLite database backend
- Secure authentication (coming soon)

## Installation

### Prerequisites
- Python 3.8+
- wkhtmltopdf ([Windows installer](https://wkhtmltopdf.org/downloads.html))
- Git

### Setup
```bash
# Clone the repository
git clone https://github.com/Sirclair/PayrollPro-system-.git
cd PayrollPro-system-

# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
copy .env.example .env
