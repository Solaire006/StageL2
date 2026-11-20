#!/usr/bin/env python3
"""Make a consistent copy of the SQLite database and keep the last N copies.

Usage: backup_db.py <db.sqlite3> <backup folder> [copies to keep, default 14]

Uses SQLite's own backup API, so the copy is safe even while the site is
running (a plain `cp` could copy a half-written file).
To restore: stop the app, copy a backup over the database file, start the app.
"""
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    db, folder = Path(sys.argv[1]), Path(sys.argv[2])
    keep = int(sys.argv[3]) if len(sys.argv) > 3 else 14
    if not db.exists():
        print(f"database not found: {db}", file=sys.stderr)
        return 1
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"db_{datetime.now():%Y%m%d_%H%M%S}.sqlite3"

    src = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    dst = sqlite3.connect(target)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    target.chmod(0o600)  # contains password hashes: owner-only

    old = sorted(folder.glob("db_*.sqlite3"))[:-keep]
    for f in old:
        f.unlink()
    print(f"backup written: {target} ({len(old)} old copies removed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
