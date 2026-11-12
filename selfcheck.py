#!/usr/bin/env python3
"""Offline sanity check — no bot token, no network.

    python selfcheck.py

Exercises the storage layer and the Persian stage/code parsing on a throwaway
database, so you can verify an edit without touching production data.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import db
import texts as T


def main() -> int:
    # Windows consoles default to cp1252 and blow up on emoji.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    tmp = Path(tempfile.mkdtemp(prefix="weddingbot-selfcheck-"))
    db.init_db(str(tmp / "test.db"))

    # --- projects -------------------------------------------------------
    p = db.create_project("WED-TEST1", "Sara Ahmadi")
    assert p["code"] == "WED-TEST1", "create_project returned wrong code"
    assert p["stage"] == 0, "new project must start at stage 0"
    assert db.project_by_code("WED-TEST1")["id"] == p["id"]
    assert db.project_by_id(p["id"])["customer_name"] == "Sara Ahmadi"

    # --- customer binding is one-shot -----------------------------------
    assert db.bind_customer(p["id"], 111) is True, "first bind must succeed"
    assert db.bind_customer(p["id"], 222) is False, "second bind must be refused"
    assert db.project_by_customer(111)["id"] == p["id"]
    assert db.project_by_customer(222) is None

    # --- mutations ------------------------------------------------------
    db.set_stage(p["id"], 3)
    assert db.project_by_code("WED-TEST1")["stage"] == 3
    db.set_note(p["id"], "رتاش عکس‌ها تمام شد")
    assert db.project_by_code("WED-TEST1")["note"] == "رتاش عکس‌ها تمام شد"
    db.set_delivery(p["id"], "1404/02/15")
    assert db.project_by_code("WED-TEST1")["delivery_date"] == "1404/02/15"

    db.add_media(p["id"], "https://drive.google.com/preview", "پیش‌نمایش")
    assert len(db.list_media(p["id"])) == 1

    db.log_event(p["id"], "111", "stage", T.STAGES[3])
    assert len(db.recent_events(p["id"])) == 1

    # --- lookup by name -------------------------------------------------
    assert db.project_by_name("sara") is not None, "name match must be case-insensitive"
    assert db.project_by_name("Sara Ahmadi") is not None
    assert db.project_by_name("nobody") is None

    # --- staff ----------------------------------------------------------
    db.add_staff(333, p["id"])
    staff = db.get_staff(333)
    assert staff is not None and staff["project_id"] == p["id"]
    db.add_staff(444)  # project-wide crew (no project_id)
    assert db.get_staff(444)["project_id"] is None
    assert len(db.list_staff()) == 2
    assert db.remove_staff(333) is True
    assert db.get_staff(333) is None

    # --- reset / rebind -------------------------------------------------
    assert db.reset_customer(p["id"]) is True
    assert db.project_by_customer(111) is None
    assert db.bind_customer(p["id"], 555) is True, "rebind after reset must work"
    assert db.reset_customer(p["id"]) is True

    # --- Persian stage parsing -----------------------------------------
    assert T.parse_stage("4") == 3
    assert T.parse_stage("رتاش عکس‌ها") == 3
    assert T.parse_stage("آلبوم") == 4, "fuzzy fragment should match آلبوم دیجیتال"
    assert T.parse_stage("  آلبوم چاپی  ") == 5
    assert T.parse_stage("1") == 0
    assert T.parse_stage("0") is None, "stages are 1-based for humans"
    assert T.parse_stage("8") is None
    assert T.parse_stage("هیچ‌چیز") is None

    # --- code normalisation --------------------------------------------
    assert T.normalize_code("WED-7K4Q") == "WED-7K4Q"
    assert T.normalize_code("7k4q") == "WED-7K4Q"
    assert T.normalize_code("wed 7k4q") == "WED-7K4Q"
    assert T.normalize_code("wed_7k4q") == "WED-7K4Q"

    # --- progress bar ---------------------------------------------------
    assert len(T.bar(0)) == len(T.STAGES)
    assert T.bar(0).startswith("🔵")
    assert T.bar(len(T.STAGES) - 1).endswith("🔵")
    assert "🟢" in T.bar(3)

    # --- every copy template must be formattable ------------------------
    from string import Formatter

    for name in dir(T):
        value = getattr(T, name)
        if not isinstance(value, str) or "{" not in value:
            continue
        fields = {f for _, f, _, _ in Formatter().parse(value) if f}
        try:
            value.format(**{f: "X" for f in fields})
        except Exception as exc:
            raise AssertionError(f"template {name} is malformed: {exc}") from exc

    db.close()
    print("✅ selfcheck passed — storage, stages, codes all behave.")
    print(f"   temp db was: {tmp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
