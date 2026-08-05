"""Admin autentifikasiyası — pbkdf2 parol hash-i + MySQL-də sessiyalar."""
import hashlib
import hmac
import secrets

import config
import db

_ITERATIONS = 200_000


def hash_password(password):
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return f"pbkdf2_sha256${_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password, stored):
    try:
        algo, iterations, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False


ROLES = {"hr": "HR mütəxəssis", "bas_hr": "Baş HR mütəxəssis"}


def role_label(role):
    return ROLES.get(role, role)


def upsert_user(username, password, full_name=None, role="hr"):
    """İstifadəçini yaradır, varsa parolunu/adını/rolunu yeniləyir."""
    if role not in ROLES:
        role = "hr"
    conn = db.connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (username, password_hash, full_name, role) "
                "VALUES (%s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE password_hash=VALUES(password_hash), "
                "  full_name=VALUES(full_name), role=VALUES(role), is_active=1",
                (username, hash_password(password), full_name, role),
            )
    finally:
        conn.close()


def register_user(username, password, full_name, role):
    """Qeydiyyat — mövcud istifadəçinin üstünə YAZMIR.

    Qaytarır: (xəta_mətni, None) və ya (None, istifadəçi_dict).
    """
    if role not in ROLES:
        return "Rol düzgün seçilməyib", None

    conn = db.connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE username = %s", (username,))
            if cur.fetchone():
                return "Bu istifadəçi adı artıq mövcuddur", None
            cur.execute(
                "INSERT INTO users (username, password_hash, full_name, role) "
                "VALUES (%s, %s, %s, %s)",
                (username, hash_password(password), full_name, role),
            )
            user_id = cur.lastrowid
    finally:
        conn.close()

    return None, {"id": user_id, "username": username,
                  "full_name": full_name, "role": role}


def login(username, password):
    """Uğurlu olsa sessiya tokeni, əks halda None qaytarır."""
    conn = db.connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username, password_hash, full_name, role FROM users "
                "WHERE username = %s AND is_active = 1",
                (username,),
            )
            user = cur.fetchone()
            if not user or not verify_password(password, user["password_hash"]):
                return None

            token = secrets.token_urlsafe(32)
            # Vaxtlar MySQL saatı ilə hesablanır — bax db.get_timing()
            cur.execute(
                "INSERT INTO sessions (token, user_id, expires_at) "
                "VALUES (%s, %s, TIMESTAMPADD(HOUR, %s, NOW()))",
                (token, user["id"], config.SESSION_HOURS),
            )
            cur.execute("UPDATE users SET last_login = NOW() WHERE id = %s", (user["id"],))
            # Vaxtı keçmiş sessiyaları təmizlə
            cur.execute("DELETE FROM sessions WHERE expires_at < NOW()")
    finally:
        conn.close()

    return {
        "token": token,
        "username": user["username"],
        "full_name": user["full_name"] or user["username"],
        "role": user["role"],
        "role_label": role_label(user["role"]),
    }


def list_users():
    conn = db.connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username, full_name, role, is_active, "
                "  DATE_FORMAT(created_at, '%%Y-%%m-%%d %%H:%%i') AS created_at, "
                "  DATE_FORMAT(last_login, '%%Y-%%m-%%d %%H:%%i') AS last_login "
                "FROM users ORDER BY id"
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    for row in rows:
        row["role_label"] = role_label(row["role"])
        row["is_active"] = bool(row["is_active"])
    return rows


def delete_user(user_id):
    conn = db.connect()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
            return cur.rowcount == 1
    finally:
        conn.close()


def count_leads(exclude_id=None):
    """Aktiv Baş HR mütəxəssislərin sayı — sonuncunu silməmək üçün."""
    conn = db.connect()
    try:
        with conn.cursor() as cur:
            if exclude_id:
                cur.execute("SELECT COUNT(*) AS n FROM users "
                            "WHERE role='bas_hr' AND is_active=1 AND id <> %s", (exclude_id,))
            else:
                cur.execute("SELECT COUNT(*) AS n FROM users "
                            "WHERE role='bas_hr' AND is_active=1")
            return int(cur.fetchone()["n"])
    finally:
        conn.close()


def get_session(token):
    """Etibarlı sessiyanı qaytarır, ya da None (vaxtı keçibsə silir)."""
    if not token:
        return None
    conn = db.connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT s.token, u.id AS user_id, u.username, u.full_name, u.role, "
                "  (s.expires_at < NOW()) AS expired "
                "FROM sessions s JOIN users u ON u.id = s.user_id "
                "WHERE s.token = %s AND u.is_active = 1",
                (token,),
            )
            session = cur.fetchone()
            if not session:
                return None
            if session["expired"]:
                cur.execute("DELETE FROM sessions WHERE token = %s", (token,))
                return None
            return {
                "user_id": session["user_id"],
                "username": session["username"],
                "full_name": session["full_name"] or session["username"],
                "role": session["role"],
                "role_label": role_label(session["role"]),
            }
    finally:
        conn.close()


def logout(token):
    if not token:
        return
    conn = db.connect()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sessions WHERE token = %s", (token,))
    finally:
        conn.close()
