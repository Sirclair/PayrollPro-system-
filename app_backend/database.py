import sqlite3

# In database.py
def initialize_database():
    conn = sqlite3.connect("payroll.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,  -- This enforces unique names
            hourly_rate REAL NOT NULL,
            tax_rate REAL DEFAULT 0.15
        )
    ''')
    conn.commit()
    conn.close()