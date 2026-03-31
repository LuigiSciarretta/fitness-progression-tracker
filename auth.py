"""Authentication module — registration + login using bcrypt and Streamlit session state."""

import bcrypt
import streamlit as st
import database as db


def _hash_password(password: str) -> str:
    """Hash a password with bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its bcrypt hash."""
    return bcrypt.checkpw(password.encode(), hashed.encode())


def _do_login(username: str, password: str) -> bool:
    """Attempt login. Returns True on success, sets session state."""
    user = db.get_user_by_username(username.strip().lower())
    if user and _verify_password(password, user["password_hash"]):
        st.session_state["authenticated"] = True
        st.session_state["user_id"] = user["id"]
        st.session_state["username"] = user["username"]
        st.session_state["user_name"] = user["name"]
        return True
    return False


def _do_register(username: str, name: str, password: str, password2: str) -> str | None:
    """Attempt registration. Returns error message or None on success."""
    username = username.strip().lower()
    name = name.strip()
    if not username or not name or not password:
        return "Tutti i campi sono obbligatori."
    if len(username) < 3:
        return "Username deve avere almeno 3 caratteri."
    if len(password) < 6:
        return "La password deve avere almeno 6 caratteri."
    if password != password2:
        return "Le password non coincidono."
    if db.get_user_by_username(username):
        return "Username già in uso."

    hashed = _hash_password(password)
    user_id = db.create_user(username, name, hashed)
    db.seed_default_exercises_for_user(user_id)
    st.session_state["authenticated"] = True
    st.session_state["user_id"] = user_id
    st.session_state["username"] = username
    st.session_state["user_name"] = name
    return None


def get_current_user_id() -> int:
    """Return the logged-in user's id."""
    return st.session_state["user_id"]


def get_current_user_name() -> str:
    """Return the logged-in user's display name."""
    return st.session_state.get("user_name", "")


def is_authenticated() -> bool:
    """Check if the user is authenticated."""
    return st.session_state.get("authenticated", False)


def logout():
    """Clear auth session state."""
    for key in ["authenticated", "user_id", "username", "user_name"]:
        st.session_state.pop(key, None)


def show_auth_page():
    """Render the login/registration page. Returns True if authenticated."""
    if is_authenticated():
        return True

    st.title("🏋️ Fitness Tracker")
    st.caption("Accedi o crea un account per tracciare i tuoi progressi in palestra.")

    tab_login, tab_register = st.tabs(["🔐 Accedi", "📝 Registrati"])

    with tab_login:
        with st.form("login_form"):
            username = st.text_input("Username", key="login_user")
            password = st.text_input("Password", type="password", key="login_pass")
            submitted = st.form_submit_button("Accedi", use_container_width=True, type="primary")
            if submitted:
                if _do_login(username, password):
                    st.rerun()
                else:
                    st.error("Username o password errati.")

    with tab_register:
        with st.form("register_form"):
            reg_name = st.text_input("Nome completo", key="reg_name")
            reg_user = st.text_input("Username", key="reg_user")
            reg_pass = st.text_input("Password (min. 6 caratteri)", type="password", key="reg_pass")
            reg_pass2 = st.text_input("Conferma password", type="password", key="reg_pass2")
            submitted = st.form_submit_button("Crea account", use_container_width=True, type="primary")
            if submitted:
                err = _do_register(reg_user, reg_name, reg_pass, reg_pass2)
                if err:
                    st.error(err)
                else:
                    st.success("Account creato! Accesso in corso...")
                    st.rerun()

    return False
