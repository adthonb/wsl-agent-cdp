#!/usr/bin/env python3
"""Keep the dedicated Chromium profile free of saved passwords."""

from __future__ import annotations

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import tempfile


PASSWORD_FILES = {
    "Login Data",
    "Login Data-wal",
    "Login Data-shm",
    "Login Data-journal",
    "Login Data For Account",
    "Login Data For Account-wal",
    "Login Data For Account-shm",
    "Login Data For Account-journal",
}


def profile_dirs(root: Path) -> list[Path]:
    directories = [root / "Default"]
    if root.is_dir():
        directories.extend(
            child for child in root.iterdir()
            if child.is_dir() and not child.is_symlink() and child.name != "Default"
            and ((child / "Preferences").exists()
                 or any((child / name).exists() for name in PASSWORD_FILES))
        )
    return directories


def preferences_safe(path: Path) -> bool:
    if not path.is_file():
        return False
    prefs = json.loads(path.read_text(encoding="utf-8"))
    return (
        prefs.get("credentials_enable_service") is False
        and prefs.get("profile", {}).get("password_manager_enabled") is False
        and prefs.get("signin", {}).get("allowed") is False
        and prefs.get("signin", {}).get("allowed_on_next_startup") is False
    )


def pending(root: Path) -> list[str]:
    if not root.exists():
        return []
    problems = []
    for directory in profile_dirs(root):
        prefs = directory / "Preferences"
        try:
            safe = preferences_safe(prefs)
        except (OSError, ValueError, TypeError, AttributeError):
            safe = False
        if not safe:
            problems.append(f"{prefs}: hardening needed")
        for base in ("Login Data", "Login Data For Account"):
            database = directory / base
            if not database.exists():
                if any((directory / (base + suffix)).exists() for suffix in ("-wal", "-shm", "-journal")):
                    problems.append(f"{database}: orphaned password-store file present")
                continue
            try:
                with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=1)) as connection:
                    rows = connection.execute("SELECT COUNT(*) FROM logins").fetchone()[0]
                if rows:
                    problems.append(f"{database}: {rows} saved login(s) present")
            except sqlite3.Error:
                problems.append(f"{database}: password store could not be checked")
    return problems


def harden(root: Path) -> None:
    if root.is_symlink() or (root / "Default").is_symlink():
        raise ValueError("Refusing to harden a symlinked agent profile")
    for directory in profile_dirs(root):
        directory.mkdir(parents=True, exist_ok=True)
        prefs_path = directory / "Preferences"
        prefs = json.loads(prefs_path.read_text(encoding="utf-8")) if prefs_path.exists() else {}
        if not isinstance(prefs, dict):
            raise ValueError(f"Invalid preferences: {prefs_path}")
        for key in ("profile", "signin"):
            if not isinstance(prefs.get(key, {}), dict):
                raise ValueError(f"Invalid {key} preferences: {prefs_path}")
        prefs["credentials_enable_service"] = False
        prefs.setdefault("profile", {})["password_manager_enabled"] = False
        prefs.setdefault("signin", {})["allowed"] = False
        prefs["signin"]["allowed_on_next_startup"] = False

        # Replace Preferences atomically so a failed write cannot truncate it.
        descriptor, temp_name = tempfile.mkstemp(prefix=".Preferences-", dir=directory)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(prefs, stream, separators=(",", ":"), ensure_ascii=False)
            os.replace(temp_name, prefs_path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

        # Chromium keeps cookies in Network/Cookies. Removing only these password
        # databases also removes WAL/journal copies of old credential records.
        for name in PASSWORD_FILES:
            (directory / name).unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "harden"))
    parser.add_argument("profile", type=Path)
    args = parser.parse_args()
    if args.action == "harden":
        harden(args.profile)
    elif not args.profile.exists():
        print(f"Profile not created; launch will harden it: {args.profile}")
        return
    problems = pending(args.profile)
    if problems:
        for problem in problems:
            print(problem)
        raise SystemExit(1)
    print(f"Profile hardened: {args.profile}")


if __name__ == "__main__":
    main()
