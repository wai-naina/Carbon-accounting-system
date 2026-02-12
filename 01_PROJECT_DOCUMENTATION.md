# Octavia Carbon Accounting System (CAS)
## Project Documentation

**Version:** 1.0  
**Date:** January 2026  
**Project:** Project Hummingbird Phase 1  
**Location:** Gilgil, Kenya  
**Prepared for:** Octavia Carbon  

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Company & Operations Overview](#2-company--operations-overview)
3. [System Purpose & Objectives](#3-system-purpose--objectives)
4. [Methodology Framework](#4-methodology-framework)
5. [Glossary of Terms](#5-glossary-of-terms)

---

## 1. Executive Summary

### 1.1 Project Overview

Octavia Carbon operates a Direct Air Capture (DAC) facility in Gilgil, Kenya, designed to remove CO₂ directly from the atmosphere and prepare it for geological storage. The Carbon Accounting System (CAS) serves as an internal ledger to track, measure, and report the company's net carbon removal performance.

### 1.2 Core Objective

The primary objective of the CAS is to determine whether Octavia Carbon's operations are **net positive** (removing more CO₂ than emitted through operations) or **net negative** (emitting more than captured). This is critical for:

- Internal performance monitoring
- Operational optimization
- Future Puro.earth CORC certification readiness
- Stakeholder reporting
- Strategic decision-making (e.g., geothermal transition)

### 1.3 Key Metrics

| Metric | Description |
|--------|-------------|
| **Gross CO₂ Captured** | Total CO₂ successfully liquefied and ready for geological storage |
| **Operational Emissions** | Emissions from energy consumption (thermal + auxiliary) |
| **Embodied Emissions** | Amortized emissions from infrastructure and sorbent materials |
| **CO₂ Losses** | CO₂ lost through the capture-to-liquefaction process chain |
| **Net CO₂ Removal** | Gross Captured - (Operational + Embodied + Losses) |

### 1.4 Target Capacity

- **Design Capacity:** 100 tonnes CO₂/year
- **Plant Lifetime:** 10 years
- **Sorbent Lifetime:** 3 years per batch
- **Reporting Period:** Weekly

---

## 2. Company & Operations Overview

### 2.1 Process Description

Octavia Carbon's DAC process consists of four main phases:

#### Phase 1: Adsorption (CO₂ Capture)
- Ambient air is drawn through 4 reactor modules using fans
- Each module pair operates together: Module 1n3 and Module 2n4
- The reactors contain 352 monoliths total (88 per reactor)
- Monoliths are honeycomb-structured cordierite supports coated with alumina washcoat
- Polyethyleneimine (PEI) amine-based sorbent is embedded in the support
- PEI is mixed with methanol for application to enable flow
- CO₂ from the passing air is adsorbed onto the PEI sorbent

#### Phase 2: Desorption (CO₂ Release)
- When monoliths reach saturation, desorption begins
- Reactor is isolated and pressure drops to ~150 mbar
- Oxygen and non-condensable gases (NCGS) are purged
- Steam is introduced via modulating valve to prevent condensation
- Condensation would cause PEI leaching, degrading sorbent
- Temperature and pressure rise, releasing CO₂ from sorbent
- Steam purges the suspended CO₂ to downstream processing

#### Phase 3: Processing (CO₂ Separation)
- CO₂ and steam mixture passes through Plate Heat Exchanger (PHE)
- Macro and micro coolers separate water from CO₂
- Gas analyzer measures CO₂ purity
- CO₂ with >95% purity proceeds to gas balloon
- CO₂ below threshold is recycled or vented

#### Phase 4: Liquefaction (CO₂ Preparation for Storage)
- Gas balloon contents transfer to liquefaction unit
- CO₂ is compressed and cooled to liquid state
- Liquid CO₂ stored in cryogenic tank
- Ready for transport to geological storage partner

### 2.2 Plant Zones

| Zone | Description | Key Equipment |
|------|-------------|---------------|
| Zone 1: Capture | Container housing 4 reactor modules | Fans (NM1-NM4), Boiler, Monoliths, Piping |
| Zone 2: Processing | Tent structure for CO₂ separation | PHE, Separator, Vacuum Pump (SRV/LRVP), Gas Balloon |
| Zone 3: Liquefaction | Liquefaction and storage area | Liquefaction Unit, Cryogenic Tank, Buffer Balloon |

### 2.3 Operational Data Sources

| Data Type | Source | Frequency |
|-----------|--------|-----------|
| Cycle Performance | SCADA System | Per cycle |
| Energy Consumption | SCADA System | Per cycle |
| CO₂ Measurements | SCADA System | Per cycle |
| Liquefied CO₂ | Manual Entry | Weekly |
| Equipment Status | SCADA System | Continuous |

---

## 3. System Purpose & Objectives

### 3.1 Primary Functions

1. **Carbon Ledger**: Track all CO₂ flows from capture to liquefaction
2. **Emissions Calculator**: Quantify operational and embodied emissions
3. **Net Position Calculator**: Determine net positive/negative status
4. **Performance Analytics**: Monitor efficiency metrics (kWh/tCO₂)
5. **Scenario Modeling**: Monte Carlo simulations for operational changes
6. **Reporting**: Weekly summaries and trend analysis

### 3.2 User Requirements

| User Type | Capabilities |
|-----------|-------------|
| **Admin** | Full access: data entry, user management, all reports, configuration |
| **User** | View-only access: dashboards, reports, analytics |

### 3.3 Data Entry Requirements

| Data Category | Entry Method | Frequency | Responsible |
|--------------|--------------|-----------|-------------|
| Cycle Data | Auto-import from CSV | Weekly | Admin |
| Energy Data | Auto-import from CSV | Weekly | Admin |
| Liquefied CO₂ | Manual entry | Weekly | Admin |
| Embodied Emissions | Initial setup + updates | As needed | Admin |
| User Accounts | Admin interface | As needed | Admin |

### 3.4 Reporting Requirements

- **Weekly Summary Dashboard**: Current week performance vs. targets
- **Cumulative Tracking**: Year-to-date and lifetime metrics
- **Trend Analysis**: Week-over-week comparisons
- **Efficiency Metrics**: kWh/tCO₂ for thermal and auxiliary energy
- **Loss Analysis**: Breakdown of CO₂ losses by process stage
- **Net Position**: Clear indication of net positive/negative status

---

## 4. Methodology Framework

### 4.1 Puro.earth GSC Methodology Alignment

While this system is for internal tracking, it is designed to align with the Puro Standard Geologically Stored Carbon (GSC) Methodology 2024 Edition requirements:

| Puro Requirement | CAS Implementation |
|-----------------|-------------------|
| Net CO₂ Removal quantification | Gross - Operational - Embodied - Losses |
| LCA-based emissions accounting | Embodied emissions from LCA data |
| Operational emissions tracking | Energy consumption × grid factor |
| CO₂ purity ≥95% | Tracked via gas analyzer data |
| Leakage accounting | CO₂ losses tracked at each process stage |
| Uncertainty management | Included in calculations |

### 4.2 System Boundaries

**Included in CAS:**
- CO₂ capture operations (adsorption/desorption)
- CO₂ processing (separation, purification)
- CO₂ liquefaction
- All energy consumption (thermal + auxiliary)
- Embodied emissions (infrastructure + sorbent)
- CO₂ losses throughout process chain

**Excluded from CAS:**
- Transport to geological storage site
- Geological injection and storage
- Office/amenity operations
- Employee commuting

### 4.3 Emission Factors

| Factor | Value | Unit | Source |
|--------|-------|------|--------|
| Kenya Grid Electricity | 0.049 | kg CO₂/kWh | Kenya Power 2024 |
| Geothermal Steam | ~0.000 | kg CO₂/kWh | Near-zero (scenario) |
| Stainless Steel 304 | 7.14 | kg CO₂/kg | Idemat 2025 |
| Mild Steel | 2.4 | kg CO₂/kg | Idemat 2026 |
| Aluminium | 11.75 | kg CO₂/kg | Idemat 2026 |
| Concrete | 0.13 | kg CO₂/kg | Idemat 2026 |
| Alumina (sorbent support) | 1.91 | kg CO₂/kg | Idemat 2026 |
| PEI (active sorbent) | 11.05 | kg CO₂/kg | Climeworks LCA |
| Methanol | 0.92 | kg CO₂/kg | Idemat 2026 |

### 4.4 Amortization Periods

| Asset Category | Lifetime | Amortization |
|---------------|----------|--------------|
| Infrastructure (Zones 1-3) | 10 years | 520 weeks |
| Transport Emissions | 10 years | 520 weeks |
| Sorbent Materials | 3 years | 156 weeks |

---

## 5. Glossary of Terms

| Term | Definition |
|------|------------|
| **Adsorption** | Process of CO₂ molecules binding to the sorbent surface |
| **Desorption** | Process of releasing captured CO₂ from the sorbent using heat/vacuum |
| **BAG CO₂** | CO₂ quantity measured in the gas balloon after processing |
| **CORC** | CO₂ Removal Certificate (Puro.earth's carbon credit unit) |
| **Cycle** | One complete adsorption-desorption sequence for a reactor pair |
| **DAC** | Direct Air Capture - capturing CO₂ directly from ambient air |
| **Embodied Emissions** | Emissions from manufacturing/construction of equipment |
| **Grid EF** | Grid Emission Factor - CO₂ emitted per kWh of grid electricity |
| **Gross Capture** | Total CO₂ captured before accounting for losses |
| **LCA** | Life Cycle Assessment - comprehensive environmental impact analysis |
| **Monolith** | Honeycomb-structured support material for sorbent |
| **NCGS** | Non-Condensable Gases - gases that don't condense during processing |
| **Module** | Reactor modules (paired as 1&3, 2&4) |
| **Net Removal** | Gross capture minus all emissions and losses |
| **Operational Emissions** | Emissions from energy used during operations |
| **PEI** | Polyethyleneimine - the amine-based sorbent material |
| **PHE** | Plate Heat Exchanger - equipment for heat transfer |
| **SCADA** | Supervisory Control and Data Acquisition system |
| **Sorbent** | Material that captures CO₂ through chemical bonding |
| **SRV/LRVP** | Steam Ring Vacuum Pump / Liquid Ring Vacuum Pump |
| **Thermal Energy** | Energy used for steam generation (boiler) |
| **Auxiliary Energy** | Energy for pumps, fans, compressors, instruments |

---

*Document continues in 02_CALCULATIONS_AND_FORMULAS.md*
