import auth


class DummyStreamlit:
    """Tiny stand-in for Streamlit exposing only session_state."""

    def __init__(self):
        self.session_state = {}


def test_hash_and_verify_password_roundtrip():
    """Password hashing should be non-reversible and verification-safe."""
    password = "MySecurePass123"
    hashed = auth._hash_password(password)

    assert hashed != password
    assert auth._verify_password(password, hashed)
    assert not auth._verify_password("wrong", hashed)


def test_login_success_sets_session(monkeypatch):
    """Successful login should populate expected auth session keys."""
    st = DummyStreamlit()
    monkeypatch.setattr(auth, "st", st)

    hashed = auth._hash_password("secret123")
    user = {"id": 7, "username": "mario", "name": "Mario Rossi", "password_hash": hashed}

    monkeypatch.setattr(auth.db, "get_user_by_username", lambda username: user if username == "mario" else None)

    ok = auth._do_login("Mario", "secret123")

    assert ok is True
    assert st.session_state["authenticated"] is True
    assert st.session_state["user_id"] == 7
    assert st.session_state["username"] == "mario"
    assert st.session_state["user_name"] == "Mario Rossi"


def test_login_failure_does_not_set_session(monkeypatch):
    """Failed login should leave session state untouched."""
    st = DummyStreamlit()
    monkeypatch.setattr(auth, "st", st)
    monkeypatch.setattr(auth.db, "get_user_by_username", lambda username: None)

    ok = auth._do_login("ghost", "any")

    assert ok is False
    assert st.session_state == {}


def test_register_validation_errors(monkeypatch):
    """Registration should reject invalid usernames/passwords consistently."""
    st = DummyStreamlit()
    monkeypatch.setattr(auth, "st", st)
    monkeypatch.setattr(auth.db, "get_user_by_username", lambda username: None)

    assert auth._do_register("ab", "Mario", "123456", "123456") == "Username deve avere almeno 3 caratteri."
    assert auth._do_register("mario", "Mario", "123", "123") == "La password deve avere almeno 6 caratteri."
    assert auth._do_register("mario", "Mario", "123456", "654321") == "Le password non coincidono."


def test_register_success_creates_user_and_logs_in(monkeypatch):
    """Valid registration should create user, seed defaults, and authenticate."""
    st = DummyStreamlit()
    monkeypatch.setattr(auth, "st", st)

    monkeypatch.setattr(auth.db, "get_user_by_username", lambda username: None)

    captured = {}

    def _create_user(username, name, password_hash):
        captured["username"] = username
        captured["name"] = name
        captured["password_hash"] = password_hash
        return 42

    monkeypatch.setattr(auth.db, "create_user", _create_user)

    seeded = {"called": False}

    def _seed_default_exercises_for_user(user_id):
        seeded["called"] = True
        seeded["user_id"] = user_id

    monkeypatch.setattr(auth.db, "seed_default_exercises_for_user", _seed_default_exercises_for_user)

    err = auth._do_register(" Mario ", " Mario Rossi ", "secret123", "secret123")

    assert err is None
    assert captured["username"] == "mario"
    assert captured["name"] == "Mario Rossi"
    assert captured["password_hash"] != "secret123"
    assert seeded["called"] is True
    assert seeded["user_id"] == 42
    assert st.session_state["authenticated"] is True
    assert st.session_state["user_id"] == 42


def test_logout_clears_session(monkeypatch):
    """Logout should remove auth-related keys and keep unrelated state."""
    st = DummyStreamlit()
    st.session_state.update({
        "authenticated": True,
        "user_id": 1,
        "username": "mario",
        "user_name": "Mario",
        "other": "preserve",
    })
    monkeypatch.setattr(auth, "st", st)

    auth.logout()

    assert "authenticated" not in st.session_state
    assert "user_id" not in st.session_state
    assert "username" not in st.session_state
    assert "user_name" not in st.session_state
    assert st.session_state["other"] == "preserve"
