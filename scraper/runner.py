"""Run the scraper in a background thread so the web UI doesn't block.

State lives in memory, so this suits a single-process server (runserver, one
gunicorn worker). For production with several workers, use Celery or a cron job.
"""
import io
import threading

from django.core.management import call_command
from django.db import connection
from django.utils import timezone

_lock = threading.Lock()
_state = {"running": False, "started_at": None, "finished_at": None, "message": "", "ok": None}


def get_state() -> dict:
    with _lock:
        return dict(_state)


def start_scrape(max_pages: int = 1) -> bool:
    """Start a scrape. Returns False if one is already running."""
    with _lock:
        if _state["running"]:
            return False
        _state.update(running=True, started_at=timezone.now(), finished_at=None, message="", ok=None)
    threading.Thread(target=_run, args=(max_pages,), daemon=True).start()
    return True


def _run(max_pages: int) -> None:
    out, err = io.StringIO(), io.StringIO()
    ok, message = True, ""
    try:
        call_command("scrape_recruteomg", max_pages=max_pages, stdout=out, stderr=err)
        lines = [l for l in out.getvalue().splitlines() if l.strip()]
        message = " · ".join(lines[-2:])
        if err.getvalue().strip():
            message += " ⚠ " + err.getvalue().strip().splitlines()[-1]
    except Exception as exc: 
        ok, message = False, f"Erreur : {exc}"
    finally:
        connection.close() 
        with _lock:
            _state.update(running=False, finished_at=timezone.now(), message=message, ok=ok)
