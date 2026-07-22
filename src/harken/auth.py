"""Local password, role, and opaque-session primitives."""

from __future__ import annotations

import base64
import hashlib
import re
import secrets

ROLES = ("viewer", "operator", "admin")
MUTATING_ROLES = {"operator", "admin"}
PASSWORD_ITERATIONS = 600_000
_USERNAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@+-]{0,63}$")


def validate_username(value: str) -> str:
    username = value.strip()
    if not _USERNAME.fullmatch(username):
        raise ValueError("username must be 1-64 characters and use letters, numbers, or . _ @ + -")
    return username


def validate_role(value: str) -> str:
    role = value.strip().lower()
    if role not in ROLES:
        raise ValueError(f"role must be one of {', '.join(ROLES)}")
    return role


def validate_password(value: str) -> str:
    if len(value) < 12:
        raise ValueError("password must be at least 12 characters")
    if len(value) > 1024:
        raise ValueError("password must be at most 1024 characters")
    return value


def hash_password(
    password: str,
    *,
    iterations: int = PASSWORD_ITERATIONS,
    salt: bytes | None = None,
) -> str:
    validate_password(password)
    if not 100_000 <= iterations <= 2_000_000:
        raise ValueError("PBKDF2 iterations must be between 100000 and 2000000")
    actual_salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), actual_salt, iterations, dklen=32
    )
    return f"pbkdf2_sha256${iterations}${_b64(actual_salt)}${_b64(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, raw_iterations, raw_salt, raw_digest = encoded.split("$", 3)
        iterations = int(raw_iterations)
        if algorithm != "pbkdf2_sha256" or not 100_000 <= iterations <= 2_000_000:
            return False
        salt = _unb64(raw_salt)
        expected = _unb64(raw_digest)
        if len(salt) < 16 or len(expected) != 32:
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, iterations, dklen=len(expected)
        )
    except (TypeError, ValueError):
        return False
    return secrets.compare_digest(actual, expected)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def session_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


# Equalizes the expensive verifier path for unknown and inactive usernames.
# The value is process-local and never represents a real account.
DUMMY_PASSWORD_HASH = hash_password("invalid-account-password", salt=b"\x00" * 16)
