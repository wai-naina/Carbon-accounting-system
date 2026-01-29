from datetime import date

import streamlit as st


def week_year_selector() -> tuple[int, int]:
    today = date.today()
    year = st.selectbox("Year", options=[today.year - 1, today.year, today.year + 1], index=1)
    week = st.selectbox("Week", options=list(range(1, 54)), index=min(today.isocalendar().week - 1, 52))
    return year, week
