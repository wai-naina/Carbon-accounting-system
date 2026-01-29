from __future__ import annotations

import streamlit as st

from app.auth.authentication import require_login


def require_admin() -> bool:
    if not require_login():
        return False
    if st.session_state.get("role") != "admin":
        st.error("Admin access required.")
        return False
    return True
