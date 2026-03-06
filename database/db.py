import hashlib
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'mlabs_transcription.db')

BOOTSTRAP_OWNER_EMAIL = os.getenv("BOOTSTRAP_OWNER_EMAIL", "mendioroz87@gmail.com").strip().lower()
BOOTSTRAP_OWNER_USERNAME = os.getenv("BOOTSTRAP_OWNER_USERNAME", "mendioroz87").strip()
BOOTSTRAP_OWNER_PASSWORD_HASH = os.getenv(
    "BOOTSTRAP_OWNER_PASSWORD_HASH",
    "5d1c242929b20af70542f3e0e457fe5d8031a4620ac09a2c93eeea28f1c17b1e",
).strip().lower()
BOOTSTRAP_OWNER_PASSWORD = os.getenv("BOOTSTRAP_OWNER_PASSWORD", "").strip()
GOOGLE_PROVIDER = "google"
GOOGLE_ONLY_PASSWORD_SENTINEL = "!google-only!"
PASSWORD_RESET_TTL_MINUTES = max(5, int(os.getenv("PASSWORD_RESET_TTL_MINUTES", "60")))

PERMISSION_LEVELS = {
    "use_only": {
        "label": "Use App Only",
        "can_edit_personal_api_keys": 0,
        "can_edit_team_api_keys": 0,
    },
    "own_key": {
        "label": "Can Edit Own API Keys",
        "can_edit_personal_api_keys": 1,
        "can_edit_team_api_keys": 0,
    },
    "team_key": {
        "label": "Can Edit Team API Keys",
        "can_edit_personal_api_keys": 1,
        "can_edit_team_api_keys": 1,
    },
}

def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def _to_bool(value) -> bool:
    return bool(int(value)) if value is not None else False

def _table_columns(conn, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] for row in rows}

def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()

def _is_pending_invitation_row(invitation_row) -> bool:
    if not invitation_row:
        return False

    expires_at = datetime.fromisoformat(invitation_row["expires_at"])
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return (
        not invitation_row["accepted_at"]
        and not invitation_row["revoked_at"]
        and datetime.now(timezone.utc) <= expires_at
    )

def _permission_flags(permission_level: str) -> tuple[int, int]:
    preset = PERMISSION_LEVELS.get(permission_level, PERMISSION_LEVELS["own_key"])
    return int(preset["can_edit_personal_api_keys"]), int(preset["can_edit_team_api_keys"])

def _permission_level_for(member_row: dict) -> str:
    if bool(member_row.get("can_edit_team_api_keys")):
        return "team_key"
    if bool(member_row.get("can_edit_personal_api_keys")):
        return "own_key"
    return "use_only"

def _normalize_member_dict(row) -> dict | None:
    if not row:
        return None
    member = dict(row)
    member["can_edit_personal_api_keys"] = _to_bool(member.get("can_edit_personal_api_keys"))
    member["can_edit_team_api_keys"] = _to_bool(member.get("can_edit_team_api_keys"))
    member["can_manage_members"] = _to_bool(member.get("can_manage_members"))
    member["is_owner"] = _to_bool(member.get("is_owner"))
    member["is_personal"] = _to_bool(member.get("is_personal"))
    member["permission_level"] = _permission_level_for(member)
    return member

def _get_team_member_row(conn, team_id: int, user_id: int):
    return conn.execute(
        """
        SELECT
            t.id,
            tm.id AS membership_id,
            tm.team_id,
            tm.user_id,
            tm.can_edit_personal_api_keys,
            tm.can_edit_team_api_keys,
            tm.can_manage_members,
            tm.created_at AS member_created_at,
            t.name,
            t.name AS team_name,
            t.owner_user_id,
            t.is_personal,
            CASE WHEN t.owner_user_id = tm.user_id THEN 1 ELSE 0 END AS is_owner
        FROM team_members tm
        JOIN teams t ON t.id = tm.team_id
        WHERE tm.team_id = ? AND tm.user_id = ?
        """,
        (team_id, user_id),
    ).fetchone()

def _ensure_personal_team_for_user(conn, user_id: int, username: str) -> int:
    existing = conn.execute(
        "SELECT id FROM teams WHERE owner_user_id=? AND is_personal=1",
        (user_id,),
    ).fetchone()
    if existing:
        team_id = existing["id"]
    else:
        team_id = conn.execute(
            "INSERT INTO teams (name, owner_user_id, is_personal) VALUES (?, ?, 1)",
            (f"{username}'s Team", user_id),
        ).lastrowid

    conn.execute(
        """
        INSERT OR IGNORE INTO team_members (
            team_id, user_id, can_edit_personal_api_keys, can_edit_team_api_keys, can_manage_members
        ) VALUES (?, ?, 1, 1, 1)
        """,
        (team_id, user_id),
    )
    return team_id

def _migrate_team_data(conn):
    if "team_id" not in _table_columns(conn, "projects"):
        conn.execute("ALTER TABLE projects ADD COLUMN team_id INTEGER")

    users = conn.execute("SELECT id, username FROM users").fetchall()
    personal_team_map = {}
    for user in users:
        personal_team_map[user["id"]] = _ensure_personal_team_for_user(conn, user["id"], user["username"])

    for user_id, team_id in personal_team_map.items():
        conn.execute(
            """
            UPDATE projects
            SET team_id = ?
            WHERE user_id = ?
              AND (team_id IS NULL OR team_id = '')
            """,
            (team_id, user_id),
        )

