from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path


FIXED_TIMESTAMP = datetime(2025, 1, 1, tzinfo=UTC).timestamp()
SKIP_DIRECTORIES = {
    ".git",
    ".venv",
    "assets",
    "build",
    "data",
    "dist",
    "release",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
}


def _is_reparse(path: Path) -> bool:
    try:
        details = path.lstat()
    except OSError:
        return False
    return path.is_symlink() or bool(getattr(details, "st_file_attributes", 0) & 0x400)


def _remove_zone_identifier(path: Path) -> None:
    if os.name != "nt":
        return
    try:
        os.remove(f"{path}:Zone.Identifier")
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise RuntimeError(f"cannot remove alternate data stream from {path.name}: {exc}") from exc


def normalize(root: Path) -> int:
    root = root.resolve(strict=True)
    touched = 0
    pending = [root]
    while pending:
        directory = pending.pop()
        if _is_reparse(directory):
            raise RuntimeError("the public tree cannot contain a reparse point")
        for child in directory.iterdir():
            if _is_reparse(child):
                raise RuntimeError("the public tree cannot contain a reparse point")
            if child.is_dir():
                if child.name.casefold() not in SKIP_DIRECTORIES:
                    pending.append(child)
                continue
            _remove_zone_identifier(child)
            os.utime(child, (FIXED_TIMESTAMP, FIXED_TIMESTAMP))
            touched += 1
        os.utime(directory, (FIXED_TIMESTAMP, FIXED_TIMESTAMP))
    return touched


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Normalize timestamps and remove Windows Zone.Identifier streams from source."
    )
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    arguments = parser.parse_args()
    try:
        touched = normalize(arguments.root)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Metadata normalization failed: {exc}", file=sys.stderr)
        return 1
    print(f"Normalized publishable metadata for {touched} files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
