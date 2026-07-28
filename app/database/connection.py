from __future__ import annotations

import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from datetime import datetime

from app.config import ensure_directories, load_config
from app.database.models import Base, CarbonNestSorbentConfig, SystemConfig, User
from app.auth.security import hash_password


def get_engine():
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        # PostgreSQL (e.g. Neon) - ensure postgresql:// scheme for SQLAlchemy
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        return create_engine(
            database_url,
            future=True,
            # Serverless/free-tier Postgres (Neon etc.) can suspend the
            # instance or drop idle connections; without pool_pre_ping,
            # SQLAlchemy hands out the stale connection anyway and the next
            # query fails with OperationalError instead of transparently
            # reconnecting. pool_recycle proactively retires connections
            # before a proxy/server-side idle timeout kills them first.
            pool_pre_ping=True,
            pool_recycle=300,
        )
    # Fallback to SQLite for local development
    ensure_directories()
    config = load_config()
    db_path = config.db_path
    return create_engine(
        f"sqlite:///{db_path}",
        future=True,
        pool_pre_ping=True,
        # A concurrent Streamlit Cloud app reruns this on every user
        # interaction from every connected session — SQLite's default
        # behavior is to raise "database is locked" immediately on any
        # write/read contention rather than wait. A busy timeout makes it
        # wait for the other transaction to finish instead of failing.
        connect_args={"timeout": 15},
    )


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())


def get_session():
    return SessionLocal()


_initialized = False


def init_db() -> None:
    """Create tables and seed defaults — but only once per running server
    process, not on every script rerun.

    Every page in this app calls init_db() unconditionally at the top of its
    own main(), and Streamlit reruns that on every single user interaction
    for every connected session. On a hosted deployment with several people
    using the app at once, that turned into a steady stream of redundant
    schema-check + seed-check queries hitting the same database concurrently
    — exactly the kind of write contention that produces intermittent
    OperationalErrors (SQLite raises "database is locked" under concurrent
    access, and even Postgres has no reason to re-run this every time). A
    process-wide flag makes every call after the first a no-op. If init
    fails partway, the flag is never set, so the next call retries properly.
    """
    global _initialized
    if _initialized:
        return
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _seed_system_config()
    _seed_admin_user()
    _seed_sorbent_config()
    _initialized = True


def _seed_system_config() -> None:
    config = load_config()
    defaults = {
        "grid_emission_factor": (
            str(config.get("emission_factors", "grid", "kenya_power", default=0.049)),
            "float",
            "Kenya grid EF (kg CO2/kWh) - Miniplant 2.0",
        ),
        "carbon_nest_grid_emission_factor": (
            str(config.get("emission_factors", "grid", "carbon_nest_kenya_power", default=0.0579)),
            "float",
            "Kenya grid EF (kg CO2/kWh) - Carbon Nest",
        ),
        "geothermal_emission_factor": (
            str(config.get("emission_factors", "grid", "geothermal", default=0.0)),
            "float",
            "Geothermal EF (kg CO2/kWh)",
        ),
        "plant_start_date": (
            str(config.get("plant", "start_date", default="2026-01-01")),
            "string",
            "Plant operational start date",
        ),
        "plant_lifetime_years": (
            str(config.get("plant", "infrastructure_lifetime_years", default=10)),
            "int",
            "Infrastructure amortization period",
        ),
        "sorbent_lifetime_years": (
            str(config.get("plant", "sorbent_lifetime_years", default=3)),
            "int",
            "Sorbent batch lifetime",
        ),
        "target_capacity_tonnes_year": (
            str(config.get("plant", "target_capacity_tonnes_year", default=100)),
            "float",
            "Annual target capacity",
        ),
    }
    session = get_session()
    try:
        for key, (value, value_type, description) in defaults.items():
            if session.query(SystemConfig).filter(SystemConfig.key == key).first():
                continue
            session.add(
                SystemConfig(
                    key=key, value=value, value_type=value_type, description=description
                )
            )
        session.commit()
    finally:
        session.close()


def _seed_sorbent_config() -> None:
    """Seed the initial (module_prefix, sorbent_charge_kg, bed_volume_m3) rows,
    effective from the plant's own start date so they apply to all historical
    cycles unless a later row (e.g. after a sorbent reload) overrides them."""
    config = load_config()
    effective_date_str = config.get("plant", "start_date", default="2026-01-01")
    effective_date = datetime.strptime(str(effective_date_str), "%Y-%m-%d")
    defaults = [
        ("N1", 513.8, 0.59388),
        ("N2", 457.5, 0.59388),
        ("N1N2", 971.3, 1.18776),
    ]
    session = get_session()
    try:
        for prefix, charge_kg, volume_m3 in defaults:
            exists = (
                session.query(CarbonNestSorbentConfig)
                .filter(
                    CarbonNestSorbentConfig.module_prefix == prefix,
                    CarbonNestSorbentConfig.effective_date == effective_date,
                )
                .first()
            )
            if exists:
                continue
            session.add(
                CarbonNestSorbentConfig(
                    module_prefix=prefix,
                    effective_date=effective_date,
                    sorbent_charge_kg=charge_kg,
                    bed_volume_m3=volume_m3,
                    notes="Initial commissioning values",
                )
            )
        session.commit()
    finally:
        session.close()


def _seed_admin_user() -> None:
    session = get_session()
    try:
        if session.query(User).filter(User.role == "admin").first():
            return
        username = os.getenv("CAS_ADMIN_USERNAME", "admin")
        password = os.getenv("CAS_ADMIN_PASSWORD")
        if not password:
            if os.getenv("DATABASE_URL"):
                raise ValueError(
                    "CAS_ADMIN_PASSWORD environment variable must be set for production deployments"
                )
            password = "admin123"  # local SQLite dev only — change via admin UI after first login
        email = os.getenv("CAS_ADMIN_EMAIL", "admin@octavia.local")
        session.add(
            User(
                username=username,
                password_hash=hash_password(password),
                email=email,
                role="admin",
                is_active=True,
            )
        )
        session.commit()
    finally:
        session.close()