def _migrate_transcription_data(conn):
    if "summary_text" not in _table_columns(conn, "transcriptions"):
        conn.execute("ALTER TABLE transcriptions ADD COLUMN summary_text TEXT")

def _migrate_user_identity_data(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_identities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            provider TEXT NOT NULL,
            provider_subject TEXT NOT NULL,
            provider_email TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(provider, provider_subject),
            UNIQUE(user_id, provider),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )

def _migrate_password_reset_data(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            email TEXT NOT NULL,
            token TEXT UNIQUE NOT NULL,
            expires_at TEXT NOT NULL,
            used_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )

def _get_bootstrap_password_hash() -> str:
    if BOOTSTRAP_OWNER_PASSWORD:
        return hash_password(BOOTSTRAP_OWNER_PASSWORD)
    if len(BOOTSTRAP_OWNER_PASSWORD_HASH) == 64:
        return BOOTSTRAP_OWNER_PASSWORD_HASH
    return hash_password("sJ7fux9XAHrZbPL")

def _next_available_username(conn, preferred_username: str) -> str:
    base = (preferred_username or "").strip() or "owner"
    if not conn.execute("SELECT 1 FROM users WHERE username=?", (base,)).fetchone():
        return base

    suffix = 2
    while True:
        candidate = f"{base}{suffix}"
        if not conn.execute("SELECT 1 FROM users WHERE username=?", (candidate,)).fetchone():
            return candidate
        suffix += 1

def _ensure_bootstrap_owner(conn):
    if not BOOTSTRAP_OWNER_EMAIL:
        return

    bootstrap_password_hash = _get_bootstrap_password_hash()
    owner = conn.execute(
        "SELECT id, username FROM users WHERE lower(email)=lower(?)",
        (BOOTSTRAP_OWNER_EMAIL,),
    ).fetchone()

    if owner:
        owner_id = owner["id"]
        owner_username = owner["username"]
        conn.execute(
            "UPDATE users SET password_hash=? WHERE id=?",
            (bootstrap_password_hash, owner_id),
        )
    else:
        owner_username = _next_available_username(
            conn,
            BOOTSTRAP_OWNER_USERNAME or BOOTSTRAP_OWNER_EMAIL.split("@")[0],
        )
        owner_id = conn.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
            (owner_username, BOOTSTRAP_OWNER_EMAIL, bootstrap_password_hash),
        ).lastrowid

    _ensure_personal_team_for_user(conn, owner_id, owner_username)
    conn.execute(
        """
        UPDATE team_members
        SET can_edit_personal_api_keys=1,
            can_edit_team_api_keys=1,
            can_manage_members=1
        WHERE user_id=?
          AND team_id IN (SELECT id FROM teams WHERE owner_user_id=?)
        """,
        (owner_id, owner_id),
    )

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

        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            owner_user_id INTEGER NOT NULL,
            is_personal INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (owner_user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS team_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            can_edit_personal_api_keys INTEGER DEFAULT 1,
            can_edit_team_api_keys INTEGER DEFAULT 0,
            can_manage_members INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(team_id, user_id),
            FOREIGN KEY (team_id) REFERENCES teams(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            team_id INTEGER,
            name TEXT NOT NULL,
            description TEXT,
            model TEXT DEFAULT 'whisper',
            api_key TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (team_id) REFERENCES teams(id)
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
            summary_text TEXT,
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

        CREATE TABLE IF NOT EXISTS team_api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER NOT NULL,
            provider TEXT NOT NULL,
            api_key TEXT NOT NULL,
            label TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(team_id, provider),
            FOREIGN KEY (team_id) REFERENCES teams(id)
        );

        CREATE TABLE IF NOT EXISTS team_invitations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER NOT NULL,
            email TEXT NOT NULL,
            invite_token TEXT UNIQUE NOT NULL,
            invited_by_user_id INTEGER NOT NULL,
            can_edit_personal_api_keys INTEGER DEFAULT 1,
            can_edit_team_api_keys INTEGER DEFAULT 0,
            expires_at TEXT NOT NULL,
            accepted_at TEXT,
            revoked_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (team_id) REFERENCES teams(id),
            FOREIGN KEY (invited_by_user_id) REFERENCES users(id)
        );
    """)

    _migrate_team_data(conn)
    _migrate_transcription_data(conn)
    _migrate_user_identity_data(conn)
    _migrate_password_reset_data(conn)
    _ensure_bootstrap_owner(conn)
    cursor.executescript("""
        CREATE INDEX IF NOT EXISTS idx_projects_team_id ON projects(team_id);
        CREATE INDEX IF NOT EXISTS idx_team_members_user_id ON team_members(user_id);
        CREATE INDEX IF NOT EXISTS idx_transcriptions_project_id ON transcriptions(project_id);
        CREATE INDEX IF NOT EXISTS idx_team_invitations_team_id ON team_invitations(team_id);
        CREATE INDEX IF NOT EXISTS idx_user_identities_user_id ON user_identities(user_id);
        CREATE INDEX IF NOT EXISTS idx_password_reset_user_id ON password_reset_tokens(user_id);
    """)
    conn.commit()
    conn.close()

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def has_local_password(user_or_row) -> bool:
    if not user_or_row:
        return False
    if hasattr(user_or_row, "keys") and "password_hash" in user_or_row.keys():
        password_hash = user_or_row["password_hash"]
    elif hasattr(user_or_row, "get"):
        password_hash = user_or_row.get("password_hash")
    else:
        password_hash = str(user_or_row or "")
    return bool(password_hash) and password_hash != GOOGLE_ONLY_PASSWORD_SENTINEL

# --- USER OPERATIONS ---

def create_user(username: str, email: str, password: str):
    return False, "Account creation is invite-only. Ask a team owner for an invite."

def _create_user_internal(
    conn,
    username: str,
    email: str,
    password: str | None = None,
    *,
    password_hash: str | None = None,
):
    username = (username or "").strip()
    email = _normalize_email(email)
    if not username:
        return False, "Username is required.", None
    if not email:
        return False, "Email is required.", None
    if password_hash is None and len(password or "") < 6:
        return False, "Password must be at least 6 characters.", None

    final_password_hash = password_hash or hash_password(password or "")

    try:
        user_id = conn.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
            (username, email, final_password_hash),
        ).lastrowid
    except sqlite3.IntegrityError as exc:
        err = str(exc).lower()
        if "username" in err:
            return False, "Username already taken.", None
        if "email" in err:
            return False, "Email already registered.", None
        return False, str(exc), None

    _ensure_personal_team_for_user(conn, user_id, username)
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return True, "Account created successfully.", dict(user) if user else None

def authenticate_user(username_or_email: str, password: str):
    conn = get_connection()
    try:
        user = conn.execute(
            "SELECT * FROM users WHERE username=? OR lower(email)=lower(?)",
            (username_or_email, username_or_email),
        )
        user = user.fetchone()
        if not user or not has_local_password(user):
            return None
        if user["password_hash"] != hash_password(password):
            return None
        return dict(user)
    finally:
        conn.close()

def verify_user_password(user_id: int, password: str) -> bool:
    conn = get_connection()
    try:
        user = conn.execute("SELECT password_hash FROM users WHERE id=?", (user_id,)).fetchone()
        if not user or not has_local_password(user):
            return False
        return user["password_hash"] == hash_password(password)
    finally:
        conn.close()

def set_user_password(user_id: int, new_password: str):
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE users SET password_hash=? WHERE id=?",
            (hash_password(new_password), user_id),
        )
        conn.commit()
    finally:
        conn.close()

def get_user_by_id(user_id: int):
    conn = get_connection()
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return dict(user) if user else None

def get_user_by_email(email: str):
    conn = get_connection()
    user = conn.execute("SELECT * FROM users WHERE lower(email)=lower(?)", (_normalize_email(email),)).fetchone()
    conn.close()
    return dict(user) if user else None

def get_user_identities(user_id: int):
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT provider, provider_subject, provider_email, created_at
            FROM user_identities
            WHERE user_id=?
            ORDER BY provider ASC
            """,
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def _get_pending_invitation_rows_for_email(conn, email: str):
    return conn.execute(
        """
        SELECT
            i.*,
            t.name AS team_name,
            u.username AS invited_by_username
        FROM team_invitations i
        JOIN teams t ON t.id = i.team_id
        JOIN users u ON u.id = i.invited_by_user_id
        WHERE lower(i.email)=lower(?)
          AND i.accepted_at IS NULL
          AND i.revoked_at IS NULL
        ORDER BY i.created_at DESC
        """,
        (_normalize_email(email),),
    ).fetchall()

