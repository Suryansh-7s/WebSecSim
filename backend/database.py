import sqlite3
import os
from passlib.context import CryptContext

# Password Hashing Config
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- PATH FIX: Always create DB in the backend folder ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "websecsim.db")

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Create Users Table
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (username TEXT PRIMARY KEY, password_hash TEXT, role TEXT)''')
    
    # Create Dummy Admin (Password: admin123)
    admin_hash = pwd_context.hash("admin123")
    try:
        c.execute("INSERT INTO users VALUES (?, ?, ?)", ("admin", admin_hash, "admin"))
    except sqlite3.IntegrityError:
        pass # Already exists

    # Create Dummy Student (Password: student123)
    student_hash = pwd_context.hash("student123")
    try:
        c.execute("INSERT INTO users VALUES (?, ?, ?)", ("student", student_hash, "student"))
    except sqlite3.IntegrityError:
        pass

    conn.commit()
    conn.close()
    print(f"Database Initialized at: {DB_NAME}")
    print("Users: admin/admin123, student/student123")

def get_user(username):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # This might fail if table doesn't exist, but init_db fixes that
    c.execute("SELECT * FROM users WHERE username=?", (username,))
    user = c.fetchone()
    conn.close()
    return user

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

if __name__ == "__main__":
    init_db()