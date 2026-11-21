#!/usr/bin/env python3
"""Fail closed until an explicit production-release approval is recorded.

Set the repository variable PILOT_RELEASE_APPROVED to the exact value "true"
only after licensing/redistribution and legacy visual acceptance are complete.
"""

from __future__ import annotations

import os
import sys

VARIABLE = "PILOT_RELEASE_APPROVED"
CHECKLIST = (
    "generated artifact redistribution/licensing approval",
    "CheerpJ Community Edition usage approval",
    "legacy visual acceptance",
)


def main() -> int:
    value = os.environ.get(VARIABLE, "").strip().lower()
    if value != "true":
        message = (
            f"Production publication is blocked: {VARIABLE} is not \"true\". "
            f"Required approvals: {', '.join(CHECKLIST)}."
        )
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print(f"::error::{message}")
        else:
            print(f"[BLOCKED] {message}", file=sys.stderr)
        return 1

    print(f"[APPROVED] {VARIABLE}=true; production release gate is open.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
