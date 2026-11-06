"""Coarse stdout only. Browser/library output is suppressed at the FD boundary."""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys

from .config import ConfigError, load_config
from .dedupe import Dedupe, private_write

@contextmanager
def quiet_io():
    sys.stdout.flush()
    sys.stderr.flush()
    saved = [os.dup(fd) for fd in (1, 2)]
    try:
        with open(os.devnull, "w") as sink:
            for fd in (1, 2):
                os.dup2(sink.fileno(), fd)
            yield
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        for fd, original in zip((1, 2), saved):
            os.dup2(original, fd)
            os.close(original)


def private_directory():
    path = Path(os.environ.get("RUN_PRIVATE_DIR", "/tmp/inventory-monitor-private")).expanduser()
    package = Path(__file__).resolve().parent.parent
    if path.is_symlink() or path.resolve().is_relative_to(package):
        raise ValueError("Private output must be outside repository")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.stat().st_uid != os.getuid():
        raise ValueError("Private directory must belong to this user")
    path.chmod(0o700)
    return path


def execute(config, private, run_watch, playwright):
    latch = private / "blocked.json"
    dedupe = Dedupe(private / "dedupe.json")
    latched = latch.exists()
    summaries, details = [], []
    for index, watch in enumerate(config.watches, 1):
        label = f"watch-{index}"
        if latched:
            summaries.append({"id_hash_or_generic_label": label, "status": "BLOCKED_LATCHED", "card_count": 0, "match_count": 0, "blocked": True})
            continue
        try:
            result = run_watch(playwright, watch)
            status = result.status
            if status == "BLOCKED":
                latched = True
                private_write(latch, {"blocked": True})
            events = [{"card": card.to_dict(), "event": dedupe.event(card)} for card in result.matches]
            details.append({"watch": label, "status": status, "matches": events})
            summaries.append({"id_hash_or_generic_label": label, "status": status, "card_count": result.card_count, "match_count": len(result.matches), "blocked": latched})
        except Exception:
            # Do not print arbitrary exception strings: these can contain private URLs.
            summaries.append({"id_hash_or_generic_label": label, "status": "ERROR", "card_count": 0, "match_count": 0, "blocked": latched})
    private_write(private / "results.json", details)
    dedupe.save()
    ok = all(row["status"] in {"LOADED_EMPTY", "LOADED_WITH_CARDS"} for row in summaries)
    return {"ok": ok, "watches": summaries, "note": "manual_resume_required" if latched else "complete" if ok else "incomplete"}


def main(argv=None):
    parser = argparse.ArgumentParser(description="One-shot public UI inventory monitor")
    parser.add_argument("--resume-blocked", action="store_true", help="Explicitly clear the local challenge latch")
    args = parser.parse_args(argv)
    summary = {"ok": False, "watches": [], "note": "execution_failed"}
    try:
        config = load_config()
        with quiet_io():
            private = private_directory()
            if args.resume_blocked:
                (private / "blocked.json").unlink(missing_ok=True)
            from playwright.sync_api import sync_playwright
            from .browser_ui import run_watch
            with sync_playwright() as playwright:
                summary = execute(config, private, run_watch, playwright)
    except ConfigError:
        summary["note"] = "invalid_configuration"
    except Exception:
        pass
    print(json.dumps(summary, separators=(",", ":")))
    return 0 if summary["ok"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
