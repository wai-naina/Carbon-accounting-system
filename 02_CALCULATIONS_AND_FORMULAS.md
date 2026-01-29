# Octavia Carbon Accounting System (CAS)
## Calculations and Formulas Reference

**Version:** 1.0  
**Date:** January 2026  

---

## Table of Contents

1. [Core Carbon Accounting Formula](#1-core-carbon-accounting-formula)
2. [CO₂ Flow Calculations](#2-co₂-flow-calculations)
3. [Energy Calculations](#3-energy-calculations)
4. [Operational Emissions Calculations](#4-operational-emissions-calculations)
5. [Embodied Emissions Calculations](#5-embodied-emissions-calculations)
6. [Loss Calculations](#6-loss-calculations)
7. [Efficiency Metrics](#7-efficiency-metrics)
8. [Aggregation Formulas](#8-aggregation-formulas)
9. [Monte Carlo Simulation Parameters](#9-monte-carlo-simulation-parameters)
10. [Break-Even Analysis](#10-break-even-analysis)

---

## 1. Core Carbon Accounting Formula

### 1.1 Net CO₂ Removal (Primary Metric)

The fundamental equation determining net positive/negative status:

```
Net_CO2_Removal = Gross_CO2_Captured - Total_Emissions
```

Where:
```
Total_Emissions = Operational_Emissions + Amortized_Embodied_Emissions
```

And:
```
Gross_CO2_Captured = Liquefied_CO2
```

### 1.2 Expanded Formula

```
Net_CO2_Removal = Liquefied_CO2 
                  - (Thermal_Emissions + Auxiliary_Emissions)
                  - (Infrastructure_Embodied_Weekly + Sorbent_Embodied_Weekly)
```

### 1.3 Net Position Determination

```python
if Net_CO2_Removal > 0:
    status = "NET POSITIVE"  # Removing more CO₂ than emitting
elif Net_CO2_Removal < 0:
    status = "NET NEGATIVE"  # Emitting more CO₂ than removing
else:
    status = "NEUTRAL"       # Breaking even
```

### 1.4 Weekly Summary

```
Net_CO2_Removal_Weekly = Sum(Liquefied_CO2_weekly) 
                        - Sum(Operational_Emissions_weekly)
                        - Weekly_Embodied_Charge
```

---

## 2. CO₂ Flow Calculations

### 2.1 CO₂ Measurements (Per Cycle)

From SCADA system, three measurements are recorded per cycle:

| Measurement | Field Name | Description |
|-------------|------------|-------------|
| Adsorbed CO₂ | `ADS_CO2` | CO₂ captured by sorbent (kg) |
| Desorbed CO₂ | `DES_CO2` | CO₂ released from sorbent (kg) |
| Bag CO₂ | `BAG_CO2` | CO₂ in gas balloon after processing (kg) |

### 2.2 Process Stage CO₂ Tracking

```
                    [Atmosphere]
                         │
                         ▼
              ┌──────────────────┐
              │  ADS_CO2 (kg)    │  Adsorption Phase
              │  (what sorbent   │
              │   captured)      │
              └────────┬─────────┘
                       │
                       ▼ Loss_Stage_1
              ┌──────────────────┐
              │  DES_CO2 (kg)    │  Desorption Phase
              │  (what sorbent   │
              │   released)      │
              └────────┬─────────┘
                       │
                       ▼ Loss_Stage_2
              ┌──────────────────┐
              │  BAG_CO2 (kg)    │  Processing Phase
              │  (in gas balloon │
              │   after cooling) │
              └────────┬─────────┘
                       │
                       ▼ Loss_Stage_3
              ┌──────────────────┐
              │  LIQ_CO2 (kg)    │  Liquefaction Phase
              │  (liquefied,     │
              │   ready for      │
              │   storage)       │
              └──────────────────┘
```

### 2.3 Cycle-Level CO₂ Calculations

**Desorption Efficiency (per cycle):**
```
Desorption_Efficiency = (DES_CO2 / ADS_CO2) × 100%
```

**Processing Efficiency (per cycle):**
```
Processing_Efficiency = (BAG_CO2 / DES_CO2) × 100%
```

*Note: Processing efficiency can be >100% if prior cycle's residual CO₂ carries over*

### 2.4 Weekly CO₂ Aggregation

```python
# Sum all cycles in the week
Weekly_ADS_CO2 = Σ(ADS_CO2_cycle_i) for all cycles in week
Weekly_DES_CO2 = Σ(DES_CO2_cycle_i) for all cycles in week
Weekly_BAG_CO2 = Σ(BAG_CO2_cycle_i) for all cycles in week
Weekly_LIQ_CO2 = Manual_Entry  # Entered by admin
```

---

## 3. Energy Calculations

### 3.1 Energy Categories

Energy consumption is divided into two categories:

| Category | Components | Purpose |
|----------|------------|---------|
| **Thermal Energy** | Boiler | Steam generation for desorption |
| **Auxiliary Energy** | SRV/LRVP, CT, Fans (NM1-4) | Pumps, cooling, air movement |

### 3.2 Cycle-Level Energy

From SCADA energy report:

```python
Thermal_Energy_cycle = Boiler_kWh

Auxiliary_Energy_cycle = SRV_LRVP_kWh + CT_kWh + NM1_Fan_kWh + 
                         NM2_Fan_kWh + NM3_Fan_kWh + NM4_Fan_kWh

Total_Energy_cycle = Thermal_Energy_cycle + Auxiliary_Energy_cycle
# Should equal eTotal_kWh from SCADA
```

### 3.3 Weekly Energy Aggregation

```python
Weekly_Thermal_Energy = Σ(Boiler_kWh_cycle_i) for all cycles in week
Weekly_Auxiliary_Energy = Σ(Auxiliary_Energy_cycle_i) for all cycles in week
Weekly_Total_Energy = Weekly_Thermal_Energy + Weekly_Auxiliary_Energy
```

### 3.4 Energy Component Breakdown

For detailed analysis, auxiliary energy is further broken down:

```python
Weekly_Vacuum_Pump_Energy = Σ(SRV_LRVP_kWh)
Weekly_Cooling_Energy = Σ(CT_kWh)
Weekly_Fan_Energy = Σ(NM1_Fan_kWh + NM2_Fan_kWh + NM3_Fan_kWh + NM4_Fan_kWh)
```

---

## 4. Operational Emissions Calculations

### 4.1 Grid Emission Factor

```
Grid_EF = 0.049 kg CO₂/kWh  # Kenya Power 2024
```

### 4.2 Cycle-Level Operational Emissions

```python
Thermal_Emissions_cycle = Boiler_kWh × Grid_EF
Auxiliary_Emissions_cycle = Auxiliary_Energy_cycle × Grid_EF
Total_Operational_Emissions_cycle = Total_Energy_cycle × Grid_EF
```

### 4.3 Weekly Operational Emissions

```python
Weekly_Thermal_Emissions = Weekly_Thermal_Energy × Grid_EF
Weekly_Auxiliary_Emissions = Weekly_Auxiliary_Energy × Grid_EF
Weekly_Total_Operational_Emissions = Weekly_Total_Energy × Grid_EF
```

### 4.4 Example Calculation

```python
# Example: Week with 100 cycles
Weekly_Thermal_Energy = 6,500 kWh
Weekly_Auxiliary_Energy = 2,500 kWh
Grid_EF = 0.049 kg CO₂/kWh

Weekly_Thermal_Emissions = 6,500 × 0.049 = 318.5 kg CO₂
Weekly_Auxiliary_Emissions = 2,500 × 0.049 = 122.5 kg CO₂
Weekly_Total_Operational_Emissions = 441.0 kg CO₂
```

---

## 5. Embodied Emissions Calculations

### 5.1 Infrastructure Embodied Emissions

Infrastructure embodied emissions are calculated from LCA data and amortized over 10 years (520 weeks).

**Total Infrastructure Embodied (One-time Calculation):**
```python
Infrastructure_Embodied_Total = (
    Zone1_Embodied +      # Capture modules
    Zone2_Embodied +      # Processing
    Zone3_Embodied +      # Liquefaction
    Transport_Embodied    # Equipment shipping
)
```

**Weekly Infrastructure Charge:**
```python
Infrastructure_Embodied_Weekly = Infrastructure_Embodied_Total / 520
```

### 5.2 Zone Embodied Calculations

Each zone's embodied emissions are calculated as:

```python
Zone_Embodied = Σ(Material_Weight_kg × Material_EF_kgCO2_per_kg)
```

**Zone 1 (Capture) Components:**
```python
Zone1_Embodied = (
    Container_Weight × Mild_Steel_EF +
    Iron_Sheet_Area × Iron_Sheet_Weight_Factor × Mild_Steel_EF +
    Concrete_Volume × Concrete_Density × Concrete_EF +
    Module_Frames_Weight × Stainless_Steel_EF +
    Sorbent_Bed_Structure_Weight × Stainless_Steel_EF +
    Fan_Weights × Mixed_Metal_EF +
    Boiler_Weight × Mild_Steel_EF +
    Internal_Piping_Weight × Stainless_Steel_EF +
    Electrical_Weight × Mixed_EF
)
```

**Zone 2 (Processing) Components:**
```python
Zone2_Embodied = (
    Tent_Frame_Weight × Mild_Steel_EF +
    Iron_Sheet_Area × Iron_Sheet_Weight_Factor × Mild_Steel_EF +
    Concrete_Volume × Concrete_Density × Concrete_EF +
    PHE_Weight × Stainless_Steel_EF +
    Separator_Weight × Stainless_Steel_EF +
    Vacuum_Pump_Weight × Mixed_Metal_EF +
    Gas_Balloon_Weight × Polymer_EF +
    Piping_Weight × Stainless_Steel_EF +
    Valves_Weight × Stainless_Steel_EF
)
```

**Zone 3 (Liquefaction) Components:**
```python
Zone3_Embodied = (
    Iron_Sheet_Area × Iron_Sheet_Weight_Factor × Mild_Steel_EF +
    Concrete_Volume × Concrete_Density × Concrete_EF +
    Buffer_Balloon_Weight × Polymer_EF +
    Liquefaction_Unit_Weight × Mixed_EF +
    Cryogenic_Tank_Weight × Stainless_Steel_EF +
    Transfer_Pumps_Weight × Mixed_Metal_EF +
    Piping_Weight × Stainless_Steel_EF +
    Valves_Weight × Stainless_Steel_EF +
    Insulation_Weight × Mixed_EF
)
```

### 5.3 Transport Embodied Emissions

```python
Transport_Embodied = (
    Sea_Distance_km × Equipment_Weight_tonnes × Sea_Shipping_EF +
    Road_Distance_km × Equipment_Weight_tonnes × Road_Trucking_EF +
    Sorbent_Road_Distance_km × Sorbent_Weight_tonnes × Road_Trucking_EF +
    Other_Materials_Transport
)
```

Where:
```
Sea_Shipping_EF = 0.005 kg CO₂/t-km
Road_Trucking_EF = 0.086 kg CO₂/t-km
```

### 5.4 Sorbent Embodied Emissions

Sorbent materials have a 3-year (156-week) lifetime and require separate amortization.

**Production Emissions (per batch):**
```python
Sorbent_Production_Embodied = (
    Alumina_kg × Alumina_EF +      # Support material
    PEI_kg × PEI_EF +              # Active sorbent
    Methanol_kg × Methanol_EF      # Regeneration solvent
)
```

**End-of-Life Emissions (per batch):**
```python
Sorbent_EOL_Embodied = (
    Alumina_kg × Alumina_EOL_EF +  # Landfill
    PEI_kg × PEI_EOL_EF +          # Combustion
    Methanol_kg × Methanol_EOL_EF  # Combustion
)
```

**Total Sorbent Embodied (per batch):**
```python
Sorbent_Batch_Embodied = Sorbent_Production_Embodied + Sorbent_EOL_Embodied
```

**Weekly Sorbent Charge:**
```python
Sorbent_Embodied_Weekly = Sorbent_Batch_Embodied / 156
```

### 5.5 Total Weekly Embodied Charge

```python
Total_Weekly_Embodied = Infrastructure_Embodied_Weekly + Sorbent_Embodied_Weekly
```

### 5.6 Emission Factor Reference Table

| Material | Production EF (kg CO₂/kg) | EOL EF (kg CO₂/kg) |
|----------|--------------------------|-------------------|
| Stainless Steel 304 | 7.14 | 0.02 (landfill) |
| Mild Steel | 2.4 | 0.02 (landfill) |
| Aluminium | 11.75 | 0.02 (landfill) |
| Concrete | 0.13 | - |
| Polymer | 2.5 | - |
| Mixed Metals | 3.5 | 0.02 (landfill) |
| Mixed Materials | 3.0-4.0 | - |
| Alumina | 1.91 | 0.02 (landfill) |
| PEI | 11.05 | 1.29 (combustion) |
| Methanol | 0.92 | 1.29 (combustion) |

---

## 6. Loss Calculations

### 6.1 Loss Definition

CO₂ losses represent CO₂ that was captured but not ultimately liquefied. Per Puro methodology, losses reduce the gross capture (they are NOT counted as emissions, but they reduce the credit for removal).

### 6.2 Stage-by-Stage Losses

**Stage 1: Adsorption to Desorption Loss**
```python
Loss_Stage_1 = ADS_CO2 - DES_CO2
Loss_Stage_1_Percent = (Loss_Stage_1 / ADS_CO2) × 100%
```

*This represents CO₂ that was adsorbed but not successfully desorbed*

**Stage 2: Desorption to Bag Loss**
```python
Loss_Stage_2 = DES_CO2 - BAG_CO2
Loss_Stage_2_Percent = (Loss_Stage_2 / DES_CO2) × 100%
```

*This represents CO₂ lost during processing/separation*

**Stage 3: Bag to Liquefaction Loss**
```python
Loss_Stage_3 = BAG_CO2 - LIQ_CO2
Loss_Stage_3_Percent = (Loss_Stage_3 / BAG_CO2) × 100%
```

*This represents CO₂ lost during liquefaction*

### 6.3 Total Loss Calculation

**Total Loss (Cycle):**
```python
Total_Loss_Cycle = ADS_CO2 - LIQ_CO2
# Or equivalently:
Total_Loss_Cycle = Loss_Stage_1 + Loss_Stage_2 + Loss_Stage_3
```

**Overall Capture Efficiency:**
```python
Capture_Efficiency = (LIQ_CO2 / ADS_CO2) × 100%
# Or equivalently:
Capture_Efficiency = 100% - Total_Loss_Percent
```

### 6.4 Weekly Loss Aggregation

```python
Weekly_Loss_Stage_1 = Weekly_ADS_CO2 - Weekly_DES_CO2
Weekly_Loss_Stage_2 = Weekly_DES_CO2 - Weekly_BAG_CO2
Weekly_Loss_Stage_3 = Weekly_BAG_CO2 - Weekly_LIQ_CO2
Weekly_Total_Loss = Weekly_ADS_CO2 - Weekly_LIQ_CO2
```

### 6.5 Loss Impact on Net Removal

Losses don't add to emissions but reduce gross capture:

```python
# What counts for removal credit
Gross_CO2_Captured = Weekly_LIQ_CO2  # Only liquefied CO₂ counts
# NOT Weekly_ADS_CO2 (what was adsorbed)
```

---

## 7. Efficiency Metrics

### 7.1 Energy Intensity (kWh/tCO₂)

**Total Energy Intensity:**
```python
Energy_Intensity_Total = (Total_Energy_kWh / Liquefied_CO2_tonnes)
# Unit: kWh/tCO₂
```

**Thermal Energy Intensity:**
```python
Energy_Intensity_Thermal = (Thermal_Energy_kWh / Liquefied_CO2_tonnes)
# Unit: kWh/tCO₂
```

**Auxiliary Energy Intensity:**
```python
Energy_Intensity_Auxiliary = (Auxiliary_Energy_kWh / Liquefied_CO2_tonnes)
# Unit: kWh/tCO₂
```

### 7.2 Weekly Efficiency Calculations

```python
# Convert CO₂ from kg to tonnes for standard reporting
Weekly_LIQ_CO2_tonnes = Weekly_LIQ_CO2 / 1000

Weekly_Energy_Intensity = Weekly_Total_Energy / Weekly_LIQ_CO2_tonnes
Weekly_Thermal_Intensity = Weekly_Thermal_Energy / Weekly_LIQ_CO2_tonnes
Weekly_Auxiliary_Intensity = Weekly_Auxiliary_Energy / Weekly_LIQ_CO2_tonnes
```

### 7.3 Emissions Intensity

**Operational Emissions per tCO₂ Captured:**
```python
Emissions_Intensity = (Weekly_Total_Operational_Emissions / Weekly_LIQ_CO2_tonnes)
# Unit: kg CO₂ emitted per tonne CO₂ captured
```

### 7.4 Steam Efficiency

```python
Steam_per_tCO2 = Weekly_Steam_kg / Weekly_LIQ_CO2_tonnes
# Unit: kg steam per tonne CO₂ captured
```

### 7.5 Cycle Efficiency Metrics

**Cycles per Week:**
```python
Cycles_per_Week = Count(cycles in week)
```

**Average CO₂ per Cycle:**
```python
Avg_ADS_per_Cycle = Weekly_ADS_CO2 / Cycles_per_Week
Avg_BAG_per_Cycle = Weekly_BAG_CO2 / Cycles_per_Week
Avg_Energy_per_Cycle = Weekly_Total_Energy / Cycles_per_Week
```

---

## 8. Aggregation Formulas

### 8.1 Weekly Aggregation (Primary Reporting Period)

```python
# Define week boundaries (Monday 00:00 to Sunday 23:59)
week_start = datetime(year, month, day, 0, 0, 0)  # Monday
week_end = week_start + timedelta(days=7)

# Aggregate cycles within week
cycles_in_week = [c for c in all_cycles if week_start <= c.timestamp < week_end]

# Sum metrics
Weekly_Summary = {
    'week_number': week_number,
    'year': year,
    'start_date': week_start,
    'end_date': week_end,
    'total_cycles': len(cycles_in_week),
    
    # CO₂ Flows (kg)
    'ads_co2': sum(c.ads_co2 for c in cycles_in_week),
    'des_co2': sum(c.des_co2 for c in cycles_in_week),
    'bag_co2': sum(c.bag_co2 for c in cycles_in_week),
    'liq_co2': manual_entry,  # Weekly liquefied amount
    
    # Energy (kWh)
    'thermal_energy': sum(c.boiler_kwh for c in cycles_in_week),
    'auxiliary_energy': sum(c.auxiliary_kwh for c in cycles_in_week),
    'total_energy': sum(c.total_kwh for c in cycles_in_week),
    
    # Steam (kg)
    'steam': sum(c.steam_kg for c in cycles_in_week),
    
    # Operational Emissions (kg CO₂)
    'thermal_emissions': thermal_energy * GRID_EF,
    'auxiliary_emissions': auxiliary_energy * GRID_EF,
    'total_operational_emissions': total_energy * GRID_EF,
    
    # Embodied Emissions (kg CO₂)
    'infrastructure_embodied': INFRASTRUCTURE_WEEKLY_CHARGE,
    'sorbent_embodied': SORBENT_WEEKLY_CHARGE,
    'total_embodied': INFRASTRUCTURE_WEEKLY_CHARGE + SORBENT_WEEKLY_CHARGE,
    
    # Losses (kg)
    'loss_stage_1': ads_co2 - des_co2,
    'loss_stage_2': des_co2 - bag_co2,
    'loss_stage_3': bag_co2 - liq_co2,
    'total_loss': ads_co2 - liq_co2,
    
    # Net Calculation (kg)
    'gross_captured': liq_co2,
    'total_emissions': total_operational_emissions + total_embodied,
    'net_removal': liq_co2 - (total_operational_emissions + total_embodied)
}
```

### 8.2 Monthly Aggregation

```python
Monthly_Summary = {
    'month': month,
    'year': year,
    'weeks_in_month': [weekly_summaries for week in month],
    
    # Sum weekly values
    'total_cycles': sum(w.total_cycles for w in weeks),
    'ads_co2': sum(w.ads_co2 for w in weeks),
    'liq_co2': sum(w.liq_co2 for w in weeks),
    'total_energy': sum(w.total_energy for w in weeks),
    'total_operational_emissions': sum(w.total_operational_emissions for w in weeks),
    'total_embodied': sum(w.total_embodied for w in weeks),
    'net_removal': sum(w.net_removal for w in weeks)
}
```

### 8.3 Year-to-Date (YTD) Aggregation

```python
YTD_Summary = {
    'year': year,
    'through_week': current_week,
    
    # Sum all weeks YTD
    'total_cycles': sum(w.total_cycles for w in weeks_ytd),
    'liq_co2_tonnes': sum(w.liq_co2 for w in weeks_ytd) / 1000,
    'total_energy': sum(w.total_energy for w in weeks_ytd),
    'total_operational_emissions': sum(w.total_operational_emissions for w in weeks_ytd),
    'total_embodied': sum(w.total_embodied for w in weeks_ytd),
    'net_removal_tonnes': sum(w.net_removal for w in weeks_ytd) / 1000
}
```

### 8.4 Lifetime Aggregation

```python
Lifetime_Summary = {
    'start_date': plant_start_date,
    'through_date': current_date,
    'weeks_operational': total_weeks,
    
    # Cumulative totals
    'total_liq_co2_tonnes': sum(all_liq_co2) / 1000,
    'total_operational_emissions_tonnes': sum(all_operational_emissions) / 1000,
    'total_embodied_emissions_tonnes': sum(all_embodied) / 1000,
    'lifetime_net_removal_tonnes': sum(all_net_removal) / 1000,
    
    # Progress toward capacity
    'annual_run_rate': (total_liq_co2_tonnes / weeks_operational) * 52,
    'capacity_utilization': annual_run_rate / TARGET_CAPACITY * 100
}
```

---

## 9. Monte Carlo Simulation Parameters

### 9.1 Geothermal Transition Scenario

The Monte Carlo simulation models the impact of replacing boiler steam with geothermal steam.

**Base Scenario (Current State):**
```python
Current_Thermal_Emissions = Weekly_Thermal_Energy × Grid_EF
Geothermal_EF = 0.0  # Near-zero emissions from geothermal
```

**Geothermal Scenario:**
```python
# 100% thermal load replacement
Geothermal_Thermal_Emissions = Weekly_Thermal_Energy × Geothermal_EF
# = Weekly_Thermal_Energy × 0.0 = 0

# New operational emissions
New_Operational_Emissions = Weekly_Auxiliary_Emissions + 0
# Only auxiliary energy contributes to emissions
```

**Emissions Reduction:**
```python
Emissions_Reduction = Current_Thermal_Emissions - Geothermal_Thermal_Emissions
Emissions_Reduction_Percent = (Current_Thermal_Emissions / Current_Total_Operational_Emissions) × 100%
```

### 9.2 Simulation Variables

For Monte Carlo simulation, the following parameters should vary:

| Parameter | Distribution | Range | Notes |
|-----------|-------------|-------|-------|
| Capture Efficiency | Normal | μ based on historical, σ = 5% | Cycle-to-cycle variation |
| Thermal Energy per Cycle | Normal | μ based on historical, σ = 10% | Seasonal/operational variation |
| Auxiliary Energy per Cycle | Normal | μ based on historical, σ = 8% | Equipment efficiency variation |
| Equipment Uptime | Beta | α=9, β=1 (mean ~90%) | Maintenance/downtime |
| Processing Loss Rate | Beta | α=2, β=18 (mean ~10%) | Process efficiency |

### 9.3 Simulation Process

```python
def monte_carlo_simulation(n_iterations=10000):
    results = []
    
    for i in range(n_iterations):
        # Sample parameters
        capture_eff = np.random.normal(historical_mean, historical_std)
        thermal_energy = np.random.normal(thermal_mean, thermal_std)
        auxiliary_energy = np.random.normal(aux_mean, aux_std)
        uptime = np.random.beta(9, 1)
        loss_rate = np.random.beta(2, 18)
        
        # Calculate weekly outcomes
        cycles_per_week = expected_cycles * uptime
        gross_captured = cycles_per_week * avg_capture_per_cycle * capture_eff
        losses = gross_captured * loss_rate
        net_captured = gross_captured - losses
        
        # Geothermal scenario: thermal emissions = 0
        operational_emissions = auxiliary_energy * cycles_per_week * GRID_EF
        embodied = WEEKLY_EMBODIED_CHARGE
        
        net_removal = net_captured - operational_emissions - embodied
        results.append(net_removal)
    
    return {
        'mean': np.mean(results),
        'std': np.std(results),
        'p5': np.percentile(results, 5),
        'p50': np.percentile(results, 50),
        'p95': np.percentile(results, 95),
        'prob_net_positive': sum(r > 0 for r in results) / n_iterations
    }
```

### 9.4 Scenario Comparison Output

```python
Scenario_Comparison = {
    'current': {
        'weekly_net_removal': net_removal_current,
        'prob_net_positive': prob_current
    },
    'geothermal': {
        'weekly_net_removal': net_removal_geothermal,
        'prob_net_positive': prob_geothermal,
        'emissions_reduction': emissions_saved,
        'improvement': net_removal_geothermal - net_removal_current
    }
}
```

---

## 10. Break-Even Analysis

### 10.1 Break-Even Point

The break-even point is where Net CO₂ Removal = 0:

```python
# At break-even:
Gross_Captured = Total_Emissions

# Therefore:
LIQ_CO2_breakeven = Operational_Emissions + Embodied_Emissions
```

### 10.2 Minimum Capture Required

To be net positive, weekly liquefied CO₂ must exceed:

```python
Min_LIQ_CO2_weekly = Weekly_Total_Operational_Emissions + Weekly_Embodied_Charge
```

**Example Calculation:**
```python
Weekly_Total_Energy = 9,000 kWh
Grid_EF = 0.049 kg CO₂/kWh
Weekly_Operational_Emissions = 9,000 × 0.049 = 441 kg CO₂

Weekly_Infrastructure_Embodied = 50 kg CO₂  # Example
Weekly_Sorbent_Embodied = 30 kg CO₂         # Example
Weekly_Embodied_Total = 80 kg CO₂

Min_LIQ_CO2_weekly = 441 + 80 = 521 kg CO₂

# To be net positive, must liquefy > 521 kg CO₂ per week
```

### 10.3 Operational Emissions Reduction Target

To achieve net positive at current capture rates:

```python
# If current capture is below break-even
Current_LIQ_CO2 = 400 kg/week  # Example
Required_Emissions_Reduction = Total_Emissions - Current_LIQ_CO2

# What operational improvement is needed?
Max_Allowable_Operational = Current_LIQ_CO2 - Embodied_Emissions
Operational_Reduction_Needed = Current_Operational - Max_Allowable_Operational
Reduction_Percent = (Operational_Reduction_Needed / Current_Operational) × 100%
```

### 10.4 Energy Reduction Calculator

How much energy reduction is needed to achieve net positive:

```python
def energy_reduction_needed(current_capture_kg, current_energy_kwh, embodied_weekly_kg, grid_ef):
    """
    Calculate energy reduction needed to break even or achieve target net removal
    """
    current_operational = current_energy_kwh * grid_ef
    total_current_emissions = current_operational + embodied_weekly_kg
    
    # For break-even
    max_operational_for_breakeven = current_capture_kg - embodied_weekly_kg
    max_energy_for_breakeven = max_operational_for_breakeven / grid_ef
    energy_reduction_for_breakeven = current_energy_kwh - max_energy_for_breakeven
    
    return {
        'current_net': current_capture_kg - total_current_emissions,
        'max_energy_for_breakeven': max_energy_for_breakeven,
        'energy_reduction_needed': energy_reduction_for_breakeven,
        'reduction_percent': (energy_reduction_for_breakeven / current_energy_kwh) * 100
    }
```

### 10.5 Sensitivity Analysis

Impact of changing key parameters on net removal:

```python
def sensitivity_analysis():
    base_net_removal = calculate_net_removal(base_params)
    
    sensitivities = {}
    
    # Test ±10% change in each parameter
    for param in ['capture_efficiency', 'thermal_energy', 'auxiliary_energy', 
                  'grid_ef', 'embodied_weekly']:
        # +10%
        params_high = base_params.copy()
        params_high[param] *= 1.10
        net_high = calculate_net_removal(params_high)
        
        # -10%
        params_low = base_params.copy()
        params_low[param] *= 0.90
        net_low = calculate_net_removal(params_low)
        
        sensitivities[param] = {
            'change_per_10pct_increase': net_high - base_net_removal,
            'change_per_10pct_decrease': net_low - base_net_removal,
            'elasticity': (net_high - net_low) / (base_net_removal * 0.20)
        }
    
    return sensitivities
```

---

## Appendix A: Constants Reference

```python
# Grid Emission Factors
GRID_EF_KENYA = 0.049  # kg CO₂/kWh (Kenya Power 2024)
GRID_EF_GEOTHERMAL = 0.0  # kg CO₂/kWh (geothermal scenario)

# Material Emission Factors (kg CO₂/kg)
EF_STAINLESS_STEEL = 7.14
EF_MILD_STEEL = 2.40
EF_ALUMINIUM = 11.75
EF_CONCRETE = 0.13
EF_POLYMER = 2.50
EF_MIXED_METALS = 3.50
EF_ALUMINA = 1.91
EF_PEI = 11.05
EF_METHANOL = 0.92

# EOL Emission Factors (kg CO₂/kg)
EOL_LANDFILL = 0.02
EOL_COMBUSTION = 1.29

# Transport Emission Factors
EF_SEA_SHIPPING = 0.005  # kg CO₂/t-km
EF_ROAD_TRUCKING = 0.086  # kg CO₂/t-km

# Amortization Periods
INFRASTRUCTURE_LIFETIME_WEEKS = 520  # 10 years
SORBENT_LIFETIME_WEEKS = 156  # 3 years

# Conversion Factors
KG_PER_TONNE = 1000
CONCRETE_DENSITY = 2400  # kg/m³
IRON_SHEET_WEIGHT_FACTOR = 5.5  # kg/m²
```

---

*Document continues in 03_SYSTEM_ARCHITECTURE.md*
