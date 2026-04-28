from passlib.context import CryptContext
from itsdangerous import URLSafeTimedSerializer
from fastapi import Request, HTTPException

SECRET_KEY = "change-this-to-a-long-random-string-before-deploying"
SESSION_COOKIE = "gr_session"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
serializer = URLSafeTimedSerializer(SECRET_KEY)


def hash_password(password: str) -> str:
    """This function hashes a plain-text password using bcrypt and returns the hash."""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """This function verifies a plain-text password against a bcrypt hash and returns True if they match."""
    return pwd_context.verify(plain, hashed)


def create_session(user_id: int) -> str:
    """This function creates a signed session token containing the user's ID and returns it as a string."""
    return serializer.dumps(user_id)


def decode_session(token: str) -> int:
    """This function decodes a signed session token and returns the user ID, or raises an exception if invalid or expired."""
    try:
        return serializer.loads(token, max_age=60 * 60 * 24 * 7)  # 7 days
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired session")


def get_current_user_id(request: Request) -> int:
    """This function reads the session cookie from the request and returns the logged-in user's ID, or raises a 401 if not logged in."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Not logged in")
    return decode_session(token)
