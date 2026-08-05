"""MySQL (`musahibe` bazası) — sxem və bütün sorğular.

Bütün məlumat MySQL-də saxlanılır; SQLite istifadə olunmur.
"""
import json
import uuid
from datetime import datetime

import pymysql

import config  # noqa: F401  (sxem miqrasiyasında default dəyər üçün)


def connect():
    return pymysql.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=config.DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS candidates (
        id            INT AUTO_INCREMENT PRIMARY KEY,
        first_name    VARCHAR(190)  NOT NULL,
        last_name     VARCHAR(190)  NOT NULL,
        role          VARCHAR(255)  NOT NULL,
        access_token  CHAR(36)      NOT NULL UNIQUE,
        session_id    VARCHAR(64)   NULL,
        duration_minutes INT        NOT NULL DEFAULT 15,
        status        ENUM('pending','active','completed') NOT NULL DEFAULT 'pending',
        started_at    DATETIME      NULL,
        finished_at   DATETIME      NULL,
        created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_status (status),
        INDEX idx_created (created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS skills (
        id            INT AUTO_INCREMENT PRIMARY KEY,
        candidate_id  INT           NOT NULL,
        name          VARCHAR(255)  NOT NULL,
        level         TINYINT       NOT NULL,
        INDEX idx_candidate (candidate_id),
        CONSTRAINT fk_skills_candidate FOREIGN KEY (candidate_id)
            REFERENCES candidates(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS messages (
        id            INT AUTO_INCREMENT PRIMARY KEY,
        candidate_id  INT           NOT NULL,
        role          ENUM('user','assistant') NOT NULL,
        content       MEDIUMTEXT    NOT NULL,
        created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_candidate (candidate_id, id),
        CONSTRAINT fk_messages_candidate FOREIGN KEY (candidate_id)
            REFERENCES candidates(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS reports (
        id             INT AUTO_INCREMENT PRIMARY KEY,
        candidate_id   INT           NOT NULL UNIQUE,
        overall_score  DECIMAL(3,1)  NULL,
        skill_scores   JSON          NULL,
        strengths      JSON          NULL,
        weaknesses     JSON          NULL,
        summary        TEXT          NULL,
        recommendation ENUM('hire','consider','reject') NULL,
        error          TEXT          NULL,
        created_at     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_reports_candidate FOREIGN KEY (candidate_id)
            REFERENCES candidates(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS users (
        id             INT AUTO_INCREMENT PRIMARY KEY,
        username       VARCHAR(100)  NOT NULL UNIQUE,
        password_hash  VARCHAR(255)  NOT NULL,
        full_name      VARCHAR(255)  NULL,
        role           ENUM('hr','bas_hr') NOT NULL DEFAULT 'hr',
        is_active      TINYINT(1)    NOT NULL DEFAULT 1,
        created_at     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
        last_login     DATETIME      NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS sessions (
        token       CHAR(43)  PRIMARY KEY,
        user_id     INT       NOT NULL,
        expires_at  DATETIME  NOT NULL,
        created_at  DATETIME  NOT NULL DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_expires (expires_at),
        CONSTRAINT fk_sessions_user FOREIGN KEY (user_id)
            REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
]


def _ensure_column(cur, table, column, definition):
    """Sütun yoxdursa əlavə edir — mövcud bazaların miqrasiyası üçün."""
    cur.execute(
        "SELECT COUNT(*) AS n FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
        (table, column),
    )
    if cur.fetchone()["n"] == 0:
        cur.execute(f"ALTER TABLE `{table}` ADD COLUMN `{column}` {definition}")


def init_schema():
    """Cədvəlləri yaradır və miqrasiyaları tətbiq edir (idempotent)."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            for statement in SCHEMA:
                cur.execute(statement)
            # Cihaz kilidi sonradan əlavə olundu
            _ensure_column(cur, "candidates", "session_id", "VARCHAR(64) NULL AFTER access_token")
            # Müsahibə müddəti hər namizəd üçün ayrıca təyin olunur
            _ensure_column(cur, "candidates", "duration_minutes",
                           f"INT NOT NULL DEFAULT {config.INTERVIEW_MINUTES} AFTER session_id")
            # Rollar sonradan əlavə olundu — mövcud istifadəçilər sadə 'hr' olur
            _ensure_column(cur, "users", "role",
                           "ENUM('hr','bas_hr') NOT NULL DEFAULT 'hr' AFTER full_name")
    finally:
        conn.close()


def _json_loads(value, default):
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _fmt(row):
    """DATETIME/DECIMAL sahələrini JSON-a uyğun tiplərə çevirir."""
    if row is None:
        return None
    out = {}
    for key, value in row.items():
        if isinstance(value, datetime):
            out[key] = value.strftime("%Y-%m-%d %H:%M:%S")
        elif hasattr(value, "quantize"):  # Decimal
            out[key] = float(value)
        else:
            out[key] = value
    return out


# ---------------------------------------------------------------- namizədlər

def create_candidate(first_name, last_name, role, skills, duration_minutes=None):
    """skills: [{"name": str, "level": 1..10}] — namizədi və bacarıqlarını yazır."""
    token = str(uuid.uuid4())
    if duration_minutes is None:
        duration_minutes = config.INTERVIEW_MINUTES
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO candidates "
                "  (first_name, last_name, role, access_token, duration_minutes) "
                "VALUES (%s, %s, %s, %s, %s)",
                (first_name, last_name, role, token, duration_minutes),
            )
            candidate_id = cur.lastrowid
            for skill in skills:
                cur.execute(
                    "INSERT INTO skills (candidate_id, name, level) VALUES (%s, %s, %s)",
                    (candidate_id, skill["name"], skill["level"]),
                )
    finally:
        conn.close()
    return get_candidate(candidate_id)


def update_candidate(candidate_id, first_name, last_name, role, skills,
                     duration_minutes):
    """Namizədi yeniləyir — YALNIZ müsahibə hələ başlamayıbsa (status='pending').

    Başlamış müsahibədə suallar artıq verilmiş bacarıqlara görə qurulub, ona görə
    dəyişiklik yazışma ilə hesabatı uyğunsuz edərdi.

    Qaytarır: True — yeniləndi, False — namizəd yoxdur və ya artıq başlayıb.
    """
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE candidates SET first_name=%s, last_name=%s, role=%s, "
                "  duration_minutes=%s "
                "WHERE id=%s AND status='pending'",
                (first_name, last_name, role, duration_minutes, candidate_id),
            )
            if cur.rowcount != 1:
                # Sətir tapılmadı, ya da dəyərlər eynidir — statusu yoxlayaq
                cur.execute("SELECT status FROM candidates WHERE id=%s", (candidate_id,))
                row = cur.fetchone()
                if not row or row["status"] != "pending":
                    return False

            cur.execute("DELETE FROM skills WHERE candidate_id=%s", (candidate_id,))
            for skill in skills:
                cur.execute(
                    "INSERT INTO skills (candidate_id, name, level) VALUES (%s, %s, %s)",
                    (candidate_id, skill["name"], skill["level"]),
                )
            return True
    finally:
        conn.close()


def _load_skills(cur, candidate_id):
    cur.execute(
        "SELECT name, level FROM skills WHERE candidate_id = %s ORDER BY id",
        (candidate_id,),
    )
    return [dict(r) for r in cur.fetchall()]


def get_candidate(candidate_id):
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM candidates WHERE id = %s", (candidate_id,))
            row = cur.fetchone()
            if not row:
                return None
            candidate = _fmt(row)
            candidate["skills"] = _load_skills(cur, candidate_id)
            return candidate
    finally:
        conn.close()


def get_candidate_by_token(token):
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM candidates WHERE access_token = %s", (token,))
            row = cur.fetchone()
            if not row:
                return None
            candidate = _fmt(row)
            candidate["skills"] = _load_skills(cur, candidate["id"])
            return candidate
    finally:
        conn.close()


def list_candidates():
    """Admin siyahısı — hər namizəd üçün bacarıqlar və (varsa) hesabat xülasəsi."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM candidates ORDER BY id DESC")
            rows = [_fmt(r) for r in cur.fetchall()]
            for candidate in rows:
                candidate["skills"] = _load_skills(cur, candidate["id"])
                cur.execute(
                    "SELECT overall_score, recommendation FROM reports WHERE candidate_id = %s",
                    (candidate["id"],),
                )
                report = cur.fetchone()
                candidate["report"] = _fmt(report) if report else None
                # Cihaz kilidi vurulubmu (session_id özü admin panelə göndərilmir)
                candidate["locked"] = bool(candidate.pop("session_id", None))
            return rows
    finally:
        conn.close()


def delete_candidate(candidate_id):
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM candidates WHERE id = %s", (candidate_id,))
            return cur.rowcount == 1
    finally:
        conn.close()


def mark_started(candidate_id):
    """pending → active (yalnız bir dəfə; başlanğıc vaxtını yazır)."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE candidates SET status = 'active', started_at = NOW() "
                "WHERE id = %s AND status = 'pending'",
                (candidate_id,),
            )
    finally:
        conn.close()


def bind_session_if_free(candidate_id, session_id):
    """Müsahibəni cihaz sessiyasına bağlayır — ATOMİK iddia.

    Yalnız `session_id` hələ boşdursa yazır. Bu çağırışla bağlandısa True,
    artıq başqa cihaza bağlıdırsa False qaytarır. Şərtli UPDATE olduğu üçün
    iki brauzer eyni anda açsa da yalnız biri qazanır.
    """
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE candidates SET session_id = %s "
                "WHERE id = %s AND session_id IS NULL",
                (session_id, candidate_id),
            )
            return cur.rowcount == 1
    finally:
        conn.close()


MAX_DURATION_MINUTES = 180


def extend_interview(candidate_id, minutes):
    """Müsahibənin ümumi müddətini `minutes` qədər artırır.

    Taymer `started_at + duration_minutes` ilə hesablandığı üçün ümumi müddəti
    artırmaq bitmə vaxtını irəli çəkir. Tamamlanmış müsahibə uzadıla bilməz.

    Qaytarır: (xəta_mətni, None) və ya (None, yeni_ümumi_müddət).
    """
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status, duration_minutes FROM candidates WHERE id = %s",
                (candidate_id,),
            )
            row = cur.fetchone()
            if not row:
                return "Namizəd tapılmadı", None
            if row["status"] == "completed":
                return "Müsahibə artıq tamamlanıb", None

            new_total = int(row["duration_minutes"]) + minutes
            if new_total > MAX_DURATION_MINUTES:
                return (f"Ümumi müddət {MAX_DURATION_MINUTES} dəqiqədən çox ola bilməz "
                        f"(hazırda {row['duration_minutes']} dəq)"), None

            cur.execute(
                "UPDATE candidates SET duration_minutes = %s "
                "WHERE id = %s AND status <> 'completed'",
                (new_total, candidate_id),
            )
            if cur.rowcount != 1:
                return "Müsahibə artıq tamamlanıb", None
            return None, new_total
    finally:
        conn.close()


def get_timing(candidate_id):
    """Müsahibənin qalan vaxtı. Qaytarır None — hələ başlamayıbsa.

    Müddət namizədin öz `duration_minutes` sütunundan götürülür.
    Bütün hesablama MySQL saatı ilə aparılır: `started_at` MySQL `NOW()` ilə
    yazılır, müqayisə də `NOW()` ilə gedir. Python `utcnow()` ilə müqayisə
    etsək, MySQL yerli vaxtda (+04) işlədiyi üçün 4 saat sürüşmə olardı.
    """
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT started_at, duration_minutes, "
                "  TIMESTAMPADD(MINUTE, duration_minutes, started_at) AS expires_at, "
                "  TIMESTAMPDIFF(SECOND, NOW(), "
                "    TIMESTAMPADD(MINUTE, duration_minutes, started_at)) AS remaining "
                "FROM candidates WHERE id = %s",
                (candidate_id,),
            )
            row = cur.fetchone()
    finally:
        conn.close()

    if not row or not row["started_at"]:
        return None
    remaining = int(row["remaining"])
    return {
        "started_at": row["started_at"].strftime("%Y-%m-%d %H:%M:%S"),
        "expires_at": row["expires_at"].strftime("%Y-%m-%d %H:%M:%S"),
        "duration_minutes": int(row["duration_minutes"]),
        "remaining_seconds": max(0, remaining),
        "expired": remaining <= 0,
    }


def mark_completed(candidate_id):
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE candidates SET status = 'completed', finished_at = NOW() "
                "WHERE id = %s",
                (candidate_id,),
            )
    finally:
        conn.close()


# ------------------------------------------------------------------ mesajlar

def add_message(candidate_id, role, content):
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO messages (candidate_id, role, content) VALUES (%s, %s, %s)",
                (candidate_id, role, content),
            )
    finally:
        conn.close()


def get_messages(candidate_id):
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT role, content, created_at FROM messages "
                "WHERE candidate_id = %s ORDER BY id",
                (candidate_id,),
            )
            return [_fmt(r) for r in cur.fetchall()]
    finally:
        conn.close()


# ------------------------------------------------------------------ hesabat

def save_report(candidate_id, report):
    """report: dict — overall_score, skill_scores, strengths, weaknesses,
    summary, recommendation, error (ixtiyari). Təkrar çağırışda üstünə yazır."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO reports (candidate_id, overall_score, skill_scores, "
                "  strengths, weaknesses, summary, recommendation, error) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE "
                "  overall_score=VALUES(overall_score), skill_scores=VALUES(skill_scores), "
                "  strengths=VALUES(strengths), weaknesses=VALUES(weaknesses), "
                "  summary=VALUES(summary), recommendation=VALUES(recommendation), "
                "  error=VALUES(error), created_at=NOW()",
                (
                    candidate_id,
                    report.get("overall_score"),
                    json.dumps(report.get("skill_scores") or {}, ensure_ascii=False),
                    json.dumps(report.get("strengths") or [], ensure_ascii=False),
                    json.dumps(report.get("weaknesses") or [], ensure_ascii=False),
                    report.get("summary"),
                    report.get("recommendation"),
                    report.get("error"),
                ),
            )
    finally:
        conn.close()


def get_report(candidate_id):
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM reports WHERE candidate_id = %s", (candidate_id,))
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        return None
    report = _fmt(row)
    report["skill_scores"] = _json_loads(report.get("skill_scores"), {})
    report["strengths"] = _json_loads(report.get("strengths"), [])
    report["weaknesses"] = _json_loads(report.get("weaknesses"), [])
    return report
