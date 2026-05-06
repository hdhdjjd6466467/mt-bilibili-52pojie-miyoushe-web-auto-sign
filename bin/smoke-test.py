#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from signadmin import store  # noqa: E402
from signadmin.web import app  # noqa: E402


def main() -> int:
    pages = [
        "/",
        "/members/new",
        "/targets/new",
        "/settings",
        "/login",
        "/setup",
    ]

    original_admin_is_configured = store.admin_is_configured
    store.admin_is_configured = lambda: True

    try:
        with app.test_client() as client:
            with client.session_transaction() as session:
                session["signadmin_logged_in"] = True
                session["signadmin_username"] = "smoke-test"

            failures: list[str] = []
            for path in pages:
                response = client.get(path, follow_redirects=True)
                if response.status_code != 200:
                    failures.append(f"{path} -> {response.status_code}")
                else:
                    print(f"[ok] {path} -> {response.status_code}")

            if failures:
                print("[failed]")
                for item in failures:
                    print(item)
                return 1

        print("[done] template rendering smoke test passed")
        return 0
    finally:
        store.admin_is_configured = original_admin_is_configured


if __name__ == "__main__":
    raise SystemExit(main())
