"""Local account security primitives and persistence invariants."""

from datetime import datetime, timedelta, timezone

import pytest

from harken.auth import (
    hash_password,
    new_session_token,
    session_token_hash,
    validate_password,
    validate_role,
    validate_username,
    verify_password,
)
from harken.store import Store


def fast_hash(password: str) -> str:
    return hash_password(password, iterations=100_000)


def test_password_hash_is_salted_and_strictly_verified():
    first = fast_hash("correct horse battery")
    second = fast_hash("correct horse battery")
    assert first != second
    assert verify_password("correct horse battery", first)
    assert not verify_password("incorrect horse battery", first)
    assert not verify_password("anything at all", "broken")


@pytest.mark.parametrize("password", ["short", "x" * 1025])
def test_password_policy_rejects_unsafe_lengths(password):
    with pytest.raises(ValueError):
        validate_password(password)


def test_username_and_role_validation():
    assert validate_username("alice@example.test") == "alice@example.test"
    assert validate_role("OPERATOR") == "operator"
    with pytest.raises(ValueError):
        validate_username("../alice")
    with pytest.raises(ValueError):
        validate_role("owner")


def test_opaque_session_tokens_are_hashed_before_storage():
    token = new_session_token()
    assert len(token) >= 40
    assert token not in session_token_hash(token)
    assert session_token_hash(token) == session_token_hash(token)


def test_first_user_and_last_admin_invariants(tmp_path):
    with Store(tmp_path / "users.db") as store:
        with pytest.raises(ValueError, match="first active user"):
            store.create_user("viewer", fast_hash("viewer password 123"), "viewer")
        admin = store.create_user("Admin", fast_hash("admin password 123"), "admin")
        viewer = store.create_user("viewer", fast_hash("viewer password 123"), "viewer")
        assert store.user_for_login("admin")["id"] == admin["id"]
        assert "password_hash" not in store.users()[0]

        with pytest.raises(ValueError, match="last active admin"):
            store.set_user_role(admin["id"], "operator")
        with pytest.raises(ValueError, match="last active admin"):
            store.set_user_active(admin["id"], False)
        with pytest.raises(ValueError, match="last active admin"):
            store.delete_user(admin["id"])

        second_admin = store.create_user("backup-admin", fast_hash("backup password 123"), "admin")
        assert store.set_user_role(admin["id"], "operator")
        assert store.set_user_active(viewer["id"], False)
        assert not store.user_for_login("viewer")["active"]
        assert store.set_user_role(admin["id"], "admin")
        assert store.delete_user(second_admin["id"])


def test_sessions_expire_and_password_change_revokes_them(tmp_path):
    now = datetime(2026, 7, 21, tzinfo=timezone.utc)
    with Store(tmp_path / "sessions.db") as store:
        user = store.create_user("admin", fast_hash("admin password 123"), "admin")
        token_hash = session_token_hash("session-token")
        store.create_session(user["id"], token_hash, now + timedelta(hours=1), now=now)
        assert store.session_user(token_hash, now=now)["username"] == "admin"
        assert store.session_user(token_hash, now=now + timedelta(hours=2)) is None

        fresh_hash = session_token_hash("fresh-token")
        store.create_session(user["id"], fresh_hash, now + timedelta(hours=3), now=now)
        assert store.set_user_password(user["id"], fast_hash("new admin password 123"))
        assert store.session_user(fresh_hash, now=now) is None