def _link_user_identity(conn, user_id: int, provider: str, provider_subject: str, provider_email: str):
    normalized_email = _normalize_email(provider_email)
    existing = conn.execute(
        """
        SELECT id
        FROM user_identities
        WHERE (provider=? AND provider_subject=?)
           OR (user_id=? AND provider=?)
        """,
        (provider, provider_subject, user_id, provider),
    ).fetchone()
    if existing:
        conn.execute(
            """
            UPDATE user_identities
            SET user_id=?, provider_subject=?, provider_email=?
            WHERE id=?
            """,
            (user_id, provider_subject, normalized_email, existing["id"]),
        )
        return

    conn.execute(
        """
        INSERT INTO user_identities (user_id, provider, provider_subject, provider_email)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, provider, provider_subject, normalized_email),
    )

def resolve_google_user_login(provider_subject: str, email: str, preferred_username: str | None = None):
    normalized_email = _normalize_email(email)
    subject = (provider_subject or "").strip()
    if not subject:
        return False, "Google subject claim is missing.", None
    if not normalized_email:
        return False, "Google email claim is missing.", None

    conn = get_connection()
    try:
        identity_user = conn.execute(
            """
            SELECT u.*
            FROM user_identities ui
            JOIN users u ON u.id = ui.user_id
            WHERE ui.provider=? AND ui.provider_subject=?
            """,
            (GOOGLE_PROVIDER, subject),
        ).fetchone()
        if identity_user:
            _link_user_identity(conn, identity_user["id"], GOOGLE_PROVIDER, subject, normalized_email)
            conn.commit()
            return True, "Signed in with Google.", dict(identity_user)

        existing_user = conn.execute(
            "SELECT * FROM users WHERE lower(email)=lower(?)",
            (normalized_email,),
        ).fetchone()
        if existing_user:
            _link_user_identity(conn, existing_user["id"], GOOGLE_PROVIDER, subject, normalized_email)
            conn.commit()
            return True, "Google login linked to your existing account.", dict(existing_user)

        pending_invites = [
            row for row in _get_pending_invitation_rows_for_email(conn, normalized_email) if _is_pending_invitation_row(row)
        ]
        if not pending_invites:
            return False, "This Gmail address does not have a pending invitation.", None

        base_username = (preferred_username or normalized_email.split("@")[0]).strip() or "member"
        username = _next_available_username(conn, base_username)
        ok, msg, user = _create_user_internal(
            conn=conn,
            username=username,
            email=normalized_email,
            password_hash=GOOGLE_ONLY_PASSWORD_SENTINEL,
        )
        if not ok or not user:
            return False, msg, None

        _link_user_identity(conn, user["id"], GOOGLE_PROVIDER, subject, normalized_email)
        conn.commit()
        return True, "Google account created from your invitation.", user
    finally:
        conn.close()

def create_password_reset_request(identifier: str):
    lookup_value = (identifier or "").strip()
    if not lookup_value:
        return False, "Username or email is required.", None

    conn = get_connection()
    try:
        user = conn.execute(
            "SELECT * FROM users WHERE username=? OR lower(email)=lower(?)",
            (lookup_value, lookup_value),
        ).fetchone()
        if not user:
            return True, "If an account matches that identifier, a reset email will be sent.", None

        conn.execute(
            "UPDATE password_reset_tokens SET used_at=? WHERE user_id=? AND used_at IS NULL",
            (_utc_now_iso(), user["id"]),
        )

        token = secrets.token_urlsafe(32)
        expires_at = (
            datetime.now(timezone.utc) + timedelta(minutes=PASSWORD_RESET_TTL_MINUTES)
        ).replace(microsecond=0).isoformat()
        reset_id = conn.execute(
            """
            INSERT INTO password_reset_tokens (user_id, email, token, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (user["id"], _normalize_email(user["email"]), token, expires_at),
        ).lastrowid
        conn.commit()

        payload = conn.execute(
            """
            SELECT prt.id, prt.user_id, prt.email, prt.token, prt.expires_at, prt.created_at, u.username
            FROM password_reset_tokens prt
            JOIN users u ON u.id = prt.user_id
            WHERE prt.id=?
            """,
            (reset_id,),
        ).fetchone()
        return True, "Password reset token created.", dict(payload) if payload else None
    finally:
        conn.close()

def revoke_password_reset_token(token: str):
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE password_reset_tokens SET used_at=? WHERE token=? AND used_at IS NULL",
            (_utc_now_iso(), (token or "").strip()),
        )
        conn.commit()
    finally:
        conn.close()

