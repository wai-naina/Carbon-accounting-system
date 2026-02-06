from __future__ import annotations

from datetime import datetime, date

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    email = Column(String, unique=True)
    full_name = Column(String)
    role = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime)
    created_by = Column(Integer, ForeignKey("users.id"))

    __table_args__ = (CheckConstraint("role IN ('admin', 'user')", name="ck_user_role"),)

    creator = relationship("User", remote_side=[id], backref="created_users")


class CycleData(Base):
    __tablename__ = "cycle_data"

    id = Column(Integer, primary_key=True)
    weekly_summary_id = Column(Integer, ForeignKey("weekly_summary.id"))
    cycle_number = Column(Integer, nullable=False)
    machine = Column(String, nullable=False)
    start_time = Column(DateTime, nullable=False)

    ads_co2_kg = Column(Float)
    ads_hours = Column(Float)
    des_co2_kg = Column(Float)
    des_hours = Column(Float)
    bag_co2_kg = Column(Float)

    total_kwh = Column(Float)
    boiler_kwh = Column(Float)
    srv_lrvp_kwh = Column(Float)
    ct_kwh = Column(Float)
    nm1_fan_kwh = Column(Float)
    nm2_fan_kwh = Column(Float)
    nm3_fan_kwh = Column(Float)
    nm4_fan_kwh = Column(Float)

    steam_kg = Column(Float)

    des_n = Column(Float)
    vol_capacity = Column(Float)

    import_batch_id = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    weekly_summary = relationship("WeeklySummary", back_populates="cycles")

    __table_args__ = (
        UniqueConstraint("cycle_number", "machine", name="uq_cycle_machine"),
    )


class WeeklySummary(Base):
    __tablename__ = "weekly_summary"

    id = Column(Integer, primary_key=True)
    year = Column(Integer, nullable=False)
    week_number = Column(Integer, nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)

    total_ads_co2_kg = Column(Float)
    total_des_co2_kg = Column(Float)
    total_bag_co2_kg = Column(Float)
    liquefied_co2_kg = Column(Float)
    # Plant-level liquefaction energy for the week (kWh)
    liquefaction_energy_kwh = Column(Float)

    loss_stage_1_kg = Column(Float)
    loss_stage_2_kg = Column(Float)
    loss_stage_3_kg = Column(Float)
    total_loss_kg = Column(Float)

    thermal_energy_kwh = Column(Float)
    auxiliary_energy_kwh = Column(Float)
    total_energy_kwh = Column(Float)

    total_steam_kg = Column(Float)

    thermal_emissions_kg = Column(Float)
    auxiliary_emissions_kg = Column(Float)
    total_operational_emissions_kg = Column(Float)

    infrastructure_embodied_kg = Column(Float)
    sorbent_embodied_kg = Column(Float)
    total_embodied_emissions_kg = Column(Float)

    gross_captured_kg = Column(Float)
    total_emissions_kg = Column(Float)
    net_removal_kg = Column(Float)

    is_net_positive = Column(Boolean)

    energy_intensity_kwh_per_tonne = Column(Float)
    total_cycles = Column(Integer)

    notes = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    cycles = relationship("CycleData", back_populates="weekly_summary")

    __table_args__ = (
        UniqueConstraint("year", "week_number", name="uq_week"),
    )


class EmbodiedInfrastructure(Base):
    __tablename__ = "embodied_infrastructure"

    id = Column(Integer, primary_key=True)
    zone = Column(String, nullable=False)
    item = Column(String, nullable=False)
    material_type = Column(String)
    quantity = Column(Float)
    unit = Column(String)
    weight_kg = Column(Float)
    emission_factor = Column(Float)
    embodied_co2_kg = Column(Float)
    lifetime_years = Column(Integer, default=10)
    weekly_charge_kg = Column(Float)
    notes = Column(Text)
    updated_at = Column(DateTime, default=datetime.utcnow)
    updated_by = Column(Integer, ForeignKey("users.id"))


class EmbodiedSorbent(Base):
    __tablename__ = "embodied_sorbent"

    id = Column(Integer, primary_key=True)
    batch_number = Column(Integer, unique=True, nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date)
    alumina_kg = Column(Float)
    pei_kg = Column(Float)
    methanol_kg = Column(Float)
    production_embodied_kg = Column(Float)
    eol_embodied_kg = Column(Float)
    total_embodied_kg = Column(Float)
    lifetime_weeks = Column(Integer, default=156)
    weekly_charge_kg = Column(Float)
    is_active = Column(Boolean, default=True)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_by = Column(Integer, ForeignKey("users.id"))


class SystemConfig(Base):
    __tablename__ = "system_config"

    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)
    value_type = Column(String, default="string")
    description = Column(String)
    updated_at = Column(DateTime, default=datetime.utcnow)
    updated_by = Column(Integer, ForeignKey("users.id"))


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"))
    action = Column(String, nullable=False)
    table_name = Column(String, nullable=False)
    record_id = Column(Integer)
    field_name = Column(String)
    old_value = Column(Text)
    new_value = Column(Text)
    ip_address = Column(String)
