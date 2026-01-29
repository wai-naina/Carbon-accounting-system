from __future__ import annotations

from datetime import datetime

import streamlit as st

from app.auth.security import verify_password
from app.database.connection import get_session
from app.database.models import User


def require_login() -> bool:
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if not st.session_state.authenticated:
        show_login_form()
        return False
    return True


def show_login_form() -> None:
    st.title("🌍 Octavia Carbon Accounting System")
    st.subheader("Login")
    with st.form("login_form", clear_on_submit=False):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")
        if submitted:
            if authenticate_user(username.strip(), password):
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Invalid username or password")


def authenticate_user(username: str, password: str) -> bool:
    session = get_session()
    try:
        user = (
            session.query(User)
            .filter(User.username == username, User.is_active.is_(True))
            .first()
        )
        if user and verify_password(password, user.password_hash):
            st.session_state.user_id = user.id
            st.session_state.username = user.username
            st.session_state.role = user.role
            user.last_login = datetime.utcnow()
            session.commit()
            return True
    finally:
        session.close()
    return False


def logout() -> None:
    for key in ["authenticated", "user_id", "username", "role"]:
        if key in st.session_state:
            del st.session_state[key]
