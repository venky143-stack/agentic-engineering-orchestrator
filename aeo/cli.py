from __future__ import annotations

import argparse
import json
from pathlib import Path

from .orchestrator import run_assessment


def main():
    parser = argparse.ArgumentParser(
        description="Run the Agentic Engineering Orchestrator"
    )
    parser.add_argument(
        "--requirement",
        type=Path,
        default=Path("examples/url_shortener.md"),
        help="Requirement Markdown file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("generated/run"),
        help="Output directory for reviewable artifacts",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="Repository path to scan read-only",
    )
    parser.add_argument(
        "--approve",
        action="store_true",
        help=(
            "Request approval review for passing artifacts; "
            "does not authenticate approval or authorize deployment"
        ),
    )

    args = parser.parse_args()

    report = run_assessment(
        args.requirement.resolve(),
        args.output.resolve(),
        args.repo.resolve(),
        args.approve,
    )

    print(
        json.dumps(
            {
                "status": report["status"],
                "output": str(args.output.resolve()),
                "validation": report["validation"],
            },
            indent=2,
        )
    )

    if not report["validation"]["passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()