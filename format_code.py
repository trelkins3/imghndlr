"""Run repository formatting with black and isort.

Usage:
    python format_code.py
    python format_code.py --check

Install requirements first:
    python -m pip install -r requirements.txt
"""

import argparse
import subprocess
import sys


def run_module(module: str, args: list[str]) -> int:
    cmd = [sys.executable, "-m", module] + args
    print(f"{module} running...")
    result = subprocess.run(cmd)
    if result.returncode == 0:
        print(f"{module} OK")
    else:
        print(f"{module} failed (exit code {result.returncode})")
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run black and isort on the repository."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Run black and isort in check mode without modifying files.",
    )
    args = parser.parse_args()

    target = ["."]
    common_args = ["--check"] if args.check else []

    exit_codes = []
    exit_codes.append(run_module("isort", common_args + target))
    exit_codes.append(run_module("black", common_args + target))

    if any(code != 0 for code in exit_codes):
        print("\nOne or more formatting tools failed.")
        return 1

    print("\nFormatting completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
