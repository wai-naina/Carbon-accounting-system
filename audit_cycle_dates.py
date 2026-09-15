"""Audit Carbon Nest cycle timestamps for day/month transposition damage.

Background: app/services/carbon_nest_import.py used to parse the export's
dates with a bare pd.to_datetime(errors="coerce"). Pandas infers a layout
from the FIRST row and applies it to the whole column, so a day-first
(DD/MM/YYYY) export loaded through a month-first guess produced two kinds
of damage at once:

  * rows whose real day was <= 12 were silently transposed - "07/09/2026"
    (7 Sep) was stored as 9 July;
  * rows whose real day was > 12 could not be read as a month at all, were
    coerced to NaT, and were dropped from the import entirely.

Both kinds scatter cycles out of their true week, which is why a weekly
entry screen can report 12 cycles when the plant actually ran 77.

Dry-run by default; nothing is written unless --commit is passed. On SQLite
the database file is copied to a timestamped .bak first, matching
delete_cycle.py - a cycle row carries SCADA values that cannot be
re-derived, so re-importing the original export is the only way back.

    python audit_cycle_dates.py                        # report only
    python audit_cycle_dates.py --batch <id>           # detail for one batch
    python audit_cycle_dates.py --delete-batch <id> --commit

Runs against whatever the app itself would use: Neon when DATABASE_URL is
set, otherwise local SQLite at data/octavia.db. It prints which one, since
operating on the wrong database is the easy mistake here.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import load_config
from app.database.connection import get_session
from app.database.models import CarbonNestCycleData, CarbonNestWeeklySummary
from app.services.carbon_nest_aggregation import get_carbon_nest_week_bounds

# A transposed date can only ever land on a day of 1-12, because the value
# that ends up in the day slot came from the month slot.
MAX_TRANSPOSABLE = 12

# Consecutive cycle numbers are hours apart in reality. Anything beyond this
# is either genuine downtime or a transposition; the audit flags it either
# way and lets the operator judge.
SUSPICIOUS_GAP_DAYS = 20


def describe_target() -> tuple[str, Path | None]:
    """Return a human label for the active database, and its file if SQLite."""
    url = os.getenv("DATABASE_URL")
    if url:
        # Never print the URL itself - it carries the Neon password.
        host = url.split("@")[-1].split("/")[0] if "@" in url else "(unparsed)"
        return f"PostgreSQL/Neon at {host}", None
    db_path = load_config().db_path
    return f"local SQLite at {db_path}", db_path


def backup_sqlite(db_path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = db_path.with_suffix(f".{stamp}.bak")
    shutil.copy2(db_path, dest)
    return dest


def transposed(dt: datetime | None) -> datetime | None:
    """The same timestamp with day and month swapped, or None if impossible."""
    if dt is None or dt.day > MAX_TRANSPOSABLE:
        return None
    try:
        return dt.replace(month=dt.day, day=dt.month)
    except ValueError:
        return None


def audit(cycles: list) -> dict:
    """Classify a set of cycle rows against the symptoms of transposition."""
    horizon = datetime.now() + timedelta(days=1)

    future = [c for c in cycles if c.start_time and c.start_time > horizon]
    backwards = [
        c for c in cycles
        if c.start_time and c.end_time and c.end_time < c.start_time
    ]

    ordered = sorted(
        (c for c in cycles if c.start_time), key=lambda c: c.cycle_number
    )
    out_of_order = [
        (prev, cur)
        for prev, cur in zip(ordered, ordered[1:])
        if cur.start_time < prev.start_time
    ]
    big_gaps = [
        (prev, cur)
        for prev, cur in zip(ordered, ordered[1:])
        if (cur.start_time - prev.start_time).days >= SUSPICIOUS_GAP_DAYS
    ]

    # The fingerprint of a swap: two ADJACENT cycles sharing a day-of-month
    # while the month jumps. Real consecutive cycles are hours apart, so this
    # is physically impossible — but it is exactly what transposition produces,
    # because consecutive real DAYS become consecutive stored MONTHS.
    #
    # Adjacency is what makes this sound. Simply counting how many months a
    # given day-of-month appears in would flag any honest multi-month history
    # (the 9th of June, July, August and September are all real dates); those
    # cycles are hundreds of cycle numbers apart, not neighbours.
    fingerprint = [
        (prev, cur)
        for prev, cur in zip(ordered, ordered[1:])
        if prev.start_time.day == cur.start_time.day
        and prev.start_time.month != cur.start_time.month
    ]

    return {
        "count": len(cycles),
        "min": min((c.start_time for c in cycles if c.start_time), default=None),
        "max": max((c.start_time for c in cycles if c.start_time), default=None),
        "future": future,
        "backwards": backwards,
        "out_of_order": out_of_order,
        "big_gaps": big_gaps,
        "fingerprint": fingerprint,
    }


def verdict(result: dict) -> str:
    if result["future"] or result["fingerprint"]:
        return "CORRUPT"
    if result["out_of_order"] or result["backwards"]:
        return "SUSPECT"
    if result["big_gaps"]:
        return "CHECK"
    return "ok"


def report_batches(session) -> None:
    cycles = session.query(CarbonNestCycleData).all()
    print(f"Total Carbon Nest cycles: {len(cycles)}\n")
    if not cycles:
        return

    by_batch = defaultdict(list)
    for c in cycles:
        by_batch[c.import_batch_id].append(c)

    print(f"{'batch':38} {'rows':>5}  {'range':26} verdict")
    print("-" * 88)
    for batch, rows in sorted(
        by_batch.items(),
        key=lambda kv: min(
            (c.start_time for c in kv[1] if c.start_time), default=datetime.max
        ),
    ):
        result = audit(rows)
        span = "(no dates)"
        if result["min"] and result["max"]:
            span = f"{result['min']:%Y-%m-%d} -> {result['max']:%Y-%m-%d}"
        print(f"{str(batch):38} {result['count']:>5}  {span:26} {verdict(result)}")

    print()
    overall = audit(cycles)
    if overall["future"]:
        print(f"!! {len(overall['future'])} cycle(s) start in the FUTURE - "
              "conclusive evidence of a day/month swap.")
        for c in sorted(overall["future"], key=lambda c: c.cycle_number)[:10]:
            fixed = transposed(c.start_time)
            hint = f"  (really {fixed:%Y-%m-%d %H:%M})" if fixed else ""
            print(f"     cycle {c.cycle_number}: {c.start_time:%Y-%m-%d %H:%M}{hint}")
    if overall["fingerprint"]:
        print(f"!! {len(overall['fingerprint'])} pair(s) of ADJACENT cycles share a "
              "day-of-month but sit in different months - transposed dates.")
        for prev, cur in overall["fingerprint"][:10]:
            print(f"     cycle {prev.cycle_number} {prev.start_time:%Y-%m-%d %H:%M}"
                  f"  ->  cycle {cur.cycle_number} {cur.start_time:%Y-%m-%d %H:%M}")
    if not overall["future"] and not overall["fingerprint"]:
        print("No transposition symptoms found.")


def report_detail(session, batch: str) -> None:
    rows = (
        session.query(CarbonNestCycleData)
        .filter(CarbonNestCycleData.import_batch_id == batch)
        .order_by(CarbonNestCycleData.cycle_number)
        .all()
    )
    if not rows:
        print(f"No cycles found for batch {batch}")
        return

    print(f"Batch {batch}: {len(rows)} cycles\n")
    print(f"{'cycle':>6} {'module':14} {'stored start':17} {'if transposed':17}")
    print("-" * 60)
    for c in rows:
        stored = f"{c.start_time:%Y-%m-%d %H:%M}" if c.start_time else "(none)"
        fixed = transposed(c.start_time)
        alt = f"{fixed:%Y-%m-%d %H:%M}" if fixed else "(unswappable)"
        print(f"{c.cycle_number:>6} {str(c.raw_module):14} {stored:17} {alt:17}")

    weeks = sorted(
        {get_carbon_nest_week_bounds(c.start_time)[0] for c in rows if c.start_time}
    )
    print(f"\nTouches {len(weeks)} week(s): "
          + ", ".join(f"{w:%Y-%m-%d}" for w in weeks))


def delete_batch(session, batch: str, commit: bool) -> None:
    rows = (
        session.query(CarbonNestCycleData)
        .filter(CarbonNestCycleData.import_batch_id == batch)
        .all()
    )
    if not rows:
        print(f"No cycles found for batch {batch} - nothing to delete.")
        return

    numbers = sorted(c.cycle_number for c in rows)
    print(f"Batch {batch}: {len(rows)} cycles (#{numbers[0]} .. #{numbers[-1]})")

    # Weekly summaries built from these rows are now wrong and must be
    # recalculated after the clean re-import, so name them explicitly.
    affected = sorted({c.weekly_summary_id for c in rows if c.weekly_summary_id})
    if affected:
        summaries = (
            session.query(CarbonNestWeeklySummary)
            .filter(CarbonNestWeeklySummary.id.in_(affected))
            .all()
        )
        print("\nWeekly summaries that will need recalculating afterwards:")
        for s in sorted(summaries, key=lambda s: s.start_date):
            print(f"  {s.start_date:%Y-%m-%d %H:%M} -> {s.end_date:%Y-%m-%d %H:%M}")

    if not commit:
        print("\nDRY RUN - nothing deleted. Re-run with --commit to apply.")
        return

    for c in rows:
        session.delete(c)
    session.commit()
    print(f"\nDeleted {len(rows)} cycles. Re-import the original CSV now that "
          "the parser is fixed, then recalculate the weeks listed above.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", help="show per-cycle detail for one import batch")
    parser.add_argument("--delete-batch", help="delete every cycle from one import batch")
    parser.add_argument("--commit", action="store_true", help="actually write changes")
    args = parser.parse_args()

    label, db_path = describe_target()
    print(f"Database: {label}\n")

    session = get_session()
    try:
        if args.delete_batch:
            if args.commit and db_path:
                print(f"Backup: {backup_sqlite(db_path)}\n")
            delete_batch(session, args.delete_batch, args.commit)
        elif args.batch:
            report_detail(session, args.batch)
        else:
            report_batches(session)
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
