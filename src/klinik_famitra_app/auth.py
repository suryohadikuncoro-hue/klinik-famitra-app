"""Autentikasi: hashing password + sesi login berbasis token (stdlib only)."""
import hashlib
import secrets
import time

from . import database as db

SESSION_TTL_DAYS = 7


def hash_password(password: str, iterations: int = 200_000) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        iters = int(iters)
    except (ValueError, AttributeError):
        return False
    salt = bytes.fromhex(salt_hex)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iters)
    return secrets.compare_digest(dk.hex(), hash_hex)


def create_session(conn, user_id: int, ttl_days: int = SESSION_TTL_DAYS) -> str:
    token = secrets.token_hex(32)
    expires = int(time.time()) + ttl_days * 86400
    conn.execute(
        "INSERT INTO sessions (token, user_id, expires_at) VALUES (%s,%s,%s)",
        (token, user_id, expires),
    )
    conn.commit()
    return token


def get_user_by_token(token: str):
    if not token:
        return None
    conn = db.get_conn()
    row = conn.execute(
        "SELECT u.id, u.username, u.nama, u.role, s.expires_at "
        "FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token = %s",
        (token,),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    if row["expires_at"] < time.time():
        return None
    return dict(row)


def delete_session(token: str):
    conn = db.get_conn()
    conn.execute("DELETE FROM sessions WHERE token = %s", (token,))
    conn.commit()
    conn.close()


def cleanup_expired_sessions():
    conn = db.get_conn()
    conn.execute("DELETE FROM sessions WHERE expires_at < %s", (int(time.time()),))
    conn.commit()
    conn.close()
