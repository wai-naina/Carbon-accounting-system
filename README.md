# Octavia Carbon Accounting System (CAS)
## Developer Quick Reference

**Version:** 1.0 | **Date:** January 2026

---

## 🎯 Project Summary

Build a Streamlit web application for Octavia Carbon to track their Direct Air Capture operations and determine if they are **net positive** (removing more CO₂ than emitting) or **net negative**.

---

## 📁 Documentation Files

| File | Purpose |
|------|---------|
| `01_PROJECT_DOCUMENTATION.md` | Business context, operations overview, glossary |
| `02_CALCULATIONS_AND_FORMULAS.md` | **ALL calculation formulas** - reference this for implementation |
| `03_SYSTEM_ARCHITECTURE.md` | Database schema, SQLAlchemy models, directory structure |
| `04_PRD.md` | Functional requirements, user stories, acceptance criteria |

---

## 🔑 Core Formula (Most Important!)

```python
Net_CO2_Removal = Liquefied_CO2 - Operational_Emissions - Embodied_Emissions

Where:
- Liquefied_CO2 = Manual weekly entry (kg)
- Operational_Emissions = Total_Energy_kWh × 0.049 (Grid EF)
- Embodied_Emissions = Infrastructure_Weekly + Sorbent_Weekly
```

---

## 🗄️ Key Database Tables

1. **users** - Authentication (username, password_hash, role)
2. **cycle_data** - Raw SCADA imports (CO2, energy per cycle)
3. **weekly_summary** - Aggregated weekly calculations
4. **embodied_infrastructure** - LCA data by zone
5. **embodied_sorbent** - Sorbent batch tracking
6. **system_config** - Emission factors, settings
7. **audit_log** - Change tracking

---

## 📊 Main Pages to Build

1. **Dashboard** - KPIs, net status indicator, trend charts, weekly table
2. **Data Entry** (Admin) - CSV import, manual liquefied CO2 entry
3. **Reports** - Detailed weekly/monthly breakdowns
4. **Simulations** - Monte Carlo for geothermal scenario
5. **Configuration** (Admin) - Emission factors
6. **User Management** (Admin) - Add/edit users

---

## 🔢 Key Constants

```python
GRID_EF = 0.049  # kg CO2/kWh (Kenya Power)
GEOTHERMAL_EF = 0.0  # For simulation
INFRASTRUCTURE_LIFETIME = 520  # weeks (10 years)
SORBENT_LIFETIME = 156  # weeks (3 years)
```

---

## 📥 CSV Import Mappings

**Cycle Data (plant_cycles_*.csv):**
```
Cycle # → cycle_number
Machine → machine  
Start Time → start_time
ADS CO2 (kg) → ads_co2_kg
DES CO2 (kg) → des_co2_kg
BAG CO2 → bag_co2_kg
eTotal kWh → total_kwh
Steam (kg) → steam_kg
```

**Energy Data (cycle_energy_*.csv):**
```
Cycle # → cycle_number
Machine → machine
Boiler (kWh) → boiler_kwh
SRV/LRVP (kWh) → srv_lrvp_kwh
CT (kWh) → ct_kwh
NM1-4 Fan (kWh) → nm1_fan_kwh, etc.
```

---

## 🎨 UI Color Scheme

| Element | Color |
|---------|-------|
| Net Positive | #28A745 (Green) |
| Net Negative | #DC3545 (Red) |
| Thermal Energy | #FD7E14 (Orange) |
| Auxiliary Energy | #17A2B8 (Cyan) |
| Embodied | #6F42C1 (Purple) |

---

## ✅ Acceptance Test Checklist

- [ ] Admin can log in
- [ ] Admin can import CSV files
- [ ] Admin can enter liquefied CO2
- [ ] Weekly summary calculates correctly
- [ ] Dashboard shows net positive/negative status
- [ ] User (non-admin) cannot access data entry
- [ ] Monte Carlo simulation runs and shows geothermal improvement

---

## 🚀 Quick Start Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Initialize database
python -c "from app.database.connection import init_db; init_db()"

# Run application
streamlit run app/main.py --server.port 8502
```

---

## 📄 Weekly report export — PDF vs HTML/CSV

The weekly report is laid out with ReportLab, which is pure pip. The one
host-dependent piece is Chrome: the PDF embeds its Plotly charts as rasterized
PNGs and `kaleido` needs a real Chrome/Chromium binary to produce them.

`app/services/pdf_support.py` probes for that binary at runtime — no download,
no launch — and the reports page offers the PDF only when one is present.
Otherwise it offers the same report as **self-contained HTML** (same figures,
same sentences, interactive charts, prints to PDF from the browser) plus a
headline-numbers **CSV**. Both formats read one `WeekReportContext`
(`app/services/report_data.py`), so they cannot disagree.

Override the probe with `PDF_EXPORT_ENABLED=on|off` when it guesses wrong.

### Why `packages.txt` is parked as `packages.txt.disabled`

As of **2026-09-08**, Streamlit Community Cloud fails during dependency
processing for *any* app that has a `packages.txt`:

```
E: Release file for http://deb.debian.org/debian-security/dists/bullseye-security/InRelease is expired
```

The base image is Debian trixie but still carries a stale `bullseye-security`
apt source, so `apt-get update` fails *before* it ever reads which packages we
asked for. That's Streamlit's image to fix and isn't reachable from this repo —
and because the failure is at the update step, trimming lines doesn't help. The
whole file has to be absent, hence the rename.

**To restore chromium (and the PDF) on cloud once Streamlit fixes the image:**

```bash
git mv packages.txt.disabled packages.txt
```

That's the entire change. Detection then finds the browser on its own and the
reports page goes back to offering the PDF; no code edit, no flag to flip.
Restoring the file also brings back `fonts-liberation` / `fonts-dejavu-core`,
which `_register_unicode_font()` needs for `→`, `−` and `₂` — without a real
TTF those glyphs are invisible in the PDF (see `app/services/pdf_report.py`).

---

## 🔐 Default Admin Login

- Username: `admin`
- Password: `admin123`
- Override via environment variables: `CAS_ADMIN_USERNAME`, `CAS_ADMIN_PASSWORD`, `CAS_ADMIN_EMAIL`

---

## 📞 Questions?

Refer to the detailed documentation files for specifics:
- **Calculations**: See `02_CALCULATIONS_AND_FORMULAS.md`
- **Database Schema**: See `03_SYSTEM_ARCHITECTURE.md` Section 3
- **Requirements**: See `04_PRD.md` Section 3

---

*Good luck building! 🌍*
