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


class CarbonNestCycleData(Base):
    """Cycle-level SCADA data from the Carbon Nest system.

    Kept fully separate from the legacy Miniplant 2.0 `CycleData` table so
    cycle numbering, column shape, and history never collide between the
    two data sources. Carbon Nest cycle numbers are unique on their own
    (no Machine/Module component needed to disambiguate).
    """

    __tablename__ = "carbon_nest_cycle_data"

    id = Column(Integer, primary_key=True)
    weekly_summary_id = Column(Integer, ForeignKey("carbon_nest_weekly_summary.id"))
    cycle_number = Column(Integer, nullable=False, unique=True)

    raw_module = Column(String, nullable=False)  # e.g. "N1N2-M1n3", "N2-M2n4" as exported by SCADA
    series = Column(String, nullable=False)  # "1n3" or "2n4" — the module group/series
    nelion = Column(String)  # "N1"/"N2"/"N3"/"N4" when unambiguous; NULL when SCADA reports a combined reading

    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime)
    cycle_type = Column(String)  # "Interleaved" / "Concurrent"

    ads_co2_kg = Column(Float)
    ads_hours = Column(Float)
    ads_lost_co2_kg = Column(Float)
    ads_efficiency = Column(Float)
    ads_mass_cap = Column(Float)
    ads_vol_cap = Column(Float)

    des_co2_kg = Column(Float)
    des_hours = Column(Float)
    des_efficiency = Column(Float)
    des_vol_cap = Column(Float)

    bag_co2_kg = Column(Float)
    bag_efficiency = Column(Float)

    total_kwh = Column(Float)
    mwh_per_tco2 = Column(Float)

    fans_kwh = Column(Float)
    ct_kwh = Column(Float)
    ct_pump_kwh = Column(Float)
    vp402_kwh = Column(Float)
    vp501_kwh = Column(Float)
    boiler_a_kwh = Column(Float)
    boiler_b_kwh = Column(Float)
    main_utility_kwh = Column(Float)

    steam_kg = Column(Float)

    import_batch_id = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    weekly_summary = relationship("CarbonNestWeeklySummary", back_populates="cycles")


class CarbonNestWeeklySummary(Base):
    __tablename__ = "carbon_nest_weekly_summary"

    id = Column(Integer, primary_key=True)
    # Carbon Nest weeks run Saturday 18:00 -> Saturday 18:00, matching
    # Athena's own weekly report cadence (Miniplant 2.0 keeps its Mon-based
    # ISO week, untouched). start_date is the true unique key; year/week_number
    # are derived, human-readable labels only — see
    # app/services/carbon_nest_aggregation.py:get_carbon_nest_week_bounds().
    year = Column(Integer, nullable=False)
    week_number = Column(Integer, nullable=False)
    start_date = Column(DateTime, nullable=False, unique=True)
    end_date = Column(DateTime, nullable=False)

    total_ads_co2_kg = Column(Float)
    total_des_co2_kg = Column(Float)
    total_bag_co2_kg = Column(Float)
    liquefied_co2_kg = Column(Float)

    loss_stage_1_kg = Column(Float)
    loss_stage_2_kg = Column(Float)
    loss_stage_3_kg = Column(Float)
    total_loss_kg = Column(Float)

    # Per-cycle metered energy (SCADA CSV import), summed for the week.
    fans_kwh = Column(Float)
    ct_kwh = Column(Float)
    ct_pump_kwh = Column(Float)
    vp402_kwh = Column(Float)
    vp501_kwh = Column(Float)
    boiler_a_kwh = Column(Float)
    boiler_b_kwh = Column(Float)
    main_utility_kwh = Column(Float)  # imported for reference only — not used in totals, see below

    # Manually entered each week from the Athena weekly PDF report, which is
    # the only source for these right now: the CSV's "Main Utility" column is
    # a known-buggy/incomplete stand-in for cooling tower/pump/compressor
    # draw (confirmed with Octavia's SCADA lead, 2026-07-28), and standby
    # power for boiler/VP units isn't in the CSV export at all. These replace
    # main_utility_kwh in the weekly total until the SCADA export is fixed.
    water_pumps_kwh = Column(Float)
    compressor_a_kwh = Column(Float)
    compressor_b_kwh = Column(Float)
    boiler_a_standby_kwh = Column(Float)
    boiler_b_standby_kwh = Column(Float)
    vp402_standby_kwh = Column(Float)
    vp501_standby_kwh = Column(Float)
    ct_standby_kwh = Column(Float)  # CT & CT Pump also runs process-only in the CSV — confirmed 2026-07-29
    liquefaction_active_transfer_kwh = Column(Float)
    liquefaction_standby_kwh = Column(Float)
    # Sum of the two liquefaction fields above — kept as its own column since
    # existing code (e.g. per-series liquefaction proration) reads a single
    # liquefaction energy figure.
    liquefaction_energy_kwh = Column(Float)

    thermal_energy_kwh = Column(Float)
    auxiliary_energy_kwh = Column(Float)
    total_energy_kwh = Column(Float)
    # Process-only energy (Fans/CT/CT Pump/VP402/VP501/Boiler A/B from the
    # CSV) — matches SCADA's own per-cycle "MWh/tCO2" convention exactly.
    # Used for the energy-intensity KPI; total_energy_kwh (above) is used for
    # operational emissions and includes the manual utility/standby/
    # liquefaction entries too.
    process_energy_kwh = Column(Float)

    total_steam_kg = Column(Float)

    thermal_emissions_kg = Column(Float)
    auxiliary_emissions_kg = Column(Float)
    total_operational_emissions_kg = Column(Float)

    # Output-based embodied emissions (v0.6 Carbon Nest LCA, kg CO2-eq/t driver
    # intensities applied to actual captured CO2 this week) — see
    # app/services/carbon_nest_embodied.py for methodology and sourcing.
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

    cycles = relationship("CarbonNestCycleData", back_populates="weekly_summary")


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


class CarbonNestSorbentConfig(Base):
    """Versioned sorbent charge / bed volume per module prefix (N1, N2, N1N2).

    These are plant configuration, not measured data — but they change when a
    sorbent bed is reloaded, and a flat "current value" would silently rewrite
    the working-capacity history for weeks before that reload. Keyed by
    `effective_date` so a lookup for a given cycle always uses whichever row
    was in force at that cycle's start_time (the latest row with
    effective_date <= start_time), leaving earlier weeks' figures untouched
    when a new row is added for a reload.
    """

    __tablename__ = "carbon_nest_sorbent_config"

    id = Column(Integer, primary_key=True)
    module_prefix = Column(String, nullable=False)  # "N1", "N2", "N1N2"
    effective_date = Column(DateTime, nullable=False)
    sorbent_charge_kg = Column(Float, nullable=False)
    bed_volume_m3 = Column(Float, nullable=False)
    notes = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(Integer, ForeignKey("users.id"))

    __table_args__ = (
        UniqueConstraint("module_prefix", "effective_date", name="uq_sorbent_config_prefix_date"),
    )
