# Octavia Carbon Accounting System (CAS)
## Developer Documentation & Technical Assessment

**Version:** 1.0 (Phase 1)  
**Last Updated:** January 2026  
**Project:** Project Hummingbird - Direct Air Capture (DAC) Pilot Plant  
**Location:** Gilgil, Kenya  
**Organization:** Octavia Carbon  

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Project Background](#2-project-background)
3. [System Architecture](#3-system-architecture)
4. [Directory Structure](#4-directory-structure)
5. [Core Components](#5-core-components)
6. [Database Schema](#6-database-schema)
7. [Configuration Files](#7-configuration-files)
8. [Carbon Accounting Logic](#8-carbon-accounting-logic)
9. [Energy Scenario Analysis](#9-energy-scenario-analysis)
10. [LCA Methodology](#10-lca-methodology)
11. [User Interface](#11-user-interface)
12. [Data Flow](#12-data-flow)
13. [SCADA Integration](#13-scada-integration)
14. [Deployment](#14-deployment)
15. [Future Enhancements](#15-future-enhancements)
16. [Glossary](#16-glossary)

---

## 1. Executive Summary

The Octavia Carbon Accounting System (CAS) is an internal web application designed to track, calculate, and report carbon removal metrics for a Direct Air Capture (DAC) pilot plant. The system calculates whether the plant achieves **net carbon removal** by comparing CO₂ captured against operational and embodied emissions.

### Key Capabilities

| Feature | Description |
|---------|-------------|
| **Weekly Data Entry** | Input SCADA readings for CO₂ flow and energy consumption |
| **Automated Calculations** | Compute net removal, emissions, and efficiency metrics |
| **Dashboard Visualization** | Real-time charts and KPIs for carbon balance monitoring |
| **LCA Integration** | Amortized embodied emissions from Life Cycle Assessment |
| **Scenario Analysis** | Compare current grid vs. future geothermal operations |
| **Report Generation** | Export data for Puro.earth carbon credit certification |

### Technology Stack

- **Backend:** Python 3.8+
- **Web Framework:** Streamlit
- **Database:** SQLite (Phase 1), PostgreSQL-ready (Phase 2)
- **Data Processing:** Pandas, NumPy
- **Visualization:** Altair
- **Authentication:** streamlit-authenticator

---

## 2. Project Background

### What is Direct Air Capture (DAC)?

Direct Air Capture is a technology that extracts CO₂ directly from ambient air. The captured CO₂ can be permanently stored underground or used in industrial processes. When the CO₂ is permanently stored, it creates **carbon dioxide removal (CDR)** credits.

### Octavia Carbon's Process Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  ADSORPTION │ ──▶ │  DESORPTION │ ──▶ │  COLLECTION │ ──▶ │ LIQUEFACTION│
│             │     │             │     │  (Balloon)  │     │             │
│ Air passes  │     │ Heat applied│     │ CO₂ stored  │     │ CO₂ cooled  │
│ through     │     │ to release  │     │ in gas      │     │ to liquid   │
│ sorbent     │     │ CO₂         │     │ balloon     │     │ state       │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
      │                   │                   │                   │
      ▼                   ▼                   ▼                   ▼
 CO₂ Adsorbed        CO₂ Desorbed        BAG CO₂           CO₂ Liquefied
   (SCADA)             (SCADA)            (SCADA)          (Load Cell)
```

### Plant Configuration (Phase 1)

| Parameter | Value |
|-----------|-------|
| Plant Name | Project Hummingbird Phase 1 |
| Location | Gilgil, Kenya |
| Target Capacity | 100 tonnes CO₂/year |
| Modules | 4 reactors (Nelion 1n3, 2n4) |
| Monoliths | 352 total (88 per module) |
| Plant Lifetime | 10 years |
| Sorbent Batch Life | 3 years |

### Why Carbon Accounting Matters

To sell carbon credits (CORCs - CO₂ Removal Certificates), Octavia must prove **net carbon negativity**:

```
Net Carbon Removal = CO₂ Captured − (Operational Emissions + Embodied Emissions)
```

If this value is **positive**, the plant is removing more CO₂ than it emits. This is what the CAS tracks and reports.

---

## 3. System Architecture

### High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           USER INTERFACE (Streamlit)                      │
├──────────────┬──────────────┬──────────────┬──────────────┬──────────────┤
│   Home.py    │  Dashboard   │  Data Entry  │   Reports    │   Scenarios  │
│   (Login)    │   (KPIs)     │  (Admin)     │   (Export)   │  (Analysis)  │
└──────────────┴──────────────┴──────────────┴──────────────┴──────────────┘
                                     │
                                     ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                           APPLICATION LAYER (src/)                        │
├──────────────┬──────────────┬──────────────┬──────────────────────────────┤
│    auth.py   │ database.py  │calculations.py│         utils.py            │
│ (Login/RBAC) │ (SQLite ORM) │ (Formulas)   │    (Helpers)                │
└──────────────┴──────────────┴──────────────┴──────────────────────────────┘
                                     │
                                     ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                              DATA LAYER                                   │
├─────────────────────────────────┬────────────────────────────────────────┤
│    SQLite Database              │       Configuration (YAML)              │
│    (data/octavia_cas.db)        │       (config/lca_config.yaml)          │
└─────────────────────────────────┴────────────────────────────────────────┘
```

### Component Responsibilities

| Component | File | Responsibility |
|-----------|------|----------------|
| **Authentication** | `src/auth.py` | User login, session management, role-based access |
| **Database** | `src/database.py` | CRUD operations, schema management, queries |
| **Calculations** | `src/calculations.py` | Carbon accounting formulas, scenario comparison |
| **Utilities** | `src/utils.py` | Date helpers, formatting, common functions |
| **Configuration** | `config/lca_config.yaml` | LCA parameters, emission factors, scenarios |

---

## 4. Directory Structure

```
octavia-cas/
│
├── Home.py                          # Main entry point (login page)
│
├── pages/                           # Streamlit multi-page app
│   ├── 1_📊_Dashboard.py            # KPIs and trend charts
│   ├── 2_📝_Data_Entry.py           # Weekly data input (admin only)
│   ├── 3_📈_Reports.py              # Export and analysis
│   ├── 4_⚙️_Admin.py                # User management, settings
│   └── 5_🔋_Energy_Scenarios.py     # Grid vs geothermal comparison
│
├── src/                             # Application logic
│   ├── __init__.py
│   ├── auth.py                      # Authentication & authorization
│   ├── database.py                  # Database operations
│   ├── calculations.py              # Carbon accounting formulas
│   └── utils.py                     # Helper functions
│
├── config/                          # Configuration files
│   ├── lca_config.yaml              # LCA parameters & emission factors
│   └── users.yaml                   # User credentials (hashed)
│
├── data/                            # Data storage
│   └── octavia_cas.db               # SQLite database
│
├── docs/                            # Documentation
│   ├── DATABASE_SETUP_GUIDE.md      # Database initialization guide
│   └── DEVELOPER_GUIDE.md           # This document
│
├── requirements.txt                 # Python dependencies
├── .env                             # Environment variables (not in git)
├── .gitignore                       # Git ignore rules
└── README.md                        # Project readme
```

---

## 5. Core Components

### 5.1 Authentication (`src/auth.py`)

The authentication system provides:
- **Login/Logout:** Session-based authentication
- **Role-Based Access Control (RBAC):** Admin vs. Viewer roles
- **Password Hashing:** Secure credential storage

```python
# Key functions
def require_auth() -> Optional[Dict]:
    """Check if user is authenticated, return user info or None."""
    
def is_admin(user_info: Dict) -> bool:
    """Check if user has admin privileges."""
    
def login_form():
    """Render login form widget."""
```

**User Roles:**

| Role | Permissions |
|------|-------------|
| **Admin** | Enter data, view dashboard, manage users, export reports |
| **Viewer** | View dashboard, view reports (read-only) |

### 5.2 Database (`src/database.py`)

SQLite database with SQLAlchemy-ready structure for future PostgreSQL migration.

```python
# Key functions
def init_database():
    """Create tables if they don't exist."""
    
def save_weekly_entry(week_start, week_end, co2_adsorbed_kg, ...):
    """Insert or update weekly SCADA data."""
    
def save_weekly_results(week_start, net_co2_retained_kg, ...):
    """Save calculated results for a week."""
    
def get_combined_data() -> pd.DataFrame:
    """Get all entries joined with results for dashboard."""
    
def get_summary_stats() -> Dict:
    """Calculate aggregate statistics for KPIs."""
```

### 5.3 Calculations (`src/calculations.py`)

The core carbon accounting engine implementing all formulas.

```python
# Data classes
@dataclass
class WeeklyInputs:
    co2_adsorbed_kg: float
    co2_desorbed_kg: float
    co2_collected_kg: float
    electricity_kwh: float
    boiler_kwh: Optional[float] = None      # Component tracking
    fans_kwh: Optional[float] = None
    other_kwh: Optional[float] = None

@dataclass
class WeeklyResults:
    net_co2_retained_kg: float
    co2_lost_kg: float
    operational_emissions_kg: float
    embodied_emissions_kg: float
    internal_net_removal_kg: float
    is_net_negative: bool
    # ... additional fields

@dataclass
class ScenarioComparison:
    current_operational_emissions_kg: float
    geothermal_operational_emissions_kg: float
    emissions_reduction_kg: float
    # ... comparison metrics

# Key functions
def calculate_weekly(inputs: WeeklyInputs, config: Dict, scenario: str) -> WeeklyResults:
    """Calculate all weekly carbon metrics."""

def calculate_scenario_comparison(inputs: WeeklyInputs, config: Dict) -> ScenarioComparison:
    """Compare current grid vs geothermal scenarios."""

def validate_inputs(inputs: WeeklyInputs) -> Dict[str, str]:
    """Validate input data, return errors if any."""
```

### 5.4 Utilities (`src/utils.py`)

Helper functions used across the application.

```python
def get_week_dates(date: date) -> Tuple[date, date]:
    """Get Monday-Sunday bounds for any date."""

def format_week_label(week_start: date) -> str:
    """Format date as 'Jan 15 - Jan 21, 2026'."""

def status_color(is_net_negative: bool) -> str:
    """Return green/red color code based on status."""

def status_text(is_net_negative: bool) -> str:
    """Return 'Net Removal' or 'Net Emitter'."""
```

---

## 6. Database Schema

### Entity Relationship Diagram

```
┌─────────────────────────┐       ┌─────────────────────────┐
│     weekly_entries      │       │     weekly_results      │
├─────────────────────────┤       ├─────────────────────────┤
│ id (PK)                 │       │ id (PK)                 │
│ week_start (UNIQUE)     │◄─────►│ week_start (FK)         │
│ week_end                │       │ net_co2_retained_kg     │
│ co2_adsorbed_kg         │       │ co2_lost_kg             │
│ co2_desorbed_kg         │       │ operational_emissions_kg│
│ co2_collected_kg        │       │ embodied_emissions_kg   │
│ electricity_kwh         │       │ internal_net_removal_kg │
│ boiler_kwh              │       │ is_net_negative         │
│ fans_kwh                │       │ calculated_at           │
│ other_kwh               │       └─────────────────────────┘
│ notes                   │
│ created_by              │       ┌─────────────────────────┐
│ created_at              │       │        config           │
│ updated_at              │       ├─────────────────────────┤
└─────────────────────────┘       │ id (PK)                 │
                                  │ key (UNIQUE)            │
┌─────────────────────────┐       │ value                   │
│       audit_log         │       │ updated_at              │
├─────────────────────────┤       │ updated_by              │
│ id (PK)                 │       └─────────────────────────┘
│ timestamp               │
│ user                    │
│ action                  │
│ table_name              │
│ record_id               │
│ details                 │
└─────────────────────────┘
```

### Table Definitions

#### `weekly_entries`
Stores raw SCADA input data entered by admin.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key, auto-increment |
| `week_start` | DATE | Monday of the week (unique) |
| `week_end` | DATE | Sunday of the week |
| `co2_adsorbed_kg` | REAL | Total CO₂ captured by sorbent |
| `co2_desorbed_kg` | REAL | Total CO₂ released by heating |
| `co2_collected_kg` | REAL | Total CO₂ liquefied and stored |
| `electricity_kwh` | REAL | Total electricity consumed |
| `boiler_kwh` | REAL | Boiler energy (optional) |
| `fans_kwh` | REAL | Fans energy (optional) |
| `other_kwh` | REAL | Other equipment energy (optional) |
| `notes` | TEXT | Admin notes for the week |
| `created_by` | TEXT | Username who entered data |
| `created_at` | TIMESTAMP | Record creation time |
| `updated_at` | TIMESTAMP | Last modification time |

#### `weekly_results`
Stores calculated results from the carbon accounting formulas.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key, auto-increment |
| `week_start` | DATE | Foreign key to weekly_entries |
| `net_co2_retained_kg` | REAL | CO₂ successfully stored |
| `co2_lost_kg` | REAL | CO₂ lost in process |
| `operational_emissions_kg` | REAL | Emissions from electricity |
| `embodied_emissions_kg` | REAL | Amortized LCA emissions |
| `internal_net_removal_kg` | REAL | Net carbon removed |
| `is_net_negative` | BOOLEAN | True if net removal > 0 |
| `calculated_at` | TIMESTAMP | Calculation timestamp |

---

## 7. Configuration Files

### 7.1 LCA Configuration (`config/lca_config.yaml`)

This file contains all Life Cycle Assessment parameters, emission factors, and scenario definitions.

```yaml
# Plant Parameters
plant:
  name: "Project Hummingbird Phase 1"
  location: "Gilgil, Kenya"
  lifetime_years: 10
  lifetime_weeks: 520
  annual_design_capacity_kg: 100000

# Sorbent System Parameters
sorbent:
  batch_lifetime_years: 3
  batch_lifetime_weeks: 156
  alumina_kg_per_batch: 880
  pei_kg_per_batch: 880
  methanol_kg_per_batch: 1000

# Energy Scenarios
energy_scenarios:
  current:
    name: "Grid Electricity"
    grid_ef_kg_per_kwh: 0.049
    thermal_ef_kg_per_kwh: 0.049
    source: "Kenya Power & Lighting 2024"
  
  geothermal:
    name: "Geothermal Steam"
    grid_ef_kg_per_kwh: 0.049
    thermal_ef_kg_per_kwh: 0.008
    source: "Kenya Geothermal (Olkaria) - IPCC 2023"

# Emission Factors
emission_factors:
  grid_electricity_kg_per_kwh: 0.049
  geothermal_steam_kg_per_kwh: 0.008
  # ... material factors

# Weekly Embodied Charges (kg CO₂/week)
weekly_embodied_charges:
  infrastructure: 49.87
  material_transport: 0.95
  sorbent_system: 94.66
  total: 145.48

# Energy Component Breakdown
energy_components:
  boiler:
    typical_percentage: 70.8
    affected_by_geothermal: true
  fans:
    typical_percentage: 22.8
    affected_by_geothermal: false
  # ... other components
```

### 7.2 Users Configuration (`config/users.yaml`)

```yaml
credentials:
  usernames:
    admin:
      name: Admin User
      password: <hashed_password>
      role: admin
    viewer:
      name: Viewer User
      password: <hashed_password>
      role: viewer
```

---

## 8. Carbon Accounting Logic

### 8.1 Core Formulas

The system implements four key carbon accounting metrics:

#### Formula 1: Net CO₂ Retained
```
Net CO₂ Retained = CO₂ Collected (Liquefied)
```
This is the CO₂ that has been successfully captured, liquefied, and is ready for permanent storage.

#### Formula 2: CO₂ Lost
```
CO₂ Lost = CO₂ Adsorbed − CO₂ Collected
```
The difference between what was captured from air and what was successfully stored.

#### Formula 3: Operational Emissions
```
Operational Emissions = Electricity (kWh) × Grid EF (kg CO₂/kWh)
```
For the current scenario with grid electricity:
```
= 5000 kWh × 0.049 kg CO₂/kWh
= 245 kg CO₂
```

With component-level tracking (for geothermal scenario):
```
Operational Emissions = (Boiler kWh × Thermal EF) + (Other kWh × Grid EF)
```

#### Formula 4: Internal Net Removal
```
Internal Net Removal = Net CO₂ Retained − (Operational Emissions + Embodied Emissions)
```

**Interpretation:**
- **Positive value** → Net carbon removal (plant is carbon negative) ✓
- **Negative value** → Net carbon emitter (plant emits more than it captures) ✗

### 8.2 Embodied Emissions Calculation

Embodied emissions are amortized weekly charges from the Life Cycle Assessment:

```
Weekly Embodied = (Infrastructure / Plant Weeks) + (Sorbent / Batch Weeks)
```

For Phase 1:
```
Infrastructure: 25,932.5 kg CO₂ / 520 weeks = 49.87 kg/week
Transport:         492.4 kg CO₂ / 520 weeks =  0.95 kg/week
Sorbent:        14,767.6 kg CO₂ / 156 weeks = 94.66 kg/week
─────────────────────────────────────────────────────────────
TOTAL:                                        145.48 kg/week
```

### 8.3 Efficiency Metrics

```python
# Capture Efficiency: How much adsorbed CO₂ was desorbed?
capture_efficiency = (CO₂_desorbed / CO₂_adsorbed) × 100

# Collection Efficiency: How much desorbed CO₂ was collected?
collection_efficiency = (CO₂_collected / CO₂_desorbed) × 100

# Overall Efficiency: End-to-end process efficiency
overall_efficiency = (CO₂_collected / CO₂_adsorbed) × 100
```

---

## 9. Energy Scenario Analysis

### 9.1 Why Geothermal Matters

The boiler accounts for **70.8%** of total energy consumption. By switching from grid electricity to geothermal steam, operational emissions can be dramatically reduced.

| Energy Source | Emission Factor | Reduction |
|--------------|-----------------|-----------|
| Kenya Grid | 0.049 kg CO₂/kWh | Baseline |
| Geothermal Steam | 0.008 kg CO₂/kWh | **84%** lower |

### 9.2 Scenario Calculation Logic

```python
def calculate_scenario_comparison(inputs, config):
    # Split energy by component
    boiler_fraction = 0.708  # 70.8%
    boiler_kwh = inputs.electricity_kwh * boiler_fraction
    other_kwh = inputs.electricity_kwh * (1 - boiler_fraction)
    
    # Current scenario (all grid)
    current_emissions = inputs.electricity_kwh * 0.049
    
    # Geothermal scenario (boiler uses geothermal, rest uses grid)
    geo_emissions = (boiler_kwh * 0.008) + (other_kwh * 0.049)
    
    # Improvement
    reduction = current_emissions - geo_emissions
    reduction_percent = (reduction / current_emissions) * 100
```

### 9.3 Example Comparison

With 5,000 kWh weekly consumption:

| Metric | Current (Grid) | Geothermal | Improvement |
|--------|---------------|------------|-------------|
| Boiler Emissions | 173.5 kg | 28.3 kg | -145.2 kg |
| Other Emissions | 71.5 kg | 71.5 kg | 0 kg |
| **Total Operational** | **245.0 kg** | **99.8 kg** | **-145.2 kg** |
| Embodied | 145.5 kg | 145.5 kg | 0 kg |
| **Total Emissions** | **390.5 kg** | **245.3 kg** | **-145.2 kg** |

---

## 10. LCA Methodology

### 10.1 System Boundary

The LCA covers **cradle-to-gate** emissions for the capture facility:

**INCLUDED:**
- Infrastructure materials (steel, concrete, equipment)
- Equipment manufacturing and transport
- Sorbent materials (alumina, PEI, methanol)
- Operational electricity consumption
- End-of-life disposal

**EXCLUDED:**
- CO₂ transport to storage site
- CO₂ injection and storage
- Office buildings and amenities

### 10.2 Phase 1 Equipment Inventory

#### Zone 1: Capture Modules (Container)
| Component | Material | Weight (kg) | EF (kg CO₂/kg) | Embodied (kg CO₂) |
|-----------|----------|-------------|----------------|-------------------|
| Container | Mild Steel | 2,200 | 2.4 | 5,280 |
| Module frames | Stainless Steel | 14 | 7.14 | 100 |
| Fans (×4) | Mixed | 100 | 3.5 | 350 |
| Boiler | Mild Steel | 500 | 2.4 | 1,200 |
| **Zone 1 Total** | | | | **8,279 kg CO₂** |

#### Zone 2: Processing (Tent Structure)
| Component | Material | Weight (kg) | EF (kg CO₂/kg) | Embodied (kg CO₂) |
|-----------|----------|-------------|----------------|-------------------|
| Tent frame | Mild Steel | 1,300 | 2.4 | 3,120 |
| PHE | Stainless Steel | 80 | 7.14 | 571 |
| Vacuum Pump | Mixed | 150 | 3.5 | 525 |
| **Zone 2 Total** | | | | **6,033 kg CO₂** |

#### Zone 3: Liquefaction
| Component | Material | Weight (kg) | EF (kg CO₂/kg) | Embodied (kg CO₂) |
|-----------|----------|-------------|----------------|-------------------|
| Cryogenic Tank | Stainless Steel | 1,000 | 7.14 | 7,140 |
| Liquefaction Unit | Mixed | 400 | 4.0 | 1,600 |
| **Zone 3 Total** | | | | **11,128 kg CO₂** |

### 10.3 Sorbent System

| Material | Qty/Batch (kg) | EF (kg CO₂/kg) | Embodied (kg CO₂) |
|----------|----------------|----------------|-------------------|
| Alumina | 880 | 1.91 | 1,681 |
| PEI | 880 | 11.05 | 9,724 |
| Methanol | 1,000 | 0.92 | 920 |
| EOL Processing | — | — | 2,443 |
| **Sorbent Total** | | | **14,768 kg CO₂** |

### 10.4 Amortization

| Category | Total (kg CO₂) | Period (weeks) | Weekly (kg CO₂/week) |
|----------|----------------|----------------|---------------------|
| Infrastructure | 25,933 | 520 | 49.87 |
| Transport | 492 | 520 | 0.95 |
| Sorbent | 14,768 | 156 | 94.66 |
| **TOTAL** | | | **145.48** |

---

## 11. User Interface

### 11.1 Page Structure

#### Home (`Home.py`)
- Login form
- Company branding
- Quick navigation after login

#### Dashboard (`pages/1_📊_Dashboard.py`)
- Key Performance Indicators (KPIs)
- Net removal status indicator
- Historical trend charts
- Scenario comparison snapshot
- LCA parameters reference

#### Data Entry (`pages/2_📝_Data_Entry.py`)
- Week selector
- CO₂ flow inputs (adsorbed, desorbed, collected)
- Energy consumption inputs (total, optional component breakdown)
- Notes field
- Validation feedback
- Calculated results preview

#### Reports (`pages/3_📈_Reports.py`)
- Date range selection
- Data export (CSV, Excel)
- Cumulative statistics
- Puro.earth format export

#### Admin (`pages/4_⚙️_Admin.py`)
- User management
- Configuration editor
- Audit log viewer
- Database maintenance

#### Energy Scenarios (`pages/5_🔋_Energy_Scenarios.py`)
- Interactive scenario calculator
- Grid vs geothermal comparison
- Visual charts
- Historical "what-if" analysis

### 11.2 UI Design Principles

- **Color Coding:**
  - 🟢 Green: Net removal (positive outcome)
  - 🔴 Red: Net emitter (needs attention)
  - 🔵 Blue: Input fields, data entry
  - 🟠 Orange: Energy/scenario analysis

- **Layout:**
  - Wide layout for dashboards
  - Centered layout for data entry
  - Consistent header styling per page

---

## 12. Data Flow

### 12.1 Weekly Data Entry Flow

```
┌─────────────────┐
│  Admin enters   │
│  weekly SCADA   │
│  data           │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  validate_inputs│
│  ()             │
└────────┬────────┘
         │
    ┌────┴────┐
    │ Valid?  │
    └────┬────┘
         │
    Yes  │  No
    ┌────┘  └────┐
    ▼            ▼
┌─────────┐  ┌─────────┐
│save_    │  │Show     │
│weekly_  │  │error    │
│entry()  │  │messages │
└────┬────┘  └─────────┘
     │
     ▼
┌─────────────────┐
│calculate_weekly │
│()               │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│save_weekly_     │
│results()        │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│Display results  │
│& confirmation   │
└─────────────────┘
```

### 12.2 Dashboard Data Flow

```
┌─────────────────┐
│  User opens     │
│  dashboard      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│get_combined_data│
│()               │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│get_summary_stats│
│()               │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│load_lca_config  │
│()               │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│Render KPIs,     │
│charts, tables   │
└─────────────────┘
```

---

## 13. SCADA Integration

### 13.1 Current Data Sources

The plant's SCADA system produces CSV files with cycle-level data:

#### Plant Cycles Data (`plant_cycles_YYYY-MM-DD.csv`)
```csv
Cycle #,Machine,Start Time,End Time,ADS CO2,DES CO2,BAG CO2,eTotal kWh,Steam (kg),DES n
1,Module 1n3,2026-01-12 00:15,2026-01-12 02:30,3.82,2.15,1.95,89.2,85.6,56.3
```

| Column | Description | Unit |
|--------|-------------|------|
| ADS CO2 | CO₂ adsorbed | kg |
| DES CO2 | CO₂ desorbed | kg |
| BAG CO2 | CO₂ in gas balloon | kg |
| eTotal kWh | Energy consumed | kWh |
| Steam (kg) | Steam used | kg |
| DES n | Desorption efficiency | % |

#### Cycle Energy Data (`cycle_energy_YYYY-MM-DD.csv`)
```csv
Cycle #,NM1 kWh,NM2 kWh,NM3 kWh,NM4 kWh,Boiler kWh,SRV kWh,LRVP kWh,CT kWh,Total kWh
1,3.2,3.1,3.3,3.0,63.5,2.8,1.9,1.2,89.2
```

### 13.2 Data Aggregation

Currently, weekly totals are calculated manually from SCADA CSVs and entered into the CAS. Future enhancement: automated CSV upload and aggregation.

```python
# Example aggregation logic
weekly_totals = df.groupby(df['Start Time'].dt.isocalendar().week).agg({
    'ADS CO2': 'sum',
    'DES CO2': 'sum',
    'BAG CO2': 'sum',
    'eTotal kWh': 'sum'
})
```

### 13.3 Liquefaction Tracking

The load cell on the cryogenic tank measures liquefied CO₂ but is not yet integrated into SCADA. Currently entered manually as "CO₂ Collected" in the CAS.

---

## 14. Deployment

### 14.1 Local Development

```bash
# Clone repository
git clone https://github.com/octavia-carbon/octavia-cas.git
cd octavia-cas

# Create virtual environment
python -m venv cas_env
source cas_env/bin/activate  # Linux/Mac
# or: cas_env\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Initialize database
python init_db.py

# Run application
streamlit run Home.py
```

### 14.2 Streamlit Community Cloud

For multi-user access, deploy to Streamlit Community Cloud:

1. Push code to GitHub
2. Connect repository to share.streamlit.io
3. Configure secrets for sensitive data
4. Deploy

### 14.3 Future: PostgreSQL Migration

For Phase 2 cloud deployment, migrate from SQLite to PostgreSQL:

1. Update `DATABASE_URL` in environment
2. Run schema migration scripts
3. Transfer data using pandas
4. Update connection in `database.py`

---

## 15. Future Enhancements

### Phase 2 Roadmap

| Feature | Priority | Description |
|---------|----------|-------------|
| **CSV Upload** | High | Direct SCADA CSV upload instead of manual entry |
| **API Integration** | High | Real-time SCADA data feed |
| **Load Cell Integration** | High | Automatic liquefaction tracking |
| **PostgreSQL Migration** | Medium | Cloud-ready database |
| **Multi-Plant Support** | Medium | Track multiple DAC sites |
| **Puro API Integration** | Medium | Automated credit submission |
| **Mobile App** | Low | Field data entry |

### Suggested Code Improvements

1. **Add unit tests** for calculation functions
2. **Implement logging** for audit trail
3. **Add data backup** functionality
4. **Create API endpoints** for external integrations
5. **Add email notifications** for weekly summaries

---

## 16. Glossary

| Term | Definition |
|------|------------|
| **ADS CO₂** | CO₂ adsorbed from air by the sorbent material |
| **BAG CO₂** | CO₂ collected in the gas balloon before liquefaction |
| **CORC** | CO₂ Removal Certificate - tradeable carbon credit |
| **DAC** | Direct Air Capture - technology to capture CO₂ from ambient air |
| **DES CO₂** | CO₂ desorbed (released) from sorbent by heating |
| **DES n** | Desorption efficiency percentage |
| **EF** | Emission Factor - kg CO₂ emitted per unit of activity |
| **Embodied Emissions** | Emissions from manufacturing equipment and materials |
| **Grid EF** | Emission factor for grid electricity (kg CO₂/kWh) |
| **LCA** | Life Cycle Assessment - analysis of environmental impacts |
| **LCI** | Life Cycle Inventory - data collection phase of LCA |
| **Monolith** | Sorbent structure unit (88 per module) |
| **MRV** | Monitoring, Reporting, and Verification |
| **Net Negative** | State where CO₂ removal exceeds emissions |
| **Operational Emissions** | Emissions from electricity consumption |
| **PEI** | Polyethyleneimine - active sorbent material |
| **PHE** | Plate Heat Exchanger - cooling system component |
| **Puro.earth** | Carbon credit registry and standard |
| **SCADA** | Supervisory Control and Data Acquisition |
| **SRV/LRVP** | Valves and liquid ring vacuum pumps |
| **Thermal EF** | Emission factor for thermal energy (steam/heat) |

---

## Appendix A: Quick Reference

### Key File Locations

| File | Purpose |
|------|---------|
| `Home.py` | Application entry point |
| `config/lca_config.yaml` | All configurable parameters |
| `src/calculations.py` | Carbon accounting formulas |
| `data/octavia_cas.db` | SQLite database |

### Key Configuration Values (Phase 1)

| Parameter | Value |
|-----------|-------|
| Plant Lifetime | 10 years (520 weeks) |
| Sorbent Batch Life | 3 years (156 weeks) |
| Grid EF | 0.049 kg CO₂/kWh |
| Geothermal EF | 0.008 kg CO₂/kWh |
| Weekly Embodied | 145.48 kg CO₂/week |
| Target Capacity | 100 tCO₂/year |

### Key Formulas

```
Net CO₂ Retained = CO₂ Collected

CO₂ Lost = CO₂ Adsorbed − CO₂ Collected

Operational Emissions = Electricity × Grid EF

Internal Net Removal = Net CO₂ Retained − (Operational + Embodied)
```

---

**Document Version:** 1.0  
**Last Updated:** January 22, 2026  
**Author:** Octavia Carbon Engineering Team  
**Contact:** engineering@octaviacarbon.com