def get_password_reset_token(token: str):
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT
                prt.*,
                u.username,
                u.email AS user_email
            FROM password_reset_tokens prt
            JOIN users u ON u.id = prt.user_id
            WHERE prt.token=?
            """,
            ((token or "").strip(),),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def validate_password_reset_token(token: str):
    reset_row = get_password_reset_token(token)
    if not _is_reset_token_active(reset_row):
        return False, "This reset link is invalid or has expired.", None
    return True, "Reset link is valid.", reset_row

def _is_reset_token_active(reset_row) -> bool:
    if not reset_row or reset_row.get("used_at"):
        return False
    expires_at = datetime.fromisoformat(reset_row["expires_at"])
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) <= expires_at

def complete_password_reset(token: str, new_password: str):
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT prt.id, prt.user_id, prt.token, prt.expires_at, prt.used_at
            FROM password_reset_tokens prt
            WHERE prt.token=?
            """,
            ((token or "").strip(),),
        ).fetchone()
        reset_payload = dict(row) if row else None
        if not _is_reset_token_active(reset_payload):
            return False, "This reset link is invalid or has expired."

        conn.execute(
            "UPDATE users SET password_hash=? WHERE id=?",
            (hash_password(new_password), reset_payload["user_id"]),
        )
        conn.execute(
            "UPDATE password_reset_tokens SET used_at=? WHERE id=?",
            (_utc_now_iso(), reset_payload["id"]),
        )
        conn.commit()
        return True, "Password updated. You can now sign in."
    finally:
        conn.close()

# --- TEAM / INVITATION OPERATIONS ---

