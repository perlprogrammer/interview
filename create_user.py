#!/usr/bin/env python3
"""Panel istifadəçisi yaratmaq / parolunu yeniləmək (serverdən, əl ilə).

Adətən istifadəçilər panelin içindən Baş HR tərəfindən yaradılır. Bu skript
təcili hallar üçündür — məsələn bütün Baş HR hesabları itsə.

İstifadə:
    python3 create_user.py <istifadəçi> [parol] ["Ad Soyad"] [hr|bas_hr]

Parol verilməsə təsadüfi güclü parol yaradılır və bir dəfə ekrana yazılır.
"""
import secrets
import string
import sys

import auth
import db


def _random_password(length=16):
    alphabet = string.ascii_letters + string.digits + "!@#$%*-_"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    username = sys.argv[1]
    password = sys.argv[2] if len(sys.argv) > 2 else _random_password()
    full_name = sys.argv[3] if len(sys.argv) > 3 else username
    role = sys.argv[4] if len(sys.argv) > 4 else "hr"
    generated = len(sys.argv) <= 2

    if role not in auth.ROLES:
        print(f"Xəta: rol '{role}' düzgün deyil. Mümkün: {', '.join(auth.ROLES)}")
        sys.exit(1)

    db.init_schema()
    auth.upsert_user(username, password, full_name, role)
    print(f"Hazırdır — {username} ({auth.role_label(role)})")
    if generated:
        print(f"Parol: {password}")
        print("Bu parol bir daha göstərilməyəcək — indi qeyd edin.")


if __name__ == "__main__":
    main()
