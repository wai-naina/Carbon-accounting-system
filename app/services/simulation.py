from __future__ import annotations

from typing import Dict, List

import numpy as np

from app.database.models import SystemConfig, WeeklySummary


def _get_config_value(session, key: str, default: float) -> float:
    config = session.query(SystemConfig).filter(SystemConfig.key == key).first()
    if not config:
        return default
    try:
        return float(config.value)
    except ValueError:
        return default


def _recent_weeks(session, limit: int) -> List[WeeklySummary]:
    return (
        session.query(WeeklySummary)
        .order_by(WeeklySummary.year.desc(), WeeklySummary.week_number.desc())
        .limit(limit)
        .all()
    )


def run_monte_carlo(
    session,
    *,
    iterations: int,
    base_weeks: int,
    include_geothermal: bool = True,
) -> Dict[str, Dict[str, float]]:
    weeks = _recent_weeks(session, base_weeks)
    if not weeks:
        return {}

    avg_liq = np.mean([w.liquefied_co2_kg or 0 for w in weeks])
    avg_ads = np.mean([w.total_ads_co2_kg or 0 for w in weeks]) or avg_liq
    avg_thermal = np.mean([w.thermal_energy_kwh or 0 for w in weeks])
    avg_aux = np.mean([w.auxiliary_energy_kwh or 0 for w in weeks])
    avg_embodied = np.mean([w.total_embodied_emissions_kg or 0 for w in weeks])

    eff = avg_liq / avg_ads if avg_ads else 0.0
    eff_std = 0.05

    grid_ef = _get_config_value(session, "grid_emission_factor", 0.049)
    geo_ef = _get_config_value(session, "geothermal_emission_factor", 0.0)

    def simulate(thermal_ef: float) -> Dict[str, float]:
        results = []
        for _ in range(iterations):
            capture_eff = max(0.0, np.random.normal(eff, eff_std))
            uptime = np.random.beta(9, 1)
            loss_rate = np.random.beta(2, 18)
            thermal_energy = max(0.0, np.random.normal(avg_thermal, avg_thermal * 0.10))
            auxiliary_energy = max(0.0, np.random.normal(avg_aux, avg_aux * 0.08))

            gross_captured = avg_ads * capture_eff * uptime
            net_captured = gross_captured * (1 - loss_rate)

            operational = (thermal_energy * thermal_ef) + (auxiliary_energy * grid_ef)
            net_removal = net_captured - operational - avg_embodied
            results.append(net_removal)

        results = np.array(results)
        return {
            "mean": float(np.mean(results)),
            "std": float(np.std(results)),
            "p5": float(np.percentile(results, 5)),
            "p50": float(np.percentile(results, 50)),
            "p95": float(np.percentile(results, 95)),
            "prob_net_positive": float(np.mean(results > 0)),
        }

    output = {"current": simulate(grid_ef)}
    if include_geothermal:
        output["geothermal"] = simulate(geo_ef)
    return output