def get_user_teams(user_id: int):
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT
            t.id,
            t.name,
            t.owner_user_id,
            t.is_personal,
            t.created_at,
            tm.can_edit_personal_api_keys,
            tm.can_edit_team_api_keys,
            tm.can_manage_members,
            CASE WHEN t.owner_user_id = tm.user_id THEN 1 ELSE 0 END AS is_owner
        FROM team_members tm
        JOIN teams t ON t.id = tm.team_id
        WHERE tm.user_id = ?
        ORDER BY t.is_personal DESC, t.name ASC
        """,
        (user_id,),
    ).fetchall()
    conn.close()
    return [_normalize_member_dict(r) for r in rows]

def get_user_team(user_id: int, team_id: int):
    conn = get_connection()
    row = _get_team_member_row(conn, team_id, user_id)
    conn.close()
    return _normalize_member_dict(row)

def get_user_default_team_id(user_id: int):
    teams = get_user_teams(user_id)
    if not teams:
        return None
    personal = next((team for team in teams if team.get("is_personal")), None)
    return (personal or teams[0])["id"]

def create_team(owner_user_id: int, name: str):
    team_name = (name or "").strip()
    if not team_name:
        return False, "Team name is required.", None

    conn = get_connection()
    try:
        team_id = conn.execute(
            "INSERT INTO teams (name, owner_user_id, is_personal) VALUES (?, ?, 0)",
            (team_name, owner_user_id),
        ).lastrowid
        conn.execute(
            """
            INSERT INTO team_members (
                team_id, user_id, can_edit_personal_api_keys, can_edit_team_api_keys, can_manage_members
            ) VALUES (?, ?, 1, 1, 1)
            """,
            (team_id, owner_user_id),
        )
        conn.commit()
        return True, "Team created.", get_user_team(owner_user_id, team_id)
    finally:
        conn.close()

def get_team_members(team_id: int, acting_user_id: int):
    conn = get_connection()
    try:
        acting_member = _get_team_member_row(conn, team_id, acting_user_id)
        if not acting_member:
            return []

        rows = conn.execute(
            """
            SELECT
                tm.team_id,
                tm.user_id,
                u.username,
                u.email,
                tm.can_edit_personal_api_keys,
                tm.can_edit_team_api_keys,
                tm.can_manage_members,
                t.owner_user_id,
                t.is_personal,
                CASE WHEN t.owner_user_id = tm.user_id THEN 1 ELSE 0 END AS is_owner
            FROM team_members tm
            JOIN users u ON u.id = tm.user_id
            JOIN teams t ON t.id = tm.team_id
            WHERE tm.team_id = ?
            ORDER BY is_owner DESC, u.username ASC
            """,
            (team_id,),
        ).fetchall()
        return [_normalize_member_dict(r) for r in rows]
    finally:
        conn.close()

def update_team_member_permissions(team_id: int, target_user_id: int, acting_user_id: int, permission_level: str):
    conn = get_connection()
    try:
        acting_member = _normalize_member_dict(_get_team_member_row(conn, team_id, acting_user_id))
        if not acting_member:
            return False, "You are not a member of this team."
        if not acting_member.get("can_manage_members"):
            return False, "You do not have permission to manage team members."

        team = conn.execute("SELECT owner_user_id FROM teams WHERE id=?", (team_id,)).fetchone()
        if not team:
            return False, "Team not found."
        if int(target_user_id) == int(team["owner_user_id"]):
            return False, "Owner permissions cannot be changed."

        exists = conn.execute(
            "SELECT 1 FROM team_members WHERE team_id=? AND user_id=?",
            (team_id, target_user_id),
        ).fetchone()
        if not exists:
            return False, "Target user is not a team member."

        can_edit_personal_api_keys, can_edit_team_api_keys = _permission_flags(permission_level)
        conn.execute(
            """
            UPDATE team_members
            SET can_edit_personal_api_keys=?, can_edit_team_api_keys=?
            WHERE team_id=? AND user_id=?
            """,
            (can_edit_personal_api_keys, can_edit_team_api_keys, team_id, target_user_id),
        )
        conn.commit()
        return True, "Member permissions updated."
    finally:
        conn.close()

def remove_team_member(team_id: int, target_user_id: int, acting_user_id: int):
    conn = get_connection()
    try:
        acting_member = _normalize_member_dict(_get_team_member_row(conn, team_id, acting_user_id))
        if not acting_member:
            return False, "You are not a member of this team."
        if not acting_member.get("can_manage_members"):
            return False, "You do not have permission to manage team members."

        team = conn.execute("SELECT owner_user_id FROM teams WHERE id=?", (team_id,)).fetchone()
        if not team:
            return False, "Team not found."
        if int(target_user_id) == int(team["owner_user_id"]):
            return False, "Owner cannot be removed."

        conn.execute("DELETE FROM team_members WHERE team_id=? AND user_id=?", (team_id, target_user_id))
        conn.commit()
        return True, "Member removed."
    finally:
        conn.close()

def create_team_invitation(
    team_id: int,
    invited_by_user_id: int,
    email: str,
    permission_level: str = "own_key",
    days_valid: int = 7,
):
    normalized_email = _normalize_email(email)
    if not normalized_email:
        return False, "Email is required.", None
    if not normalized_email.endswith("@gmail.com"):
        return False, "Only Gmail addresses can be invited with this flow.", None

    conn = get_connection()
    try:
        inviter = _normalize_member_dict(_get_team_member_row(conn, team_id, invited_by_user_id))
        if not inviter:
            return False, "You are not a member of this team.", None
        if not inviter.get("can_manage_members"):
            return False, "You do not have permission to invite users.", None

        pending = conn.execute(
            """
            SELECT id
            FROM team_invitations
            WHERE team_id=?
              AND lower(email)=lower(?)
              AND accepted_at IS NULL
              AND revoked_at IS NULL
            """,
            (team_id, normalized_email),
        ).fetchone()
        if pending:
            return False, "There is already a pending invite for this email.", None

        can_edit_personal_api_keys, can_edit_team_api_keys = _permission_flags(permission_level)
        invite_token = secrets.token_urlsafe(24)
        expires_at = (datetime.now(timezone.utc) + timedelta(days=max(1, int(days_valid)))).replace(
            microsecond=0
        ).isoformat()

        invitation_id = conn.execute(
            """
            INSERT INTO team_invitations (
                team_id, email, invite_token, invited_by_user_id,
                can_edit_personal_api_keys, can_edit_team_api_keys, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                team_id,
                normalized_email,
                invite_token,
                invited_by_user_id,
                can_edit_personal_api_keys,
                can_edit_team_api_keys,
                expires_at,
            ),
        ).lastrowid
        conn.commit()

        invite = conn.execute(
            """
            SELECT
                id, team_id, email, invite_token, can_edit_personal_api_keys,
                can_edit_team_api_keys, expires_at, created_at
            FROM team_invitations
            WHERE id=?
            """,
            (invitation_id,),
        ).fetchone()
        payload = dict(invite) if invite else None
        if payload:
            payload["can_edit_personal_api_keys"] = _to_bool(payload["can_edit_personal_api_keys"])
            payload["can_edit_team_api_keys"] = _to_bool(payload["can_edit_team_api_keys"])
            payload["permission_level"] = _permission_level_for(payload)
        return True, "Invitation created.", payload
    finally:
        conn.close()

