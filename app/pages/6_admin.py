import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from app.auth.authorization import require_admin
from app.auth.security import hash_password
from app.components.branding import get_brand_css, render_logo
from app.database.connection import get_session, init_db
from app.database.models import AuditLog, User, WeeklySummary, CycleData


def log_action(session, user_id, action, table_name, record_id, field_name=None, old=None, new=None):
    session.add(
        AuditLog(
            user_id=user_id,
            action=action,
            table_name=table_name,
            record_id=record_id,
            field_name=field_name,
            old_value=old,
            new_value=new,
        )
    )


def main() -> None:
    st.set_page_config(page_title="Admin - Octavia CAS", page_icon="👥", layout="wide")
    init_db()
    if not require_admin():
        return

    # Apply brand CSS and logo
    st.markdown(get_brand_css(), unsafe_allow_html=True)
    render_logo(location="sidebar")

    st.title("👥 Administration")
    st.markdown("Manage users, view audit logs, and system maintenance")

    session = get_session()
    try:
        # Get stats
        total_users = session.query(User).count()
        active_users = session.query(User).filter(User.is_active == True).count()
        admin_users = session.query(User).filter(User.role == "admin", User.is_active == True).count()
        audit_entries = session.query(AuditLog).count()
        
        # Overview
        st.markdown("### 📊 System Overview")
        
        stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
        
        with stat_col1:
            st.metric("Total Users", total_users)
        with stat_col2:
            st.metric("Active Users", active_users)
        with stat_col3:
            st.metric("Administrators", admin_users)
        with stat_col4:
            st.metric("Audit Entries", audit_entries)

        st.divider()

        # Tabs
        tab1, tab2, tab3, tab4 = st.tabs(["👤 Create User", "📋 User List", "📜 Audit Log", "🔧 Maintenance"])

        with tab1:
            st.markdown("### Create New User")
            st.markdown("Add new users to the system. Users can view data, admins can also modify data.")
            
            with st.form("create_user"):
                form_col1, form_col2 = st.columns(2)
                
                with form_col1:
                    username = st.text_input("Username *", placeholder="e.g., jsmith")
                    full_name = st.text_input("Full Name *", placeholder="e.g., John Smith")
                    email = st.text_input("Email", placeholder="e.g., john@octaviacarbon.com")
                
                with form_col2:
                    role = st.selectbox("Role *", options=["user", "admin"])
                    password = st.text_input("Password *", type="password")
                    confirm_password = st.text_input("Confirm Password *", type="password")
                
                st.markdown("""
                <div style="background:#e7f3ff; padding:1rem; border-radius:8px; margin:1rem 0;">
                    <strong>Role Permissions:</strong><br>
                    • <strong>User:</strong> View dashboard, reports, and scenarios<br>
                    • <strong>Admin:</strong> All user permissions + data entry, configuration, user management
                </div>
                """, unsafe_allow_html=True)
                
                submitted = st.form_submit_button("➕ Create User", type="primary", width="stretch")
                
                if submitted:
                    errors = []
                    if not username:
                        errors.append("Username is required")
                    if not full_name:
                        errors.append("Full name is required")
                    if not password:
                        errors.append("Password is required")
                    if password != confirm_password:
                        errors.append("Passwords do not match")
                    if len(password) < 6:
                        errors.append("Password must be at least 6 characters")
                    if session.query(User).filter(User.username == username).first():
                        errors.append("Username already exists")
                    
                    if errors:
                        for err in errors:
                            st.error(err)
                    else:
                        user = User(
                            username=username.strip(),
                            full_name=full_name.strip(),
                            email=email.strip() or None,
                            role=role,
                            password_hash=hash_password(password),
                            is_active=True,
                            created_by=st.session_state.get("user_id"),
                        )
                        session.add(user)
                        session.commit()
                        log_action(
                            session,
                            st.session_state.get("user_id"),
                            "create",
                            "users",
                            user.id,
                        )
                        session.commit()
                        st.success(f"✅ User '{username}' created successfully!")
                        st.balloons()

        with tab2:
            st.markdown("### User List")
            
            users = session.query(User).order_by(User.username).all()
            
            if users:
                for user in users:
                    status_emoji = "🟢" if user.is_active else "⚪"
                    role_badge = "🔐 Admin" if user.role == "admin" else "👤 User"
                    
                    with st.expander(f"{status_emoji} {user.username} - {role_badge}"):
                        u_col1, u_col2, u_col3 = st.columns(3)
                        
                        with u_col1:
                            st.markdown("**Account Info**")
                            st.write(f"- Username: {user.username}")
                            st.write(f"- Full Name: {user.full_name or 'N/A'}")
                            st.write(f"- Email: {user.email or 'N/A'}")
                        
                        with u_col2:
                            st.markdown("**Status**")
                            st.write(f"- Role: {user.role.title()}")
                            st.write(f"- Active: {'Yes' if user.is_active else 'No'}")
                            st.write(f"- Created: {user.created_at.strftime('%Y-%m-%d') if user.created_at else 'N/A'}")
                            st.write(f"- Last Login: {user.last_login.strftime('%Y-%m-%d %H:%M') if user.last_login else 'Never'}")
                        
                        with u_col3:
                            st.markdown("**Actions**")
                            
                            if user.id != st.session_state.get("user_id"):
                                if user.is_active:
                                    if st.button(f"🚫 Deactivate", key=f"deactivate_{user.id}"):
                                        user.is_active = False
                                        log_action(session, st.session_state.get("user_id"), "deactivate", 
                                                   "users", user.id, "is_active", "True", "False")
                                        session.commit()
                                        st.success(f"User '{user.username}' deactivated.")
                                        st.rerun()
                                else:
                                    if st.button(f"✅ Reactivate", key=f"reactivate_{user.id}"):
                                        user.is_active = True
                                        log_action(session, st.session_state.get("user_id"), "reactivate",
                                                   "users", user.id, "is_active", "False", "True")
                                        session.commit()
                                        st.success(f"User '{user.username}' reactivated.")
                                        st.rerun()
                                
                                # Reset password
                                new_pass = st.text_input(f"New Password", type="password", key=f"pass_{user.id}")
                                if st.button(f"🔑 Reset Password", key=f"reset_{user.id}"):
                                    if new_pass and len(new_pass) >= 6:
                                        user.password_hash = hash_password(new_pass)
                                        log_action(session, st.session_state.get("user_id"), "password_reset",
                                                   "users", user.id)
                                        session.commit()
                                        st.success(f"Password reset for '{user.username}'.")
                                    else:
                                        st.error("Password must be at least 6 characters.")
                            else:
                                st.info("This is your account")
            else:
                st.info("No users found.")

        with tab3:
            st.markdown("### Audit Log")
            st.markdown("Track all administrative actions in the system")
            
            logs = session.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(50).all()
            
            if logs:
                log_data = []
                for log in logs:
                    user = session.query(User).filter(User.id == log.user_id).first() if log.user_id else None
                    log_data.append({
                        "Timestamp": log.timestamp.strftime("%Y-%m-%d %H:%M:%S") if log.timestamp else "N/A",
                        "User": user.username if user else "System",
                        "Action": log.action,
                        "Table": log.table_name,
                        "Record ID": log.record_id,
                        "Field": log.field_name or "-",
                        "Old Value": log.old_value or "-",
                        "New Value": log.new_value or "-",
                    })
                
                st.dataframe(log_data, width="stretch", hide_index=True)
            else:
                st.info("No audit entries yet.")

        with tab4:
            st.markdown("### System Maintenance")
            st.warning("⚠️ These actions are irreversible. Use with caution!")
            
            maint_col1, maint_col2 = st.columns(2)
            
            with maint_col1:
                st.markdown("#### Database Statistics")
                
                total_cycles = session.query(CycleData).count()
                total_weeks = session.query(WeeklySummary).count()
                
                st.write(f"- Cycle records: {total_cycles}")
                st.write(f"- Weekly summaries: {total_weeks}")
                st.write(f"- Users: {total_users}")
                st.write(f"- Audit entries: {audit_entries}")
            
            with maint_col2:
                st.markdown("#### Clear Data")
                
                if st.button("🗑️ Clear All Cycle Data", type="secondary"):
                    session.query(CycleData).delete()
                    session.commit()
                    log_action(session, st.session_state.get("user_id"), "clear_all", "cycle_data", None)
                    session.commit()
                    st.success("All cycle data cleared.")
                
                if st.button("🗑️ Clear All Weekly Summaries", type="secondary"):
                    session.query(WeeklySummary).delete()
                    session.commit()
                    log_action(session, st.session_state.get("user_id"), "clear_all", "weekly_summary", None)
                    session.commit()
                    st.success("All weekly summaries cleared.")
                
                if st.button("🗑️ Clear Audit Log", type="secondary"):
                    session.query(AuditLog).delete()
                    session.commit()
                    st.success("Audit log cleared.")

    finally:
        session.close()


if __name__ == "__main__":
    main()
