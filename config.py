"""Konfiqurasiya — `.env` faylından oxunur (xarici kitabxana olmadan)."""
import os

_ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def _load_env():
    if not os.path.exists(_ENV_PATH):
        return
    with open(_ENV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            # Mühitdə artıq varsa üstündən yazmırıq (deploy zamanı env üstünlük təşkil edir)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env()


def _get(key, default=None):
    value = os.environ.get(key)
    return value if value not in (None, "") else default


# --- Claude API ---
ANTHROPIC_API_KEY = _get("ANTHROPIC_API_KEY", "")

# Müsahibə gedişi — sürət vacibdir (namizəd hər cavabdan sonra gözləyir).
MODEL = _get("MODEL", "claude-sonnet-5")

# Yekun hesabat — bir dəfə yaranır, gecikmə əhəmiyyətsizdir, keyfiyyət vacibdir.
REPORT_MODEL = _get("REPORT_MODEL", "claude-opus-5")

# --- Veb server ---
PORT = int(_get("PORT", "5000"))

# --- MySQL ---
DB_HOST = _get("DB_HOST", "127.0.0.1")
DB_PORT = int(_get("DB_PORT", "3306"))
DB_USER = _get("DB_USER", "")
DB_PASSWORD = _get("DB_PASSWORD", "")
DB_NAME = _get("DB_NAME", "musahibe")

# --- Müsahibə parametrləri ---
# Hər bacarıq üçün neçə sual verilsin
QUESTIONS_PER_SKILL = int(_get("QUESTIONS_PER_SKILL", "2"))

# Müsahibənin vaxt limiti (dəqiqə). İlk mesajdan etibarən sayılır.
INTERVIEW_MINUTES = int(_get("INTERVIEW_MINUTES", "15"))

# Admin sessiyasının müddəti (saat)
SESSION_HOURS = int(_get("SESSION_HOURS", "8"))