def get_team_invitations(team_id: int, acting_user_id: int):
    conn = get_connection()
    try:
        acting_member = _get_team_member_row(conn, team_id, acting_user_id)
        if not acting_member:
            return []

        rows = conn.execute(
            """
            SELECT
                i.id,
                i.team_id,
                i.email,
                i.invite_token,
                i.can_edit_personal_api_keys,
                i.can_edit_team_api_keys,
                i.expires_at,
                i.accepted_at,
                i.revoked_at,
                i.created_at,
                u.username AS invited_by_username
            FROM team_invitations i
            JOIN users u ON u.id = i.invited_by_user_id
            WHERE i.team_id=?
            ORDER BY i.created_at DESC
            """,
            (team_id,),
        ).fetchall()

        invites = []
        for row in rows:
            invite = dict(row)
            invite["can_edit_personal_api_keys"] = _to_bool(invite["can_edit_personal_api_keys"])
            invite["can_edit_team_api_keys"] = _to_bool(invite["can_edit_team_api_keys"])
            invite["permission_level"] = _permission_level_for(invite)
            invites.append(invite)
        return invites
    finally:
        conn.close()

def get_pending_invitations_for_email(email: str):
    normalized_email = _normalize_email(email)
    if not normalized_email:
        return []

    conn = get_connection()
    try:
        invites = []
        for row in _get_pending_invitation_rows_for_email(conn, normalized_email):
            if not _is_pending_invitation_row(row):
                continue
            invite = dict(row)
            invite["can_edit_personal_api_keys"] = _to_bool(invite.get("can_edit_personal_api_keys"))
            invite["can_edit_team_api_keys"] = _to_bool(invite.get("can_edit_team_api_keys"))
            invite["permission_level"] = _permission_level_for(invite)
            invites.append(invite)
        return invites
    finally:
        conn.close()

def revoke_team_invitation(invitation_id: int, acting_user_id: int):
    conn = get_connection()
    try:
        invitation = conn.execute(
            "SELECT team_id FROM team_invitations WHERE id=?",
            (invitation_id,),
        ).fetchone()
        if not invitation:
            return False, "Invitation not found."

        acting_member = _normalize_member_dict(_get_team_member_row(conn, invitation["team_id"], acting_user_id))
        if not acting_member or not acting_member.get("can_manage_members"):
            return False, "You do not have permission to revoke invites."

        conn.execute(
            """
            UPDATE team_invitations
            SET revoked_at=?
            WHERE id=?
              AND accepted_at IS NULL
              AND revoked_at IS NULL
            """,
            (_utc_now_iso(), invitation_id),
        )
        conn.commit()
        return True, "Invitation revoked."
    finally:
        conn.close()

def accept_team_invitation(invite_token: str, email: str, password: str, username: str = None):
    conn = get_connection()
    try:
        invitation = conn.execute(
            """
            SELECT *
            FROM team_invitations
            WHERE invite_token=?
              AND accepted_at IS NULL
              AND revoked_at IS NULL
            """,
            ((invite_token or "").strip(),),
        ).fetchone()
        if not invitation:
            return False, "Invalid or inactive invite token.", None

        normalized_email = _normalize_email(email)
        if normalized_email != (invitation["email"] or "").strip().lower():
            return False, "Invite email does not match.", None

        expires_at = datetime.fromisoformat(invitation["expires_at"])
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires_at:
            return False, "This invite has expired.", None

        user_row = conn.execute(
            "SELECT * FROM users WHERE lower(email)=lower(?)",
            (normalized_email,),
        ).fetchone()

        if user_row:
            if not has_local_password(user_row):
                return False, "This account uses Google sign-in. Use Google to accept the invitation.", None
            if hash_password(password or "") != user_row["password_hash"]:
                return False, "Password is incorrect for this existing account.", None
            user_id = user_row["id"]
        else:
            ok, msg, user = _create_user_internal(
                conn=conn,
                username=username or "",
                email=normalized_email,
                password=password or "",
            )
            if not ok:
                return False, msg, None
            user_id = user["id"]
            user_row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()

        conn.execute(
            """
            INSERT OR IGNORE INTO team_members (
                team_id, user_id, can_edit_personal_api_keys, can_edit_team_api_keys, can_manage_members
            ) VALUES (?, ?, ?, ?, 0)
            """,
            (
                invitation["team_id"],
                user_id,
                int(invitation["can_edit_personal_api_keys"]),
                int(invitation["can_edit_team_api_keys"]),
            ),
        )
        conn.execute(
            "UPDATE team_invitations SET accepted_at=? WHERE id=?",
            (_utc_now_iso(), invitation["id"]),
        )
        conn.commit()

        return True, "Invitation accepted. You can now use the app.", {
            "user": dict(user_row),
            "team_id": invitation["team_id"],
        }
    finally:
        conn.close()

