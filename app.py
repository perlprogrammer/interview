"""AI müsahibə platforması — HTTP server (çərçivəsiz, `http.server`)."""
import hmac
import json
import os
import re
import socketserver
import traceback
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler

import agent
import auth
import config
import db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

# Müsahibəni ilk açan brauzerə bağlayan cookie
EXAM_COOKIE = "musahibe_sess"

MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".png": "image/png",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "Musahibe/1.0"

    # ------------------------------------------------------------- köməkçilər

    def log_message(self, fmt, *args):
        print("%s - [%s] %s" % (self.address_string(),
                                self.log_date_time_string(),
                                fmt % args), flush=True)

    def send_json(self, data, status=200, set_cookie=None):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        if set_cookie:
            self.send_header("Set-Cookie", set_cookie)
        self.end_headers()
        self.wfile.write(body)

    # ------------------------------------------------- cihaz kilidi (cookie)

    def get_cookie(self, name):
        raw = self.headers.get("Cookie") or ""
        for part in raw.split(";"):
            if "=" in part:
                key, value = part.strip().split("=", 1)
                if key == name:
                    return value
        return ""

    def exam_cookie(self):
        return self.get_cookie(EXAM_COOKIE)

    def cookie_header(self, value):
        return (f"{EXAM_COOKIE}={value}; Path=/; Max-Age=86400; "
                f"HttpOnly; SameSite=Lax")

    def session_matches(self, candidate):
        """Müsahibə bir cihaza bağlıdırsa, cari brauzer həmin cihazdırmı?

        Hələ bağlanmayıbsa (session_id boş) True qaytarır.
        """
        bound = candidate.get("session_id")
        if not bound:
            return True
        return self.exam_cookie() == bound

    def send_locked(self):
        self.send_json({
            "error": "Bu müsahibə linki başqa cihazda açılıb",
            "locked": True,
        }, 403)

    def send_text(self, text, status=200):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        """Sorğu gövdəsini oxuyur — həm Content-Length, həm chunked üçün.

        Proxy arxasında (nginx/Istio) POST gövdəsi tez-tez chunked gəlir;
        `http.server` onu avtomatik açmır.
        """
        encoding = (self.headers.get("Transfer-Encoding") or "").lower()
        if "chunked" in encoding:
            chunks = []
            while True:
                line = self.rfile.readline()
                if not line:
                    break
                try:
                    size = int(line.strip().split(b";")[0], 16)
                except (ValueError, IndexError):
                    break
                if size == 0:
                    self.rfile.readline()
                    break
                chunks.append(self.rfile.read(size))
                self.rfile.readline()
            raw = b"".join(chunks)
        else:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length > 0 else b""

        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except (ValueError, UnicodeDecodeError):
            return {}

    def admin_session(self):
        token = self.headers.get("X-Admin-Token") or ""
        return auth.get_session(token)

    def require_admin(self, role=None):
        """Sessiya varsa qaytarır, yoxdursa 401/403 göndərib None qaytarır.

        role verilsə, istifadəçinin rolu həmin rol olmalıdır.
        """
        session = self.admin_session()
        if not session:
            self.send_json({"error": "Giriş tələb olunur"}, 401)
            return None
        if role and session.get("role") != role:
            self.send_json({
                "error": "Bu əməliyyat üçün icazəniz yoxdur",
                "required_role": auth.role_label(role),
            }, 403)
            return None
        return session

    def serve_file(self, relative_path):
        file_path = os.path.abspath(os.path.join(STATIC_DIR, relative_path))
        if os.path.commonpath([file_path, STATIC_DIR]) != STATIC_DIR:
            self.send_text("Forbidden", 403)
            return
        if not os.path.isfile(file_path):
            self.send_text("Not Found", 404)
            return

        _, ext = os.path.splitext(file_path)
        with open(file_path, "rb") as f:
            content = f.read()
        self.send_response(200)
        self.send_header("Content-Type", MIME_TYPES.get(ext.lower(), "application/octet-stream"))
        self.send_header("Content-Length", str(len(content)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(content)

    def redirect(self, location):
        self.send_response(302)
        self.send_header("Location", location)
        self.end_headers()

    # -------------------------------------------------------------------- GET

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        try:
            # --- statik səhifələr ---
            if path == "/":
                self.send_json({"name": "AI Müsahibə Platforması", "status": "işləyir",
                                "admin": "/admin/"})
                return
            if path in ("/admin", "/candidate", "/watch"):
                query = f"?{parsed.query}" if parsed.query else ""
                self.redirect(f"{path}/{query}")
                return
            if path == "/admin/":
                self.serve_file("admin/index.html")
                return
            if path == "/watch/":
                self.serve_file("watch/index.html")
                return
            if path == "/candidate/":
                self.serve_file("candidate/index.html")
                return
            if (path.startswith("/admin/") or path.startswith("/candidate/")
                    or path.startswith("/watch/")):
                self.serve_file(path.lstrip("/"))
                return


            # --- admin API ---
            if path == "/api/admin/me":
                session = self.require_admin()
                if session:
                    self.send_json(session)
                return

            if path == "/api/admin/candidates":
                if not self.require_admin():
                    return
                self.send_json(db.list_candidates())
                return

            # --- istifadəçilər (yalnız Baş HR mütəxəssis) ---
            if path == "/api/admin/users":
                session = self.require_admin(role="bas_hr")
                if not session:
                    return
                self.send_json({
                    "users": auth.list_users(),
                    "me": session["user_id"],
                    "roles": [{"value": k, "label": v} for k, v in auth.ROLES.items()],
                })
                return

            match = re.fullmatch(r"/api/admin/candidates/(\d+)", path)
            if match:
                if not self.require_admin():
                    return
                candidate = db.get_candidate(int(match.group(1)))
                if not candidate:
                    self.send_json({"error": "Namizəd tapılmadı"}, 404)
                    return
                candidate["report"] = db.get_report(candidate["id"])
                candidate["messages"] = db.get_messages(candidate["id"])
                self.send_json(candidate)
                return

            # --- canlı izləmə (yalnız Baş HR mütəxəssis) ---
            # Yalnız OXUYUR: cihaz kilidini vurmur, sessiya yaratmır, mesaj yazmır.
            match = re.fullmatch(r"/api/watch/([0-9a-fA-F-]{36})", path)
            if match:
                if not self.require_admin(role="bas_hr"):
                    return
                candidate = db.get_candidate_by_token(match.group(1))
                if not candidate:
                    self.send_json({"error": "Müsahibə tapılmadı"}, 404)
                    return
                self.send_json({
                    "first_name": candidate["first_name"],
                    "last_name": candidate["last_name"],
                    "role": candidate["role"],
                    "status": candidate["status"],
                    "skills": candidate["skills"],
                    "messages": db.get_messages(candidate["id"]),
                    "timing": db.get_timing(candidate["id"]),
                    "duration_minutes": candidate["duration_minutes"],
                })
                return

            # --- namizəd API ---
            match = re.fullmatch(r"/api/interview/([0-9a-fA-F-]{36})", path)
            if match:
                token = match.group(1)
                candidate = db.get_candidate_by_token(token)
                if not candidate:
                    self.send_json({"error": "Link etibarsızdır"}, 404)
                    return

                # --- cihaz kilidi: linki ilk açan brauzer sahiblənir ---
                set_cookie = None
                if not candidate.get("session_id"):
                    my_sid = self.exam_cookie() or uuid.uuid4().hex
                    if db.bind_session_if_free(candidate["id"], my_sid):
                        set_cookie = self.cookie_header(my_sid)
                        candidate["session_id"] = my_sid
                    else:
                        # Yarışda uduzduq — həmin an başqa brauzer bağladı
                        candidate = db.get_candidate_by_token(token)
                        if not self.session_matches(candidate):
                            self.send_locked()
                            return
                elif not self.session_matches(candidate):
                    self.send_locked()
                    return

                timing = db.get_timing(candidate["id"])
                # Namizəd səhifəni bağlayıb vaxt bitəndən sonra qayıdıbsa — bağlayırıq
                if candidate["status"] == "active" and timing and timing["expired"]:
                    finalize_interview(candidate, timeout_note(candidate))
                    candidate = db.get_candidate(candidate["id"])

                self.send_json({
                    "first_name": candidate["first_name"],
                    "last_name": candidate["last_name"],
                    "role": candidate["role"],
                    "status": candidate["status"],
                    "skills": candidate["skills"],
                    "messages": db.get_messages(candidate["id"]),
                    "timing": timing,
                    "duration_minutes": candidate["duration_minutes"],
                }, set_cookie=set_cookie)
                return

            self.send_text("Not Found", 404)

        except Exception as exc:
            traceback.print_exc()
            self.send_json({"error": f"Server xətası: {exc}"}, 500)

    # ------------------------------------------------------------------- POST

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        data = self.read_body()

        try:
            # --- giriş / çıxış ---
            if path == "/api/admin/login":
                username = (data.get("username") or "").strip()
                password = data.get("password") or ""
                if not username or not password:
                    self.send_json({"error": "İstifadəçi adı və parol tələb olunur"}, 400)
                    return
                session = auth.login(username, password)
                if not session:
                    self.send_json({"error": "İstifadəçi adı və ya parol yanlışdır"}, 401)
                    return
                self.send_json(session)
                return

            # --- müsahibənin vaxtını uzatmaq (yalnız Baş HR mütəxəssis) ---
            match = re.fullmatch(r"/api/watch/([0-9a-fA-F-]{36})/extend", path)
            if match:
                session = self.require_admin(role="bas_hr")
                if not session:
                    return
                candidate = db.get_candidate_by_token(match.group(1))
                if not candidate:
                    self.send_json({"error": "Müsahibə tapılmadı"}, 404)
                    return
                try:
                    minutes = int(data.get("minutes"))
                except (TypeError, ValueError):
                    self.send_json({"error": "Dəqiqə rəqəm olmalıdır"}, 400)
                    return
                if not 1 <= minutes <= 60:
                    self.send_json({"error": "Bir dəfəyə 1-60 dəqiqə əlavə etmək olar"}, 400)
                    return

                error, new_total = db.extend_interview(candidate["id"], minutes)
                if error:
                    self.send_json({"error": error}, 409)
                    return

                print(f"Vaxt uzadıldı: namizəd #{candidate['id']} +{minutes} dəq "
                      f"(yeni ümumi: {new_total}) — {session['username']}", flush=True)
                self.send_json({
                    "ok": True,
                    "added": minutes,
                    "duration_minutes": new_total,
                    "timing": db.get_timing(candidate["id"]),
                })
                return

            # --- yeni istifadəçi (yalnız Baş HR mütəxəssis, giriş tələb olunur) ---
            if path == "/api/admin/users":
                session = self.require_admin(role="bas_hr")
                if not session:
                    return
                error, user = _new_user(data, session)
                if error:
                    self.send_json({"error": error}, 400)
                else:
                    self.send_json(user, 201)
                return

            if path == "/api/admin/logout":
                auth.logout(self.headers.get("X-Admin-Token") or "")
                self.send_json({"ok": True})
                return

            # --- namizədi düzəltmək (yalnız müsahibə başlamayıbsa) ---
            match = re.fullmatch(r"/api/admin/candidates/(\d+)", path)
            if match:
                if not self.require_admin():
                    return
                candidate_id = int(match.group(1))
                existing = db.get_candidate(candidate_id)
                if not existing:
                    self.send_json({"error": "Namizəd tapılmadı"}, 404)
                    return
                if existing["status"] != "pending":
                    self.send_json({
                        "error": "Müsahibə artıq başlayıb — düzəliş etmək olmaz"}, 409)
                    return
                error, payload = _validate_candidate(data)
                if error:
                    self.send_json({"error": error}, 400)
                    return
                db.update_candidate(candidate_id, **payload)
                self.send_json(db.get_candidate(candidate_id))
                return

            # --- namizəd yaratmaq ---
            if path == "/api/admin/candidates":
                if not self.require_admin():
                    return
                error, payload = _validate_candidate(data)
                if error:
                    self.send_json({"error": error}, 400)
                    return
                candidate = db.create_candidate(**payload)
                self.send_json(candidate, 201)
                return

            # --- müsahibə mesajı ---
            match = re.fullmatch(r"/api/interview/([0-9a-fA-F-]{36})/message", path)
            if match:
                candidate = db.get_candidate_by_token(match.group(1))
                if not candidate:
                    self.send_json({"error": "Link etibarsızdır"}, 404)
                    return

                # Cihaz kilidi. Kilid hələ vurulmayıbsa (namizəd səhifəni açmadan
                # birbaşa POST gəlirsə) burada da ATOMİK olaraq vurulur — əks halda
                # tokeni bilən hər kəs cavab yaza bilərdi.
                set_cookie = None
                if not candidate.get("session_id"):
                    my_sid = self.exam_cookie() or uuid.uuid4().hex
                    if db.bind_session_if_free(candidate["id"], my_sid):
                        # Kilidi məhz bu sorğu vurdu — cookie hələ brauzerdə
                        # olmadığı üçün uyğunluq yoxlaması aparılmır.
                        set_cookie = self.cookie_header(my_sid)
                        candidate["session_id"] = my_sid
                    else:
                        # Yarışda uduzduq — həmin an başqası kilidi vurdu
                        candidate = db.get_candidate(candidate["id"])
                        if not self.session_matches(candidate):
                            self.send_locked()
                            return
                elif not self.session_matches(candidate):
                    self.send_locked()
                    return

                if candidate["status"] == "completed":
                    self.send_json({
                        "reply": "Bu müsahibə artıq tamamlanıb.",
                        "finished": True,
                    }, set_cookie=set_cookie)
                    return

                if candidate["status"] == "pending":
                    db.mark_started(candidate["id"])
                    candidate = db.get_candidate(candidate["id"])  # started_at yenilənsin

                # Vaxt limiti — bitibsə yeni cavab qəbul edilmir
                timing = db.get_timing(candidate["id"])
                if timing and timing["expired"]:
                    note = timeout_note(candidate)
                    finalize_interview(candidate, note)
                    self.send_json({"reply": note, "finished": True, "timing": timing},
                                   set_cookie=set_cookie)
                    return

                user_message = (data.get("message") or "").strip()
                if len(user_message) > 8000:
                    self.send_json({"error": "Mesaj çox uzundur (maksimum 8000 simvol)"}, 400)
                    return

                try:
                    reply, finished = agent.next_turn(candidate, user_message)
                except RuntimeError as exc:  # API açarı yoxdur
                    self.send_json({"error": str(exc)}, 503)
                    return

                if finished:
                    finalize_interview(candidate)

                self.send_json({
                    "reply": reply,
                    "finished": finished,
                    "timing": db.get_timing(candidate["id"]),
                }, set_cookie=set_cookie)
                return

            self.send_text("Not Found", 404)

        except Exception as exc:
            traceback.print_exc()
            self.send_json({"error": f"Server xətası: {exc}"}, 500)

    # ----------------------------------------------------------------- DELETE

    def do_DELETE(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            # --- istifadəçini silmək (yalnız Baş HR mütəxəssis) ---
            match = re.fullmatch(r"/api/admin/users/(\d+)", path)
            if match:
                session = self.require_admin(role="bas_hr")
                if not session:
                    return
                user_id = int(match.group(1))
                if user_id == session["user_id"]:
                    self.send_json({"error": "Öz hesabınızı silə bilməzsiniz"}, 400)
                    return
                # Sonuncu Baş HR silinsə panelə heç kim istifadəçi əlavə edə bilməz
                if auth.count_leads(exclude_id=user_id) == 0:
                    self.send_json({
                        "error": "Sonuncu Baş HR mütəxəssisi silmək olmaz — "
                                 "əvvəlcə başqa Baş HR yaradın"}, 400)
                    return
                if auth.delete_user(user_id):
                    self.send_json({"ok": True})
                else:
                    self.send_json({"error": "İstifadəçi tapılmadı"}, 404)
                return

            match = re.fullmatch(r"/api/admin/candidates/(\d+)", path)
            if match:
                if not self.require_admin():
                    return
                if db.delete_candidate(int(match.group(1))):
                    self.send_json({"ok": True})
                else:
                    self.send_json({"error": "Namizəd tapılmadı"}, 404)
                return
            self.send_text("Not Found", 404)
        except Exception as exc:
            traceback.print_exc()
            self.send_json({"error": f"Server xətası: {exc}"}, 500)


def finalize_interview(candidate, note=None):
    """Müsahibəni bağlayır və hesabatı hazırlayır (ikiqat generasiyadan qorunur)."""
    candidate_id = candidate["id"]
    if note:
        db.add_message(candidate_id, "assistant", note)
    db.mark_completed(candidate_id)
    if not db.get_report(candidate_id):
        agent.generate_report(db.get_candidate(candidate_id))


def timeout_note(candidate):
    return (f"Müsahibə üçün ayrılan {candidate['duration_minutes']} dəqiqə başa çatdı. "
            f"Vaxtınız üçün təşəkkür edirik — nəticələr sizə ayrıca bildiriləcək.")


def _new_user(data, session):
    """Panel daxilində yeni istifadəçi yaradır (yalnız Baş HR çağıra bilər).

    Qaytarır: (xəta_mətni, None) və ya (None, istifadəçi_dict).
    """
    full_name = (data.get("full_name") or "").strip()
    username = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""
    role = (data.get("role") or "hr").strip()

    if not full_name or len(full_name) < 3:
        return "Ad və soyad tam yazılmalıdır", None
    if not re.fullmatch(r"[a-z0-9._-]{2,50}", username):
        return ("İstifadəçi adı 2-50 simvol olmalı və yalnız kiçik latın hərfləri, "
                "rəqəm, nöqtə, alt xətt və defis daxil etməlidir"), None
    if len(password) < 8:
        return "Parol ən azı 8 simvol olmalıdır", None
    if role not in auth.ROLES:
        return "Rol düzgün seçilməyib", None

    error, user = auth.register_user(username, password, full_name[:255], role)
    if error:
        return error, None
    print(f"İstifadəçi yaradıldı: {username} ({role}) — yaradan: {session['username']}",
          flush=True)
    return None, {
        "id": user["id"],
        "username": user["username"],
        "full_name": user["full_name"],
        "role": user["role"],
        "role_label": auth.role_label(user["role"]),
    }


def _validate_candidate(data):
    """(xəta_mətni, düzgün_payload) qaytarır."""
    first_name = (data.get("first_name") or "").strip()
    last_name = (data.get("last_name") or "").strip()
    role = (data.get("role") or "").strip()
    raw_skills = data.get("skills")

    if not first_name or not last_name or not role:
        return "Ad, soyad və vəzifə tələb olunur", None

    duration = data.get("duration_minutes", config.INTERVIEW_MINUTES)
    try:
        duration = int(duration)
    except (TypeError, ValueError):
        return "Müsahibə müddəti rəqəm olmalıdır", None
    if not 1 <= duration <= 180:
        return "Müsahibə müddəti 1-180 dəqiqə arası olmalıdır", None

    if not isinstance(raw_skills, list) or not raw_skills:
        return "Ən azı bir bacarıq əlavə edilməlidir", None
    if len(raw_skills) > 20:
        return "Maksimum 20 bacarıq əlavə edilə bilər", None

    skills = []
    seen = set()
    for item in raw_skills:
        if not isinstance(item, dict):
            return "Bacarıq formatı yanlışdır", None
        name = (item.get("name") or "").strip()
        if not name:
            return "Bacarığın adı boş ola bilməz", None
        if name.lower() in seen:
            return f"Təkrarlanan bacarıq: {name}", None
        seen.add(name.lower())
        try:
            level = int(item.get("level"))
        except (TypeError, ValueError):
            return f"'{name}' üçün səviyyə rəqəm olmalıdır", None
        if not 1 <= level <= 10:
            return f"'{name}' üçün səviyyə 1-10 arası olmalıdır", None
        skills.append({"name": name[:255], "level": level})

    return None, {
        "first_name": first_name[:190],
        "last_name": last_name[:190],
        "role": role[:255],
        "skills": skills,
        "duration_minutes": duration,
    }


class ThreadedServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    db.init_schema()
    if not config.ANTHROPIC_API_KEY:
        print("XƏBƏRDARLIQ: ANTHROPIC_API_KEY .env faylında təyin edilməyib — "
              "müsahibə başlamayacaq.", flush=True)

    server = ThreadedServer(("0.0.0.0", config.PORT), Handler)
    print(f"Müsahibə platforması: http://localhost:{config.PORT}", flush=True)
    print(f"Admin panel:          http://localhost:{config.PORT}/admin/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDayandırılır...", flush=True)
        server.server_close()
