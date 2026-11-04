from __future__ import annotations

import argparse
import os
import re
import stat
import sys
from pathlib import Path


MAX_SOURCE_FILE_BYTES = 1_000_000
SKIP_DIRECTORIES = {".git"}
DENIED_DIRECTORIES = {
    ".idea",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "backups",
    "build",
    "dist",
    "htmlcov",
    "release",
    "venv",
}
LOCAL_ONLY_DIRECTORIES = {"assets", "data"}
DENIED_SUFFIXES = {
    ".avi",
    ".dll",
    ".exe",
    ".gif",
    ".jpeg",
    ".jpg",
    ".mkv",
    ".mov",
    ".mp3",
    ".mp4",
    ".msi",
    ".png",
    ".pyd",
    ".wav",
    ".webm",
    ".zip",
}
DENIED_FILE_NAMES = {
    "avatar_studio_project.json",
    "desktop.ini",
    "thumbs.db",
    ".ds_store",
}
TEXT_SUFFIXES = {"", ".json", ".md", ".ps1", ".py", ".toml", ".txt", ".yml", ".yaml"}
DEFAULT_PATTERNS = (
    re.compile(r"[A-Za-z]:\\" + "Users" + r"\\", re.IGNORECASE),
    re.compile(r"/[Uu]sers/"),
    re.compile("/" + "home" + "/", re.IGNORECASE),
    re.compile("[Oo]ne" + "[Dd]rive"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?:ghp|github_pat|sk|pk)_[A-Za-z0-9_-]{20,}"),
)


def _is_reparse(path: Path) -> bool:
    try:
        details = path.lstat()
    except OSError:
        return False
    return path.is_symlink() or bool(getattr(details, "st_file_attributes", 0) & 0x400)


def _relative(root: Path, candidate: Path) -> str:
    return candidate.relative_to(root).as_posix()


def _has_named_stream(path: Path) -> bool:
    if os.name != "nt":
        return False
    try:
        with open(f"{path}:Zone.Identifier", "rb"):
            return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def _text_for_scan(path: Path) -> str | None:
    if path.suffix.casefold() not in TEXT_SUFFIXES:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return "<non-utf8-text>"
    except OSError:
        return "<unreadable-text>"


def _audit_local_only_directory(root: Path, directory: Path, findings: list[str]) -> None:
    try:
        allowed = [child for child in directory.iterdir() if child.name != ".gitkeep"]
    except OSError as exc:
        findings.append(f"unreadable local-only directory: {_relative(root, directory)} ({exc})")
        return
    if allowed:
        findings.append(
            f"local-only directory contains files: {_relative(root, directory)}"
        )


def audit(root: Path, forbidden_terms: tuple[str, ...]) -> list[str]:
    root = root.resolve(strict=True)
    findings: list[str] = []
    patterns = [*DEFAULT_PATTERNS]
    patterns.extend(re.compile(re.escape(term), re.IGNORECASE) for term in forbidden_terms)
    pending = [root]
    while pending:
        directory = pending.pop()
        if _is_reparse(directory):
            findings.append(f"reparse point: {_relative(root, directory)}")
            continue
        try:
            children = sorted(directory.iterdir(), key=lambda item: (item.name.casefold(), item.name))
        except OSError as exc:
            findings.append(f"unreadable directory: {_relative(root, directory)} ({exc})")
            continue
        for child in children:
            relative = _relative(root, child)
            if _is_reparse(child):
                findings.append(f"reparse point: {relative}")
                continue
            if child.is_dir():
                name = child.name.casefold()
                if name in SKIP_DIRECTORIES:
                    continue
                if name in DENIED_DIRECTORIES:
                    findings.append(f"private/generated directory present: {relative}")
                elif name in LOCAL_ONLY_DIRECTORIES:
                    _audit_local_only_directory(root, child, findings)
                else:
                    pending.append(child)
                continue
            try:
                metadata = child.stat(follow_symlinks=False)
            except OSError as exc:
                findings.append(f"unreadable file: {relative} ({exc})")
                continue
            if not stat.S_ISREG(metadata.st_mode):
                findings.append(f"unsupported filesystem node: {relative}")
                continue
            if child.name.casefold() in DENIED_FILE_NAMES:
                findings.append(f"operating-system or local-runtime metadata present: {relative}")
            if child.suffix.casefold() in DENIED_SUFFIXES:
                findings.append(f"binary/media file is not publishable source: {relative}")
            if metadata.st_size > MAX_SOURCE_FILE_BYTES:
                findings.append(f"source file exceeds {MAX_SOURCE_FILE_BYTES} bytes: {relative}")
            if _has_named_stream(child):
                findings.append(f"alternate data stream present: {relative}")
            contents = _text_for_scan(child)
            if contents is None:
                continue
            if contents.startswith("<non-") or contents.startswith("<unreadable-"):
                findings.append(f"source text is not readable UTF-8: {relative}")
                continue
            for pattern in patterns:
                if pattern.search(contents):
                    findings.append(f"sensitive-pattern match: {relative}")
                    break
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail closed if a GitHub candidate contains local data or unsafe metadata."
    )
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--forbid",
        action="append",
        default=[],
        help="additional private text to reject; use locally and never commit the value",
    )
    arguments = parser.parse_args()
    try:
        findings = audit(arguments.root, tuple(arguments.forbid))
    except (OSError, ValueError) as exc:
        print(f"Public-tree audit could not run safely: {exc}", file=sys.stderr)
        return 2
    if findings:
        print("Public-tree audit failed:", file=sys.stderr)
        for finding in findings:
            print(f"- {finding}", file=sys.stderr)
        return 1
    print("Public-tree audit passed: no blocked files, metadata, or configured sensitive patterns.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