def accept_pending_team_invitation(invitation_id: int, user_id: int):
    conn = get_connection()
    try:
        invitation = conn.execute(
            """
            SELECT
                i.*,
                t.name AS team_name
            FROM team_invitations i
            JOIN teams t ON t.id = i.team_id
            WHERE i.id=?
            """,
            (invitation_id,),
        ).fetchone()
        if not invitation or not _is_pending_invitation_row(invitation):
            return False, "Invitation is no longer active.", None

        user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if not user:
            return False, "User account not found.", None

        if _normalize_email(user["email"]) != _normalize_email(invitation["email"]):
            return False, "This invitation belongs to a different email address.", None

        conn.execute(
            """
            INSERT OR IGNORE INTO team_members (
                team_id, user_id, can_edit_personal_api_keys, can_edit_team_api_keys, can_manage_members
            ) VALUES (?, ?, ?, ?, 0)
            """,
            (
                invitation["team_id"],
                user_id,
                int(invitation["can_edit_personal_api_keys"]),
                int(invitation["can_edit_team_api_keys"]),
            ),
        )
        conn.execute(
            "UPDATE team_invitations SET accepted_at=? WHERE id=?",
            (_utc_now_iso(), invitation_id),
        )
        conn.commit()

        return True, f"Joined {invitation['team_name']}.", {
            "team_id": invitation["team_id"],
            "team_name": invitation["team_name"],
        }
    finally:
        conn.close()

# --- PROJECT OPERATIONS ---

