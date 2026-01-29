# Octavia Carbon Accounting System (CAS)
## Product Requirements Document (PRD)

**Version:** 1.0  
**Date:** January 2026  
**Product Owner:** Octavia Carbon  

---

## Table of Contents

1. [Product Overview](#1-product-overview)
2. [User Stories](#2-user-stories)
3. [Functional Requirements](#3-functional-requirements)
4. [Non-Functional Requirements](#4-non-functional-requirements)
5. [User Interface Specifications](#5-user-interface-specifications)
6. [Data Requirements](#6-data-requirements)
7. [Acceptance Criteria](#8-acceptance-criteria)
8. [Implementation Phases](#9-implementation-phases)

---

## 1. Product Overview

### 1.1 Problem Statement

Octavia Carbon operates a Direct Air Capture (DAC) facility and needs to determine whether operations are net positive or net negative. Currently there is no integrated system to track CO₂ flows, calculate emissions, and determine net removal status.

### 1.2 Solution

The Carbon Accounting System (CAS) is an internal web application that serves as a carbon ledger, providing automated import of SCADA data, carbon accounting calculations, and scenario modeling.

### 1.3 Success Metrics

| Metric | Target |
|--------|--------|
| Data entry time | < 15 minutes/week |
| Calculation accuracy | 100% |
| System availability | 99% |

### 1.4 Scope

**In Scope:** CO₂ tracking, emissions calculation, reporting, Monte Carlo simulations, user authentication

**Out of Scope:** SCADA integration, transport to storage, mobile app

---

## 2. User Stories

### 2.1 Administrator Stories

| ID | Story | Priority |
|----|-------|----------|
| A1 | Import cycle data from CSV files | Must Have |
| A2 | Import energy data from CSV files | Must Have |
| A3 | Manually enter weekly liquefied CO₂ amounts | Must Have |
| A4 | Configure emission factors | Must Have |
| A5 | Add and manage user accounts | Must Have |
| A6 | Edit embodied emissions data | Should Have |
| A7 | View audit logs | Should Have |
| A8 | Export reports to Excel | Should Have |

### 2.2 User Stories (View-Only)

| ID | Story | Priority |
|----|-------|----------|
| U1 | See current net positive/negative status | Must Have |
| U2 | View weekly carbon accounting summaries | Must Have |
| U3 | See trend charts over time | Must Have |
| U4 | View energy intensity metrics | Must Have |
| U5 | Run Monte Carlo simulations | Should Have |
| U6 | Compare scenarios (current vs geothermal) | Should Have |

---

## 3. Functional Requirements

### 3.1 Authentication & Authorization

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-AUTH-01 | System shall require username/password login | Must Have |
| FR-AUTH-02 | System shall support two roles: Admin and User | Must Have |
| FR-AUTH-03 | System shall hash passwords using bcrypt | Must Have |
| FR-AUTH-04 | Admins shall be able to create new user accounts | Must Have |
| FR-AUTH-05 | Admins shall be able to deactivate user accounts | Must Have |

### 3.2 Data Import

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-IMP-01 | Import cycle data CSV (Cycle#, Machine, Start Time, ADS/DES/BAG CO2, Energy, Steam) | Must Have |
| FR-IMP-02 | Import energy data CSV (Cycle#, Machine, Boiler, SRV/LRVP, CT, Fans) | Must Have |
| FR-IMP-03 | Validate CSV column headers before import | Must Have |
| FR-IMP-04 | Detect and handle duplicate cycle entries | Must Have |
| FR-IMP-05 | Merge cycle and energy data on Cycle# and Machine | Must Have |
| FR-IMP-06 | Report import results (rows added, skipped, errors) | Must Have |

### 3.3 Manual Data Entry

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-MAN-01 | Admin manually enters weekly liquefied CO₂ (kg) | Must Have |
| FR-MAN-02 | Validate liquefied CO₂ is non-negative | Must Have |
| FR-MAN-03 | Allow notes to be added to weekly entries | Should Have |

### 3.4 Carbon Accounting Calculations

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-CALC-01 | Calculate weekly CO₂ losses at each stage | Must Have |
| FR-CALC-02 | Calculate operational emissions = Energy × Grid EF | Must Have |
| FR-CALC-03 | Calculate embodied emissions using amortized LCA values | Must Have |
| FR-CALC-04 | Calculate Net Removal = Liquefied - Operational - Embodied | Must Have |
| FR-CALC-05 | Determine net positive (>0) or net negative (<0) status | Must Have |
| FR-CALC-06 | Calculate energy intensity (kWh/tCO₂) | Must Have |
| FR-CALC-07 | Separate thermal and auxiliary energy/emissions | Must Have |
| FR-CALC-08 | Amortize infrastructure over 520 weeks (10 years) | Must Have |
| FR-CALC-09 | Amortize sorbent over 156 weeks (3 years) | Must Have |

### 3.5 Reporting & Visualization

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-REP-01 | Dashboard displays: Net Removal, Gross Captured, Total Emissions | Must Have |
| FR-REP-02 | Dashboard displays net positive/negative status indicator | Must Have |
| FR-REP-03 | Dashboard displays weekly trend chart | Must Have |
| FR-REP-04 | Dashboard displays emissions breakdown pie chart | Must Have |
| FR-REP-05 | Dashboard displays weekly summary table | Must Have |
| FR-REP-06 | Reports exportable to Excel format | Should Have |

### 3.6 Monte Carlo Simulations

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-SIM-01 | Simulate geothermal scenario (thermal EF = 0) | Must Have |
| FR-SIM-02 | Run 10,000 iterations per simulation | Should Have |
| FR-SIM-03 | Display probability of net positive under each scenario | Should Have |
| FR-SIM-04 | Compare current vs geothermal scenarios side-by-side | Should Have |

### 3.7 Configuration Management

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-CFG-01 | Admin configures grid emission factor | Must Have |
| FR-CFG-02 | Admin configures geothermal emission factor | Must Have |
| FR-CFG-03 | Store all configuration in database | Must Have |

### 3.8 Embodied Emissions Management

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-EMB-01 | Store infrastructure embodied emissions by zone | Must Have |
| FR-EMB-02 | Store sorbent batch embodied emissions | Must Have |
| FR-EMB-03 | Calculate weekly embodied charges automatically | Must Have |

---

## 4. Non-Functional Requirements

### 4.1 Performance

| Requirement | Target |
|-------------|--------|
| Page load time | < 3 seconds |
| CSV import (1000 rows) | < 10 seconds |
| Monte Carlo (10K iterations) | < 30 seconds |

### 4.2 Security

| Requirement | Target |
|-------------|--------|
| Password storage | bcrypt hashing |
| Data access | Role-based |
| Audit logging | All admin actions |

### 4.3 Scalability

| Requirement | Target |
|-------------|--------|
| Concurrent users | Up to 10 |
| Data retention | 10+ years |
| Database migration | SQLite → PostgreSQL ready |

---

## 5. User Interface Specifications

### 5.1 Navigation Structure

```
SIDEBAR                    MAIN CONTENT
────────                   ────────────
📊 Dashboard               [Selected page content]
📥 Data Entry*             
📈 Reports                 
🎲 Simulations             
⚙️ Configuration*          
👥 User Management*        

* = Admin only
```

### 5.2 Dashboard Layout

```
┌────────────────────────────────────────────────────────────────┐
│  KEY METRICS ROW                                               │
│  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────────────────┐   │
│  │Net CO2 │  │Captured│  │Emissions│  │  NET STATUS       │   │
│  │+245 kg │  │ 520 kg │  │ 275 kg │  │  ● NET POSITIVE   │   │
│  └────────┘  └────────┘  └────────┘  └────────────────────┘   │
│                                                                │
│  CHARTS ROW                                                    │
│  ┌─────────────────────────┐  ┌────────────────────────────┐  │
│  │  Weekly Trend (8 wks)   │  │  Emissions Breakdown       │  │
│  │  [Line chart]           │  │  [Pie chart]               │  │
│  └─────────────────────────┘  └────────────────────────────┘  │
│                                                                │
│  SUMMARY TABLE                                                 │
│  ┌────────────────────────────────────────────────────────┐   │
│  │ Week │ Cycles │ Captured │ Emissions │ Net   │ Status  │   │
│  │  3   │   98   │  520 kg  │  275 kg   │+245kg │ ●Pos    │   │
│  │  2   │   95   │  480 kg  │  290 kg   │+190kg │ ●Pos    │   │
│  └────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────┘
```

### 5.3 Data Entry Page Layout

```
┌────────────────────────────────────────────────────────────────┐
│  STEP 1: IMPORT SCADA DATA                                     │
│  ──────────────────────────                                    │
│  Cycle Data CSV:  [Browse...] [filename.csv]                  │
│  Energy Data CSV: [Browse...] [filename.csv]                  │
│                                                                │
│  [Preview Data]  [Import Data]                                │
│                                                                │
│  Import Results:                                               │
│  • 69 cycles imported                                         │
│  • Date range: Jan 12-16, 2026                               │
├────────────────────────────────────────────────────────────────┤
│  STEP 2: ENTER WEEKLY LIQUEFIED CO₂                           │
│  ────────────────────────────────────                          │
│  Week: [Week 3 ▼]  Year: [2026 ▼]                             │
│  Liquefied CO₂ (kg): [________]                               │
│  Notes: [____________________________________]                 │
│                                                                │
│  [Save & Calculate Weekly Summary]                            │
└────────────────────────────────────────────────────────────────┘
```

### 5.4 Simulations Page Layout

```
┌────────────────────────────────────────────────────────────────┐
│  CONFIGURATION                                                 │
│  ─────────────                                                 │
│  Base Data Period: [Last 4 Weeks ▼]                           │
│  Iterations: [10,000]                                         │
│                                                                │
│  Scenarios:                                                    │
│  [x] Current Operations                                       │
│  [x] Geothermal Steam                                         │
│                                                                │
│  [Run Simulation]                                             │
├────────────────────────────────────────────────────────────────┤
│  RESULTS                                                       │
│  ───────                                                       │
│  ┌──────────────────┐  ┌──────────────────┐                   │
│  │ CURRENT          │  │ GEOTHERMAL       │                   │
│  │ Mean: +180 kg/wk │  │ Mean: +420 kg/wk │                   │
│  │ Prob Positive:78%│  │ Prob Positive:99%│                   │
│  └──────────────────┘  └──────────────────┘                   │
│                                                                │
│  [Histogram comparison chart]                                 │
└────────────────────────────────────────────────────────────────┘
```

### 5.5 Color Scheme

| Element | Color | Hex |
|---------|-------|-----|
| Net Positive | Green | #28A745 |
| Net Negative | Red | #DC3545 |
| Primary | Blue | #007BFF |
| Thermal | Orange | #FD7E14 |
| Auxiliary | Cyan | #17A2B8 |
| Embodied | Purple | #6F42C1 |

---

## 6. Data Requirements

### 6.1 Input Data

| Source | Format | Frequency | Key Fields |
|--------|--------|-----------|------------|
| Cycle Data | CSV | Weekly | Cycle#, Machine, ADS/DES/BAG CO2, Energy, Steam |
| Energy Data | CSV | Weekly | Cycle#, Machine, Boiler, SRV/LRVP, CT, Fans |
| Liquefied CO₂ | Manual | Weekly | Amount (kg) |
| Embodied Infra | Manual | Initial | Zone, Item, Weight, EF |
| Embodied Sorbent | Manual | Per batch | Alumina, PEI, Methanol quantities |

### 6.2 Output Data

| Report | Format | Content |
|--------|--------|---------|
| Weekly Summary | Screen/Excel | All metrics, calculations, status |
| Trend Report | Screen | Historical performance |
| Loss Analysis | Screen | CO₂ losses by stage |
| Simulation Results | Screen | Probability distributions |

---

## 7. Acceptance Criteria

### 7.1 Authentication

- [ ] User can log in with valid credentials
- [ ] User cannot log in with invalid credentials
- [ ] Admin can create new user accounts
- [ ] User role restricts access to admin pages

### 7.2 Data Import

- [ ] Valid cycle CSV imports without errors
- [ ] Valid energy CSV imports without errors
- [ ] Data from both CSVs merges correctly
- [ ] Invalid CSV shows appropriate error message

### 7.3 Calculations

- [ ] Weekly CO₂ aggregation matches manual sum
- [ ] Operational emissions = Energy × 0.049
- [ ] Infrastructure weekly charge = Total / 520
- [ ] Sorbent weekly charge = Total / 156
- [ ] Net removal = Captured - Operational - Embodied
- [ ] Net positive status correct when Net > 0

### 7.4 Dashboard

- [ ] Key metrics display correctly
- [ ] Net status indicator shows correct color
- [ ] Trend chart displays 8 weeks of data
- [ ] Weekly table shows all summary data

### 7.5 Simulations

- [ ] Simulation runs without errors
- [ ] Geothermal scenario shows improved metrics
- [ ] Results display probability of net positive

---

## 8. Implementation Phases

### Phase 1: Core Foundation (Week 1-2)

- Project structure setup
- Database schema implementation
- SQLAlchemy models
- Basic authentication
- Configuration management

### Phase 2: Data Import (Week 2-3)

- CSV parser for cycle data
- CSV parser for energy data
- Data validation
- Import UI
- Merge logic

### Phase 3: Calculations Engine (Week 3-4)

- Aggregation service
- Emissions calculations
- Embodied emissions amortization
- Net removal calculation
- Weekly summary generation

### Phase 4: Dashboard & Reporting (Week 4-5)

- Main dashboard
- Metric cards
- Trend charts
- Emissions breakdown
- Weekly summary table
- Reports page

### Phase 5: Simulations (Week 5-6)

- Monte Carlo engine
- Geothermal scenario
- Results visualization
- Comparison view

### Phase 6: Polish & Testing (Week 6-7)

- User management page
- Audit logging
- Export functionality
- Bug fixes
- Documentation

---

## Appendix: Reference Documents

1. `01_PROJECT_DOCUMENTATION.md` - Company overview, process description
2. `02_CALCULATIONS_AND_FORMULAS.md` - All calculation formulas
3. `03_SYSTEM_ARCHITECTURE.md` - Technical architecture, database schema
4. Puro.earth GSC Methodology 2024 - External reference

---

*End of PRD Document*
