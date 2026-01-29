# Octavia Carbon Accounting System (CAS)
## System Architecture

**Version:** 1.0  
**Date:** January 2026  

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Technology Stack](#2-technology-stack)
3. [Database Design](#3-database-design)
4. [Application Structure](#4-application-structure)
5. [Authentication & Authorization](#5-authentication--authorization)
6. [Data Flow Architecture](#6-data-flow-architecture)
7. [Configuration Management](#7-configuration-management)
8. [Scalability Considerations](#8-scalability-considerations)

---

## 1. Architecture Overview

### 1.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        OCTAVIA CARBON ACCOUNTING SYSTEM                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐     │
│  │   PRESENTATION  │    │    BUSINESS     │    │      DATA       │     │
│  │      LAYER      │◄───│     LAYER       │◄───│      LAYER      │     │
│  │                 │    │                 │    │                 │     │
│  │  • Streamlit UI │    │ • Calculations  │    │  • SQLite DB    │     │
│  │  • Dashboards   │    │ • Validation    │    │  • CSV Import   │     │
│  │  • Reports      │    │ • Aggregation   │    │  • Data Models  │     │
│  │  • Data Entry   │    │ • Simulations   │    │                 │     │
│  └─────────────────┘    └─────────────────┘    └─────────────────┘     │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Design Principles

1. **Separation of Concerns**: Clear boundaries between UI, business logic, and data
2. **Single Source of Truth**: SQLite database as the authoritative data store
3. **Scalability Ready**: Architecture supports migration to PostgreSQL
4. **Audit Trail**: All data changes are logged with timestamps
5. **Modular Design**: Components can be updated independently

---

## 2. Technology Stack

### 2.1 Core Technologies

| Component | Technology | Version | Purpose |
|-----------|------------|---------|---------|
| **Frontend** | Streamlit | 1.28+ | Web UI framework |
| **Backend** | Python | 3.10+ | Application logic |
| **Database** | SQLite | 3.x | Data persistence |
| **ORM** | SQLAlchemy | 2.0+ | Database abstraction |
| **Charts** | Plotly | 5.x | Interactive visualizations |
| **Data Processing** | Pandas | 2.x | Data manipulation |
| **Statistics** | NumPy/SciPy | Latest | Monte Carlo simulations |
| **Authentication** | streamlit-authenticator | 0.3+ | User auth |

### 2.2 Python Dependencies

```
# requirements.txt

# Core Framework
streamlit>=1.28.0
streamlit-authenticator>=0.3.0

# Database
sqlalchemy>=2.0.0
alembic>=1.12.0

# Data Processing
pandas>=2.0.0
numpy>=1.24.0
scipy>=1.11.0

# Visualization
plotly>=5.17.0

# Utilities
python-dateutil>=2.8.2
bcrypt>=4.0.0
pyyaml>=6.0.0
python-dotenv>=1.0.0

# Export
openpyxl>=3.1.0
```

### 2.3 Directory Structure

```
octavia-cas/
├── app/
│   ├── __init__.py
│   ├── main.py                 # Streamlit entry point
│   ├── config.py               # Configuration management
│   │
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── authentication.py   # Login/logout logic
│   │   └── authorization.py    # Role-based access
│   │
│   ├── database/
│   │   ├── __init__.py
│   │   ├── connection.py       # DB connection management
│   │   ├── models.py           # SQLAlchemy models
│   │   └── migrations/         # Alembic migrations
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── calculations.py     # Carbon accounting formulas
│   │   ├── data_import.py      # CSV import logic
│   │   ├── aggregation.py      # Weekly/monthly rollups
│   │   ├── simulation.py       # Monte Carlo simulations
│   │   └── export.py           # Report generation
│   │
│   ├── pages/
│   │   ├── __init__.py
│   │   ├── 1_dashboard.py      # Main dashboard
│   │   ├── 2_data_entry.py     # Data import/entry
│   │   ├── 3_reports.py        # Detailed reports
│   │   ├── 4_simulations.py    # Monte Carlo
│   │   ├── 5_configuration.py  # System config
│   │   └── 6_admin.py          # User management
│   │
│   └── components/
│       ├── __init__.py
│       ├── charts.py           # Reusable chart components
│       ├── tables.py           # Data table components
│       └── forms.py            # Input form components
│
├── data/
│   ├── octavia.db              # SQLite database
│   └── uploads/                # CSV upload staging
│
├── config/
│   ├── settings.yaml           # Application settings
│   └── emission_factors.yaml   # EF configuration
│
├── tests/
│   ├── __init__.py
│   ├── test_calculations.py
│   ├── test_import.py
│   └── test_aggregation.py
│
├── requirements.txt
├── README.md
└── .env.example
```

---

## 3. Database Design

### 3.1 Database Schema (SQLite)

```sql
-- Users table for authentication
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    email TEXT UNIQUE,
    full_name TEXT,
    role TEXT NOT NULL CHECK (role IN ('admin', 'user')),
    is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP,
    created_by INTEGER REFERENCES users(id)
);

-- Cycle data from SCADA (raw import)
CREATE TABLE cycle_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    weekly_summary_id INTEGER REFERENCES weekly_summary(id),
    cycle_number INTEGER NOT NULL,
    machine TEXT NOT NULL,
    start_time TIMESTAMP NOT NULL,
    
    -- CO2 measurements (kg)
    ads_co2_kg REAL,
    ads_hours REAL,
    des_co2_kg REAL,
    des_hours REAL,
    bag_co2_kg REAL,
    
    -- Energy measurements (kWh)
    total_kwh REAL,
    boiler_kwh REAL,
    srv_lrvp_kwh REAL,
    ct_kwh REAL,
    nm1_fan_kwh REAL,
    nm2_fan_kwh REAL,
    nm3_fan_kwh REAL,
    nm4_fan_kwh REAL,
    
    -- Steam (kg)
    steam_kg REAL,
    
    -- Derived metrics
    des_n REAL,
    vol_capacity REAL,
    
    -- Metadata
    import_batch_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(cycle_number, machine)
);

-- Weekly summary (aggregated from cycles + manual entry)
CREATE TABLE weekly_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INTEGER NOT NULL,
    week_number INTEGER NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    
    -- CO2 flows (kg)
    total_ads_co2_kg REAL,
    total_des_co2_kg REAL,
    total_bag_co2_kg REAL,
    liquefied_co2_kg REAL,  -- Manual entry
    
    -- Calculated losses (kg)
    loss_stage_1_kg REAL,
    loss_stage_2_kg REAL,
    loss_stage_3_kg REAL,
    total_loss_kg REAL,
    
    -- Energy (kWh)
    thermal_energy_kwh REAL,
    auxiliary_energy_kwh REAL,
    total_energy_kwh REAL,
    
    -- Steam (kg)
    total_steam_kg REAL,
    
    -- Operational emissions (kg CO2)
    thermal_emissions_kg REAL,
    auxiliary_emissions_kg REAL,
    total_operational_emissions_kg REAL,
    
    -- Embodied emissions (kg CO2)
    infrastructure_embodied_kg REAL,
    sorbent_embodied_kg REAL,
    total_embodied_emissions_kg REAL,
    
    -- Net calculation (kg CO2)
    gross_captured_kg REAL,
    total_emissions_kg REAL,
    net_removal_kg REAL,
    
    -- Status
    is_net_positive BOOLEAN,
    
    -- Efficiency metrics
    energy_intensity_kwh_per_tonne REAL,
    total_cycles INTEGER,
    
    -- Metadata
    notes TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    
    UNIQUE(year, week_number)
);

-- Infrastructure embodied emissions (from LCA)
CREATE TABLE embodied_infrastructure (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    zone TEXT NOT NULL,
    item TEXT NOT NULL,
    material_type TEXT,
    quantity REAL,
    unit TEXT,
    weight_kg REAL,
    emission_factor REAL,
    embodied_co2_kg REAL,
    lifetime_years INTEGER DEFAULT 10,
    weekly_charge_kg REAL,
    notes TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by INTEGER REFERENCES users(id)
);

-- Sorbent batch tracking
CREATE TABLE embodied_sorbent (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_number INTEGER NOT NULL UNIQUE,
    start_date DATE NOT NULL,
    end_date DATE,
    alumina_kg REAL,
    pei_kg REAL,
    methanol_kg REAL,
    production_embodied_kg REAL,
    eol_embodied_kg REAL,
    total_embodied_kg REAL,
    lifetime_weeks INTEGER DEFAULT 156,
    weekly_charge_kg REAL,
    is_active BOOLEAN DEFAULT 1,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by INTEGER REFERENCES users(id)
);

-- System configuration
CREATE TABLE system_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    value_type TEXT DEFAULT 'string',
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by INTEGER REFERENCES users(id)
);

-- Audit log for tracking changes
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_id INTEGER REFERENCES users(id),
    action TEXT NOT NULL,
    table_name TEXT NOT NULL,
    record_id INTEGER,
    field_name TEXT,
    old_value TEXT,
    new_value TEXT,
    ip_address TEXT
);

-- Indexes for performance
CREATE INDEX idx_cycle_data_weekly ON cycle_data(weekly_summary_id);
CREATE INDEX idx_cycle_data_time ON cycle_data(start_time);
CREATE INDEX idx_weekly_summary_date ON weekly_summary(year, week_number);
CREATE INDEX idx_audit_log_timestamp ON audit_log(timestamp);
```

### 3.2 Initial Configuration Data

```sql
-- Default system configuration
INSERT INTO system_config (key, value, value_type, description) VALUES
    ('grid_emission_factor', '0.049', 'float', 'Kenya grid EF (kg CO2/kWh)'),
    ('geothermal_emission_factor', '0.0', 'float', 'Geothermal EF (kg CO2/kWh)'),
    ('plant_start_date', '2026-01-01', 'string', 'Plant operational start date'),
    ('plant_lifetime_years', '10', 'int', 'Infrastructure amortization period'),
    ('sorbent_lifetime_years', '3', 'int', 'Sorbent batch lifetime'),
    ('target_capacity_tonnes_year', '100', 'float', 'Annual target capacity'),
    ('ef_stainless_steel', '7.14', 'float', 'Stainless steel 304 EF'),
    ('ef_mild_steel', '2.4', 'float', 'Mild steel EF'),
    ('ef_aluminium', '11.75', 'float', 'Aluminium EF'),
    ('ef_concrete', '0.13', 'float', 'Concrete EF'),
    ('ef_alumina', '1.91', 'float', 'Alumina EF'),
    ('ef_pei', '11.05', 'float', 'PEI EF'),
    ('ef_methanol', '0.92', 'float', 'Methanol EF');
```

---

## 4. Application Structure

### 4.1 Page Descriptions

| Page | Purpose | Access |
|------|---------|--------|
| **Dashboard** | Main KPIs, net status, trends | All users |
| **Data Entry** | CSV import, manual liquefaction entry | Admin only |
| **Reports** | Detailed weekly/monthly reports | All users |
| **Simulations** | Monte Carlo, geothermal scenarios | All users |
| **Configuration** | Emission factors, system settings | Admin only |
| **User Management** | Add/edit users, view audit log | Admin only |

### 4.2 Dashboard Layout

```
┌────────────────────────────────────────────────────────────────────┐
│                     OCTAVIA CAS DASHBOARD                          │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │ Net CO2  │  │  Gross   │  │  Total   │  │   NET STATUS     │   │
│  │ Removal  │  │ Captured │  │ Emissions│  │  ● NET POSITIVE  │   │
│  │ 245 kg   │  │ 520 kg   │  │ 275 kg   │  │    or            │   │
│  │ ▲ +12%   │  │          │  │          │  │  ○ NET NEGATIVE  │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘   │
│                                                                    │
│  ┌─────────────────────────────┐  ┌────────────────────────────┐  │
│  │    Weekly Trend Chart       │  │   Emissions Breakdown      │  │
│  │                             │  │                            │  │
│  │   📈 Net Removal Trend      │  │   🥧 Pie Chart             │  │
│  │      Over Past 8 Weeks      │  │   - Thermal: 65%           │  │
│  │                             │  │   - Auxiliary: 20%         │  │
│  │                             │  │   - Embodied: 15%          │  │
│  └─────────────────────────────┘  └────────────────────────────┘  │
│                                                                    │
│  ┌─────────────────────────────┐  ┌────────────────────────────┐  │
│  │   Energy Intensity          │  │   Capacity Progress        │  │
│  │   (kWh/tCO2)                │  │                            │  │
│  │   📊 Bar Chart by Week      │  │   ◐ 45/100 tonnes YTD     │  │
│  │   - Thermal                 │  │   Target: 100 t/year       │  │
│  │   - Auxiliary               │  │                            │  │
│  └─────────────────────────────┘  └────────────────────────────┘  │
│                                                                    │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │                 Weekly Summary Table                        │   │
│  │  Week │ Cycles │ Captured │ Emissions │ Net │ Status       │   │
│  │  ─────┼────────┼──────────┼───────────┼─────┼──────────    │   │
│  │   3   │   98   │  520 kg  │  275 kg   │+245 │ ● Positive   │   │
│  │   2   │   95   │  480 kg  │  290 kg   │+190 │ ● Positive   │   │
│  │   1   │   87   │  420 kg  │  450 kg   │ -30 │ ○ Negative   │   │
│  └────────────────────────────────────────────────────────────┘   │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

---

## 5. Authentication & Authorization

### 5.1 User Roles

| Role | Dashboard | Data Entry | Reports | Simulations | Config | User Mgmt |
|------|-----------|------------|---------|-------------|--------|-----------|
| **Admin** | ✅ View | ✅ Full | ✅ View | ✅ Run | ✅ Edit | ✅ Manage |
| **User** | ✅ View | ❌ None | ✅ View | ✅ Run | ❌ None | ❌ None |

### 5.2 Authentication Implementation

```python
# app/auth/authentication.py

import streamlit as st
import bcrypt
from database.connection import get_session
from database.models import User

def check_authentication():
    """Check if user is authenticated."""
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    
    if not st.session_state.authenticated:
        show_login_form()
        return False
    return True

def show_login_form():
    """Display login form."""
    st.title("🌍 Octavia Carbon Accounting System")
    st.subheader("Login")
    
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")
        
        if submitted:
            if authenticate_user(username, password):
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Invalid username or password")

def authenticate_user(username: str, password: str) -> bool:
    """Verify user credentials."""
    session = get_session()
    try:
        user = session.query(User).filter(
            User.username == username,
            User.is_active == True
        ).first()
        
        if user and verify_password(password, user.password_hash):
            st.session_state.user_id = user.id
            st.session_state.username = user.username
            st.session_state.role = user.role
            return True
    finally:
        session.close()
    return False

def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against hash."""
    return bcrypt.checkpw(
        password.encode('utf-8'),
        password_hash.encode('utf-8')
    )

def hash_password(password: str) -> str:
    """Hash a password for storage."""
    return bcrypt.hashpw(
        password.encode('utf-8'),
        bcrypt.gensalt()
    ).decode('utf-8')

def logout():
    """Clear session state on logout."""
    for key in ['authenticated', 'user_id', 'username', 'role']:
        if key in st.session_state:
            del st.session_state[key]
```

---

## 6. Data Flow Architecture

### 6.1 CSV Import Process

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  CSV Files  │────>│   Parser    │────>│  Validator  │────>│   SQLite    │
│  (SCADA)    │     │  (Pandas)   │     │             │     │     DB      │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                                              │
                                              ▼
                                    ┌─────────────────┐
                                    │  Import Report  │
                                    │  - Rows added   │
                                    │  - Errors       │
                                    │  - Warnings     │
                                    └─────────────────┘
```

### 6.2 Column Mappings

**Cycle Data CSV:**
```python
CYCLE_COLUMNS = {
    'Cycle #': 'cycle_number',
    'Machine': 'machine',
    'Start Time': 'start_time',
    'ADS CO2 (kg)': 'ads_co2_kg',
    'ADS Hours': 'ads_hours',
    'DES CO2 (kg)': 'des_co2_kg',
    'DES Hours': 'des_hours',
    'BAG CO2': 'bag_co2_kg',
    'eTotal kWh': 'total_kwh',
    'Steam (kg)': 'steam_kg',
}
```

**Energy Data CSV:**
```python
ENERGY_COLUMNS = {
    'Cycle #': 'cycle_number',
    'Machine': 'machine',
    'eTotal (kWh)': 'total_kwh',
    'Boiler (kWh)': 'boiler_kwh',
    'SRV/LRVP (kWh)': 'srv_lrvp_kwh',
    'CT (kWh)': 'ct_kwh',
    'NM1 Fan (kWh)': 'nm1_fan_kwh',
    'NM3 Fan (kWh)': 'nm3_fan_kwh',
    'NM2 Fan (kWh)': 'nm2_fan_kwh',
    'NM4 Fan (kWh)': 'nm4_fan_kwh'
}
```

---

## 7. Configuration Management

### 7.1 Configuration File

```yaml
# config/settings.yaml

app:
  name: "Octavia Carbon Accounting System"
  version: "1.0.0"

database:
  type: "sqlite"
  path: "data/octavia.db"

plant:
  name: "Project Hummingbird Phase 1"
  location: "Gilgil, Kenya"
  start_date: "2026-01-01"
  target_capacity_tonnes_year: 100
  infrastructure_lifetime_years: 10
  sorbent_lifetime_years: 3

emission_factors:
  grid:
    kenya_power: 0.049
    geothermal: 0.0
  
  materials:
    stainless_steel_304: 7.14
    mild_steel: 2.40
    aluminium: 11.75
    concrete: 0.13
    alumina: 1.91
    pei: 11.05
    methanol: 0.92
  
  eol:
    landfill: 0.02
    combustion: 1.29
  
  transport:
    sea_shipping: 0.005
    road_trucking: 0.086
```

---

## 8. Scalability Considerations

### 8.1 SQLite to PostgreSQL Migration

The system uses SQLAlchemy ORM to abstract database operations. Migration requires:

1. Update `config/settings.yaml`:
```yaml
database:
  type: "postgresql"
  host: "localhost"
  port: 5432
  database: "octavia_cas"
  username: "${DB_USERNAME}"
  password: "${DB_PASSWORD}"
```

2. Install PostgreSQL driver:
```bash
pip install psycopg2-binary
```

3. Run migration script to transfer data.

### 8.2 Deployment Options

**Local (Current):**
```bash
streamlit run app/main.py --server.port 8501
```

**Docker (Future):**
```dockerfile
FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8501
CMD ["streamlit", "run", "app/main.py", "--server.port=8501"]
```

---

*Document continues in 04_PRD.md*
