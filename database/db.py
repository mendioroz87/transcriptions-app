import sqlite3
import hashlib
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'mlabs_transcription.db')

def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            model TEXT DEFAULT 'whisper',
            api_key TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS transcriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            duration_seconds REAL,
            model_used TEXT,
            status TEXT DEFAULT 'pending',
            transcript TEXT,
            word_count INTEGER,
            language TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        );

        CREATE TABLE IF NOT EXISTS user_api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            provider TEXT NOT NULL,
            api_key TEXT NOT NULL,
            label TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, provider),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    """)

    conn.commit()
    conn.close()

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# --- USER OPERATIONS ---

def create_user(username: str, email: str, password: str):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
            (username, email, hash_password(password))
        )
        conn.commit()
        return True, "Account created successfully!"
    except sqlite3.IntegrityError as e:
        if "username" in str(e):
            return False, "Username already taken."
        if "email" in str(e):
            return False, "Email already registered."
        return False, str(e)
    finally:
        conn.close()

def authenticate_user(username_or_email: str, password: str):
    conn = get_connection()
    user = conn.execute(
        "SELECT * FROM users WHERE (username=? OR email=?) AND password_hash=?",
        (username_or_email, username_or_email, hash_password(password))
    ).fetchone()
    conn.close()
    return dict(user) if user else None

def reset_user_password(username_or_email: str, email: str, new_password: str):
    conn = get_connection()
    try:
        user = conn.execute(
            """SELECT id FROM users
               WHERE (username=? OR email=?)
               AND lower(email)=lower(?)""",
            (username_or_email, username_or_email, email)
        ).fetchone()

        if not user:
            return False, "No account matches those details."

        conn.execute(
            "UPDATE users SET password_hash=? WHERE id=?",
            (hash_password(new_password), user["id"])
        )
        conn.commit()
        return True, "Password reset successful. Please sign in with your new password."
    finally:
        conn.close()

def get_user_by_id(user_id: int):
    conn = get_connection()
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return dict(user) if user else None

# --- PROJECT OPERATIONS ---

def create_project(user_id: int, name: str, description: str, model: str, api_key: str = None):
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO projects (user_id, name, description, model, api_key) VALUES (?, ?, ?, ?, ?)",
        (user_id, name, description, model, api_key)
    )
    project_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return project_id

def get_user_projects(user_id: int):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM projects WHERE user_id=? ORDER BY created_at DESC", (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_project(project_id: int):
    conn = get_connection()
    row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def update_project(project_id: int, name: str, description: str, model: str, api_key: str = None):
    conn = get_connection()
    conn.execute(
        "UPDATE projects SET name=?, description=?, model=?, api_key=? WHERE id=?",
        (name, description, model, api_key, project_id)
    )
    conn.commit()
    conn.close()

def delete_project(project_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM transcriptions WHERE project_id=?", (project_id,))
    conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
    conn.commit()
    conn.close()

def delete_projects_bulk(project_ids: list[int]) -> int:
    """Delete multiple projects and their transcriptions. Returns number deleted."""
    if not project_ids:
        return 0

    conn = get_connection()
    try:
        q_marks = ",".join("?" for _ in project_ids)
        conn.execute(
            f"DELETE FROM transcriptions WHERE project_id IN ({q_marks})",
            project_ids
        )
        cur = conn.execute(
            f"DELETE FROM projects WHERE id IN ({q_marks})",
            project_ids
        )
        conn.commit()
        return cur.rowcount or 0
    finally:
        conn.close()

# --- TRANSCRIPTION OPERATIONS ---

def create_transcription(project_id: int, filename: str, original_filename: str, model_used: str):
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO transcriptions (project_id, filename, original_filename, model_used, status) VALUES (?, ?, ?, ?, 'processing')",
        (project_id, filename, original_filename, model_used)
    )
    tid = cursor.lastrowid
    conn.commit()
    conn.close()
    return tid

def update_transcription(tid: int, transcript: str, status: str, duration: float = None,
                          word_count: int = None, language: str = None):
    conn = get_connection()
    conn.execute(
        """UPDATE transcriptions SET transcript=?, status=?, duration_seconds=?,
           word_count=?, language=?, completed_at=? WHERE id=?""",
        (transcript, status, duration, word_count, language,
         datetime.now().isoformat(), tid)
    )
    conn.commit()
    conn.close()

def get_project_transcriptions(project_id: int):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM transcriptions WHERE project_id=? ORDER BY created_at DESC",
        (project_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_transcription(tid: int):
    conn = get_connection()
    row = conn.execute("SELECT * FROM transcriptions WHERE id=?", (tid,)).fetchone()
    conn.close()
    return dict(row) if row else None

def delete_transcription(tid: int):
    conn = get_connection()
    conn.execute("DELETE FROM transcriptions WHERE id=?", (tid,))
    conn.commit()
    conn.close()

def delete_transcriptions_bulk(transcription_ids: list[int]) -> int:
    """Delete multiple transcriptions. Returns number deleted."""
    if not transcription_ids:
        return 0

    conn = get_connection()
    try:
        q_marks = ",".join("?" for _ in transcription_ids)
        cur = conn.execute(
            f"DELETE FROM transcriptions WHERE id IN ({q_marks})",
            transcription_ids
        )
        conn.commit()
        return cur.rowcount or 0
    finally:
        conn.close()

# --- API KEYS ---

def save_api_key(user_id: int, provider: str, api_key: str, label: str = None):
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO user_api_keys (user_id, provider, api_key, label) VALUES (?, ?, ?, ?)",
        (user_id, provider, api_key, label)
    )
    conn.commit()
    conn.close()

def get_user_api_keys(user_id: int):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM user_api_keys WHERE user_id=?", (user_id,)
    ).fetchall()
    conn.close()
    return {r["provider"]: r["api_key"] for r in rows}