def create_project(
    user_id: int,
    name: str,
    description: str,
    model: str,
    api_key: str = None,
    team_id: int = None,
):
    conn = get_connection()
    try:
        target_team_id = team_id or get_user_default_team_id(user_id)
        member = _get_team_member_row(conn, target_team_id, user_id) if target_team_id else None
        if not member:
            raise PermissionError("You do not have access to the target team.")

        project_id = conn.execute(
            """
            INSERT INTO projects (user_id, team_id, name, description, model, api_key)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, target_team_id, name, description, model, api_key),
        ).lastrowid
        conn.commit()
        return project_id
    finally:
        conn.close()

def get_user_projects(user_id: int, team_id: int = None):
    conn = get_connection()
    try:
        if team_id is None:
            rows = conn.execute(
                """
                SELECT p.*
                FROM projects p
                JOIN team_members tm ON tm.team_id = p.team_id
                WHERE tm.user_id = ?
                ORDER BY p.created_at DESC
                """,
                (user_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT p.*
                FROM projects p
                JOIN team_members tm ON tm.team_id = p.team_id
                WHERE tm.user_id = ? AND p.team_id = ?
                ORDER BY p.created_at DESC
                """,
                (user_id, team_id),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def get_project(project_id: int, acting_user_id: int = None):
    conn = get_connection()
    try:
        if acting_user_id is None:
            row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        else:
            row = conn.execute(
                """
                SELECT p.*
                FROM projects p
                JOIN team_members tm ON tm.team_id = p.team_id
                WHERE p.id = ? AND tm.user_id = ?
                """,
                (project_id, acting_user_id),
            ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def update_project(
    project_id: int,
    name: str,
    description: str,
    model: str,
    api_key: str = None,
    acting_user_id: int = None,
):
    conn = get_connection()
    try:
        if acting_user_id is not None:
            project = conn.execute(
                """
                SELECT p.id
                FROM projects p
                JOIN team_members tm ON tm.team_id = p.team_id
                WHERE p.id = ? AND tm.user_id = ?
                """,
                (project_id, acting_user_id),
            ).fetchone()
            if not project:
                return False

        conn.execute(
            "UPDATE projects SET name=?, description=?, model=?, api_key=? WHERE id=?",
            (name, description, model, api_key, project_id),
        )
        conn.commit()
        return True
    finally:
        conn.close()

def delete_project(project_id: int, acting_user_id: int = None):
    conn = get_connection()
    try:
        if acting_user_id is not None:
            project = conn.execute(
                """
                SELECT p.id
                FROM projects p
                JOIN team_members tm ON tm.team_id = p.team_id
                WHERE p.id = ? AND tm.user_id = ?
                """,
                (project_id, acting_user_id),
            ).fetchone()
            if not project:
                return False

        conn.execute("DELETE FROM transcriptions WHERE project_id=?", (project_id,))
        conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
        conn.commit()
        return True
    finally:
        conn.close()

def delete_projects_bulk(project_ids: list[int], acting_user_id: int = None) -> int:
    if not project_ids:
        return 0

    conn = get_connection()
    try:
        allowed_ids = project_ids
        if acting_user_id is not None:
            q_marks = ",".join("?" for _ in project_ids)
            rows = conn.execute(
                f"""
                SELECT p.id
                FROM projects p
                JOIN team_members tm ON tm.team_id = p.team_id
                WHERE p.id IN ({q_marks}) AND tm.user_id = ?
                """,
                [*project_ids, acting_user_id],
            ).fetchall()
            allowed_ids = [row["id"] for row in rows]
            if not allowed_ids:
                return 0

        q_marks = ",".join("?" for _ in allowed_ids)
        conn.execute(f"DELETE FROM transcriptions WHERE project_id IN ({q_marks})", allowed_ids)
        cur = conn.execute(f"DELETE FROM projects WHERE id IN ({q_marks})", allowed_ids)
        conn.commit()
        return cur.rowcount or 0
    finally:
        conn.close()

# --- TRANSCRIPTION OPERATIONS ---

def create_transcription(
    project_id: int,
    filename: str,
    original_filename: str,
    model_used: str,
    acting_user_id: int = None,
):
    conn = get_connection()
    try:
        if acting_user_id is not None:
            project = conn.execute(
                """
                SELECT p.id
                FROM projects p
                JOIN team_members tm ON tm.team_id = p.team_id
                WHERE p.id = ? AND tm.user_id = ?
                """,
                (project_id, acting_user_id),
            ).fetchone()
            if not project:
                raise PermissionError("You do not have access to this project.")

        tid = conn.execute(
            """
            INSERT INTO transcriptions (project_id, filename, original_filename, model_used, status)
            VALUES (?, ?, ?, ?, 'processing')
            """,
            (project_id, filename, original_filename, model_used),
        ).lastrowid
        conn.commit()
        return tid
    finally:
        conn.close()

def update_transcription(
    tid: int,
    transcript: str,
    status: str,
    duration: float = None,
    word_count: int = None,
    language: str = None,
    summary_text: str = None,
):
    conn = get_connection()
    try:
        conn.execute(
            """UPDATE transcriptions SET transcript=?, status=?, duration_seconds=?,
               word_count=?, language=?, summary_text=?, completed_at=? WHERE id=?""",
            (
                transcript,
                status,
                duration,
                word_count,
                language,
                summary_text,
                _utc_now_iso(),
                tid,
            ),
        )
        conn.commit()
    finally:
        conn.close()

def get_project_transcriptions(project_id: int, acting_user_id: int = None):
    conn = get_connection()
    try:
        if acting_user_id is None:
            rows = conn.execute(
                "SELECT * FROM transcriptions WHERE project_id=? ORDER BY created_at DESC",
                (project_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT tx.*
                FROM transcriptions tx
                JOIN projects p ON p.id = tx.project_id
                JOIN team_members tm ON tm.team_id = p.team_id
                WHERE tx.project_id = ? AND tm.user_id = ?
                ORDER BY tx.created_at DESC
                """,
                (project_id, acting_user_id),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def get_transcription(tid: int, acting_user_id: int = None):
    conn = get_connection()
    try:
        if acting_user_id is None:
            row = conn.execute("SELECT * FROM transcriptions WHERE id=?", (tid,)).fetchone()
        else:
            row = conn.execute(
                """
                SELECT tx.*
                FROM transcriptions tx
                JOIN projects p ON p.id = tx.project_id
                JOIN team_members tm ON tm.team_id = p.team_id
                WHERE tx.id = ? AND tm.user_id = ?
                """,
                (tid, acting_user_id),
            ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def delete_transcription(tid: int, acting_user_id: int = None):
    conn = get_connection()
    try:
        if acting_user_id is not None:
            existing = conn.execute(
                """
                SELECT tx.id
                FROM transcriptions tx
                JOIN projects p ON p.id = tx.project_id
                JOIN team_members tm ON tm.team_id = p.team_id
                WHERE tx.id = ? AND tm.user_id = ?
                """,
                (tid, acting_user_id),
            ).fetchone()
            if not existing:
                return False

        conn.execute("DELETE FROM transcriptions WHERE id=?", (tid,))
        conn.commit()
        return True
    finally:
        conn.close()

def delete_transcriptions_bulk(transcription_ids: list[int], acting_user_id: int = None) -> int:
    if not transcription_ids:
        return 0

    conn = get_connection()
    try:
        allowed_ids = transcription_ids
        if acting_user_id is not None:
            q_marks = ",".join("?" for _ in transcription_ids)
            rows = conn.execute(
                f"""
                SELECT tx.id
                FROM transcriptions tx
                JOIN projects p ON p.id = tx.project_id
                JOIN team_members tm ON tm.team_id = p.team_id
                WHERE tx.id IN ({q_marks}) AND tm.user_id = ?
                """,
                [*transcription_ids, acting_user_id],
            ).fetchall()
            allowed_ids = [row["id"] for row in rows]
            if not allowed_ids:
                return 0

        q_marks = ",".join("?" for _ in allowed_ids)
        cur = conn.execute(f"DELETE FROM transcriptions WHERE id IN ({q_marks})", allowed_ids)
        conn.commit()
        return cur.rowcount or 0
    finally:
        conn.close()

# --- API KEYS ---

def save_api_key(user_id: int, provider: str, api_key: str, label: str = None):
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO user_api_keys (user_id, provider, api_key, label) VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, provider)
            DO UPDATE SET api_key=excluded.api_key, label=excluded.label
            """,
            (user_id, provider, api_key, label),
        )
        conn.commit()
    finally:
        conn.close()

def get_user_api_keys(user_id: int):
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT provider, api_key FROM user_api_keys WHERE user_id=?",
            (user_id,),
        ).fetchall()
        return {r["provider"]: r["api_key"] for r in rows}
    finally:
        conn.close()

def save_team_api_key(team_id: int, acting_user_id: int, provider: str, api_key: str, label: str = None):
    conn = get_connection()
    try:
        member = _normalize_member_dict(_get_team_member_row(conn, team_id, acting_user_id))
        if not member:
            return False, "You are not a member of this team."
        if not member.get("can_edit_team_api_keys"):
            return False, "You do not have permission to update team API keys."

        conn.execute(
            """
            INSERT INTO team_api_keys (team_id, provider, api_key, label) VALUES (?, ?, ?, ?)
            ON CONFLICT(team_id, provider)
            DO UPDATE SET api_key=excluded.api_key, label=excluded.label
            """,
            (team_id, provider, api_key, label),
        )
        conn.commit()
        return True, "Team API key saved."
    finally:
        conn.close()

def get_team_api_keys(team_id: int, acting_user_id: int = None):
    conn = get_connection()
    try:
        if acting_user_id is not None:
            member = _get_team_member_row(conn, team_id, acting_user_id)
            if not member:
                return {}

        rows = conn.execute(
            "SELECT provider, api_key FROM team_api_keys WHERE team_id=?",
            (team_id,),
        ).fetchall()
        return {r["provider"]: r["api_key"] for r in rows}
    finally:
        conn.close()
