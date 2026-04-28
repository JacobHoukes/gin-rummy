import os
import bcrypt
from itsdangerous import URLSafeTimedSerializer
from fastapi import Request, HTTPException

SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-to-a-long-random-string-before-deploying")
SESSION_COOKIE = "gr_session"

serializer = URLSafeTimedSerializer(SECRET_KEY)


def hash_password(password: str) -> str:
    """This function hashes a plain-text password using bcrypt and returns the hash as a string."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """This function verifies a plain-text password against a bcrypt hash and returns True if they match."""
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_session(user_id: int, session_version: int) -> str:
    """This function creates a signed session token containing the user ID and session version."""
    return serializer.dumps({"id": user_id, "v": session_version})


def decode_session(token: str) -> dict:
    """This function decodes a signed session token and returns the payload, or raises a 401 if invalid or expired."""
    try:
        return serializer.loads(token, max_age=60 * 60 * 24 * 7)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired session")


def get_current_user_id(request: Request) -> int:
    """This function reads the session cookie and returns the user ID, or raises a 401 if not logged in."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Not logged in")
    payload = decode_session(token)
    return payload["id"]


def get_session_payload(request: Request) -> dict:
    """This function reads the session cookie and returns the full payload including session version."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Not logged in")
    return decode_session(token)
