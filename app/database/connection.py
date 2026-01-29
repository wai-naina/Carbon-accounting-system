from __future__ import annotations

import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import ensure_directories, load_config
from app.database.models import Base, SystemConfig, User
from app.auth.security import hash_password


def get_engine():
    ensure_directories()
    config = load_config()
    db_path = config.db_path
    return create_engine(f"sqlite:///{db_path}", future=True)


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())


def get_session():
    return SessionLocal()


def init_db() -> None:
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _seed_system_config()
    _seed_admin_user()


def _seed_system_config() -> None:
    config = load_config()
    defaults = {
        "grid_emission_factor": (
            str(config.get("emission_factors", "grid", "kenya_power", default=0.049)),
            "float",
            "Kenya grid EF (kg CO2/kWh)",
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


def _seed_admin_user() -> None:
    session = get_session()
    try:
        if session.query(User).filter(User.role == "admin").first():
            return
        username = os.getenv("CAS_ADMIN_USERNAME", "admin")
        password = os.getenv("CAS_ADMIN_PASSWORD", "admin123")
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
